"""Keyword index, processing policy and document relations; classification must not gate retrieval."""
import argparse
import hashlib
import json
from cement import store
from cement.parse import text_of

PROCESS_POLICIES = ('unset', 'fast_track', 'standard', 'deprioritized', 'excluded')
RELATION_TYPES = ('supersedes', 'same_series', 'cites')


def schema(db):
    db.executescript('''
    CREATE VIRTUAL TABLE IF NOT EXISTS document_text_fts USING fts5(
      document_id UNINDEXED, title, body, tokenize='unicode61');
    CREATE TABLE IF NOT EXISTS processing_policy (
      document_id TEXT PRIMARY KEY, policy TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
      set_by TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS document_relations (
      id TEXT PRIMARY KEY, from_id TEXT NOT NULL, to_id TEXT NOT NULL,
      relation_type TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
      created_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')


def reindex():
    """Index every parsed document regardless of label so purpose classification cannot become the only retrieval gate."""
    count = 0
    with store.connect() as db:
        schema(db)
        db.execute('DELETE FROM document_text_fts')
        for doc in store.documents():
            if doc['status'] != 'parsed' or not doc['text_path']:
                continue
            db.execute('INSERT INTO document_text_fts(document_id, title, body) VALUES (?,?,?)',
                       (doc['id'], doc['title'] or '', text_of(doc)))
            count += 1
    return count


def search(query, limit=20, offset=0):
    if not query or not query.strip():
        raise ValueError('Query required')
    with store.connect() as db:
        schema(db)
        rows = db.execute('''SELECT document_id, snippet(document_text_fts, 2, '[', ']', '...', 12) AS snippet,
                              bm25(document_text_fts) AS score
                              FROM document_text_fts WHERE document_text_fts MATCH ?
                              ORDER BY score LIMIT ? OFFSET ?''', (query, limit, offset)).fetchall()
        by_id = {d['id']: d for d in store.documents()}
        results = []
        for r in rows:
            doc = by_id.get(r['document_id'])
            if not doc:
                continue
            results.append({'document_id': r['document_id'], 'snippet': r['snippet'], 'score': r['score'],
                             'label': doc['label'], 'status': doc['status'], 'title': doc['title']})
        return results


def set_policy(document_id, policy, set_by, reason=''):
    """Policy is explicit and independent of label; it must never be inferred automatically from the classifier."""
    if policy not in PROCESS_POLICIES:
        raise ValueError('Unknown policy: ' + policy)
    if not set_by.strip():
        raise ValueError('set_by required; policy cannot be set anonymously')
    with store.connect() as db:
        schema(db)
        if not db.execute('SELECT id FROM documents WHERE id=?', (document_id,)).fetchone():
            raise ValueError('Unknown document: ' + document_id)
        db.execute('''INSERT INTO processing_policy(document_id, policy, reason, set_by) VALUES (?,?,?,?)
                   ON CONFLICT(document_id) DO UPDATE SET policy=excluded.policy, reason=excluded.reason,
                   set_by=excluded.set_by, updated_at=CURRENT_TIMESTAMP''', (document_id, policy, reason, set_by))


def get_policy(document_id):
    with store.connect() as db:
        schema(db)
        row = db.execute('SELECT * FROM processing_policy WHERE document_id=?', (document_id,)).fetchone()
        return dict(row) if row else {'document_id': document_id, 'policy': 'unset', 'reason': '', 'set_by': ''}


def add_relation(from_id, to_id, relation_type, created_by, note=''):
    """Version/series relations must be declared explicitly; recency alone never implies supersession."""
    if relation_type not in RELATION_TYPES:
        raise ValueError('Unknown relation_type: ' + relation_type)
    if from_id == to_id:
        raise ValueError('from_id and to_id must differ')
    if not created_by.strip():
        raise ValueError('created_by required')
    with store.connect() as db:
        schema(db)
        for doc_id in (from_id, to_id):
            if not db.execute('SELECT id FROM documents WHERE id=?', (doc_id,)).fetchone():
                raise ValueError('Unknown document: ' + doc_id)
        rel_id = hashlib.sha256(f'{from_id}:{to_id}:{relation_type}'.encode()).hexdigest()
        db.execute('''INSERT INTO document_relations(id, from_id, to_id, relation_type, note, created_by)
                   VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET note=excluded.note''',
                   (rel_id, from_id, to_id, relation_type, note, created_by))
        return rel_id


def relations_for(document_id):
    with store.connect() as db:
        schema(db)
        rows = db.execute('''SELECT * FROM document_relations WHERE from_id=? OR to_id=?
                           ORDER BY created_at''', (document_id, document_id)).fetchall()
        return [dict(r) for r in rows]


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('reindex')
    q = sub.add_parser('query')
    q.add_argument('query')
    q.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    if args.command == 'reindex':
        print(json.dumps({'indexed': reindex()}))
    else:
        print(json.dumps(search(args.query, args.limit), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
