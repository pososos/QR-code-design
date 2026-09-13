from io import BytesIO
from pathlib import Path
from typing import Literal
import json
import time
import joblib
import qrcode
import qrcode.image.svg
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from cement import store
from cement.parse import text_of, sample

app = FastAPI(title='Cement Knowledge Intake', version='0.1.0')

@app.get('/')
def index(): return FileResponse(Path(__file__).parent / 'static' / 'index.html')

@app.get('/api/documents')
def documents(limit: int | None = None, offset: int = 0):
    # limit omitted keeps the historical full-array response so existing pages need no changes.
    if limit is None:
        return store.documents()
    return JSONResponse(store.documents(limit, offset), headers={'X-Total-Count': str(store.document_count())})

@app.get('/api/events')
def events():
    with store.connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')]

class Label(BaseModel):
    label: Literal['research', 'manual', 'guidance', 'safety', 'industry', 'experiment_log', 'manuscript_notes'] | None

@app.put('/api/documents/{doc_id}/label')
def label(doc_id: str, value: Label):
    with store.connect() as db:
        changed = db.execute('UPDATE documents SET label=? WHERE id=?', (value.label, doc_id)).rowcount
    if not changed: raise HTTPException(404, 'Document not found')
    return {'saved': True}

@app.get('/api/documents/{doc_id}/text')
def document_text(doc_id: str):
    doc = next((d for d in store.documents() if d['id'] == doc_id), None)
    if not doc: raise HTTPException(404, 'Document not found')
    return {'text': sample(text_of(doc))}

class Predict(BaseModel):
    text: str = Field(min_length=1, max_length=100000)

@app.post('/api/predict')
def predict(value: Predict):
    path = Path('models/classifier.joblib')
    if not path.exists(): raise HTTPException(409, 'No trained model. Label documents and train first.')
    start = time.perf_counter()
    # Load only this locally generated artifact; never accept uploaded pickle files.
    model = joblib.load(path)
    scores = model.predict_proba([sample(value.text)])[0]
    latency_ms = (time.perf_counter() - start) * 1000
    label = str(model.classes_[scores.argmax()])
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS prediction_log (
            id INTEGER PRIMARY KEY, latency_ms REAL NOT NULL, predicted_label TEXT NOT NULL,
            top_score REAL NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        db.execute('INSERT INTO prediction_log(latency_ms, predicted_label, top_score) VALUES (?,?,?)',
                   (latency_ms, label, float(scores.max())))
    return {'label': label, 'scores': dict(zip(model.classes_, map(float, scores))),
            'review_required': True, 'latency_ms': latency_ms}

@app.get('/api/predict-log')
def predict_log(limit: int = 50):
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS prediction_log (
            id INTEGER PRIMARY KEY, latency_ms REAL NOT NULL, predicted_label TEXT NOT NULL,
            top_score REAL NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
        rows = db.execute('SELECT * FROM prediction_log ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [dict(r) for r in rows]

@app.get('/api/model-registry')
def model_registry():
    registry_path = Path('models/registry.json')
    return json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else []

@app.get('/api/qr')
def qr(url: str = 'http://127.0.0.1:8000/'):
    if len(url) > 500 or not url.startswith(('https://', 'http://')):
        raise HTTPException(400, 'Provide a short HTTP(S) collection URL')
    out = BytesIO()
    qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage).save(out)
    return Response(out.getvalue(), media_type='image/svg+xml')


@app.get('/review')
def review_page():
    return FileResponse(Path(__file__).parent / 'static' / 'review.html')

@app.get('/api/review/{doc_id}')
def review_detail(doc_id: str, full: bool = False):
    from cement.review import schema, fingerprint
    with store.connect() as db:
        schema(db)
        doc = db.execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
        if not doc or doc['status'] != 'parsed':
            raise HTTPException(404, '沒有可審核的解析文字')
        member = db.execute('SELECT * FROM dataset_membership WHERE document_id=?', (doc_id,)).fetchone()
        pages = json.loads(Path(doc['text_path']).read_text(encoding='utf-8'))
        readable = [p for p in pages if p['text'].strip()]
        selected = pages if full else [readable[i] for i in sorted({0,len(readable)//2,len(readable)-1})] if readable else []
        return {'document_id': doc_id, 'text_hash': fingerprint(doc), 'current_label': doc['label'],
                'group_id': member['group_id'] if member else '', 'split': member['split'] if member else '',
                'membership_locked': bool(member), 'page_count':len(pages), 'full':full,
                'pages':selected if full else [{'page':p['page'],'text':p['text'][:1800], 'truncated':len(p['text'])>1800} for p in selected]}

class ReviewSubmission(BaseModel):
    document_id: str
    text_hash: str
    current_label: Literal['research', 'manual', 'guidance', 'safety', 'industry', 'experiment_log', 'manuscript_notes'] | None
    label: Literal['research', 'manual', 'guidance', 'safety', 'industry', 'experiment_log', 'manuscript_notes']
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(default='', max_length=5000)
    group_id: str = Field(min_length=1, max_length=200)
    split: Literal['train', 'validation', 'test']

@app.post('/api/review')
def save_review(value: ReviewSubmission):
    from cement.review import import_rows
    try:
        return {'saved': import_rows([value.model_dump()])}
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get('/api/review-progress')
def review_progress():
    from cement.dataset import build
    from cement.weaklabel import load_rules
    report = build(load_rules('config/term_mapping.json'))
    return {'targets': report['targets'], 'training_ready': report['training_ready'],
            'blocker_count': len(report['blockers'])}


@app.get('/api/search')
def api_search(q: str, limit: int = 20, offset: int = 0):
    from cement import search
    try:
        return search.search(q, limit, offset)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post('/api/search/reindex')
def api_reindex():
    from cement import search
    return {'indexed': search.reindex()}


class Policy(BaseModel):
    policy: Literal['unset', 'fast_track', 'standard', 'deprioritized', 'excluded']
    set_by: str = Field(min_length=1, max_length=100)
    reason: str = Field(default='', max_length=2000)

@app.put('/api/documents/{doc_id}/policy')
def api_set_policy(doc_id: str, value: Policy):
    from cement import search
    try:
        search.set_policy(doc_id, value.policy, value.set_by, value.reason)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return search.get_policy(doc_id)

@app.get('/api/documents/{doc_id}/policy')
def api_get_policy(doc_id: str):
    from cement import search
    return search.get_policy(doc_id)


class Relation(BaseModel):
    from_id: str
    to_id: str
    relation_type: Literal['supersedes', 'same_series', 'cites']
    created_by: str = Field(min_length=1, max_length=100)
    note: str = Field(default='', max_length=2000)

@app.post('/api/relations')
def api_add_relation(value: Relation):
    from cement import search
    try:
        return {'id': search.add_relation(value.from_id, value.to_id, value.relation_type, value.created_by, value.note)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@app.get('/api/documents/{doc_id}/relations')
def api_relations(doc_id: str):
    from cement import search
    return search.relations_for(doc_id)


@app.get('/graph')
def graph_page():
    return FileResponse(Path(__file__).parent / 'static' / 'graph.html')

@app.get('/api/graph/candidates')
def api_graph_candidates(status: str = 'pending'):
    from cement import graph_extract
    return graph_extract.list_candidates(status)

@app.post('/api/graph/extract')
def api_graph_extract():
    from cement import graph_extract
    result = graph_extract.extract_candidates()
    return {'candidates_created': len(result['created']), 'candidates_staled': len(result['staled'])}

class GraphReview(BaseModel):
    decision: Literal['accepted', 'rejected']
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(default='', max_length=2000)

@app.post('/api/graph/candidates/{candidate_id}/review')
def api_graph_review(candidate_id: str, value: GraphReview):
    from cement import graph_extract
    try:
        graph_extract.review_candidate(candidate_id, value.decision, value.reviewer, value.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {'saved': True}


class CandidateRelation(BaseModel):
    from_candidate_id: str
    to_candidate_id: str
    relation_type: Literal['same_event_candidate', 'precedes', 'related']
    created_by: str = Field(min_length=1, max_length=100)
    note: str = Field(default='', max_length=2000)

@app.post('/api/graph/candidate-relations')
def api_add_candidate_relation(value: CandidateRelation):
    from cement import graph_extract
    try:
        return {'id': graph_extract.add_candidate_relation(
            value.from_candidate_id, value.to_candidate_id, value.relation_type, value.created_by, value.note)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@app.get('/api/graph/candidate-relations')
def api_list_candidate_relations():
    from cement import graph_extract
    return graph_extract.list_candidate_relations()


# --- Entities, nodes, formal relations, tags, timeline (cement/graph_store.py) ---

@app.post('/api/graph/entity-mentions/extract')
def api_extract_mentions():
    from cement import graph_store
    return {'mentions_created': len(graph_store.extract_mentions())}

@app.get('/api/graph/entity-mentions')
def api_list_mentions(status: str = 'pending'):
    from cement import graph_store
    return graph_store.list_mentions(status)

class MentionLink(BaseModel):
    entity_id: str | None = None
    name_en: str = ''
    name_zh: str = ''
    created_by: str = Field(min_length=1, max_length=100)

@app.post('/api/graph/entity-mentions/{mention_id}/link')
def api_link_mention(mention_id: str, value: MentionLink):
    from cement import graph_store
    try:
        entity_id = graph_store.link_mention(
            mention_id, value.created_by, entity_id=value.entity_id,
            new_entity={'name_en': value.name_en, 'name_zh': value.name_zh} if not value.entity_id else None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {'entity_id': entity_id}

@app.get('/api/graph/entities')
def api_list_entities():
    from cement import graph_store
    return graph_store.list_entities()

@app.get('/api/graph/entities/{entity_id}/mentions')
def api_entity_mentions(entity_id: str):
    from cement import graph_store
    return graph_store.mentions_for_entity(entity_id)


class GraphNode(BaseModel):
    node_type: Literal['Event', 'Condition', 'Outcome']
    parent_candidate_id: str
    description: str = Field(min_length=1, max_length=2000)
    event_time: str = Field(default='', max_length=200)
    created_by: str = Field(min_length=1, max_length=100)

@app.post('/api/graph/nodes')
def api_create_node(value: GraphNode):
    from cement import graph_store
    payload = {'description': value.description}
    if value.event_time:
        payload['event_time'] = value.event_time
    try:
        return {'id': graph_store.create_node(value.node_type, value.parent_candidate_id, payload, value.created_by)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@app.get('/api/graph/nodes')
def api_list_nodes(document_version_id: str | None = None):
    from cement import graph_store
    return graph_store.list_nodes(document_version_id)


class GraphRelation(BaseModel):
    from_id: str
    from_type: Literal['Event', 'Condition', 'Outcome', 'Claim', 'Entity', 'DocumentVersion']
    to_id: str
    to_type: Literal['Event', 'Condition', 'Outcome', 'Claim', 'Entity', 'DocumentVersion']
    relation_type: Literal['participates_in', 'occurs_under', 'has_outcome', 'claims_cause',
                            'supports', 'contradicts', 'concludes_from', 'precedes', 'describes']
    evidence_ids: list[str] = Field(min_length=1)
    assertion_mode: Literal['explicit_in_source', 'model_inference', 'human_interpretation']
    polarity: Literal['affirmative', 'negative'] = 'affirmative'
    note: str = Field(default='', max_length=2000)
    created_by: str = Field(min_length=1, max_length=100)

@app.post('/api/graph/relations')
def api_create_relation(value: GraphRelation):
    from cement import graph_store
    try:
        return {'id': graph_store.create_relation(
            value.from_id, value.from_type, value.to_id, value.to_type, value.relation_type,
            value.created_by, value.evidence_ids, value.assertion_mode, value.note, value.polarity)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@app.get('/api/graph/relations')
def api_list_relations():
    from cement import graph_store
    return graph_store.list_relations()


class Tag(BaseModel):
    pref_label_en: str = ''
    pref_label_zh: str = ''
    definition: str = Field(default='', max_length=2000)
    broader_id: str | None = None
    created_by: str = Field(min_length=1, max_length=100)

@app.post('/api/graph/tags')
def api_create_tag(value: Tag):
    from cement import graph_store
    try:
        return {'id': graph_store.create_tag(value.created_by, value.pref_label_en, value.pref_label_zh,
                                              definition=value.definition, broader_id=value.broader_id)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@app.get('/api/graph/tags')
def api_list_tags():
    from cement import graph_store
    return graph_store.list_tags()

class NodeTag(BaseModel):
    node_id: str
    node_type: str
    tag_id: str
    created_by: str = Field(min_length=1, max_length=100)

@app.post('/api/graph/node-tags')
def api_tag_node(value: NodeTag):
    from cement import graph_store
    try:
        graph_store.tag_node(value.node_id, value.node_type, value.tag_id, value.created_by)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {'saved': True}

@app.get('/api/graph/node-tags')
def api_node_tags(node_id: str):
    from cement import graph_store
    return graph_store.tags_for(node_id)


@app.get('/timeline')
def timeline_page():
    return FileResponse(Path(__file__).parent / 'static' / 'timeline.html')

@app.get('/api/graph/timeline')
def api_timeline():
    from cement import graph_store
    return graph_store.timeline()


# --- Local semantic search (cement/vector_search.py); complements /api/search, not a replacement ---

@app.post('/api/search/semantic-reindex')
def api_semantic_reindex():
    from cement import vector_search
    return {'updated': vector_search.reindex()}

@app.get('/api/search/semantic')
def api_semantic_search(q: str, limit: int = 10, rerank: bool = False):
    from cement import vector_search
    try:
        return vector_search.semantic_search(q, limit, rerank)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
