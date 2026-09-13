"""Discover concrete-only rows from the official FHWA catalog; bounded crawl."""
import json, re
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from cement.crawl import Crawler
c = Crawler()
url = "https://www.fhwa.dot.gov/pavement/pub_listing.cfm?sort=default&areas=Design"
body, _, final = c.fetch(url, ["www.fhwa.dot.gov"], {})
sources = {}
for row in BeautifulSoup(body, "html.parser").select("tr"):
    title = row.get_text(" ", strip=True)
    if not re.search(r"concrete|cement", title, re.I):
        continue
    for a in row.select("a[href]"):
        link = urljoin(final, a["href"])
        if ".pdf" not in link.lower():
            continue
        sources[link] = dict(id=f"quota-fhwa-{len(sources):03}", url=link,
            allowed_hosts=["www.fhwa.dot.gov"], max_depth=0,
            suggested_label="guidance", language_hint="en", discovery_url=url,
            discovery_text=title, license="Public access; verify individual document rights")
configs = list(sources.values())[:90]
Path("config/sources-quota-fhwa-20260912.json").write_text(json.dumps(configs, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Discovered {len(configs)} PDF candidates", flush=True)
for source in configs:
    c.run(source, max_files=1)
