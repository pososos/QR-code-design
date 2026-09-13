import json
from fastapi.testclient import TestClient
from cement import store
from cement.api import app


def setup_docs(tmp_path, monkeypatch, count=5):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    with store.connect() as db:
        for i in range(count):
            path = tmp_path / f'{i}.json'
            path.write_text(json.dumps([{'page': 1, 'text': f'document number {i}'}]), encoding='utf-8')
            db.execute('INSERT INTO documents(id,path,kind,title,text_path,status,created_at) VALUES (?,?,?,?,?,?,?)',
                       (str(i), str(path), 'html', str(i), str(path), 'parsed', f'2026-01-0{i+1}'))


def test_store_documents_limit_offset_preserves_default_full_list(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    assert len(store.documents()) == 5
    assert store.document_count() == 5
    page = store.documents(limit=2, offset=1)
    assert len(page) == 2
    assert page != store.documents(limit=2, offset=0)


def test_api_documents_without_limit_returns_bare_array(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    client = TestClient(app)
    response = client.get('/api/documents')
    assert isinstance(response.json(), list) and len(response.json()) == 5
    assert 'x-total-count' not in response.headers


def test_api_documents_with_limit_paginates_and_reports_total(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    client = TestClient(app)
    response = client.get('/api/documents', params={'limit': 2, 'offset': 2})
    assert response.headers['x-total-count'] == '5'
    assert len(response.json()) == 2


def test_api_search_offset_pages_through_results(tmp_path, monkeypatch):
    from cement import search
    setup_docs(tmp_path, monkeypatch)
    search.reindex()
    client = TestClient(app)
    first = client.get('/api/search', params={'q': 'document', 'limit': 2, 'offset': 0}).json()
    second = client.get('/api/search', params={'q': 'document', 'limit': 2, 'offset': 2}).json()
    assert len(first) == 2 and len(second) == 2
    assert {r['document_id'] for r in first}.isdisjoint({r['document_id'] for r in second})
