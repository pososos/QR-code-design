"""Read-only semantic candidate experiment; never trains or changes human labels."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from cement import store
from cement.review import fingerprint, schema
from cement.weaklabel import classify, load_rules


def snapshot(limit=12):
    rows=[]
    with store.connect() as db:
        schema(db)
        for doc in sorted(store.documents(), key=lambda d:d['id']):
            if doc['status']!='parsed': continue
            pages=json.loads(Path(doc['text_path']).read_text(encoding='utf-8'))
            # Stable content-only prefix: no metadata title or labels in model input.
            selected=[]; remaining=1500
            for page in pages:
                if not page['text'].strip(): continue
                part=page['text'].strip()[:remaining]
                selected.append({'page':page['page'],'text':part})
                remaining-=len(part)
                if remaining<=0: break
            text='\n'.join(p['text'] for p in selected)
            if not text: continue
            digest=fingerprint(doc)
            member=db.execute('SELECT * FROM dataset_membership WHERE document_id=?',(doc['id'],)).fetchone()
            rows.append({'document_id':doc['id'],'text_hash':digest,'text':text,'pages':selected,
                         'human_label':doc['label'],'review_current':bool(member and member['text_hash']==digest),
                         'split':member['split'] if member else None,
                         'sources':[s['url'] for s in doc['sources']]})
            if len(rows)>=limit: break
    return rows


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--output',required=True)
    ap.add_argument('--model-dir', help='Optional local files with matching revision.txt')
    ap.add_argument('--method',choices=['embedding','reranker'],required=True)
    args=ap.parse_args()
    output=Path(args.output)
    if output.exists(): ap.error('Use a new output path')
    import torch
    import transformers
    from transformers import AutoTokenizer, AutoModel, AutoModelForSequenceClassification
    torch.set_num_threads(4)
    config=json.loads(Path('config/semantic-labels.json').read_text(encoding='utf-8'))
    labels=list(config['labels'])
    descriptions=[config['labels'][k]['zh']+' '+config['labels'][k]['en'] for k in labels]
    revisions=json.loads(Path('config/semantic-models.json').read_text())
    name='intfloat/multilingual-e5-small' if args.method=='embedding' else 'BAAI/bge-reranker-v2-m3'
    source=args.model_dir or name
    if args.model_dir and Path(args.model_dir,'revision.txt').read_text().strip()!=revisions[name]:
        ap.error('Local model revision mismatch')
    start=time.perf_counter()
    tokenizer=AutoTokenizer.from_pretrained(source,revision=revisions[name],cache_dir='data/model-cache',trust_remote_code=False)
    cls=AutoModel if args.method=='embedding' else AutoModelForSequenceClassification
    model=cls.from_pretrained(source,revision=revisions[name],cache_dir='data/model-cache',use_safetensors=True,trust_remote_code=False).eval()
    load_seconds=time.perf_counter()-start
    rows=snapshot()
    def encode(texts):
        inputs=tokenizer(['query: '+t for t in texts],padding=True,truncation=True,max_length=512,return_tensors='pt')
        hidden=model(**inputs).last_hidden_state
        mask=inputs['attention_mask'].unsqueeze(-1)
        pooled=(hidden*mask).sum(1)/mask.sum(1)
        return torch.nn.functional.normalize(pooled,p=2,dim=1)
    with torch.inference_mode():
        start=time.perf_counter()
        vectors=encode(descriptions) if args.method=='embedding' else None
        setup_seconds=time.perf_counter()-start
        for row in rows:
            start=time.perf_counter()
            if vectors is not None:
                values=(encode([row['text']])@vectors.T)[0].tolist()
                tokens=len(tokenizer('query: '+row['text'],verbose=False)['input_ids'])
            else:
                pairs=[[desc,row['text']] for desc in descriptions]
                inputs=tokenizer(pairs,padding=True,truncation='only_second',max_length=512,return_tensors='pt')
                values=model(**inputs).logits.reshape(-1).tolist()
                tokens=max(len(tokenizer(a,b,verbose=False)['input_ids']) for a,b in pairs)
            row['seconds']=time.perf_counter()-start
            row['tokens_before_truncation']=tokens
            row['truncated']=tokens>512
            row['scores']=dict(zip(labels,values))
            ranking=sorted(row['scores'],key=row['scores'].get,reverse=True)
            row['prediction']=ranking[0];row['margin']=row['scores'][ranking[0]]-row['scores'][ranking[1]]
            row['rule']=classify(row['pages'],load_rules('config/term_mapping.json'))['label']
            print(row['document_id'][:12],row['prediction'],round(row['seconds'],3),flush=True)
    from sklearn.metrics import classification_report
    eligible=[r for r in rows if r['human_label'] and r['review_current']]
    metrics=classification_report([r['human_label'] for r in eligible],[r['prediction'] for r in eligible],labels=labels,output_dict=True,zero_division=0) if eligible else None
    report={'method':args.method,'model':name,'revision':revisions[name],'device':'cpu','threads':4,
            'torch':torch.__version__,'transformers':transformers.__version__,
            'labels':config,'labels_hash':hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(),
            'load_download_seconds':load_seconds,'label_setup_seconds':setup_seconds,
            'policy':'first 1500 nonempty content characters; tokenizer max512; bilingual descriptions; no calibrated rejection threshold',
            'metrics_current_reviews_only':metrics,'evaluated_count':len(eligible),'rows':rows,
            'note':'Development diagnostic only, not independent evaluation or trained classifier. Scores are not probabilities; stale human reviews excluded from metrics.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print('saved',str(output),flush=True)

if __name__=='__main__':main()
