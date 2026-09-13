"""Human review exchange with content fingerprints and atomic imports."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from cement import store
from cement.weaklabel import ensure_schema as weak_schema, load_rules


def rule_hash(rules):
    return hashlib.sha256(json.dumps(rules, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def schema(db):
    weak_schema(db)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS review_log (
      review_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, text_hash TEXT NOT NULL,
      label TEXT NOT NULL, reviewer TEXT NOT NULL, note TEXT NOT NULL,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS dataset_membership (
      document_id TEXT PRIMARY KEY, group_id TEXT NOT NULL, split TEXT NOT NULL,
      text_hash TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')


def fingerprint(doc):
    return hashlib.sha256(Path(doc['text_path']).read_bytes()).hexdigest()


def current_weak(db, doc, digest, rules_digest):
    return db.execute('''SELECT * FROM weak_labels WHERE document_id=? AND text_hash=?
      AND rule_hash=? AND decision='candidate' AND review_status!='rejected' ''',
      (doc['id'], digest, rules_digest)).fetchone()


def export_review(output, rules):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with store.connect() as db:
        schema(db)
        for doc in store.documents():
            if doc['status'] != 'parsed' or not doc['text_path']:
                continue
            digest = fingerprint(doc)
            member = db.execute('SELECT * FROM dataset_membership WHERE document_id=?', (doc['id'],)).fetchone()
            # Do not show weak predictions for evaluation documents.
            weak = current_weak(db, doc, digest, rule_hash(rules)) if member and member['split']=='train' else None
            rows.append({'document_id':doc['id'], 'text_hash':digest, 'status':doc['status'],
                         'title':doc['title'], 'sources':[s['url'] for s in doc['sources']],
                         'current_label':doc['label'], 'suggested_label':weak['label'] if weak else None,
                         'evidence':json.loads(weak['evidence_json']) if weak else [],
                         'pages':json.loads(Path(doc['text_path']).read_text(encoding='utf-8-sig')),
                         'label':'', 'reviewer':'', 'note':'',
                         'group_id':member['group_id'] if member else '',
                         'split':member['split'] if member else ''})
    # Never overwrite a partially completed human review file.
    with output.open('x', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return len(rows)


def import_review(path):
    return import_rows(json.loads(Path(path).read_text(encoding='utf-8-sig')))


def import_rows(rows):
    if not isinstance(rows, list):
        raise ValueError('Review file must be a list')
    checked, seen = [], set()
    with store.connect() as db:
        schema(db)
        for row in rows:
            # Blank label means not reviewed; never guess a human judgment.
            if not row.get('label'):
                continue
            identity = row['document_id']
            if identity in seen:
                raise ValueError('Duplicate review document')
            seen.add(identity)
            if row['label'] not in store.LABELS or not row.get('reviewer','').strip():
                raise ValueError('Valid label and reviewer required')
            if row.get('split') not in ('train','validation','test') or not row.get('group_id','').strip():
                raise ValueError('Explicit group_id and split required')
            doc = db.execute('SELECT * FROM documents WHERE id=?',(identity,)).fetchone()
            if not doc or doc['status']!='parsed' or fingerprint(doc)!=row['text_hash']:
                raise ValueError('Stale or ineligible document: '+identity)
            if doc['label'] != row.get('current_label') and doc['label'] != row['label']:
                raise ValueError('Manual label changed after export: '+identity)
            existing = db.execute('SELECT * FROM dataset_membership WHERE document_id=?',(identity,)).fetchone()
            if existing and (existing['group_id']!=row['group_id'] or existing['split']!=row['split']):
                raise ValueError('Existing split/group is frozen; use a separately reviewed migration')
            checked.append(row)
        proposed = {r['document_id']: (r['group_id'],r['split']) for r in db.execute('SELECT * FROM dataset_membership')}
        proposed.update({r['document_id']:(r['group_id'],r['split']) for r in checked})
        groups = {}
        for group, split in proposed.values():
            if group in groups and groups[group]!=split:
                raise ValueError('Group crosses dataset splits: '+group)
            groups[group]=split
        # All validation completes before any human labels are mutated.
        for row in checked:
            payload = {k:row.get(k,'') for k in ('document_id','text_hash','label','reviewer','note','group_id','split')}
            review_id = hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            db.execute('INSERT OR IGNORE INTO review_log(review_id,document_id,text_hash,label,reviewer,note) VALUES (?,?,?,?,?,?)',
                       (review_id,row['document_id'],row['text_hash'],row['label'],row['reviewer'],row.get('note','')))
            db.execute('UPDATE documents SET label=? WHERE id=?',(row['label'],row['document_id']))
            db.execute('''INSERT INTO dataset_membership(document_id,group_id,split,text_hash) VALUES (?,?,?,?)
                       ON CONFLICT(document_id) DO UPDATE SET text_hash=excluded.text_hash,updated_at=CURRENT_TIMESTAMP''',
                       (row['document_id'],row['group_id'],row['split'],row['text_hash']))
            db.execute('''UPDATE weak_labels SET review_status=CASE WHEN label=? THEN 'confirmed' ELSE 'rejected' END
                       WHERE document_id=? AND text_hash=?''',(row['label'],row['document_id'],row['text_hash']))
    return len(checked)


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='command',required=True)
    export=sub.add_parser('export')
    export.add_argument('--output',required=True)
    export.add_argument('--rules',default='config/term_mapping.json')
    imp=sub.add_parser('import')
    imp.add_argument('--input',required=True)
    args=parser.parse_args()
    try:
        count=export_review(args.output,load_rules(args.rules)) if args.command=='export' else import_review(args.input)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({'documents':count,'operation':args.command}))

if __name__=='__main__': main()

