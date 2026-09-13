import json
from cement import store
from cement.semantic_benchmark import snapshot
from cement.review import schema, fingerprint


def test_snapshot_excludes_bad_status_and_flags_changed_text(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    path=tmp_path/'text.json'
    path.write_text(json.dumps([{'page':1,'text':''},{'page':2,'text':'x'*1800}]))
    with store.connect() as db:
        schema(db)
        db.execute('INSERT INTO documents(id,path,kind,text_path,status,label,title) VALUES (?,?,?,?,?,?,?)',('a','raw','pdf',str(path),'parsed','manual','do not leak title'))
        db.execute('INSERT INTO documents(id,path,kind,text_path,status) VALUES (?,?,?,?,?)',('b','raw','pdf',str(path),'needs_review'))
        db.execute('INSERT INTO dataset_membership(document_id,group_id,split,text_hash) VALUES (?,?,?,?)',('a','g','validation','old'))
    rows=snapshot()
    assert len(rows)==1 and len(rows[0]['text'])==1500
    assert rows[0]['pages'][0]['page']==2
    assert rows[0]['review_current'] is False
    assert 'title' not in rows[0]['text']
    assert store.documents()[0]['label']=='manual'
