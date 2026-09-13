"""Auditable lexical weak labels. No network calls or manual label mutation."""
import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from cement import store


def normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text).casefold()).strip()


def contains(text, term):
    term = normalize(term)
    if term.isascii():
        return re.search(r'(?<![a-z0-9])' + re.escape(term) + r'(?![a-z0-9])', text) is not None
    return term in text


def load_rules(path):
    rules = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if set(rules['classes']) != set(store.LABELS):
        raise ValueError('Rule classes must match store.LABELS')
    if rules['min_score'] <= 0 or rules['min_margin'] <= 0:
        raise ValueError('Thresholds must be positive')
    return rules


def classify(pages, rules):
    # Use visible page text, never potentially stale PDF metadata titles.
    evidence, seen = [], set()
    domain = set()
    stopped = False
    for page in pages:
        if stopped:
            break
        for original in page['text'].splitlines():
            line = normalize(original)
            if re.fullmatch(r'(references|bibliography|參考文獻|参考文献)(\s*\d*)?', line):
                stopped = True
                break
            if not line or line in seen:
                continue
            seen.add(line)
            domain.update(t for t in rules['domain_terms'] if contains(line, t))
            for label, spec in rules['classes'].items():
                for kind in ('strong', 'support'):
                    for term in spec[kind]:
                        if contains(line, term):
                            evidence.append({'label': label, 'kind': kind, 'term': term,
                                             'page': page['page'], 'snippet': original[:500]})
    scores = {}
    eligible = []
    for label in rules['classes']:
        strong = {e['term'] for e in evidence if e['label'] == label and e['kind'] == 'strong'}
        support = {e['term'] for e in evidence if e['label'] == label and e['kind'] == 'support'}
        scores[label] = 3 * len(strong) + min(3, len(support))
        if strong and support and scores[label] >= rules['min_score']:
            eligible.append(label)
    ranked = sorted(scores, key=lambda label: (-scores[label], label))
    top, second = ranked[:2]
    reason, label = 'insufficient_evidence', None
    if not domain:
        reason = 'domain_not_confirmed'
    elif len(eligible) > 1:
        reason = 'conflicting_classes'
    elif top in eligible:
        if scores[top] - scores[second] >= rules['min_margin']:
            reason, label = 'rule_candidate', top
        else:
            reason = 'small_margin'
    return {'label': label, 'decision': 'candidate' if label else 'abstain', 'reason': reason,
            'scores': scores, 'domain_terms': sorted(domain), 'evidence': evidence}


def ensure_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS weak_labels (
      assignment_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
      origin TEXT NOT NULL, rule_version TEXT NOT NULL, rule_hash TEXT NOT NULL,
      text_hash TEXT NOT NULL, label TEXT, decision TEXT NOT NULL, reason TEXT NOT NULL,
      scores_json TEXT NOT NULL, evidence_json TEXT NOT NULL, domain_json TEXT NOT NULL,
      review_status TEXT NOT NULL DEFAULT 'pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')


def run(rules):
    canonical = json.dumps(rules, sort_keys=True, ensure_ascii=False)
    rule_hash = hashlib.sha256(canonical.encode()).hexdigest()
    results = []
    with store.connect() as db:
        ensure_schema(db)
        docs = [dict(r) for r in db.execute('SELECT * FROM documents')]
        for doc in docs:
            if doc['status'] != 'parsed' or not doc['text_path']:
                results.append({'document_id': doc['id'], 'decision': 'skipped', 'reason': doc['status']})
                continue
            if doc['label'] is not None:
                results.append({'document_id': doc['id'], 'decision': 'skipped', 'reason': 'manual_label_present'})
                continue
            try:
                raw = Path(doc['text_path']).read_bytes()
                pages = json.loads(raw.decode('utf-8-sig'))
                result = classify(pages, rules)
                text_hash = hashlib.sha256(raw).hexdigest()
                assignment_id = hashlib.sha256(f'{doc["id"]}:{rule_hash}:{text_hash}'.encode()).hexdigest()
                db.execute('''INSERT OR IGNORE INTO weak_labels
                (assignment_id,document_id,origin,rule_version,rule_hash,text_hash,label,decision,reason,
                 scores_json,evidence_json,domain_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (assignment_id, doc['id'], 'term_mapping', rules['version'], rule_hash, text_hash,
                 result['label'], result['decision'], result['reason'], json.dumps(result['scores']),
                 json.dumps(result['evidence'], ensure_ascii=False), json.dumps(result['domain_terms'], ensure_ascii=False)))
                results.append({'document_id': doc['id'], 'assignment_id': assignment_id, **result})
            except (OSError, ValueError, KeyError, TypeError) as exc:
                results.append({'document_id': doc['id'], 'decision': 'error', 'reason': str(exc)})
    report = {'rule_version': rules['version'], 'rule_hash': rule_hash,
              'counts': dict(Counter(r['decision'] for r in results)), 'results': results,
              'note': 'Uncalibrated rule candidates, not human ground truth; train.py does not consume these labels.'}
    folder = store.ROOT / 'reports'
    folder.mkdir(exist_ok=True)
    (folder / 'weak_labels_latest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rules', default='config/term_mapping.json')
    parser.add_argument('--queries', action='store_true', help='Print discovery queries only; no network or DB writes')
    args = parser.parse_args()
    rules = load_rules(args.rules)
    if args.queries:
        print(json.dumps({k: v['search_terms'] for k,v in rules['classes'].items()}, ensure_ascii=False, indent=2))
        return
    print(json.dumps(run(rules)['counts'], ensure_ascii=False))

if __name__ == '__main__':
    main()
