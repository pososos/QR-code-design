"""Single-document causal-claim candidates from cue phrases in existing graph-handoff evidence.

Rule-based only, no LLM. A cue phrase inside a sentence is not proof of a real causal
mechanism; every candidate is explicit_in_source (the sentence itself) and stays 'pending'
until a person accepts or rejects it. This is one raw sentence per candidate, not yet a
decomposed Event/Condition/Outcome/claims_cause relation from docs/知識圖譜銜接設計.md.
"""
import argparse
import hashlib
import json
import re
from cement import migrations, store, graph_handoff

EXTRACTOR_VERSION = 'graph_extract-v1-rule'
CUE_PHRASES = {
    'en': ['due to', 'results in', 'result in', 'leads to', 'lead to', 'caused by',
           'because of', 'contributes to', 'contribute to'],
    'zh': ['導致', '造成', '因此', '由於', '引起', '因而'],
}
SENTENCE_SPLIT = re.compile(r'(?<=[。！？.!?])\s*|\n+')

# Cross-candidate links stay at the candidate level; full Event/Condition/Outcome nodes are
# not built yet. same_event_candidate must not be treated as a confirmed merge (docs/知識圖譜銜接設計.md).
CANDIDATE_RELATION_TYPES = ('same_event_candidate', 'precedes', 'related')


def schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS extraction_jobs (
      id TEXT PRIMARY KEY, document_version_id TEXT NOT NULL,
      extractor_version TEXT NOT NULL, schema_version TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'candidates_generated', created_at TEXT DEFAULT CURRENT_TIMESTAMP);''')
    migrations.ensure_column(db, 'extraction_jobs', 'document_id', "TEXT NOT NULL DEFAULT ''")
    db.executescript('''
    CREATE TABLE IF NOT EXISTS graph_candidates (
      id TEXT PRIMARY KEY, job_id TEXT NOT NULL, document_version_id TEXT NOT NULL,
      node_type TEXT NOT NULL, quote TEXT NOT NULL, cue_phrase TEXT NOT NULL,
      evidence_id TEXT NOT NULL, assertion_mode TEXT NOT NULL DEFAULT 'explicit_in_source',
      review_status TEXT NOT NULL DEFAULT 'pending', reviewer TEXT NOT NULL DEFAULT '',
      note TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      reviewed_at TEXT);
    CREATE TABLE IF NOT EXISTS candidate_relations (
      id TEXT PRIMARY KEY, from_candidate_id TEXT NOT NULL, to_candidate_id TEXT NOT NULL,
      relation_type TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
      created_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')


def extract_candidates():
    handoff = graph_handoff.build()
    evidence_by_version = {}
    for e in handoff['evidence']:
        evidence_by_version.setdefault(e['document_version_id'], []).append(e)
    created, staled = [], []
    with store.connect() as db:
        schema(db)
        for doc in handoff['documents']:
            version, document_id = doc['id'], doc['document_id']
            job_id = hashlib.sha256(f'{version}:{EXTRACTOR_VERSION}'.encode()).hexdigest()
            existing_job = db.execute('SELECT id FROM extraction_jobs WHERE id=?', (job_id,)).fetchone()
            if existing_job:
                # Rerunning the same version+extractor only replaces its own un-reviewed output.
                db.execute("DELETE FROM graph_candidates WHERE job_id=? AND review_status='pending'", (job_id,))
            else:
                db.execute('''INSERT INTO extraction_jobs(id, document_id, document_version_id, extractor_version, schema_version)
                           VALUES (?,?,?,?,?)''', (job_id, document_id, version, EXTRACTOR_VERSION, handoff['schema_version']))
            # The document was re-parsed into a new text_hash/version; earlier jobs for the same
            # document_id are now stale. Only pending candidates flip to stale; accepted/rejected
            # human decisions stay as a historical record tied to the version they were made on.
            for stale_job in db.execute('''SELECT id FROM extraction_jobs WHERE document_id=?
                                         AND document_version_id!=? AND status!='stale' ''', (document_id, version)).fetchall():
                changed = db.execute('''UPDATE graph_candidates SET review_status='stale'
                                      WHERE job_id=? AND review_status='pending' ''', (stale_job['id'],)).rowcount
                db.execute("UPDATE extraction_jobs SET status='stale' WHERE id=?", (stale_job['id'],))
                staled.extend([stale_job['id']] * changed)
            for ev in evidence_by_version.get(version, []):
                for sentence in filter(None, (s.strip() for s in SENTENCE_SPLIT.split(ev['quote']))):
                    for phrases in CUE_PHRASES.values():
                        for phrase in phrases:
                            if phrase in sentence:
                                cand_id = hashlib.sha256(f"{job_id}:{ev['id']}:{phrase}:{sentence}".encode()).hexdigest()
                                db.execute('''INSERT OR IGNORE INTO graph_candidates
                                    (id, job_id, document_version_id, node_type, quote, cue_phrase, evidence_id)
                                    VALUES (?,?,?,?,?,?,?)''',
                                    (cand_id, job_id, version, 'Claim', sentence, phrase, ev['id']))
                                created.append(cand_id)
    return {'created': created, 'staled': staled}


def list_candidates(status='pending'):
    with store.connect() as db:
        schema(db)
        rows = db.execute('SELECT * FROM graph_candidates WHERE review_status=? ORDER BY created_at',
                           (status,)).fetchall()
        return [dict(r) for r in rows]


def review_candidate(candidate_id, decision, reviewer, note=''):
    if decision not in ('accepted', 'rejected'):
        raise ValueError('decision must be accepted or rejected')
    if not reviewer.strip():
        raise ValueError('reviewer required')
    with store.connect() as db:
        schema(db)
        if not db.execute('SELECT id FROM graph_candidates WHERE id=?', (candidate_id,)).fetchone():
            raise ValueError('Unknown candidate: ' + candidate_id)
        db.execute('''UPDATE graph_candidates SET review_status=?, reviewer=?, note=?, reviewed_at=CURRENT_TIMESTAMP
                   WHERE id=?''', (decision, reviewer, note, candidate_id))


def add_candidate_relation(from_candidate_id, to_candidate_id, relation_type, created_by, note=''):
    """Cross-candidate links require a human decision on two already-accepted candidates.

    same_event_candidate is explicitly a candidate for merging, not a confirmed merge: entity,
    time, location/specimen and condition alignment still needs separate human judgment.
    """
    if relation_type not in CANDIDATE_RELATION_TYPES:
        raise ValueError('Unknown relation_type: ' + relation_type)
    if from_candidate_id == to_candidate_id:
        raise ValueError('from_candidate_id and to_candidate_id must differ')
    if not created_by.strip():
        raise ValueError('created_by required')
    with store.connect() as db:
        schema(db)
        for cid in (from_candidate_id, to_candidate_id):
            row = db.execute('SELECT review_status FROM graph_candidates WHERE id=?', (cid,)).fetchone()
            if not row:
                raise ValueError('Unknown candidate: ' + cid)
            if row['review_status'] != 'accepted':
                raise ValueError('Both candidates must be accepted before linking: ' + cid)
        rel_id = hashlib.sha256(f'{from_candidate_id}:{to_candidate_id}:{relation_type}'.encode()).hexdigest()
        db.execute('''INSERT INTO candidate_relations(id, from_candidate_id, to_candidate_id, relation_type, note, created_by)
                   VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET note=excluded.note''',
                   (rel_id, from_candidate_id, to_candidate_id, relation_type, note, created_by))
        return rel_id


def list_candidate_relations():
    with store.connect() as db:
        schema(db)
        return [dict(r) for r in db.execute('SELECT * FROM candidate_relations ORDER BY created_at')]


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('extract')
    lst = sub.add_parser('list')
    lst.add_argument('--status', default='pending')
    args = parser.parse_args()
    if args.command == 'extract':
        result = extract_candidates()
        print(json.dumps({'candidates_created': len(result['created']), 'candidates_staled': len(result['staled'])}))
    else:
        print(json.dumps(list_candidates(args.status), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
