"""Read-only sampling audit; source hints are not ground truth."""
import argparse,json,hashlib,re
from pathlib import Path
from collections import Counter,defaultdict
from urllib.parse import urlsplit
from cement import store
p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
docs=store.documents();host_docs=defaultdict(set);host_labels=defaultdict(Counter);texts=defaultdict(list);families=defaultdict(set)
for d in docs:
    hosts={urlsplit(s['url']).hostname for s in d['sources']}
    hints={s['suggested_label'] for s in d['sources'] if s['suggested_label'] in store.LABELS}
    label=d['label'] or (next(iter(hints)) if len(hints)==1 else 'ambiguous')
    for host in hosts:host_docs[host].add(d['id']);host_labels[host][label]+=1
    for meta in d.get('source_metadata',[]):families[meta['document_family']].add(d['id'])
    if any(s['source_id'].startswith('quota-hannover-fatigue') for s in d['sources']):families['SPP2020-fatigue-HPC-UHPC'].add(d['id'])
    if d['text_path']:
        pages=json.loads(Path(d['text_path']).read_text(encoding='utf-8'))
        norm=re.sub(r'\s+',' ', '\n'.join(x['text'] for x in pages)).strip()
        if norm:texts[hashlib.sha256(norm.encode()).hexdigest()].append(d['id'])
report=dict(total_documents=len(docs),status=dict(Counter(d['status'] for d in docs)),
  source_concentration=[dict(host=h,documents=len(ids),share=round(len(ids)/len(docs),4),purpose_hints=dict(host_labels[h]),dominant_hint_share=round(max(host_labels[h].values())/len(ids),4)) for h,ids in sorted(host_docs.items(),key=lambda x:-len(x[1]))],
  known_families={k:sorted(v) for k,v in families.items()},normalized_text_duplicate_groups=[v for v in texts.values() if len(v)>1],
  limitations=['Purpose hints are circular: this audit does not measure classifier accuracy.','Hosts are not organizations; family inventory is incomplete.','Whitespace-normalized exact text only; near duplicates and templates are not detected.','All existing documents were collected or inspected during development; none declared a new blind test.'])
with Path(args.output).open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in report.items() if k not in ['known_families','normalized_text_duplicate_groups']},ensure_ascii=False))
