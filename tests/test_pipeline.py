import json
from pathlib import Path
from fastapi.testclient import TestClient
from cement import store
from cement.api import app
from cement.crawl import Crawler, allowed
from cement.parse import main as parse

def setup_data(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)

def test_allowlist():
    assert allowed('https://www.nist.gov/document/a', ['www.nist.gov'])
    assert not allowed('https://www.nist.gov.evil.test/a', ['www.nist.gov'])
    assert not allowed('http://www.nist.gov/a', ['www.nist.gov'])
    assert not allowed('https://user@www.nist.gov/a', ['www.nist.gov'])

def test_dedup_parse_label_and_missing_model(tmp_path, monkeypatch):
    setup_data(tmp_path, monkeypatch)
    monkeypatch.setattr('sys.argv', ['parse'])
    crawler = Crawler()
    html = b'<html><title>Cement guide</title><main>Hydration and cement research document with enough text for extraction.</main></html>'
    monkeypatch.setattr(crawler, 'fetch', lambda u,h,headers: (html, {'Content-Type':'text/html', 'ETag':'abc'}, u))
    config = {'id':'test', 'url':'https://example.org/a', 'allowed_hosts':['example.org'], 'max_depth':0, 'suggested_label':'research'}
    crawler.run(config)
    config['url'] = 'https://example.org/b'
    crawler.run(config)
    docs = store.documents()
    assert len(docs) == 1 and len(docs[0]['sources']) == 2
    assert docs[0]['label'] is None
    parse()
    assert store.documents()[0]['status'] == 'parsed'
    client = TestClient(app)
    doc_id = docs[0]['id']
    assert client.put(f'/api/documents/{doc_id}/label', json={'label':'invalid'}).status_code == 422
    assert client.put(f'/api/documents/{doc_id}/label', json={'label':'research'}).status_code == 200
    assert 'Hydration' in client.get(f'/api/documents/{doc_id}/text').json()['text']
    monkeypatch.chdir(tmp_path)
    assert client.post('/api/predict', json={'text':'cement'}).status_code == 409
    assert client.get('/api/qr').headers['content-type'].startswith('image/svg+xml')

def test_conditional_request(tmp_path, monkeypatch):
    setup_data(tmp_path, monkeypatch)
    crawler = Crawler()
    config = {'id':'test', 'url':'https://example.org/a', 'allowed_hosts':['example.org'], 'max_depth':0}
    monkeypatch.setattr(crawler, 'fetch', lambda u,h,headers: (b'%PDF-test', {'ETag':'version-one'}, u))
    crawler.run(config)
    def unchanged(url, hosts, headers):
        assert headers['If-None-Match'] == 'version-one'
        return None, {}, url
    monkeypatch.setattr(crawler, 'fetch', unchanged)
    crawler.run(config)
    assert len(store.documents()) == 1
    with store.connect() as db:
        assert db.execute('SELECT status FROM events ORDER BY id DESC LIMIT 1').fetchone()[0] == 'unchanged'

def test_fetch_failure_recorded(tmp_path, monkeypatch):
    setup_data(tmp_path, monkeypatch)
    crawler = Crawler()
    def denied(*args): raise PermissionError('robots.txt disallows URL')
    monkeypatch.setattr(crawler, 'fetch', denied)
    crawler.run({'id':'test','url':'https://example.org/a','allowed_hosts':['example.org']})
    assert store.documents() == []
    with store.connect() as db:
        assert db.execute('SELECT status FROM events').fetchone()[0] == 'error'

def test_training_and_prediction_roundtrip(tmp_path, monkeypatch):
    from cement.train import main as train
    setup_data(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    with store.connect() as db:
        for index, (category, text) in enumerate([
            ('research','hydration kinetics experiment mechanism cement'),
            ('research','cement hydration research experimental kinetics'),
            ('safety','safety hazard protective gloves exposure dust'),
            ('safety','hazard dust protective equipment safety'),
            ('research','research mechanism hydration kinetics'),
            ('safety','dust safety protective gloves')]):
            path = tmp_path / f'{index}.json'
            path.write_text(json.dumps([{'page':1,'text':text}]), encoding='utf-8')
            db.execute('INSERT INTO documents(id,path,kind,text_path,status,label) VALUES (?,?,?,?,?,?)',
                       (str(index),str(path),'html',str(path),'parsed',category))
            db.execute('INSERT INTO sources(url,source_id,document_id) VALUES (?,?,?)',
                       (f'https://example.org/{index}', 'test-source' if index >= 4 else 'train-source', str(index)))
    monkeypatch.setattr('sys.argv', ['train','--holdout-sources','test-source'])
    train()
    report = json.loads(Path('models/evaluation.json').read_text())
    assert not set(report['train_ids']) & set(report['test_ids'])
    assert report['calibration']['bins']
    registry = json.loads(Path('models/registry.json').read_text())
    assert registry[0]['holdout_sources'] == ['test-source']
    assert Path(registry[0]['path']).exists()
    response = TestClient(app).post('/api/predict', json={'text':'hydration kinetics research'})
    assert response.status_code == 200
    assert set(response.json()['scores']) == {'research','safety'}
    assert response.json()['review_required'] is True
    assert response.json()['latency_ms'] >= 0
    log = TestClient(app).get('/api/predict-log').json()
    assert log[0]['predicted_label'] in {'research', 'safety'}

def test_challenge_and_corrupt_text_not_training_ready(tmp_path, monkeypatch):
    setup_data(tmp_path, monkeypatch)
    monkeypatch.setattr('sys.argv', ['parse'])
    with store.connect() as db:
        for name, text in [('blocked','Request unsuccessful. Incapsula incident ID: 1234567890'),('corrupt','x\x01' * 100)]:
            path = tmp_path / f'{name}.html'
            path.write_text(f'<html><main>{text}</main></html>')
            db.execute('INSERT INTO documents(id,path,kind) VALUES (?,?,?)', (name,str(path),'html'))
    parse()
    statuses = {d['id']:d['status'] for d in store.documents()}
    assert statuses == {'blocked':'blocked_content','corrupt':'needs_review'}

def test_parse_document_filter_leaves_other_docs_untouched(tmp_path, monkeypatch):
    setup_data(tmp_path, monkeypatch)
    monkeypatch.setattr('sys.argv', ['parse','--document-id','one'])
    with store.connect() as db:
        for identity in ['one','two']:
            path=tmp_path/f'{identity}.html'
            path.write_text('<html><main>Cement research hydration testing document with sufficient text.</main></html>')
            db.execute('INSERT INTO documents(id,path,kind) VALUES (?,?,?)',(identity,str(path),'html'))
    parse()
    assert {d['id']:d['status'] for d in store.documents()} == {'one':'parsed','two':'downloaded'}


def test_rate_limit_stops_same_host_requests(monkeypatch):
    import pytest
    from types import SimpleNamespace
    crawler = Crawler()
    monkeypatch.setattr(crawler, 'permitted', lambda url: True)
    monkeypatch.setattr(crawler, 'wait', lambda url: None)
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=429, headers={'Retry-After': '600'}, close=lambda: None)
    monkeypatch.setattr(crawler.session, 'get', get)
    with pytest.raises(RuntimeError, match='429'):
        crawler.fetch('https://example.org/a', ['example.org'], {})
    with pytest.raises(RuntimeError, match='paused'):
        crawler.fetch('https://example.org/b', ['example.org'], {})
    assert calls == ['https://example.org/a']


def test_plaintext_experiment_parse(tmp_path, monkeypatch):
    setup_data(tmp_path, monkeypatch)
    raw = tmp_path / 'record.txt'
    raw.write_text('HPC Lab 4\nSpecimen 4-O-PK01\nCasted: 01.04.2019\nCycles Force [kN]\n1 182.42\n', encoding='utf-8')
    with store.connect() as db:
        db.execute('INSERT INTO documents(id,path,kind) VALUES (?,?,?)', ('record', str(raw), 'txt'))
    monkeypatch.setattr('sys.argv', ['parse'])
    parse()
    doc = store.documents()[0]
    assert doc['status'] == 'parsed' and doc['label'] is None
    assert '182.42' in json.loads(Path(doc['text_path']).read_text(encoding='utf-8'))[0]['text']


def test_archive_preflight_and_hashed_paths(tmp_path, monkeypatch):
    import hashlib, runpy, zipfile, pytest
    setup_data(tmp_path / 'data', monkeypatch)
    archive = tmp_path / 'measurements.zip'
    def prepare(bad):
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('../../outside.txt', b'Specimen 1: load cycles and stress measurements')
            if bad: z.writestr('bad.txt', b'\xff')
        archive.with_suffix('.json').write_text(json.dumps(dict(sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),url='https://example.org/data.zip',license='test',document_family='test-family',domain='cement_concrete')),encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['import', '--archive', str(archive), '--output', str(tmp_path/'members.json')])
    prepare(True)
    with pytest.raises(UnicodeDecodeError):runpy.run_module('scripts.import_experiment_archive',run_name='__main__')
    assert not (store.ROOT/'raw').exists()
    prepare(False)
    runpy.run_module('scripts.import_experiment_archive',run_name='__main__')
    docs = store.documents()
    assert len(docs)==1 and docs[0]['label'] is None
    assert Path(docs[0]['path']).parent == store.ROOT/'raw'
    assert not (tmp_path/'outside.txt').exists()
