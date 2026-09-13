import json
from pathlib import Path
import pytest
from cement import store
from cement.review import export_review, import_review
from cement.dataset import build
from cement.weaklabel import load_rules, run

RULES=load_rules(Path(__file__).parents[1]/'config/term_mapping.json')

def seed(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    with store.connect() as db:
        for i in ('a','b'):
            path=tmp_path/f'{i}.json'
            path.write_text(json.dumps([{'page':1,'text':'Cement user guide software installation '+i}]))
            db.execute('INSERT INTO documents(id,path,kind,text_path,status) VALUES (?,?,?,?,?)',(i,str(path),'pdf',str(path),'parsed'))
    run(RULES)
    file=tmp_path/'review.json'
    export_review(file,RULES)
    return file

def fill(file):
    rows=json.loads(file.read_text())
    for r in rows:
        r.update(label='manual',reviewer='test-reviewer',split='train',group_id='family-'+r['document_id'])
    file.write_text(json.dumps(rows))
    return rows

def test_review_roundtrip_idempotent_and_no_prediction_priming(tmp_path,monkeypatch):
    file=seed(tmp_path,monkeypatch)
    assert all(r['suggested_label'] is None for r in json.loads(file.read_text()))
    with pytest.raises(FileExistsError): export_review(file,RULES)
    fill(file)
    assert import_review(file)==2
    assert import_review(file)==2
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM review_log').fetchone()[0]==2
        assert {r['label'] for r in db.execute('SELECT label FROM documents')}=={'manual'}
    report=build(RULES)
    assert all(r['origin']=='manual' for r in report['rows'])
    assert report['training_ready'] is False

def test_stale_review_atomic_and_group_collision(tmp_path,monkeypatch):
    file=seed(tmp_path,monkeypatch)
    rows=fill(file)
    rows[1]['text_hash']='stale'
    file.write_text(json.dumps(rows))
    with pytest.raises(ValueError,match='Stale'): import_review(file)
    assert all(d['label'] is None for d in store.documents())
    rows[1]['text_hash']=json.loads((tmp_path/'reports/weak_labels_latest.json').read_text())['results'][1].get('text_hash','')
    # Export again to obtain actual fingerprints, then create group leakage.
    second=tmp_path/'second.json'
    export_review(second,RULES)
    rows=fill(second)
    rows[0].update(group_id='shared',split='train')
    rows[1].update(group_id='shared',split='test')
    second.write_text(json.dumps(rows))
    with pytest.raises(ValueError,match='crosses'): import_review(second)
    assert all(d['label'] is None for d in store.documents())

def test_draft_excludes_stale_weak_and_reports_pending(tmp_path,monkeypatch):
    seed(tmp_path,monkeypatch)
    report=build(RULES)
    assert len(report['rows'])==2
    assert all('pending_weak_audit' in r['issues'] for r in report['rows'])
    path=tmp_path/'a.json'
    path.write_text(json.dumps([{'page':1,'text':'Changed content'}]))
    report=build(RULES)
    assert len(report['rows'])==1
    assert any(r['reason']=='no_current_label' for r in report['excluded'])

def test_review_rejects_overwriting_changed_manual_and_split(tmp_path,monkeypatch):
    file=seed(tmp_path,monkeypatch)
    fill(file)
    with store.connect() as db:
        db.execute("UPDATE documents SET label='research' WHERE id='a'")
    with pytest.raises(ValueError,match='changed after export'): import_review(file)
    with store.connect() as db:
        db.execute("UPDATE documents SET label=NULL WHERE id='a'")
    import_review(file)
    rows=json.loads(file.read_text())
    rows[0]['split']='test'
    file.write_text(json.dumps(rows))
    with pytest.raises(ValueError,match='frozen'): import_review(file)


def test_reading_pack_preserves_import_contract_and_hides_suggestions(tmp_path,monkeypatch):
    from cement.review_pack import create_pack
    file=seed(tmp_path,monkeypatch)
    rows=json.loads(file.read_text())
    rows[0]['suggested_label']='research'
    rows[0]['evidence']=[{'secret':'prediction_evidence'}]
    rows[0]['pages'][0]['text']='<script>alert(1)</script>'
    file.write_text(json.dumps(rows))
    output=tmp_path/'pack'
    assert create_pack(file,output)==2
    answers=output/'answers.json'
    compact=json.loads(answers.read_text())
    assert all(r['label']=='' and 'suggested_label' not in r and 'pages' not in r for r in compact)
    assert '&lt;script&gt;' in (output/'document-001.md').read_text(encoding='utf-8')
    assert 'prediction_evidence' not in ''.join(p.read_text(encoding='utf-8') for p in output.iterdir())
    with pytest.raises(FileExistsError): create_pack(file,output)
    assert import_review(answers)==0
    fill(answers)
    assert import_review(answers)==2


def test_review_api_preview_full_and_guarded_save(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from cement.api import app
    seed(tmp_path,monkeypatch)
    path=tmp_path/'a.json'
    path.write_text(json.dumps([{'page':i+1,'text':'x'*2200+str(i)} for i in range(5)]))
    client=TestClient(app)
    assert client.get('/review').status_code==200
    preview=client.get('/api/review/a').json()
    assert [p['page'] for p in preview['pages']]==[1,3,5]
    assert all(len(p['text'])==1800 for p in preview['pages'])
    full=client.get('/api/review/a?full=true').json()
    assert len(full['pages'])==5 and len(full['pages'][0]['text'])==2201
    payload={k:full[k] for k in ('document_id','text_hash','current_label')}
    payload.update(label='manual',reviewer='fixture',group_id='same',split='train',note='test only')
    assert client.post('/api/review',json={**payload,'text_hash':'stale'}).status_code==409
    assert client.post('/api/review',json={**payload,'label':'invalid'}).status_code==422
    assert client.post('/api/review',json=payload).json()=={'saved':1}
    assert client.get('/api/review/a').json()['membership_locked'] is True
    b=client.get('/api/review/b').json()
    payload.update(document_id='b',text_hash=b['text_hash'],current_label=b['current_label'],split='test')
    assert client.post('/api/review',json=payload).status_code==409
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM review_log').fetchone()[0]==1
        assert db.execute('SELECT label FROM documents WHERE id=?',('b',)).fetchone()[0] is None


def test_review_progress_counts_only_current_eligible_labels(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from cement.api import app
    file=seed(tmp_path,monkeypatch)
    client=TestClient(app)
    before=client.get('/api/review-progress').json()
    assert sum(t['target'] for t in before['targets'])==455
    assert sum(t['ready'] for t in before['targets'])==0
    fill(file)
    import_review(file)
    after=client.get('/api/review-progress').json()
    target=next(t for t in after['targets'] if t['label']=='manual' and t['split']=='train' and t['origin']=='manual')
    assert (target['target'],target['ready'],target['gap'])==(10,2,8)
    assert after['training_ready'] is False
    (tmp_path/'a.json').write_text('[]')
    stale=client.get('/api/review-progress').json()
    assert sum(t['ready'] for t in stale['targets'])==1
