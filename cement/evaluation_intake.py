"""Freeze a purpose-blind intake from a previously enumerated collection. No downloads or labels."""
import argparse,hashlib,json
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit
from cement import store

def freeze(inventory, existing_hosts, seed, limit, existing_hashes=()):
    if limit<1:raise ValueError('limit must be positive')
    if inventory.get('selection_basis')!='fixed_scope_no_purpose_filter':
        raise ValueError('Declare fixed collection scope without purpose filtering')
    if not inventory.get('scope_description'):raise ValueError('scope_description required')
    records=inventory.get('documents',[])
    if not records:raise ValueError('Empty inventory')
    seen=set();clean=[]
    for row in records:
        if set(row)-{'url','path','sha256','organization','family_id'}:raise ValueError('No labels/scores/titles allowed for selection')
        if any(not isinstance(row.get(k),str) or not row[k].strip() for k in ('organization','family_id')):raise ValueError('Organization and family_id required')
        if bool(row.get('url')) == bool(row.get('path')):raise ValueError('Provide exactly one URL or local path')
        if row.get('url'):
            u=urlsplit(row['url'])
            if u.scheme!='https' or not u.hostname or u.username or u.fragment or u.port not in (None,443):raise ValueError('HTTPS document URL required')
            if u.hostname in existing_hosts:raise ValueError('Source host already exposed in development: '+u.hostname)
        else:
            if not (Path(row['path']).is_absolute() or PureWindowsPath(row['path']).is_absolute()):raise ValueError('Absolute local path required')
            digest=row.get('sha256','')
            if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('Local content SHA256 required')
            if digest in existing_hashes:raise ValueError('Content already exposed in development')
        locator=row.get('url') or row['path']
        if locator in seen:raise ValueError('Duplicate locator in inventory')
        seen.add(locator);clean.append(dict(row))
    clean.sort(key=lambda x:x.get('url') or x['path'])
    inventory_hash=hashlib.sha256(json.dumps(clean,sort_keys=True).encode()).hexdigest()
    selected=sorted(clean,key=lambda x:hashlib.sha256((seed+'\0'+(x.get('url') or x['path'])).encode()).digest())[:limit]
    return dict(schema_version=1,scope_description=inventory['scope_description'],seed=seed,
        inventory_hash=inventory_hash,inventory_size=len(clean),selected=selected,
        all_inventory=clean,unreadable_or_untraversed=inventory.get('unreadable_or_untraversed',[]),selection_basis=inventory['selection_basis'],
        split='unassigned_evaluation_candidate',human_labels_present=False,
        limitations=['Fixed scope is a submitter declaration, not independently verified.',
        'Novel host does not guarantee novel organization or document family; verify before blind evaluation.',
        'This is intake selection, not a validated representative test set. Preserve failed downloads/OCR as outcomes.'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--inventory',required=True);p.add_argument('--output',required=True)
    p.add_argument('--seed',required=True);p.add_argument('--limit',type=int,default=50);a=p.parse_args()
    docs=store.documents()
    hosts={urlsplit(s['url']).hostname for d in docs for s in d['sources']}
    report=freeze(json.loads(Path(a.inventory).read_text(encoding='utf-8')),hosts,a.seed,a.limit,{d['id'] for d in docs})
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print('Frozen evaluation candidates:',len(report['selected']))

if __name__=='__main__':main()
