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
from cement import store, graph_handoff

EXTRACTOR_VERSION = 'graph_extract-v1-rule'
CUE_PHRASES = {
    'en': ['due to', 'results in', 'result in', 'leads to', 'lead to', 'caused by',
           'because of', 'contributes to', 'contribute to'],
    'zh': ['導致', '造成', '因此', '由於', '引起', '因而'],
}
SENTENCE_SPLIT = re.compile(r'(?<=[。！？.!?])\s*|\n+')


def schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS extraction_jobs (
      id TEXT PRIMARY KEY, document_version_id TEXT NOT NULL, extractor_version TEXT NOT NULL,
      schema_version TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'candidates_generated',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS graph_candidates (
      id TEXT PRIMARY KEY, job_id TEXT NOT NULL, document_version_id TEXT NOT NULL,
      node_type TEXT NOT NULL, quote TEXT NOT NULL, cue_phrase TEXT NOT NULL,
      evidence_id TEXT NOT NULL, assertion_mode TEXT NOT NULL DEFAULT 'explicit_in_source',
      review_status TEXT NOT NULL DEFAULT 'pending', reviewer TEXT NOT NULL DEFAULT '',
      note TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      reviewed_at TEXT);
    ''')


def extract_candidates():
    handoff = graph_handoff.build()
    evidence_by_version = {}
    for e in handoff['evidence']:
        evidence_by_version.setdefault(e['document_version_id'], []).append(e)
    created = []
    with store.connect() as db:
        schema(db)
        for doc in handoff['documents']:
            version = doc['id']
            job_id = hashlib.sha256(f'{version}:{EXTRACTOR_VERSION}'.encode()).hexdigest()
            existing_job = db.execute('SELECT id FROM extraction_jobs WHERE id=?', (job_id,)).fetchone()
            if existing_job:
                # Rerunning the same version+extractor only replaces its own un-reviewed output.
                db.execute("DELETE FROM graph_candidates WHERE job_id=? AND review_status='pending'", (job_id,))
            else:
                db.execute('''INSERT INTO extraction_jobs(id, document_version_id, extractor_version, schema_version)
                           VALUES (?,?,?,?)''', (job_id, version, EXTRACTOR_VERSION, handoff['schema_version']))
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
    return created


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


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('extract')
    lst = sub.add_parser('list')
    lst.add_argument('--status', default='pending')
    args = parser.parse_args()
    if args.command == 'extract':
        print(json.dumps({'candidates_created': len(extract_candidates())}))
    else:
        print(json.dumps(list_candidates(args.status), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
