import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from cement import demo_api, pipeline, store


def test_demo_isolation_and_limits(monkeypatch):
    monkeypatch.setattr(demo_api,'infer',lambda *a: {'label':'research','review_required':True})
    client=TestClient(demo_api.app)
    assert client.post('/api/infer',json={'text':'cement'}).json()['label']=='research'
    assert client.post('/api/infer',json={'text':'   '}).status_code==422
    assert client.post('/api/infer',json={'text':'a'*12001}).status_code==422
    assert client.post('/api/infer',content=b'x'*65537).status_code==413
    assert client.get('/api/documents').status_code==404
    demo_api.lock.acquire()
    try:assert client.post('/api/infer',json={'text':'cement'}).status_code==429
    finally:demo_api.lock.release()


def test_pipeline_resume_skips_done_and_caps_attempts(tmp_path,monkeypatch):
    state={'steps':[{'id':'one','args':[],'status':'done','attempts':1},
                    {'id':'two','args':[],'status':'pending','attempts':0}], 'data_root':str(tmp_path)}
    calls=[]
    def runner(*a,**k):calls.append(a);return SimpleNamespace(returncode=1)
    with pytest.raises(RuntimeError):pipeline.execute(tmp_path,state,runner)
    assert len(calls)==1 and state['steps'][1]['status']=='failed'
    pipeline.execute(tmp_path,state,lambda *a,**k:SimpleNamespace(returncode=0))
    assert state['steps'][1]['status']=='done'
    state['steps'][1]['status']='failed'
    with pytest.raises(RuntimeError,match='cap'):pipeline.execute(tmp_path,state,runner)


def test_inference_reranker_body_only(monkeypatch):
    from cement import inference
    monkeypatch.setattr(inference.vector_search,'encode',lambda texts:[[1.,0.] for _ in texts])
    # Identical similarities force abstention at each stage; reranker disabled must not load.
    monkeypatch.setattr(inference.vector_search,'_load_reranker',lambda:pytest.fail('unexpected reranker'))
    result=inference.infer('Cement guide\nContents\nA ... 1\nB ... 2\nC ... 3',use_reranker=False)
    assert result['label'] is None
    assert [t['stage'] for t in result['trace']]==['title','contents','body']


def test_readiness_does_not_reuse_validation(tmp_path,monkeypatch):
    from cement import evaluation,review
    monkeypatch.setattr(store,'ROOT',tmp_path)
    with store.connect() as db:review.schema(db)
    report=evaluation.inspect()
    assert not report['formal_training_ready']
    assert any('training membership' in b for b in report['blockers'])


def test_benchmark_excludes_train_and_stale(tmp_path,monkeypatch):
    from cement import evaluation,inference
    monkeypatch.chdir(tmp_path);Path('models').mkdir()
    Path('models/evaluation.json').write_text(json.dumps({'train_ids':['train'],'test_ids':['stale','test']}))
    rows=[{'document_id':k,'label':'research','current':k!='stale'} for k in ('train','stale','test')]
    monkeypatch.setattr(evaluation,'inspect',lambda:{'rows':rows})
    monkeypatch.setattr(store,'documents',lambda:[{'id':r['document_id']} for r in rows])
    monkeypatch.setattr(evaluation,'text_of',lambda d:'research')
    monkeypatch.setattr(inference,'infer',lambda *a:{'label':'research'})
    result=evaluation.benchmark()
    assert [r['document_id'] for r in result['rows']]==['test']
    assert {r['reason'] for r in result['excluded']}=={'training_exposure','stale_or_missing_review'}
    assert result['independent_test'] is False
