import json
import argparse
from pathlib import Path
from bs4 import BeautifulSoup
from pypdf import PdfReader
from cement import store

def extract_html(raw, urls=()):
    from urllib.parse import urlsplit
    soup = BeautifulSoup(raw, 'html.parser')
    title = soup.title.get_text(' ', strip=True) if soup.title else ''
    hosts = {urlsplit(u).hostname for u in urls}
    selectors = []
    if 'www.abri.gov.tw' in hosts:
        selectors = ['#CCMS_Content', '.page-footer']
    elif 'www.wra.gov.tw' in hosts:
        selectors = ['#CCMS_Content']
    elif 'www.nist.gov' in hosts:
        selectors = ['#block-nist-www-content']
    roots = [soup.select_one(sel) for sel in selectors]
    if selectors and any(root is None for root in roots):
        raise ValueError('Expected HTML content region missing; inspect source template')
    for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'form']):
        if not any(root is tag or tag in root.parents for root in roots):
            tag.decompose()
    roots = roots or [soup.find('main') or soup.find('article') or soup]
    text = '\n'.join(root.get_text('\n', strip=True) for root in roots)
    return title, [{'page': 1, 'text': text}]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--retry', action='store_true', help='Reparse all cached documents')
    parser.add_argument('--document-id', help='Only parse this document; combine with --retry for existing results')
    args = parser.parse_args()
    for doc in store.documents():
        if args.document_id and doc['id'] != args.document_id: continue
        if doc['status'] == 'out_of_scope': continue
        if doc['status'] != 'downloaded' and not args.retry: continue
        try:
            if doc['kind'] == 'pdf':
                reader = PdfReader(doc['path'])
                pages = [{'page': i + 1, 'text': page.extract_text() or ''} for i, page in enumerate(reader.pages)]
                title = str((reader.metadata or {}).get('/Title') or '')
            elif doc['kind'] == 'txt':
                text = Path(doc['path']).read_text(encoding='utf-8-sig')
                title = next((line.strip() for line in text.splitlines() if line.strip()), '')
                pages = [{'page': 1, 'text': text}]
            else:
                title, pages = extract_html(Path(doc['path']).read_bytes(), [s['url'] for s in doc['sources']])
            folder = store.ROOT / 'text'
            folder.mkdir(exist_ok=True)
            dest = folder / f'{doc["id"]}.json'
            dest.write_text(json.dumps(pages, ensure_ascii=False), encoding='utf-8')
            combined = '\n'.join(p['text'] for p in pages)
            status = 'parsed' if len(combined.strip()) >= 40 else 'needs_ocr'
            if any(marker in combined.lower() for marker in ('incapsula incident id', 'verify you are human')):
                status = 'blocked_content'
            elif any(sum(ord(c) < 32 and c not in '\n\r\t' for c in p['text']) / max(1, len(p['text'])) > .005 for p in pages):
                status = 'needs_review'
            with store.connect() as db:
                db.execute('UPDATE documents SET title=?,text_path=?,status=? WHERE id=?', (title, str(dest), status, doc['id']))
            print(doc['id'][:12], status)
        except Exception as exc:
            with store.connect() as db:
                db.execute("UPDATE documents SET status='parse_error' WHERE id=?", (doc['id'],))
            store.event(doc['id'], 'parse_error', str(exc))

def text_of(doc):
    if not doc['text_path']: return ''
    return '\n'.join(p['text'] for p in json.loads(Path(doc['text_path']).read_text(encoding='utf-8')))

def sample(text, limit=18000):
    if len(text) <= limit: return text
    size = limit // 3
    middle = len(text) // 2
    return text[:size] + '\n' + text[middle:middle+size] + '\n' + text[-size:]

if __name__ == '__main__': main()
