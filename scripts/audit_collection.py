"""Read-only candidate inventory. Counts are NOT approved training samples."""
import json,argparse
from pathlib import Path
from collections import Counter
from cement import store
p=argparse.ArgumentParser();p.add_argument("--output",required=True);args=p.parse_args()
configs={}
for path in Path("config").glob("sources-quota-*.json"):
    for row in json.loads(path.read_text(encoding="utf-8")):configs[row["id"]]=row
rows=[]
for d in store.documents():
    sources=[s for s in d["sources"] if s["source_id"] in configs]
    if not sources:continue
    cfg=configs[sources[0]["source_id"]]
    issues=[]
    if d["status"]!="parsed":issues.append(d["status"])
    if d["kind"]=="html":issues.append("landing_or_abstract_requires_scope_review")
    pages=json.loads(Path(d["text_path"]).read_text(encoding="utf-8")) if d["text_path"] else []
    coverage=sum(len(x["text"].strip())>=80 for x in pages)/max(1,len(pages))
    if pages and coverage<.5:issues.append("low_text_coverage")
    if cfg.get("document_family"):issues.append("family_grouping_required")
    rows.append(dict(document_id=d["id"],status=d["status"],kind=d["kind"],
      title=d["title"],suggested_label=cfg.get("suggested_label"),
      language_hint=cfg.get("language_hint"),domain=cfg.get("domain","cement_concrete"),
      document_family=cfg.get("document_family"),sources=sources,text_page_coverage=round(coverage,3),
      issues=issues,human_label=d["label"]))
report=dict(note="Candidate source hints only; not gold, not quota completion. HTML/full text and version families require deduplication.",
  total_raw=len(rows),status=dict(Counter(r["status"] for r in rows)),
  parsed_pdf_candidates=dict(Counter(r["suggested_label"] for r in rows if r["status"]=="parsed" and r["kind"]=="pdf")),rows=rows)
with Path(args.output).open("x",encoding="utf-8") as f:json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in report.items() if k!="rows"},ensure_ascii=False))
