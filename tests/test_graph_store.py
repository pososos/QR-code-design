import json
import pytest
from cement import store, graph_extract, graph_store


def setup_accepted_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    with store.connect() as db:
        path = tmp_path / 'a.json'
        text = 'Excess water due to high water-to-cement ratio results in reduced strength for Portland cement specimens.'
        path.write_text(json.dumps([{'page': 1, 'text': text}]), encoding='utf-8')
        db.execute('INSERT INTO documents(id,path,kind,title,text_path,status,label) VALUES (?,?,?,?,?,?,?)',
                   ('a', str(path), 'html', 'doc a', str(path), 'parsed', 'research'))
        db.execute('INSERT INTO sources(url,source_id,document_id) VALUES (?,?,?)',
                   ('https://example.org/a', 'src-a', 'a'))
    graph_extract.extract_candidates()
    candidate_id = graph_extract.list_candidates('pending')[0]['id']
    graph_extract.review_candidate(candidate_id, 'accepted', 'pososos')
    return candidate_id


def test_entity_mentions_are_rule_based_and_require_explicit_linking(tmp_path, monkeypatch):
    setup_accepted_candidate(tmp_path, monkeypatch)
    created = graph_store.extract_mentions({'material': ['Portland cement']})
    assert created
    mentions = graph_store.list_mentions('pending')
    assert mentions and mentions[0]['gazetteer_term'] == 'Portland cement'
    mention_id = mentions[0]['id']
    with pytest.raises(ValueError):
        graph_store.link_mention(mention_id, '')
    with pytest.raises(ValueError):
        graph_store.link_mention(mention_id, 'pososos')
    entity_id = graph_store.link_mention(mention_id, 'pososos', new_entity={'name_en': 'Portland cement'})
    assert graph_store.list_mentions('pending') == []
    linked = graph_store.mentions_for_entity(entity_id)
    assert linked[0]['id'] == mention_id
    assert graph_store.list_entities()[0]['id'] == entity_id


def test_node_decomposition_requires_accepted_candidate(tmp_path, monkeypatch):
    setup_accepted_candidate(tmp_path, monkeypatch)
    graph_extract.extract_candidates()
    pending_id = graph_extract.list_candidates('pending')[0]['id']
    with pytest.raises(ValueError):
        graph_store.create_node('Event', pending_id, {'description': 'x'}, 'pososos')
    with pytest.raises(ValueError):
        graph_store.create_node('NotANode', pending_id, {'description': 'x'}, 'pososos')
    with pytest.raises(ValueError):
        graph_store.create_node('Event', 'missing', {'description': 'x'}, 'pososos')
    accepted_id = graph_extract.list_candidates('accepted')[0]['id']
    with pytest.raises(ValueError):
        graph_store.create_node('Event', accepted_id, {'description': ''}, 'pososos')
    node_id = graph_store.create_node('Event', accepted_id, {'description': 'water added in excess'}, 'pososos')
    nodes = graph_store.list_nodes()
    assert nodes[0]['id'] == node_id and nodes[0]['node_type'] == 'Event'


def test_formal_relation_requires_evidence_and_valid_endpoints(tmp_path, monkeypatch):
    accepted_id = setup_accepted_candidate(tmp_path, monkeypatch)
    event_id = graph_store.create_node('Event', accepted_id, {'description': 'excess water added'}, 'pososos')
    outcome_id = graph_store.create_node('Outcome', accepted_id, {'description': 'reduced strength'}, 'pososos')
    candidate = graph_extract.list_candidates('accepted')[0]
    evidence_id = candidate['evidence_id']
    with pytest.raises(ValueError):
        graph_store.create_relation(event_id, 'Event', outcome_id, 'Outcome', 'invented', 'pososos', [evidence_id], 'explicit_in_source')
    with pytest.raises(ValueError):
        graph_store.create_relation(event_id, 'Event', outcome_id, 'Outcome', 'has_outcome', 'pososos', [], 'explicit_in_source')
    with pytest.raises(ValueError):
        graph_store.create_relation(event_id, 'Event', 'missing', 'Outcome', 'has_outcome', 'pososos', [evidence_id], 'explicit_in_source')
    with pytest.raises(ValueError):
        graph_store.create_relation(event_id, 'Event', outcome_id, 'Outcome', 'has_outcome', '', [evidence_id], 'explicit_in_source')
    rel_id = graph_store.create_relation(event_id, 'Event', outcome_id, 'Outcome', 'has_outcome', 'pososos',
                                          [evidence_id], 'explicit_in_source', note='direct quote')
    relations = graph_store.list_relations()
    assert relations[0]['id'] == rel_id and relations[0]['relation_type'] == 'has_outcome'
    assert json.loads(relations[0]['evidence_ids_json']) == [evidence_id]


def test_tag_vocabulary_requires_labels_and_valid_broader(tmp_path, monkeypatch):
    setup_accepted_candidate(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        graph_store.create_tag('pososos')
    with pytest.raises(ValueError):
        graph_store.create_tag('', pref_label_en='shrinkage')
    with pytest.raises(ValueError):
        graph_store.create_tag('pososos', pref_label_en='drying shrinkage', broader_id='missing')
    broader_id = graph_store.create_tag('pososos', pref_label_en='shrinkage', pref_label_zh='收縮')
    narrower_id = graph_store.create_tag('pososos', pref_label_en='drying shrinkage', pref_label_zh='乾燥收縮', broader_id=broader_id)
    accepted_id = graph_extract.list_candidates('accepted')[0]['id']
    with pytest.raises(ValueError):
        graph_store.tag_node(accepted_id, 'Claim', 'missing-tag', 'pososos')
    graph_store.tag_node(accepted_id, 'Claim', narrower_id, 'pososos')
    tags = graph_store.tags_for(accepted_id)
    assert tags[0]['id'] == narrower_id and tags[0]['broader_id'] == broader_id


def test_timeline_keeps_confidence_tiers_separate(tmp_path, monkeypatch):
    accepted_id = setup_accepted_candidate(tmp_path, monkeypatch)
    graph_store.create_node('Event', accepted_id, {'description': 'curing started', 'event_time': 'day 7'}, 'pososos')
    result = graph_store.timeline()
    assert result['event_times'][0]['value'] == 'day 7'
    assert result['event_times_confidence'] != result['fetch_times_confidence']
    assert result['fetch_times'] and result['fetch_times'][0]['document_id'] == 'a'
