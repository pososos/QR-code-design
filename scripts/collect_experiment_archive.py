"""Download one bounded original experiment archive; no extraction or sample inflation."""
import hashlib,json,io,zipfile
from pathlib import Path
from cement.crawl import Crawler
url="https://data.uni-hannover.de/dataset/07a67c75-b8bd-476c-ae1b-e01455c7872d/resource/92025f97-d2bb-44f0-9edb-a3e7ea735180/download/hpc-lab.-4.zip"
root=Path("data/experiment-archives");root.mkdir(exist_ok=True)
body,headers,final=Crawler().fetch(url,["data.uni-hannover.de"],{})
with zipfile.ZipFile(io.BytesIO(body)) as archive:
    entries=[dict(name=x.filename,size=x.file_size,compressed_size=x.compress_size) for x in archive.infolist()]
digest=hashlib.sha256(body).hexdigest();path=root/(digest+".zip")
if not path.exists():path.write_bytes(body)
manifest=dict(url=url,final_url=final,sha256=digest,path=str(path),domain="cement_concrete",language_hint="en",
    suggested_label="experiment_log",document_family="SPP2020-fatigue-HPC-UHPC",
    license="Open Data Commons Open Database License v1.0 (repository metadata)",
    status="archive_downloaded_not_parsed",entries=entries,
    note="One laboratory archive, not one independent sample per row or file. No extraction or training import.")
(root/(digest+".json")).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(manifest,ensure_ascii=False))
