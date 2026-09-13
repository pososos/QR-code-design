import json
import pytest
from cement import store, graph_extract


def setup_docs(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    with store.connect() as db:
        path = tmp_path / 'a.json'
        text = 'Excess water due to high water-to-cement ratio results in reduced strength.'
        path.write_text(json.dumps([{'page': 1, 'text': text}]), encoding='utf-8')
        db.execute('INSERT INTO documents(id,path,kind,title,text_path,status,label) VALUES (?,?,?,?,?,?,?)',
                   ('a', str(path), 'html', 'doc a', str(path), 'parsed', 'research'))
        db.execute('INSERT INTO sources(url,source_id,document_id) VALUES (?,?,?)',
                   ('https://example.org/a', 'src-a', 'a'))


def test_extract_finds_cue_phrase_candidates(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    created = graph_extract.extract_candidates()
    assert created
    pending = graph_extract.list_candidates('pending')
    assert len(pending) == len(created)
    phrases = {c['cue_phrase'] for c in pending}
    assert phrases <= {'due to', 'results in'}
    assert all(c['node_type'] == 'Claim' and c['assertion_mode'] == 'explicit_in_source' for c in pending)


def test_review_requires_valid_decision_and_reviewer(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    graph_extract.extract_candidates()
    candidate_id = graph_extract.list_candidates('pending')[0]['id']
    with pytest.raises(ValueError):
        graph_extract.review_candidate(candidate_id, 'maybe', 'pososos')
    with pytest.raises(ValueError):
        graph_extract.review_candidate(candidate_id, 'accepted', '')
    with pytest.raises(ValueError):
        graph_extract.review_candidate('missing', 'accepted', 'pososos')
    graph_extract.review_candidate(candidate_id, 'accepted', 'pososos', note='plausible, keep for human decomposition')
    assert all(c['id'] != candidate_id for c in graph_extract.list_candidates('pending'))
    accepted = graph_extract.list_candidates('accepted')
    assert accepted[0]['id'] == candidate_id and accepted[0]['reviewer'] == 'pososos'


def test_rerun_keeps_reviewed_candidates_and_refreshes_pending(tmp_path, monkeypatch):
    setup_docs(tmp_path, monkeypatch)
    graph_extract.extract_candidates()
    pending = graph_extract.list_candidates('pending')
    kept_id = pending[0]['id']
    graph_extract.review_candidate(kept_id, 'rejected', 'pososos')
    graph_extract.extract_candidates()
    rejected = graph_extract.list_candidates('rejected')
    assert any(c['id'] == kept_id for c in rejected)
    new_pending = graph_extract.list_candidates('pending')
    assert all(c['id'] != kept_id for c in new_pending)
