"""Development readiness and blinded review selection; never assigns gold labels/splits."""
import argparse
import hashlib
import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from urllib.parse import urlsplit
from cement import store
from cement.review import fingerprint
from cement.parse import text_of


def inspect():
    rows=[]
    with store.connect() as db:
        for doc in store.documents():
            if doc['status']!='parsed' or not doc['text_path']:continue
            digest=fingerprint(doc)
            member=db.execute('SELECT * FROM dataset_membership WHERE document_id=?',(doc['id'],)).fetchone()
            rows.append({'document_id':doc['id'],'label':doc['label'],'text_hash':digest,
                         'current':bool(member and member['text_hash']==digest),
                         'group_id':member['group_id'] if member else None,
                         'split':member['split'] if member else None,
                         'hosts':sorted({urlsplit(s['url']).hostname or '' for s in doc['sources']}),
                         'language_hint':'zh' if sum('\u4e00'<=c<='\u9fff' for c in text_of(doc)[:1500])>30 else 'en_or_other'})
    counts=Counter((r['label'],r['language_hint']) for r in rows if r['label'] and r['current'])
    train=[r for r in rows if r['label'] and r['current'] and r['split']=='train']
    blockers=[]
    if not train: blockers.append('No current manually reviewed training membership; do not reuse validation as train')
    for key in ('group_id','hosts'):
        seen=defaultdict(set)
        for r in rows:
            if not r['current'] or not r['label']:continue
            for value in (r[key] if key=='hosts' else [r[key]]):
                if value:seen[value].add(r['split'])
        blockers.extend(f'{key} crosses splits: {v}' for v,splits in seen.items() if len(splits)>1)
    for split in ('train','validation','test'):
        present={r['label'] for r in rows if r['current'] and r['split']==split and r['label']}
        missing=sorted(set(store.LABELS)-present)
        if missing:blockers.append(f'{split} missing classes: {missing}')
    return {'development_only':True,'rows':rows,'blockers':blockers,
            'formal_training_ready':False,
            'label_language_counts':[{'label':k[0],'language_hint':k[1],'count':v} for k,v in sorted(counts.items())],
            'note':'Language heuristic only; group/host checks are not complete family or near-duplicate isolation. Manual and weak audits still required.'}


def review_batch(limit=21):
    buckets=defaultdict(list)
    for d in store.documents():
        if d['status']!='parsed' or d['label'] or not d['text_path']:continue
        # Source diversity, never purpose hints. This is a development review batch, not a blind test set.
        hosts=sorted({urlsplit(s['url']).hostname or '' for s in d['sources']})
        buckets[hosts[0] if hosts else 'unknown'].append(d)
    queues=[deque(sorted(docs,key=lambda d:d['id'])) for host,docs in sorted(buckets.items())]
    selected=[];seen_text=set()
    while queues and len(selected)<limit:
        next_queues=[]
        for q in queues:
            if len(selected)>=limit:break
            d=q.popleft(); digest=fingerprint(d)
            normalized=hashlib.sha256(' '.join(text_of(d).split()).encode()).hexdigest()
            if normalized not in seen_text:
                seen_text.add(normalized)
                selected.append({'document_id':d['id'],'text_hash':digest,'status':d['status'],
                                 'title':d['title'],'current_label':None,
                                 'pages':json.loads(Path(d['text_path']).read_text(encoding='utf-8')),
                                 'sources':[s['url'] for s in d['sources']],
                                 'label':'','reviewer':'','note':'','group_id':'','split':''})
            if q:next_queues.append(q)
        queues=next_queues
    return selected


def benchmark():
    from cement.inference import infer
    from sklearn.metrics import classification_report
    provenance=Path('models/evaluation.json')
    if not provenance.exists():raise ValueError('Missing model train/test provenance')
    original=json.loads(provenance.read_text(encoding='utf-8'))
    train_ids=set(original['train_ids']);test_ids=set(original['test_ids'])
    ready=inspect();by_id={d['id']:d for d in store.documents()};results=[];excluded=[]
    for row in ready['rows']:
        if not row['label']:continue
        reason=('training_exposure' if row['document_id'] in train_ids else
                'stale_or_missing_review' if not row['current'] else
                'not_in_original_holdout' if row['document_id'] not in test_ids else None)
        if reason:excluded.append({'document_id':row['document_id'],'reason':reason});continue
        predictions={}
        for method,rerank in [('classifier',False),('retrieval',False),('retrieval',True)]:
            key=method+('_rerank' if rerank else '')
            predictions[key]=infer(text_of(by_id[row['document_id']])[:12000],method,rerank)
        results.append(dict(row,predictions=predictions))
    metrics={}
    if results:
        for method in results[0]['predictions']:
            truth=[r['label'] for r in results];pred=[r['predictions'][method]['label'] or 'abstain' for r in results]
            metrics[method]={'count':len(results),'abstentions':pred.count('abstain'),
                             'report':classification_report(truth,pred,labels=list(store.LABELS),output_dict=True,zero_division=0)}
    return {'development_only':True,'independent_test':False,'metrics':metrics,'rows':results,'excluded':excluded,
            'note':'Reused developmental holdout with current reviews only. No new independent test; seven-label macro averages include unsupported classes. Not a generalization claim.'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--review-output');ap.add_argument('--limit',type=int,default=21);ap.add_argument('--benchmark',action='store_true');args=ap.parse_args()
    if not 1<=args.limit<=100:ap.error('limit must be 1–100')
    paths=[Path(p) for p in (args.output,args.review_output) if p]
    if any(p.exists() for p in paths):ap.error('Use new output paths')
    report=benchmark() if args.benchmark else inspect()
    for path,data in [(Path(args.output),report)]+([(Path(args.review_output),review_batch(args.limit))] if args.review_output else []):
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
    print(json.dumps({'blockers':report.get('blockers',[]),'review_output':args.review_output},ensure_ascii=False))

if __name__=='__main__':main()
