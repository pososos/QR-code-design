import copy
import json
from pathlib import Path
from cement import store
from cement.weaklabel import classify, load_rules, run

RULES = load_rules(Path(__file__).parents[1] / 'config/term_mapping.json')

def pages(text):
    return [{'page': 1, 'text': text}]

def test_each_class_evidence_and_boundaries():
    examples = {'research':'Cement hydration kinetics\nMethods and results',
                'manual':'Cement software user guide\nInstallation parameter',
                'guidance':'水泥技術指引\n適用條件與建議',
                'safety':'Cement safety data sheet\nHazard identification\nFirst aid',
                'industry':'水泥永續報告書\n報告期間與排放',
                'experiment_log':'水泥實驗記錄\n試體編號與量測',
                'manuscript_notes':'水泥工作筆記\n草稿想法與待辦'}
    for label, text in examples.items():
        result = classify(pages(text), RULES)
        assert result['label'] == label
        assert result['evidence'][0]['page'] == 1
    assert classify(pages('replacement user guide software'), RULES)['label'] is None
    assert classify(pages('Cement safety issues'), RULES)['label'] is None

def test_conflict_references_and_repeat_do_not_force_labels():
    assert classify(pages('Cement user guide software\nSafety data sheet first aid'), RULES)['reason'] == 'conflicting_classes'
    assert classify(pages('Cement\nReferences\nSafety data sheet first aid'), RULES)['label'] is None
    one = classify(pages('Cement user guide software'), RULES)
    repeated = classify(pages(('Cement user guide software\n')*10), RULES)
    assert one['scores'] == repeated['scores']

def test_history_idempotence_manual_and_quality(tmp_path, monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    path = tmp_path/'text.json'
    path.write_text(json.dumps(pages('Cement user guide software')))
    with store.connect() as db:
        for identity,status,label in [('a','parsed',None),('b','parsed','research'),('c','needs_review',None)]:
            db.execute('INSERT INTO documents(id,path,kind,text_path,status,label) VALUES (?,?,?,?,?,?)',
                       (identity,str(path),'pdf',str(path),status,label))
    assert run(RULES)['counts'] == {'candidate':1,'skipped':2}
    run(RULES)
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM weak_labels').fetchone()[0] == 1
        assert db.execute("SELECT label FROM documents WHERE id='a'").fetchone()[0] is None
        assert db.execute("SELECT label FROM documents WHERE id='b'").fetchone()[0] == 'research'
    new_rules = copy.deepcopy(RULES)
    new_rules['min_score'] = 99
    assert run(new_rules)['counts']['abstain'] == 1
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM weak_labels').fetchone()[0] == 2
