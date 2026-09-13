"""Discover six verified resource pages, save bounded archives and provenance."""
import hashlib,json,io,zipfile,subprocess,sys
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from cement.crawl import Crawler
resources={1:"fc1b647b-5b6a-4d21-9c10-4c645a465575",2:"2eda63f2-389d-4cc9-a63d-c2b1e654e2da",3:"95b65673-9ac8-4e5f-b7eb-f30aad971ab7",5:"7dac8876-4ba7-4585-a31b-ed148baef039",6:"f281312a-f4cb-4141-992d-730af1ba976f",7:"e311fe27-9dc2-4f0b-ac7d-52011c2787dd"}
c=Crawler();root=Path("data/experiment-archives");results=[]
for lab,rid in resources.items():
    page="https://data.uni-hannover.de/dataset/spp-2020-experimental-fatigue-data-on-high-strength-and-ultra-high-strength-concrete/resource/"+rid
    try:
        body,_,final=c.fetch(page,["data.uni-hannover.de"],{})
        soup=BeautifulSoup(body,"html.parser")
        links=[urljoin(final,a["href"]) for a in soup.select("a[href]") if "/download/" in a["href"] and a["href"].lower().endswith(".zip")]
        if not links:raise ValueError("No ZIP download found")
        url=links[0];body,_,final=c.fetch(url,["data.uni-hannover.de"],{})
        with zipfile.ZipFile(io.BytesIO(body)) as z:entries=[dict(name=x.filename,size=x.file_size) for x in z.infolist()]
        digest=hashlib.sha256(body).hexdigest();path=root/(digest+".zip")
        if not path.exists():path.write_bytes(body)
        manifest=dict(url=url,final_url=final,sha256=digest,path=str(path),domain="cement_concrete",language_hint="en",suggested_label="experiment_log",document_family="SPP2020-fatigue-HPC-UHPC",license="Open Data Commons Open Database License v1.0 (repository metadata)",entries=entries,status="archive_downloaded_not_parsed")
        path.with_suffix(".json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        proc=subprocess.run([sys.executable,"-m","scripts.import_experiment_archive","--archive",str(path),"--source-id",f"quota-hannover-fatigue-lab{lab}","--output",f"data/reports/experiment-lab{lab}-20260913.json"])
        results.append(dict(lab=lab,path=str(path),import_exit_code=proc.returncode))
    except Exception as exc:results.append(dict(lab=lab,error=str(exc)))
    print(results[-1],flush=True)
Path("data/reports/fatigue-labs-20260913.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
