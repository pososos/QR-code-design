"""Explicit source-group holdout; never turn suggested labels into ground truth."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import joblib
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.pipeline import Pipeline
from cement import store
from cement.parse import sample, text_of


def reliability_bins(confidences, correct, n_bins=5):
    """Top-label confidence calibration; not meaningful with only a handful of test examples."""
    bins = [[] for _ in range(n_bins)]
    for confidence, is_correct in zip(confidences, correct):
        bins[min(int(confidence * n_bins), n_bins - 1)].append(is_correct)
    return [{'bin_lower': i / n_bins, 'bin_upper': (i + 1) / n_bins, 'count': len(bucket),
             'accuracy': (sum(bucket) / len(bucket)) if bucket else None} for i, bucket in enumerate(bins)]


def append_registry(entry):
    registry_path = Path('models/registry.json')
    registry = json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else []
    registry.append(entry)
    registry_path.write_text(json.dumps(registry, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--holdout-sources', required=True, help='Comma-separated source IDs; excluded from training')
    args = parser.parse_args()
    holdout = set(args.holdout_sources.split(','))
    train, test = [], []
    for doc in store.documents():
        if not doc['label'] or doc['status'] != 'parsed': continue
        item = (sample(text_of(doc)), doc['label'], doc['id'])
        (test if any(s['source_id'] in holdout for s in doc['sources']) else train).append(item)
    classes = {d[1] for d in train}
    if len(classes) < 2 or not test or {d[1] for d in test} != classes:
        parser.error('Need >=2 training classes and the same classes in independent source holdout. Collect and label more documents.')
    model = Pipeline([('tfidf', TfidfVectorizer(analyzer='char', ngram_range=(2, 4), max_features=60000, sublinear_tf=True)),
                      ('classifier', LogisticRegression(max_iter=1000, class_weight='balanced', random_state=42))])
    model.fit([d[0] for d in train], [d[1] for d in train])
    probabilities = model.predict_proba([d[0] for d in test])
    predictions = [model.classes_[row.argmax()] for row in probabilities]
    confidences = [float(row.max()) for row in probabilities]
    correct = [pred == actual for pred, actual in zip(predictions, [d[1] for d in test])]
    macro_f1 = classification_report([d[1] for d in test], predictions, output_dict=True, zero_division=0)['macro avg']['f1-score']
    report = {'classification': classification_report([d[1] for d in test], predictions, output_dict=True, zero_division=0),
              'classes': list(model.classes_), 'confusion_matrix': confusion_matrix([d[1] for d in test], predictions, labels=model.classes_).tolist(),
              'train_ids': [d[2] for d in train], 'test_ids': [d[2] for d in test], 'holdout_sources': sorted(holdout),
              'sklearn_version': sklearn.__version__, 'note': 'Prototype; prediction scores are not calibrated confidence.',
              'calibration': {'bins': reliability_bins(confidences, correct),
                               'note': f'n={len(test)} test samples; with this few examples the curve is a mechanism check, not a valid calibration estimate.'}}
    Path('models').mkdir(exist_ok=True)
    joblib.dump(model, 'models/classifier.joblib')
    Path('models/evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    timestamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    registry_id = timestamp + '-' + hashlib.sha256(json.dumps(sorted(holdout)).encode()).hexdigest()[:8]
    Path('models/registry').mkdir(parents=True, exist_ok=True)
    registry_path = f'models/registry/{registry_id}.joblib'
    joblib.dump(model, registry_path)
    append_registry({'id': registry_id, 'created_at': timestamp, 'path': registry_path,
                      'holdout_sources': sorted(holdout), 'classes': list(model.classes_),
                      'train_count': len(train), 'test_count': len(test), 'macro_f1': macro_f1,
                      'sklearn_version': sklearn.__version__})
    print(json.dumps(report['classification'], indent=2))

if __name__ == '__main__': main()
