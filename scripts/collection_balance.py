"""Read-only seven-class candidate/approved balance; hints are not truth."""
import argparse,json
from pathlib import Path
from collections import Counter,defaultdict
from urllib.parse import urlsplit
from cement import store
from cement.dataset import build
from cement.weaklabel import load_rules
p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
counts=Counter();hosts=defaultdict(set);ambiguous=[]
for d in store.documents():
    if d['status']!='parsed':continue
    hints={s['suggested_label'] for s in d['sources'] if s['suggested_label'] in store.LABELS}
    label=d['label'] or (next(iter(hints)) if len(hints)==1 else None)
    if label is None:ambiguous.append(d['id']);continue
    counts[(label,'all')]+=1
    if d['kind'] in ('pdf','txt'):counts[(label,'file')]+=1
    for s in d['sources']:hosts[label].add(urlsplit(s['url']).hostname)
r=build(load_rules('config/term_mapping.json'))
rows=[]
for label in store.LABELS:
    targets=[x for x in r['targets'] if x['label']==label]
    ready=sum(x['ready'] for x in targets)
    rows.append(dict(label=label,target=65,parsed_candidate_files=counts[(label,'file')],parsed_candidates_including_html=counts[(label,'all')],source_hosts=len(hosts[label]),approved_ready=ready,remaining=sum(x['gap'] for x in targets)))
report=dict(note='Source hints plus existing human labels; candidate counts are NOT verified purpose or independent families. approved_ready follows frozen dataset membership and current text hashes.',rows=rows,ambiguous=ambiguous,training_ready=r['training_ready'])
with Path(args.output).open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps(rows,ensure_ascii=False))
