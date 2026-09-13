import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(os.environ.get('CEMENT_DATA', 'data'))
LABELS = ('research', 'manual', 'guidance', 'safety', 'industry', 'experiment_log', 'manuscript_notes')

def connect():
    ROOT.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(ROOT / 'catalog.sqlite', timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript('''
    CREATE TABLE IF NOT EXISTS documents (
      id TEXT PRIMARY KEY, path TEXT NOT NULL, kind TEXT NOT NULL,
      title TEXT, text_path TEXT, status TEXT NOT NULL DEFAULT 'downloaded',
      label TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS sources (
      url TEXT PRIMARY KEY, source_id TEXT, document_id TEXT,
      etag TEXT, modified TEXT, license TEXT, suggested_label TEXT,
      checked_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY, url TEXT, status TEXT, detail TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')
    return db

def event(url, status, detail=''):
    with connect() as db:
        db.execute('INSERT INTO events(url,status,detail) VALUES (?,?,?)', (url, status, detail))

def documents():
    subtype_path = Path(__file__).resolve().parent.parent / 'config' / 'source-subtypes.json'
    subtypes = json.loads(subtype_path.read_text(encoding='utf-8')) if subtype_path.exists() else {}
    with connect() as db:
        rows = db.execute('SELECT * FROM documents ORDER BY created_at DESC').fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['sources'] = [dict(s) for s in db.execute('SELECT * FROM sources WHERE document_id=?', (row['id'],))]
            item['source_metadata'] = [dict(source_id=s['source_id'], **subtypes[s['source_id']]) for s in item['sources'] if s['source_id'] in subtypes] if item['kind'] != 'html' else []
            result.append(item)
        return result
