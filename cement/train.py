"""Explicit source-group holdout; never turn suggested labels into ground truth."""
import argparse
import json
from pathlib import Path
import joblib
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.pipeline import Pipeline
from cement import store
from cement.parse import sample, text_of

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
    predictions = model.predict([d[0] for d in test])
    report = {'classification': classification_report([d[1] for d in test], predictions, output_dict=True, zero_division=0),
              'classes': list(model.classes_), 'confusion_matrix': confusion_matrix([d[1] for d in test], predictions, labels=model.classes_).tolist(),
              'train_ids': [d[2] for d in train], 'test_ids': [d[2] for d in test], 'holdout_sources': sorted(holdout),
              'sklearn_version': sklearn.__version__, 'note': 'Prototype; prediction scores are not calibrated confidence.'}
    Path('models').mkdir(exist_ok=True)
    joblib.dump(model, 'models/classifier.joblib')
    Path('models/evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report['classification'], indent=2))

if __name__ == '__main__': main()
