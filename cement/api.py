from io import BytesIO
from pathlib import Path
from typing import Literal
import joblib
import qrcode
import qrcode.image.svg
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from cement import store
from cement.parse import text_of, sample

app = FastAPI(title='Cement Knowledge Intake', version='0.1.0')

@app.get('/')
def index(): return FileResponse(Path(__file__).parent / 'static' / 'index.html')

@app.get('/api/documents')
def documents(): return store.documents()

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
    # Load only this locally generated artifact; never accept uploaded pickle files.
    model = joblib.load(path)
    scores = model.predict_proba([sample(value.text)])[0]
    return {'label': str(model.classes_[scores.argmax()]), 'scores': dict(zip(model.classes_, map(float, scores))), 'review_required': True}

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
    import json
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
def api_search(q: str, limit: int = 20):
    from cement import search
    try:
        return search.search(q, limit)
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
    return {'candidates_created': len(graph_extract.extract_candidates())}

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
