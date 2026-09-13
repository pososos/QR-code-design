"""On-demand local embeddings for semantic search; incremental cache keyed by text_hash.

Complements the FTS keyword index (cement/search.py), it does not replace it: exact keyword
hits stay in FTS, this is for near-miss vocabulary and paraphrase. The corpus here is a few
hundred documents, so caching one embedding per document is reasonable; this is not a strategy
for TB-scale eager vectorization (README_總體架構.md already warns against that). Uses the same
locally cached E5-small / bge-reranker-v2-m3 weights and pooling method already vetted in
cement/semantic_benchmark.py (D-005) — this module reuses that method for retrieval instead of
one-off benchmarking.
"""
import argparse
import json
from pathlib import Path
from cement import store
from cement.parse import text_of
from cement.review import fingerprint

EMBED_MODEL = 'intfloat/multilingual-e5-small'
RERANK_MODEL = 'BAAI/bge-reranker-v2-m3'
RERANK_LOCAL_DIR = 'data/reranker-fixed'
SAMPLE_CHARS = 1500
_state = {}


def schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS document_embeddings (
      document_id TEXT PRIMARY KEY, text_hash TEXT NOT NULL, model TEXT NOT NULL,
      revision TEXT NOT NULL, dim INTEGER NOT NULL, vector_json TEXT NOT NULL,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')


def _revisions():
    return json.loads(Path('config/semantic-models.json').read_text(encoding='utf-8'))


def _load_embed_model():
    if 'embed' not in _state:
        from transformers import AutoTokenizer, AutoModel
        revision = _revisions()[EMBED_MODEL]
        tokenizer = AutoTokenizer.from_pretrained(EMBED_MODEL, revision=revision, cache_dir='data/model-cache',
                                                   trust_remote_code=False)
        model = AutoModel.from_pretrained(EMBED_MODEL, revision=revision, cache_dir='data/model-cache',
                                           use_safetensors=True, trust_remote_code=False).eval()
        _state['embed'] = (tokenizer, model)
    return _state['embed']


def encode(texts):
    """Overridable seam for tests: monkeypatch this instead of loading the real model."""
    import torch
    tokenizer, model = _load_embed_model()
    torch.set_num_threads(4)
    inputs = tokenizer(['query: ' + t for t in texts], padding=True, truncation=True, max_length=512, return_tensors='pt')
    with torch.inference_mode():
        hidden = model(**inputs).last_hidden_state
        mask = inputs['attention_mask'].unsqueeze(-1)
        pooled = (hidden * mask).sum(1) / mask.sum(1)
        normed = torch.nn.functional.normalize(pooled, p=2, dim=1)
    return normed.tolist()


def reindex():
    """Only embeds documents whose text_hash changed or were never embedded under this model+revision."""
    revision = _revisions()[EMBED_MODEL]
    updated = 0
    with store.connect() as db:
        schema(db)
        pending = []
        for doc in store.documents():
            if doc['status'] != 'parsed' or not doc['text_path']:
                continue
            digest = fingerprint(doc)
            cached = db.execute('SELECT text_hash FROM document_embeddings WHERE document_id=? AND model=? AND revision=?',
                                 (doc['id'], EMBED_MODEL, revision)).fetchone()
            if cached and cached['text_hash'] == digest:
                continue
            pending.append((doc, digest))
        for doc, digest in pending:
            text = text_of(doc)[:SAMPLE_CHARS].strip()
            if not text:
                continue
            vector = encode([text])[0]
            db.execute('''INSERT INTO document_embeddings(document_id, text_hash, model, revision, dim, vector_json)
                       VALUES (?,?,?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET
                       text_hash=excluded.text_hash, model=excluded.model, revision=excluded.revision,
                       dim=excluded.dim, vector_json=excluded.vector_json, updated_at=CURRENT_TIMESTAMP''',
                       (doc['id'], digest, EMBED_MODEL, revision, len(vector), json.dumps(vector)))
            updated += 1
    return updated


def semantic_search(query, limit=10, rerank=False, rerank_pool=5):
    if not query or not query.strip():
        raise ValueError('Query required')
    with store.connect() as db:
        schema(db)
        rows = db.execute('SELECT document_id, vector_json FROM document_embeddings').fetchall()
    if not rows:
        return []
    qvec = encode([query])[0]
    scored = [(_dot(qvec, json.loads(r['vector_json'])), r['document_id']) for r in rows]
    scored.sort(key=lambda item: item[0], reverse=True)
    by_id = {d['id']: d for d in store.documents()}
    results = []
    for score, document_id in scored[:limit]:
        doc = by_id.get(document_id)
        if not doc:
            continue
        results.append({'document_id': document_id, 'score': score, 'label': doc['label'],
                         'status': doc['status'], 'title': doc['title']})
    if rerank and results:
        head = _rerank(query, results[:rerank_pool])
        results = head + results[rerank_pool:limit]
    return results


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _load_reranker():
    if 'rerank' not in _state:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        revision = _revisions()[RERANK_MODEL]
        local = Path(RERANK_LOCAL_DIR)
        source = str(local) if (local / 'revision.txt').exists() else RERANK_MODEL
        if source == str(local) and (local / 'revision.txt').read_text().strip() != revision:
            raise ValueError('Local reranker revision mismatch')
        tokenizer = AutoTokenizer.from_pretrained(source, revision=revision, cache_dir='data/model-cache',
                                                   trust_remote_code=False)
        model = AutoModelForSequenceClassification.from_pretrained(
            source, revision=revision, cache_dir='data/model-cache', use_safetensors=True,
            trust_remote_code=False).eval()
        _state['rerank'] = (tokenizer, model)
    return _state['rerank']


def _rerank(query, results):
    """Overridable seam for tests: monkeypatch this instead of loading the (much slower) reranker."""
    import torch
    tokenizer, model = _load_reranker()
    by_id = {d['id']: d for d in store.documents()}
    pairs = []
    for r in results:
        doc = by_id.get(r['document_id'])
        text = text_of(doc)[:SAMPLE_CHARS] if doc else ''
        pairs.append([query, text])
    inputs = tokenizer(pairs, padding=True, truncation='only_second', max_length=512, return_tensors='pt')
    with torch.inference_mode():
        logits = model(**inputs).logits.reshape(-1).tolist()
    for r, score in zip(results, logits):
        r['rerank_score'] = score
    return sorted(results, key=lambda r: r['rerank_score'], reverse=True)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('reindex')
    q = sub.add_parser('query')
    q.add_argument('query')
    q.add_argument('--limit', type=int, default=10)
    q.add_argument('--rerank', action='store_true')
    args = parser.parse_args()
    if args.command == 'reindex':
        print(json.dumps({'updated': reindex()}))
    else:
        print(json.dumps(semantic_search(args.query, args.limit, args.rerank), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
