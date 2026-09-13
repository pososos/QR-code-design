import json
import pytest
from cement import store, vector_search


def setup_docs(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setattr(vector_search, '_revisions', lambda: {vector_search.EMBED_MODEL: 'rev-1'})
    with store.connect() as db:
        for identity, text in [('a', 'hydration kinetics of Portland cement'),
                                ('b', 'safety gloves for cement dust exposure')]:
            path = tmp_path / f'{identity}.json'
            path.write_text(json.dumps([{'page': 1, 'text': text}]), encoding='utf-8')
            db.execute('INSERT INTO documents(id,path,kind,title,text_path,status,label) VALUES (?,?,?,?,?,?,?)',
                       (identity, str(path), 'html', identity, str(path), 'parsed', None))


def fake_encode(texts):
    # Deterministic 2-d vectors: "hydration"-like text near [1,0], "safety"-like text near [0,1].
    vectors = []
    for t in texts:
        low = t.lower()
        vectors.append([1.0, 0.0] if 'hydration' in low or 'cement paste' in low else [0.0, 1.0])
    return vectors


def test_reindex_is_incremental_by_text_hash(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    monkeypatch.setattr(vector_search, 'encode', fake_encode)
    assert vector_search.reindex() == 2
    assert vector_search.reindex() == 0  # unchanged text_hash: nothing to redo
    (tmp_path / 'a.json').write_text(json.dumps([{'page': 1, 'text': 'a brand new hydration abstract'}]), encoding='utf-8')
    assert vector_search.reindex() == 1  # only the changed document is re-embedded


def test_semantic_search_ranks_by_cosine_similarity(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    monkeypatch.setattr(vector_search, 'encode', fake_encode)
    vector_search.reindex()
    results = vector_search.semantic_search('hydration query text')
    assert results[0]['document_id'] == 'a'
    assert results[0]['score'] > results[1]['score']


def test_semantic_search_requires_query(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    monkeypatch.setattr(vector_search, 'encode', fake_encode)
    with pytest.raises(ValueError):
        vector_search.semantic_search('   ')


def test_semantic_search_empty_index_returns_empty(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    monkeypatch.setattr(vector_search, 'encode', fake_encode)
    assert vector_search.semantic_search('hydration') == []


def test_rerank_reorders_within_pool_only(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    monkeypatch.setattr(vector_search, 'encode', fake_encode)
    vector_search.reindex()

    def fake_rerank(query, results):
        # Flip the order the embedding stage produced, to prove rerank actually ran.
        for r in results:
            r['rerank_score'] = -results.index(r)
        return list(reversed(results))
    monkeypatch.setattr(vector_search, '_rerank', fake_rerank)
    results = vector_search.semantic_search('hydration query text', rerank=True, rerank_pool=2)
    assert results[0]['document_id'] == 'b'
