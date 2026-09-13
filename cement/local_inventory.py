"""Inventory a user-selected project snapshot without purpose/extension filters."""
import argparse,hashlib,json,os
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--organization',required=True);p.add_argument('--family-id',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    root=Path(a.root).resolve();out=Path(a.output).resolve()
    if not root.is_dir():p.error('root must be an existing directory')
    if out.is_relative_to(root):p.error('output must be outside the source snapshot')
    rows=[];failures=[]
    def walk_error(exc):failures.append(dict(path=exc.filename,error=str(exc)))
    for folder,dirs,files in os.walk(root,followlinks=False,onerror=walk_error):
        for name in list(dirs):
            item=Path(folder)/name
            if item.is_symlink() or item.is_junction():
                dirs.remove(name);failures.append(dict(path=str(item),error='linked directory not traversed'))
        for name in sorted(files):
            path=Path(folder)/name
            try:
                if path.is_symlink():raise ValueError('linked file not followed')
                before=path.stat();h=hashlib.sha256()
                with path.open('rb') as f:
                    for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
                after=path.stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('file changed during hashing')
                rows.append(dict(path=str(path.resolve()),sha256=h.hexdigest(),organization=a.organization,family_id=a.family_id))
            except (OSError,ValueError) as exc:failures.append(dict(path=str(path),error=str(exc)))
    payload=dict(selection_basis='fixed_scope_no_purpose_filter',scope_description='All files under user-selected snapshot '+str(root),documents=rows,unreadable_or_untraversed=failures)
    with out.open('x',encoding='utf-8') as f:json.dump(payload,f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(inventoried=len(rows),unreadable_or_untraversed=len(failures))))

if __name__=='__main__':main()
