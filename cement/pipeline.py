"""Checkpointed local ingestion workflow; no training or human-label mutations."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from cement import store


def save(path,state):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)


def plan(limit=25,semantic=False):
    docs=sorted((d for d in store.documents() if d['status'] in ('downloaded','parse_error')),key=lambda d:d['id'])[:limit]
    steps=[{'id':'parse-'+d['id'],'args':['-m','cement.parse','--document-id',d['id'],'--retry'],
            'document_id':d['id']} for d in docs]
    steps += [{'id':'keyword-index','args':['-m','cement.search','reindex']},
              {'id':'weak-candidates','args':['-m','cement.weaklabel']},
              {'id':'graph-candidates','args':['-m','cement.graph_extract','extract']}]
    if semantic:steps.append({'id':'semantic-index','args':['-m','cement.vector_search','reindex']})
    return {'version':1,'data_root':str(store.ROOT.resolve()),'steps':[dict(s,status='pending',attempts=0) for s in steps],
            'created_at':time.time(),'note':'Snapshot of pending parse IDs. No crawl, OCR, training, gold labels or split changes. Start a new run for new files.'}


def execute(folder,state,runner=subprocess.run):
    path=folder/'state.json'
    for step in state['steps']:
        if step['status']=='done':continue
        if step['attempts']>=2:raise RuntimeError('Attempt cap reached: '+step['id'])
        if 'document_id' in step:
            d=next((d for d in store.documents() if d['id']==step['document_id']),None)
            if not d or d['status'] not in ('downloaded','parse_error'):
                step.update(status='done',outcome='already processed or excluded');save(path,state);continue
        step.update(status='running',attempts=step['attempts']+1);save(path,state)
        try:
            with (folder/(step['id']+'.log')).open('a',encoding='utf-8') as log:
                result=runner([sys.executable,'-X','utf8',*step['args']],stdout=log,stderr=subprocess.STDOUT,
                              timeout=600,env={**os.environ,'CEMENT_DATA':state['data_root']})
            if result.returncode:raise RuntimeError('Nonzero exit: '+str(result.returncode))
            if 'document_id' in step:
                d=next(d for d in store.documents() if d['id']==step['document_id'])
                if d['status']=='parse_error':raise RuntimeError('Parser reported parse_error')
                step['outcome']=d['status']
            step['status']='done';step.pop('error',None)
        except Exception as exc:
            step.update(status='failed',error=str(exc));save(path,state);raise
        save(path,state)
    return state


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run-dir',required=True);ap.add_argument('--resume',action='store_true');ap.add_argument('--semantic',action='store_true');ap.add_argument('--limit',type=int,default=25);args=ap.parse_args()
    if not 1<=args.limit<=100:ap.error('limit must be 1–100')
    folder=Path(args.run_dir);folder.mkdir(parents=True,exist_ok=True);path=folder/'state.json'
    if path.exists()!=args.resume:ap.error('Existing run requires --resume; new run must not use --resume')
    # A global lock prevents two run folders mutating the catalog concurrently.
    lock=store.ROOT/'pipeline.lock';store.ROOT.mkdir(parents=True,exist_ok=True)
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:ap.error('Pipeline locked. Verify no worker exists before removing a crash-left lock.')
    os.close(fd)
    try:
        state=json.loads(path.read_text(encoding='utf-8')) if args.resume else plan(args.limit,args.semantic)
        if state['data_root']!=str(store.ROOT.resolve()):ap.error('Data root mismatch')
        save(path,state);execute(folder,state)
        print(json.dumps({'done':sum(s['status']=='done' for s in state['steps']),'run_dir':str(folder)}))
    finally:lock.unlink(missing_ok=True)

if __name__=='__main__':main()
