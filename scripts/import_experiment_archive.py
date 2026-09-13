"""Import bounded TXT members by hash; keep archive provenance, never assign gold/splits."""
import hashlib,json,zipfile,argparse
from pathlib import Path
from urllib.parse import quote
from cement import store
parser=argparse.ArgumentParser()
parser.add_argument('--archive',default='data/experiment-archives/5d591ce98436caace74c1b8da270ce2874eb174364a37bebadaa355ae19cd3dd.zip')
parser.add_argument('--source-id',default='quota-hannover-fatigue-lab4')
parser.add_argument('--output',default='data/reports/experiment-members-20260913.json')
parser.add_argument('--max-member-mb',type=float,default=2)
args=parser.parse_args()
if not 0 < args.max_member_mb <= 10:parser.error('max-member-mb must be in (0,10]')
archive_path=Path(args.archive)
manifest=json.loads(archive_path.with_suffix(".json").read_text(encoding="utf-8"))
if hashlib.sha256(archive_path.read_bytes()).hexdigest()!=manifest["sha256"]:raise ValueError("Archive hash mismatch")
rows=[]
with zipfile.ZipFile(archive_path) as z:
    members=[x for x in z.infolist() if x.filename.endswith(".txt")]
    if len(members)>100 or sum(x.file_size for x in members)>25*1024*1024:raise ValueError("Archive import bound exceeded")
    if any(m.file_size>args.max_member_mb*1024*1024 for m in members):raise ValueError("Member too large")
    prepared=[(m,z.read(m)) for m in members]
    for member,body in prepared:body.decode("utf-8-sig")
    (store.ROOT/'raw').mkdir(parents=True,exist_ok=True)
    for member,body in prepared:
        digest=hashlib.sha256(body).hexdigest();dest=store.ROOT/"raw"/(digest+".txt")
        if not dest.exists():dest.write_bytes(body)
        url=manifest["url"]+"#member="+quote(member.filename,safe="")
        with store.connect() as db:
            db.execute("INSERT OR IGNORE INTO documents(id,path,kind) VALUES (?,?,?)",(digest,str(dest),"txt"))
            db.execute("INSERT OR IGNORE INTO sources(url,source_id,document_id,license,suggested_label) VALUES (?,?,?,?,?)",(url,args.source_id,digest,manifest["license"],"experiment_log"))
        rows.append(dict(document_id=digest,archive_sha256=manifest["sha256"],member=member.filename,
            document_family=manifest["document_family"],domain=manifest["domain"],language_hint="en"))
Path(args.output).write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
print(f"Imported {len(rows)} TXT records; same experiment family; no human labels or splits")
