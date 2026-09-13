"""Draft dataset inventory. Never turns pending weak labels into approved training data."""
import argparse
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from cement import store
from cement.review import schema, fingerprint, current_weak, rule_hash
from cement.weaklabel import load_rules


def build(rules):
    rows, excluded, blockers = [], [], []
    with store.connect() as db:
        schema(db)
        for doc in store.documents():
            if doc['status']!='parsed' or not doc['text_path']:
                excluded.append({'document_id':doc['id'],'reason':doc['status']})
                continue
            try:
                digest=fingerprint(doc)
            except OSError:
                excluded.append({'document_id':doc['id'],'reason':'missing_text'})
                continue
            member=db.execute('SELECT * FROM dataset_membership WHERE document_id=?',(doc['id'],)).fetchone()
            weak=current_weak(db,doc,digest,rule_hash(rules))
            if doc['label']:
                label,origin=doc['label'],'manual'
            elif weak:
                label,origin=weak['label'],'term_mapping'
            else:
                excluded.append({'document_id':doc['id'],'reason':'no_current_label'})
                continue
            group,split=(member['group_id'],member['split']) if member else (None,None)
            issues=[]
            if not member: issues.append('missing_membership')
            elif member['text_hash']!=digest: issues.append('stale_membership')
            if origin=='term_mapping':
                issues.append('pending_weak_audit')
                if split in ('validation','test'): issues.append('weak_evaluation_label_forbidden')
            rows.append({'document_id':doc['id'],'text_hash':digest,'label':label,'origin':origin,
                         'group_id':group,'split':split,'issues':issues,
                         'source_hosts':sorted({urlsplit(s['url']).hostname for s in doc['sources']})})
        # Check group and conservative exact source-host leakage; not full organization resolution.
        for field in ('group_id','source_hosts'):
            memberships={}
            for row in rows:
                if not row['split']: continue
                keys=row[field] if field=='source_hosts' else [row[field]]
                for key in keys:
                    memberships.setdefault(key,set()).add(row['split'])
            for key,splits in memberships.items():
                if len(splits)>1: blockers.append(f'{field} crosses splits: {key}')
    for row in rows:
        blockers.extend(f'{row["document_id"]}: {issue}' for issue in row['issues'])
    actual=Counter((r['split'],r['origin'],r['label']) for r in rows if not r['issues'])
    targets=[]
    for label in store.LABELS:
        for split,origin,target in [('train','manual',10),('train','term_mapping',40),('validation','manual',5),('test','manual',10)]:
            count=actual[(split,origin,label)]
            targets.append({'split':split,'origin':origin,'label':label,'target':target,'ready':count,'gap':max(0,target-count)})
    for split in ('train','validation','test'):
        labels={r['label'] for r in rows if r['split']==split and not r['issues']}
        if labels!=set(store.LABELS): blockers.append(f'{split}: missing ready classes {sorted(set(store.LABELS)-labels)}')
    manual=sum(r['origin']=='manual' and r['split']=='train' and not r['issues'] for r in rows)
    weak=sum(r['origin']=='term_mapping' and r['split']=='train' and not r['issues'] for r in rows)
    return {'schema_version':1,'rule_hash':rule_hash(rules),'draft_only':True,
            'training_ready':False,'blockers':blockers,
            'manual_train_fraction':manual/(manual+weak) if manual+weak else None,
            'targets':targets,'rows':rows,'excluded':excluded,
            'note':'No automatic split, weak cohort audit or mixed trainer yet; targets are planning quantities, not statistical guarantees.'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--rules',default='config/term_mapping.json')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    report=build(load_rules(args.rules))
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f: json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps({'eligible_or_candidate':len(report['rows']),'excluded':len(report['excluded']),
                      'training_ready':report['training_ready'],'blockers':len(report['blockers'])}))

if __name__=='__main__': main()
