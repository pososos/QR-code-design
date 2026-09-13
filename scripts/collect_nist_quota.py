"""Bounded official NIST author catalog discovery; title-filtered candidates."""
import json,re
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from cement.crawl import Crawler
c=Crawler()
sources={}
for page in range(10):
    url=f"https://www.nist.gov/publications/search_by_author/1147021?page={page}"
    try:
        body,_,final=c.fetch(url,["www.nist.gov"],{})
    except Exception as exc:
        print(f"Discovery stopped: {exc}",flush=True)
        break
    for a in BeautifulSoup(body,"html.parser").select("h3 a[href]"):
        title=a.get_text(" ",strip=True)
        if not re.search(r"cement|concrete|mortar|user manual|user guide",title,re.I): continue
        link=urljoin(final,a["href"])
        sources[link]=dict(id=f"quota-nist-{len(sources):03}",url=link,
            allowed_hosts=["www.nist.gov","tsapps.nist.gov","nvlpubs.nist.gov"],
            max_depth=1,link_pattern=r"(?i)\.pdf|get_pdf\.cfm",
            suggested_label="manual" if re.search(r"user manual|user guide",title,re.I) else "research",
            language_hint="en",discovery_text=title,discovery_url=url,
            document_family=link,license="Public access; verify publication rights")
configs=list(sources.values())[:85]
Path("config/sources-quota-nist-20260913.json").write_text(json.dumps(configs,ensure_ascii=False,indent=2),encoding="utf-8")
print(f"Discovered {len(configs)} candidates",flush=True)
for source in configs:c.run(source,max_files=2)
