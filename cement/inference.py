"""Bounded model inference without catalog writes or uploaded executable artifacts."""
import hashlib
import json
import time
from pathlib import Path
import joblib
from cement.parse import sample
from cement.staged_classification import stages, top
from cement import vector_search

ROOT = Path(__file__).resolve().parent.parent

def infer(text, method='retrieval', use_reranker=False):
    if not text.strip() or len(text)>12000:
        raise ValueError('Provide 1–12000 characters')
    started=time.perf_counter()
    trace=[]
    if method=='classifier':
        path=ROOT/'models/classifier.joblib'
        if not path.exists(): raise FileNotFoundError('Self-trained artifact has not been installed')
        model=joblib.load(path)
        scores=dict(zip(map(str,model.classes_),map(float,model.predict_proba([sample(text)])[0])))
        label=max(scores,key=scores.get)
        return dict(label=label,scores=scores,method=method,review_required=True,
                    model_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
                    seconds=time.perf_counter()-started,note='Small-sample developmental classifier; uncalibrated scores')
    if method!='retrieval': raise ValueError('Unknown method')
    config=json.loads((ROOT/'config/semantic-labels.json').read_text(encoding='utf-8'))
    labels=list(config['labels']); descs=[' '.join(config['labels'][k].values()) for k in labels]
    vectors=vector_search.encode(descs)
    label=None; scores={}
    # Fixed developmental settings; never claimed calibrated or selected on independent data.
    for stage in stages([{'page':1,'text':text}], 'txt'):
        vector=vector_search.encode([stage['text']])[0]
        scores={k:vector_search._dot(vector,v) for k,v in zip(labels,vectors)}
        candidate,score,gap=top(scores)
        trace.append({'stage':stage['stage'],'method':'retrieval','scores':scores,'characters':len(stage['text'])})
        if score>=.8 and gap>=.02:
            label=candidate;break
        if stage['stage']=='body' and use_reranker:
            import torch
            tokenizer,model=vector_search._load_reranker()
            inputs=tokenizer([[d,stage['text']] for d in descs],padding=True,truncation='only_second',max_length=512,return_tensors='pt')
            with torch.inference_mode(): values=model(**inputs).logits.reshape(-1).tolist()
            scores=dict(zip(labels,values));candidate,score,gap=top(scores)
            trace.append({'stage':'body','method':'reranker','scores':scores,'characters':len(stage['text'])})
            if score>=0 and gap>=1: label=candidate
    return dict(label=label,scores=scores,method=method,trace=trace,review_required=True,
                seconds=time.perf_counter()-started,labels_version=config['version'],
                model_revisions=vector_search._revisions(),
                thresholds={'retrieval_min':.8,'retrieval_margin':.02,'rerank_min':0,'rerank_margin':1},
                note='Developmental thresholds, not calibrated; only supplied excerpt is inspected; no OCR')
