"""Entities, structured Event/Condition/Outcome nodes, formal relations and a tag vocabulary.

Everything here is either a rule-based candidate (entity mentions, from a small gazetteer) or a
direct human action (node decomposition, relation authoring, entity/tag linking) taken on an
already-accepted graph_candidates row (cement/graph_extract.py). There is no LLM and no automatic
inference: same_entity_candidate and Event/Condition/Outcome nodes only exist because a person
created them, citing evidence that already has a hash/page/char-offset locator.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from cement import migrations, store, graph_handoff

NODE_TYPES = ('Event', 'Condition', 'Outcome')
RELATION_TYPES = ('participates_in', 'occurs_under', 'has_outcome', 'claims_cause',
                   'supports', 'contradicts', 'concludes_from', 'precedes', 'describes')
ASSERTION_MODES = ('explicit_in_source', 'model_inference', 'human_interpretation')
POLARITIES = ('affirmative', 'negative')
REF_TYPES = ('Event', 'Condition', 'Outcome', 'Claim', 'Entity', 'DocumentVersion')


def schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS entities (
      id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, name_en TEXT NOT NULL DEFAULT '',
      name_zh TEXT NOT NULL DEFAULT '', created_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS entity_mentions (
      id TEXT PRIMARY KEY, document_version_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
      surface_text TEXT NOT NULL, entity_type TEXT NOT NULL, gazetteer_term TEXT NOT NULL,
      entity_id TEXT, review_status TEXT NOT NULL DEFAULT 'pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS graph_nodes (
      id TEXT PRIMARY KEY, node_type TEXT NOT NULL, document_version_id TEXT NOT NULL,
      parent_candidate_id TEXT NOT NULL, payload_json TEXT NOT NULL,
      created_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS graph_relations (
      id TEXT PRIMARY KEY, from_id TEXT NOT NULL, from_type TEXT NOT NULL,
      to_id TEXT NOT NULL, to_type TEXT NOT NULL, relation_type TEXT NOT NULL,
      evidence_ids_json TEXT NOT NULL, origin TEXT NOT NULL DEFAULT 'human_authored',
      assertion_mode TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'accepted',
      polarity TEXT NOT NULL DEFAULT 'affirmative', conditions_json TEXT NOT NULL DEFAULT '{}',
      note TEXT NOT NULL DEFAULT '', created_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS tags (
      id TEXT PRIMARY KEY, pref_label_en TEXT NOT NULL DEFAULT '', pref_label_zh TEXT NOT NULL DEFAULT '',
      aliases_json TEXT NOT NULL DEFAULT '[]', definition TEXT NOT NULL DEFAULT '',
      broader_id TEXT, status TEXT NOT NULL DEFAULT 'pending',
      created_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS node_tags (
      node_id TEXT NOT NULL, node_type TEXT NOT NULL, tag_id TEXT NOT NULL,
      created_by TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (node_id, tag_id));
    ''')
    migrations.ensure_column(db, 'graph_relations', 'reviewed_at', 'TEXT')


# --- Entity mentions (rule-based candidates) and human-confirmed cross-document alignment ---

def load_gazetteer(path='config/entity-gazetteer.json'):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _find_term(term, text):
    if term.isascii():
        match = re.search(r'\b' + re.escape(term) + r'\b', text, re.IGNORECASE)
        return match.group(0) if match else None
    return term if term in text else None


def extract_mentions(gazetteer=None):
    gazetteer = gazetteer if gazetteer is not None else load_gazetteer()
    handoff = graph_handoff.build()
    created = []
    with store.connect() as db:
        schema(db)
        for ev in handoff['evidence']:
            for entity_type, terms in gazetteer.items():
                for term in terms:
                    hit = _find_term(term, ev['quote'])
                    if not hit:
                        continue
                    mention_id = hashlib.sha256(f"{ev['id']}:{entity_type}:{term}".encode()).hexdigest()
                    changed = db.execute('''INSERT OR IGNORE INTO entity_mentions
                        (id, document_version_id, evidence_id, surface_text, entity_type, gazetteer_term)
                        VALUES (?,?,?,?,?,?)''',
                        (mention_id, ev['document_version_id'], ev['id'], hit, entity_type, term)).rowcount
                    if changed:
                        created.append(mention_id)
    return created


def list_mentions(status='pending'):
    with store.connect() as db:
        schema(db)
        rows = db.execute('SELECT * FROM entity_mentions WHERE review_status=? ORDER BY created_at', (status,)).fetchall()
        return [dict(r) for r in rows]


def link_mention(mention_id, created_by, entity_id=None, new_entity=None):
    """A mention only becomes part of a canonical entity by explicit human choice; string equality never merges by itself."""
    if not created_by.strip():
        raise ValueError('created_by required')
    if not entity_id and not new_entity:
        raise ValueError('Provide entity_id or new_entity')
    with store.connect() as db:
        schema(db)
        mention = db.execute('SELECT * FROM entity_mentions WHERE id=?', (mention_id,)).fetchone()
        if not mention:
            raise ValueError('Unknown mention: ' + mention_id)
        if entity_id:
            if not db.execute('SELECT 1 FROM entities WHERE id=?', (entity_id,)).fetchone():
                raise ValueError('Unknown entity: ' + entity_id)
            target_id = entity_id
        else:
            name_en = (new_entity or {}).get('name_en', '').strip()
            name_zh = (new_entity or {}).get('name_zh', '').strip()
            if not name_en and not name_zh:
                raise ValueError('new_entity requires name_en or name_zh')
            target_id = hashlib.sha256(f"{mention['entity_type']}:{name_en}:{name_zh}".encode()).hexdigest()
            db.execute('''INSERT OR IGNORE INTO entities(id, entity_type, name_en, name_zh, created_by)
                       VALUES (?,?,?,?,?)''', (target_id, mention['entity_type'], name_en, name_zh, created_by))
        db.execute("UPDATE entity_mentions SET entity_id=?, review_status='linked' WHERE id=?", (target_id, mention_id))
        return target_id


def list_entities():
    with store.connect() as db:
        schema(db)
        return [dict(r) for r in db.execute('SELECT * FROM entities ORDER BY created_at')]


def mentions_for_entity(entity_id):
    """The cross-document payoff: every document version this canonical entity was confirmed to appear in."""
    with store.connect() as db:
        schema(db)
        rows = db.execute('SELECT * FROM entity_mentions WHERE entity_id=? ORDER BY created_at', (entity_id,)).fetchall()
        return [dict(r) for r in rows]


# --- Event/Condition/Outcome node decomposition from an accepted Claim candidate ---

def create_node(node_type, parent_candidate_id, payload, created_by):
    if node_type not in NODE_TYPES:
        raise ValueError('Unknown node_type: ' + node_type)
    if not created_by.strip():
        raise ValueError('created_by required')
    description = (payload or {}).get('description', '').strip()
    if not description:
        raise ValueError('payload.description required')
    with store.connect() as db:
        schema(db)
        candidate = db.execute('SELECT * FROM graph_candidates WHERE id=?', (parent_candidate_id,)).fetchone()
        if not candidate:
            raise ValueError('Unknown parent candidate: ' + parent_candidate_id)
        if candidate['review_status'] != 'accepted':
            raise ValueError('Decomposition requires an accepted candidate, not ' + candidate['review_status'])
        node_id = hashlib.sha256(
            f"{parent_candidate_id}:{node_type}:{json.dumps(payload, sort_keys=True, ensure_ascii=False)}".encode()
        ).hexdigest()
        db.execute('''INSERT OR IGNORE INTO graph_nodes(id, node_type, document_version_id, parent_candidate_id, payload_json, created_by)
                   VALUES (?,?,?,?,?,?)''',
                   (node_id, node_type, candidate['document_version_id'], parent_candidate_id,
                    json.dumps(payload, ensure_ascii=False), created_by))
        return node_id


def list_nodes(document_version_id=None):
    with store.connect() as db:
        schema(db)
        if document_version_id:
            rows = db.execute('SELECT * FROM graph_nodes WHERE document_version_id=? ORDER BY created_at',
                               (document_version_id,)).fetchall()
        else:
            rows = db.execute('SELECT * FROM graph_nodes ORDER BY created_at').fetchall()
        return [dict(r) for r in rows]


def _reference_exists(db, ref_id, ref_type):
    if ref_type in NODE_TYPES:
        return bool(db.execute('SELECT 1 FROM graph_nodes WHERE id=? AND node_type=?', (ref_id, ref_type)).fetchone())
    if ref_type == 'Claim':
        return bool(db.execute('SELECT 1 FROM graph_candidates WHERE id=?', (ref_id,)).fetchone())
    if ref_type == 'Entity':
        return bool(db.execute('SELECT 1 FROM entities WHERE id=?', (ref_id,)).fetchone())
    if ref_type == 'DocumentVersion':
        return bool(ref_id)
    return False


def create_relation(from_id, from_type, to_id, to_type, relation_type, created_by, evidence_ids,
                     assertion_mode, note='', polarity='affirmative', conditions=None):
    if relation_type not in RELATION_TYPES:
        raise ValueError('Unknown relation_type: ' + relation_type)
    if from_type not in REF_TYPES or to_type not in REF_TYPES:
        raise ValueError('Unknown from_type/to_type')
    if assertion_mode not in ASSERTION_MODES:
        raise ValueError('Unknown assertion_mode: ' + assertion_mode)
    if polarity not in POLARITIES:
        raise ValueError('Unknown polarity: ' + polarity)
    if not created_by.strip():
        raise ValueError('created_by required')
    if not evidence_ids:
        raise ValueError('evidence_ids required; every semantic relation must cite evidence')
    with store.connect() as db:
        schema(db)
        if not _reference_exists(db, from_id, from_type):
            raise ValueError(f'Unknown {from_type}: {from_id}')
        if not _reference_exists(db, to_id, to_type):
            raise ValueError(f'Unknown {to_type}: {to_id}')
        rel_id = hashlib.sha256(f'{from_id}:{to_id}:{relation_type}'.encode()).hexdigest()
        db.execute('''INSERT INTO graph_relations(id, from_id, from_type, to_id, to_type, relation_type,
                    evidence_ids_json, assertion_mode, polarity, conditions_json, note, created_by)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET note=excluded.note''',
                   (rel_id, from_id, from_type, to_id, to_type, relation_type,
                    json.dumps(evidence_ids), assertion_mode, polarity,
                    json.dumps(conditions or {}, ensure_ascii=False), note, created_by))
        return rel_id


def list_relations():
    with store.connect() as db:
        schema(db)
        return [dict(r) for r in db.execute('SELECT * FROM graph_relations ORDER BY created_at')]


# --- Tag vocabulary (SKOS-lite: pref labels, aliases, broader) ---

def create_tag(created_by, pref_label_en='', pref_label_zh='', aliases=None, definition='', broader_id=None):
    if not created_by.strip():
        raise ValueError('created_by required')
    if not pref_label_en.strip() and not pref_label_zh.strip():
        raise ValueError('pref_label_en or pref_label_zh required')
    with store.connect() as db:
        schema(db)
        if broader_id and not db.execute('SELECT 1 FROM tags WHERE id=?', (broader_id,)).fetchone():
            raise ValueError('Unknown broader_id: ' + broader_id)
        tag_id = hashlib.sha256(f'{pref_label_en}:{pref_label_zh}'.encode()).hexdigest()
        db.execute('''INSERT OR IGNORE INTO tags(id, pref_label_en, pref_label_zh, aliases_json, definition, broader_id, created_by)
                   VALUES (?,?,?,?,?,?,?)''',
                   (tag_id, pref_label_en, pref_label_zh, json.dumps(aliases or [], ensure_ascii=False),
                    definition, broader_id, created_by))
        return tag_id


def list_tags():
    with store.connect() as db:
        schema(db)
        return [dict(r) for r in db.execute('SELECT * FROM tags ORDER BY created_at')]


def tag_node(node_id, node_type, tag_id, created_by):
    if not created_by.strip():
        raise ValueError('created_by required')
    with store.connect() as db:
        schema(db)
        if not db.execute('SELECT 1 FROM tags WHERE id=?', (tag_id,)).fetchone():
            raise ValueError('Unknown tag: ' + tag_id)
        db.execute('INSERT OR IGNORE INTO node_tags(node_id, node_type, tag_id, created_by) VALUES (?,?,?,?)',
                   (node_id, node_type, tag_id, created_by))


def tags_for(node_id):
    with store.connect() as db:
        schema(db)
        rows = db.execute('''SELECT t.* FROM node_tags nt JOIN tags t ON t.id = nt.tag_id
                           WHERE nt.node_id=? ORDER BY nt.created_at''', (node_id,)).fetchall()
        return [dict(r) for r in rows]


# --- Timeline: kept as two separately-labeled lists, never merged into one false-precision sort ---

def timeline():
    with store.connect() as db:
        schema(db)
        event_times = []
        for row in db.execute("SELECT * FROM graph_nodes WHERE node_type='Event' ORDER BY created_at"):
            payload = json.loads(row['payload_json'])
            if payload.get('event_time'):
                event_times.append({'node_id': row['id'], 'document_version_id': row['document_version_id'],
                                     'value': payload['event_time'], 'description': payload.get('description', '')})
        fetch_times = [{'document_id': r['document_id'], 'source_id': r['source_id'], 'value': r['checked_at']}
                        for r in db.execute('SELECT document_id, source_id, checked_at FROM sources ORDER BY checked_at')]
        return {'event_times': event_times,
                'event_times_confidence': 'human_entered_relative_or_exact_time_on_an_accepted_claim',
                'fetch_times': fetch_times,
                'fetch_times_confidence': 'crawl_fetch_time_not_publication_date'}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('extract-mentions')
    sub.add_parser('timeline')
    args = parser.parse_args()
    if args.command == 'extract-mentions':
        print(json.dumps({'mentions_created': len(extract_mentions())}))
    else:
        print(json.dumps(timeline(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
