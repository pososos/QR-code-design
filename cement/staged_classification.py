"""Title -> contents -> body diagnostic and embedding-to-reranker threshold replay."""
import argparse,hashlib,itertools,json,re,time
from pathlib import Path
from cement import store
from cement.semantic_benchmark import snapshot


def stages(pages,kind):
    readable=[p for p in pages if p['text'].strip()]
    if not readable:return []
    first=readable[0]
    lines=[x.strip() for x in first['text'].splitlines() if x.strip()]
    if kind=='html':
        lines=[x for x in lines if x.upper()!='PUBLICATIONS']
        title='\n'.join(lines[:1])[:500]
    else:
        clean=[]
        for line in lines:
            if re.search(r'^(section\s*1|introduction|abstract|fhwa publication|fhwa contact|company details|材料與|一、)',line,re.I):break
            if re.search(r'^(sds no|page \d|for more information|or visit|http|www\.|nist special publication|february \d|\d+$)',line,re.I):continue
            clean.append(line)
            if re.search(r'user guide|user manual',line,re.I):break
            if len(clean)>=8:break
        title='\n'.join(clean)[:500]
        # Covers may put navigation before the report title. Preserve a detected report-title line.
        for i,line in enumerate(lines[:30]):
            if re.search(r'(annual|sustainability) report|年報|永續報告',line,re.I):
                start=i-1 if i and re.fullmatch(r'Annual and',lines[i-1],re.I) else i
                title='\n'.join(lines[start:i+1])[:500]
                break
    toc=[];toc_pages=[]
    for p in readable[:10]:
        ls=[x.strip() for x in p['text'].splitlines() if x.strip()]
        entries=[x for x in ls if re.search(r'\.{3,}|…{2,}',x)]
        if re.search(r'(?im)^\s*(table of contents|contents|目錄)\s*$',p['text']):
            entries=ls
        if len(entries)>=3:
            toc.extend(entries);toc_pages.append(p['page'])
    body_parts=[];body_pages=[];remaining=1500
    for page in readable:
        part=page['text'][:remaining];body_parts.append(part);body_pages.append(page['page']);remaining-=len(part)
        if remaining<=0:break
    body='\n'.join(body_parts)
    # A long paragraph is not a reliable title candidate. Missing title is allowed.
    if lines and len(lines[0])>160:title=''
    candidates=[('title',title,[first['page']], 'heuristic title candidate; inspect before trusting'),
                ('contents','\n'.join(toc)[:1500],toc_pages,'detected contents lines within first ten nonempty pages'),
                ('body',body,body_pages,'first 1500 body characters; may repeat title')]
    return [{'stage':name,'text':text,'source_pages':ids,'extraction_note':note} for name,text,ids,note in candidates if text.strip()]


def top(scores):
    order=sorted(scores,key=scores.get,reverse=True)
    return order[0],scores[order[0]],scores[order[0]]-scores[order[1]]


def route(row,threshold,margin,rerank_min,rerank_margin):
    cost=0.;calls=0;trace=[]
    for stage in row['stages']:
        label,score,gap=top(stage['embedding']['scores']);cost+=stage['embedding']['seconds']
        trace.append(stage['stage']+':embedding')
        if score>=threshold and gap>=margin:
            return {'prediction':label,'stage':stage['stage'],'method':'embedding','seconds_estimate':cost,'reranker_calls':calls,'trace':trace}
        if stage['stage']!='body':
            continue
        label,score,gap=top(stage['reranker']['scores']);cost+=stage['reranker']['seconds'];calls+=1
        trace.append(stage['stage']+':reranker')
        if score>=rerank_min and gap>=rerank_margin:
            return {'prediction':label,'stage':stage['stage'],'method':'reranker','seconds_estimate':cost,'reranker_calls':calls,'trace':trace}
    return {'prediction':None,'stage':None,'method':'abstain','seconds_estimate':cost,'reranker_calls':calls,'trace':trace}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--scores-input');ap.add_argument('--reuse-scores');args=ap.parse_args()
    out=Path(args.output)
    if out.exists():ap.error('Use new output directory')
    out.mkdir(parents=True)
    config=json.loads(Path('config/semantic-labels.json').read_text(encoding='utf-8'))
    revisions=json.loads(Path('config/semantic-models.json').read_text())
    labels=list(config['labels']);descs=[' '.join(config['labels'][k].values()) for k in labels]
    cached={}
    if args.reuse_scores:
        old=json.loads(Path(args.reuse_scores).read_text(encoding='utf-8'))
        if old['revisions']!=revisions or old['labels']!=config:raise ValueError('Cached model/label mismatch')
        for row in old['rows']:
            for stage in row['stages']:
                for method in ('embedding','reranker'):
                    if method in stage:cached[(method,stage['text'])]=stage[method]
    if args.scores_input:
        report=json.loads(Path(args.scores_input).read_text(encoding='utf-8'));rows=report['rows']
    else:
        import torch
        from transformers import AutoTokenizer,AutoModel,AutoModelForSequenceClassification
        torch.set_num_threads(4)
        docs={d['id']:d for d in store.documents()};rows=snapshot()
        for row in rows:
            d=docs[row['document_id']];pages=json.loads(Path(d['text_path']).read_text(encoding='utf-8'))
            row['stages']=stages(pages,d['kind'])
        report={'rows':rows,'revisions':revisions,'labels':config,'policy':'v2 title then contents embedding; reranker only on body; CPU4; max512 tokens; paired full five classes','note':'All stages precomputed for threshold replay; simulated routed cost, not measured end-to-end deployment latency.'}
        for method,name in [('embedding','intfloat/multilingual-e5-small'),('reranker','BAAI/bge-reranker-v2-m3')]:
            source=name if method=='embedding' else 'data/reranker-fixed'
            if method=='reranker' and Path(source,'revision.txt').read_text().strip()!=revisions[name]:raise ValueError('Revision mismatch')
            kwargs={'revision':revisions[name],'cache_dir':'data/model-cache','local_files_only':True,'trust_remote_code':False}
            tok=AutoTokenizer.from_pretrained(source,**kwargs)
            cls=AutoModel if method=='embedding' else AutoModelForSequenceClassification
            model=cls.from_pretrained(source,use_safetensors=True,**kwargs).eval()
            def encode(texts):
                inputs=tok(['query: '+t for t in texts],padding=True,truncation=True,max_length=512,return_tensors='pt')
                hidden=model(**inputs).last_hidden_state;mask=inputs['attention_mask'].unsqueeze(-1)
                return torch.nn.functional.normalize((hidden*mask).sum(1)/mask.sum(1),p=2,dim=1)
            with torch.inference_mode():
                vectors=encode(descs) if method=='embedding' else None
                for row in rows:
                    for stage in row['stages']:
                        if method=='reranker' and stage['stage']!='body':continue
                        if (method,stage['text']) in cached:
                            stage[method]={**cached[(method,stage['text'])], 'reused':True}
                            continue
                        start=time.perf_counter()
                        if vectors is not None:
                            scores=(encode([stage['text']])@vectors.T)[0].tolist()
                            n=len(tok('query: '+stage['text'],verbose=False)['input_ids'])
                        else:
                            pairs=[[d,stage['text']] for d in descs]
                            inputs=tok(pairs,padding=True,truncation='only_second',max_length=512,return_tensors='pt')
                            scores=model(**inputs).logits.flatten().tolist()
                            n=max(len(tok(a,b,verbose=False)['input_ids']) for a,b in pairs)
                        stage[method]={'scores':dict(zip(labels,scores)),'seconds':time.perf_counter()-start,'tokens_before_truncation':n,'truncated':n>512}
                    print(method,row['document_id'][:12],flush=True)
            del model
            import gc;gc.collect()
        (out/'scores.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    grid=[]
    for t,m,rt,rm in itertools.product([0.75,0.80,0.85,0.90],[0.0,0.02,0.05,0.10],[0.0,2.0],[0.0,1.0,2.0]):
        decisions=[route(r,t,m,rt,rm) for r in rows]
        pairs=[(r,d) for r,d in zip(rows,decisions) if r['human_label'] and r['review_current']]
        accepted=sum(d['prediction'] is not None for r,d in pairs)
        correct=sum(d['prediction']==r['human_label'] for r,d in pairs)
        grid.append({'embedding_min':t,'embedding_margin':m,'reranker_logit_min':rt,'reranker_margin':rm,
                     'evaluated':len(pairs),'accepted':accepted,'correct':correct,'wrong':accepted-correct,
                     'abstained':len(pairs)-accepted,'accepted_accuracy':correct/accepted if accepted else None,
                     'reranker_calls_all_docs':sum(d['reranker_calls'] for d in decisions),
                     'seconds_estimate_all_docs':sum(d['seconds_estimate'] for d in decisions),
                     'decisions':decisions})
    (out/'thresholds.json').write_text(json.dumps(grid,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 標題 → 目錄 → 內容：門檻開發實驗','', '標題與目錄只用 embedding；不過則下一階段。內容 embedding 不過才 reranker，仍不過最後棄權。標題為自動擷取候選，不使用人工答案。缺目錄直接略過。所有階段已預計算，下表時間是路由推估，不是部署實測。','', '|E5 最低／差距|Reranker logit／差距|一致／有效人工|誤判|棄權|Reranker 次數（全文件）|路由估秒（全文件）|','|---|---|---|---|---|---|---|']
    best=sorted(grid,key=lambda g:(-g['correct'],g['wrong'],g['seconds_estimate_all_docs']))[:12]
    for g in best:
        lines.append(f"|{g['embedding_min']}/{g['embedding_margin']}|{g['reranker_logit_min']}/{g['reranker_margin']}|{g['correct']}/{g['evaluated']}|{g['wrong']}|{g['abstained']}|{g['reranker_calls_all_docs']}|{g['seconds_estimate_all_docs']:.2f}|")
    lines+=['','這些是同批調參結果，不是獨立驗證，也不自動設定正式門檻。分數非校準機率，閾值未由研究指定。全量 96 組與各文件路徑見 thresholds.json。過期文字審核不計入。']
    (out/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('complete',str(out),flush=True)

if __name__=='__main__':main()
