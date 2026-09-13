"""Export candidate extraction inputs; no automatic events or causal assertions."""
import argparse,hashlib,json
from pathlib import Path
from cement import store
from cement.review import fingerprint


def build():
    documents=[];evidence=[]
    for d in store.documents():
        if d['status']!='parsed':continue
        digest=fingerprint(d)
        version=d['id']+':'+digest
        documents.append({'id':version,'document_id':d['id'],'text_hash':digest,'purpose_label':d['label'],
                          'sources':[s['url'] for s in d['sources']], 'classification_is_extraction_gate':False})
        pages=json.loads(Path(d['text_path']).read_text(encoding='utf-8'))
        # Initial extraction scope only; consumers must not treat this as full-document coverage.
        remaining=1500
        for p in pages:
            if not p['text'].strip():continue
            start=len(p['text'])-len(p['text'].lstrip())
            quote=p['text'][start:start+remaining]
            key=f"{version}:{p['page']}:{start}:{start+len(quote)}"
            evidence.append({'id':hashlib.sha256(key.encode()).hexdigest(),'document_version_id':version,
                             'document_id':d['id'],'text_hash':digest,'page':p['page'],
                             'start_char':start,'end_char':start+len(quote),'quote':quote})
            remaining-=len(quote)
            if remaining<=0:break
    return {'schema_version':'cement-graph-v1-draft','scope':'first 1500 nonempty text characters per document; HTML page 1 is extraction block',
            'documents':documents,'evidence':evidence,'entities':[],'events':[],'conditions':[],
            'outcomes':[],'claims':[],'relations':[],'tags':[],
            'note':'Extraction input only. Empty events/relations are intentional; no knowledge assertions inferred.'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args()
    result=build();p=Path(a.output);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'documents':len(result['documents']),'evidence':len(result['evidence'])}))

if __name__=='__main__':main()
