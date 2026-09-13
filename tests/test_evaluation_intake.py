from pathlib import Path
import pytest
from cement.evaluation_intake import freeze

def inventory():
    return dict(selection_basis='fixed_scope_no_purpose_filter',scope_description='All files in fixed project snapshot',documents=[dict(url=f'https://new.example/{i}.pdf',organization='Org A',family_id='project-1') for i in range(8)])

def test_selection_reproducible_and_order_independent():
    x=inventory();r=freeze(x,set(),'fixed-seed',3)
    x['documents'].reverse();s=freeze(x,set(),'fixed-seed',3)
    assert r['selected']==s['selected'] and r['inventory_hash']==s['inventory_hash']
    assert len(r['all_inventory'])==8 and len(r['selected'])==3

def test_rejects_exposed_sources_and_label_driven_input():
    with pytest.raises(ValueError,match='exposed'):freeze(inventory(),{'new.example'},'seed',3)
    x=inventory();x['documents'][0]['suggested_label']='research'
    with pytest.raises(ValueError,match='labels'):freeze(x,set(),'seed',3)
    x=inventory();x['documents'].append(x['documents'][0])
    with pytest.raises(ValueError,match='Duplicate'):freeze(x,set(),'seed',3)


def test_local_inventory_rejects_exposed_content():
    x=inventory();x['documents']=[dict(path='D:/project/scan.pdf',sha256='a'*64,organization='Company',family_id='Project 9')]
    assert freeze(x,set(),'seed',1)['selected'][0]['path']=='D:/project/scan.pdf'
    with pytest.raises(ValueError,match='exposed'):freeze(x,set(),'seed',1,{'a'*64})


def test_local_inventory_keeps_mixed_extensions(tmp_path,monkeypatch):
    import json,runpy
    root=tmp_path/'project';root.mkdir()
    (root/'manual.pdf').write_bytes(b'not a real pdf')
    (root/'unknown.bin').write_bytes(bytes([0,255,1]))
    out=tmp_path/'inventory.json'
    monkeypatch.setattr('sys.argv',['inventory','--root',str(root),'--organization','A','--family-id','P1','--output',str(out)])
    runpy.run_module('cement.local_inventory',run_name='__main__')
    result=json.loads(out.read_text(encoding='utf-8'))
    assert {Path(r['path']).suffix for r in result['documents']}=={'.pdf','.bin'}
    assert not result['unreadable_or_untraversed']
