"""Bounded, allowlisted crawler; no JavaScript or login bypass."""
import argparse
import hashlib
import json
import re
import time
from collections import deque
from urllib.parse import urljoin, urlsplit, urldefrag
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from cement import store

AGENT = 'CementKnowledgeDemo/0.1'

def allowed(url, hosts):
    p = urlsplit(url)
    return p.scheme == 'https' and p.hostname in hosts and not p.username and p.port in (None, 443)

class Crawler:
    def __init__(self, delay=2, max_mb=25):
        self.session = requests.Session()
        self.session.headers['User-Agent'] = AGENT
        self.delay, self.limit = delay, int(max_mb * 1024 * 1024)
        self.robots, self.last = {}, {}
        self.rate_limited = set()

    def wait(self, url):
        host = urlsplit(url).netloc
        pause = max(self.delay, self.robots.get(host, (None, 0))[1])
        time.sleep(max(0, pause - (time.monotonic() - self.last.get(host, 0))))
        self.last[host] = time.monotonic()

    def permitted(self, url):
        p = urlsplit(url)
        if p.netloc not in self.robots:
            self.wait(url)
            r = self.session.get(f'https://{p.netloc}/robots.txt', timeout=(10, 30), allow_redirects=False)
            parser = RobotFileParser()
            if r.status_code == 404:
                parser.parse([])
            elif r.status_code == 200:
                parser.parse(r.text.splitlines())
            else:
                raise RuntimeError(f'robots unavailable: HTTP {r.status_code}')
            self.robots[p.netloc] = (parser, parser.crawl_delay(AGENT) or parser.crawl_delay('*') or 0)
        return self.robots[p.netloc][0].can_fetch(AGENT, url)

    def fetch(self, url, hosts, headers):
        for _ in range(6):
            if not allowed(url, hosts):
                raise ValueError('URL outside configured HTTPS hosts')
            if urlsplit(url).netloc in self.rate_limited:
                raise RuntimeError('Host paused after HTTP 429 for this crawler session')
            if not self.permitted(url):
                raise PermissionError('robots.txt disallows URL')
            self.wait(url)
            r = self.session.get(url, headers=headers, stream=True, timeout=(10, 60), allow_redirects=False)
            if r.status_code == 429:
                self.rate_limited.add(urlsplit(url).netloc)
                retry_after = r.headers.get('Retry-After', 'unspecified')
                r.close()
                raise RuntimeError(f'HTTP 429; host paused for this session; Retry-After={retry_after}')
            if r.status_code in (301, 302, 303, 307, 308):
                next_url = urljoin(url, r.headers['Location'])
                r.close()
                url, headers = next_url, {}
                continue
            if r.status_code == 304:
                r.close()
                return None, r.headers.copy(), url
            try:
                r.raise_for_status()
                body = bytearray()
                for chunk in r.iter_content(65536):
                    body.extend(chunk)
                    if len(body) > self.limit:
                        raise ValueError('download size limit exceeded')
                return bytes(body), r.headers.copy(), url
            finally:
                r.close()
        raise ValueError('too many redirects')

    def run(self, config, max_files=10):
        queue = deque([(config['url'], 0)])
        seen = set()
        while queue and len(seen) < max_files:
            url, depth = queue.popleft()
            url = urldefrag(url)[0]
            if url in seen or not allowed(url, config['allowed_hosts']):
                continue
            seen.add(url)
            try:
                with store.connect() as db:
                    old = db.execute('SELECT * FROM sources WHERE url=?', (url,)).fetchone()
                headers = {}
                # Discovery pages must be fetched to rediscover their links.
                if old and depth >= config.get('max_depth', 0):
                    if old['etag']: headers['If-None-Match'] = old['etag']
                    if old['modified']: headers['If-Modified-Since'] = old['modified']
                body, response, final = self.fetch(url, config['allowed_hosts'], headers)
                if body is None:
                    store.event(url, 'unchanged', 'HTTP 304')
                    continue
                is_pdf = body.startswith(b'%PDF-')
                is_html = 'text/html' in response.get('Content-Type', '')
                if not is_pdf and not is_html:
                    raise ValueError('unsupported content type or invalid PDF')
                if is_html and any(marker in body.lower() for marker in (b'incapsula incident id', b'cf-chl-', b'verify you are human')):
                    raise ValueError('access challenge page; not a document')
                kind = 'pdf' if is_pdf else 'html'
                digest = hashlib.sha256(body).hexdigest()
                folder = store.ROOT / 'raw'
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f'{digest}.{kind}'
                if not path.exists():
                    temp = path.with_suffix('.part')
                    temp.write_bytes(body)
                    temp.replace(path)
                with store.connect() as db:
                    db.execute('INSERT OR IGNORE INTO documents(id,path,kind) VALUES (?,?,?)', (digest, str(path), kind))
                    db.execute('''INSERT INTO sources(url,source_id,document_id,etag,modified,license,suggested_label)
                    VALUES (?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET
                    document_id=excluded.document_id,etag=excluded.etag,modified=excluded.modified,checked_at=CURRENT_TIMESTAMP''',
                    (url, config['id'], digest, response.get('ETag'), response.get('Last-Modified'), config.get('license'), config.get('suggested_label')))
                store.event(url, 'saved', digest)
                if is_html and depth < config.get('max_depth', 0):
                    soup = BeautifulSoup(body, 'html.parser')
                    for a in soup.select('a[href]'):
                        link = urljoin(final, a['href'])
                        if re.search(config.get('link_pattern', r'(?i)\.pdf'), link + ' ' + a.get_text()):
                            queue.append((link, depth + 1))
                print(f'saved {config["id"]}: {url}', flush=True)
            except (requests.RequestException, ValueError, RuntimeError, PermissionError) as exc:
                store.event(url, 'error', str(exc))
                print(f'skipped {url}: {exc}', flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', default='sources.json')
    p.add_argument('--source')
    p.add_argument('--max-files', type=int, default=10, help='Request cap per source, including discovery pages')
    p.add_argument('--delay', type=float, default=2)
    p.add_argument('--max-mb', type=float, default=25)
    args = p.parse_args()
    configs = json.loads(open(args.config, encoding='utf-8').read())
    selected = [s for s in configs if not args.source or s['id'] == args.source]
    if not selected: p.error('unknown source')
    crawler = Crawler(max(1, args.delay), args.max_mb)
    for source in selected: crawler.run(source, args.max_files)

if __name__ == '__main__': main()
