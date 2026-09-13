import json
import pytest
from cement import store, search


def setup_docs(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    with store.connect() as db:
        for identity, label, text in [
            ('a', 'research', 'hydration kinetics of Portland cement paste'),
            ('b', 'safety', 'protective gloves required for cement dust exposure'),
            ('c', None, 'unlabeled document about hydration curing conditions'),
        ]:
            path = tmp_path / f'{identity}.json'
            path.write_text(json.dumps([{'page': 1, 'text': text}]), encoding='utf-8')
            db.execute('INSERT INTO documents(id,path,kind,title,text_path,status,label) VALUES (?,?,?,?,?,?,?)',
                       (identity, str(path), 'html', identity, str(path), 'parsed', label))
    return ['a', 'b', 'c']


def test_reindex_and_search_ignores_label(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    assert search.reindex() == 3
    hits = search.search('hydration')
    assert {h['document_id'] for h in hits} == {'a', 'c'}
    # Unlabeled document must still be searchable; classification is not the retrieval gate.
    assert any(h['document_id'] == 'c' and h['label'] is None for h in hits)


def test_search_requires_query(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    search.reindex()
    with pytest.raises(ValueError):
        search.search('   ')


def test_processing_policy_explicit_and_validated(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        search.set_policy('a', 'not-a-policy', 'reviewer')
    with pytest.raises(ValueError):
        search.set_policy('a', 'fast_track', '')
    with pytest.raises(ValueError):
        search.set_policy('missing', 'fast_track', 'reviewer')
    search.set_policy('a', 'fast_track', 'pososos', reason='high manual demand')
    saved = search.get_policy('a')
    assert saved['policy'] == 'fast_track' and saved['reason'] == 'high manual demand' and saved['set_by'] == 'pososos'
    assert search.get_policy('b')['policy'] == 'unset'


def test_document_relations_require_explicit_declaration(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        search.add_relation('a', 'b', 'invented-type', 'pososos')
    with pytest.raises(ValueError):
        search.add_relation('a', 'a', 'same_series', 'pososos')
    with pytest.raises(ValueError):
        search.add_relation('a', 'missing', 'cites', 'pososos')
    with pytest.raises(ValueError):
        search.add_relation('a', 'b', 'cites', '')
    rel_id = search.add_relation('a', 'b', 'supersedes', 'pososos', note='newer edition')
    rows = search.relations_for('b')
    assert len(rows) == 1 and rows[0]['id'] == rel_id and rows[0]['relation_type'] == 'supersedes'
    assert search.relations_for('a') == rows
