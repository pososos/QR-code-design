"""Cement purpose-classification demo for a Hugging Face Space (ZeroGPU).

Self-contained port of cement/inference.py's staged retrieval (+ optional
rerank) logic, so this Space does not need the rest of the local repo — no
SQLite catalog, no crawler, no review/upload endpoints, no local file access.
Same fixed developmental thresholds, model ids and revisions as the local
experiment (D-005/staged_classification.py); this is not a calibrated or
independently validated classifier. Source: https://github.com/pososos/QR-code-design
"""
import re
import time
import gradio as gr
import spaces
import torch
from transformers import AutoTokenizer, AutoModel, AutoModelForSequenceClassification

EMBED_MODEL = 'intfloat/multilingual-e5-small'
EMBED_REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
RERANK_MODEL = 'BAAI/bge-reranker-v2-m3'
RERANK_REVISION = '953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e'

# Same bilingual class descriptions as config/semantic-labels.json (purpose-bilingual-v3-course-notes).
LABELS = {
    'research': 'Research paper or report presenting a research question, methods, experiments or models, results and scientific conclusions. 研究論文或研究報告：提出研究問題、方法、實驗或模型，分析結果並形成研究結論。',
    'manual': 'User manual explaining installation, configuration, operating steps and how to use a tool or software. 操作手冊：說明工具或軟體的安裝、設定、操作步驟及功能使用方法。',
    'guidance': 'Engineering guidance or construction specification providing recommendations or requirements for material selection, mixtures, construction and quality inspection. 工程應用指引或施工規範：提供材料選用、配比、施工、品質檢驗的建議或要求。',
    'safety': 'Safety data sheet describing product composition, hazard identification, first aid, exposure controls and safe handling. 安全資料表：說明產品成分、危害辨識、急救措施、暴露防護及安全處置。',
    'industry': 'Corporate annual, sustainability or industry report disclosing operations, financial results, revenue, emissions and sustainability performance. 企業年報、永續報告或產業報告：揭露營運、財務、營收、排放與永續績效。',
    'experiment_log': 'Experiment log or laboratory record documenting run dates, specimen identifiers, operating conditions, measurements, raw observations and anomalies. 實驗記錄：逐次記載試驗日期、試體編號、操作條件、量測數值、原始觀察與異常的紀錄表或實驗日誌。',
    'manuscript_notes': 'Draft manuscripts, working notes, classroom notes, course handouts or lecture slides, typed or handwritten, recording ideas or teaching material. Track subtypes separately; exclude formal research reports and equipment operating manuals. 手稿筆記：草稿、工作筆記、課堂筆記、講義或課堂投影片；可打字或手寫。以記錄想法或教學整理為主，子類分開標記。正式研究報告與設備操作手冊不屬此類。',
}
LABEL_NAMES = list(LABELS)

_state = {}


def _load_embed_model():
    if 'embed' not in _state:
        tokenizer = AutoTokenizer.from_pretrained(EMBED_MODEL, revision=EMBED_REVISION)
        model = AutoModel.from_pretrained(EMBED_MODEL, revision=EMBED_REVISION, use_safetensors=True).eval()
        _state['embed'] = (tokenizer, model)
    return _state['embed']


def _load_reranker():
    if 'rerank' not in _state:
        tokenizer = AutoTokenizer.from_pretrained(RERANK_MODEL, revision=RERANK_REVISION)
        model = AutoModelForSequenceClassification.from_pretrained(
            RERANK_MODEL, revision=RERANK_REVISION, use_safetensors=True).eval()
        _state['rerank'] = (tokenizer, model)
    return _state['rerank']


def encode(texts):
    tokenizer, model = _load_embed_model()
    inputs = tokenizer(['query: ' + t for t in texts], padding=True, truncation=True, max_length=512, return_tensors='pt')
    with torch.inference_mode():
        hidden = model(**inputs).last_hidden_state
        mask = inputs['attention_mask'].unsqueeze(-1)
        pooled = (hidden * mask).sum(1) / mask.sum(1)
        normed = torch.nn.functional.normalize(pooled, p=2, dim=1)
    return normed.tolist()


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def stages(pages, kind):
    """Verbatim port of cement/staged_classification.py:stages — title -> contents -> body extraction."""
    readable = [p for p in pages if p['text'].strip()]
    if not readable:
        return []
    first = readable[0]
    lines = [x.strip() for x in first['text'].splitlines() if x.strip()]
    if kind == 'html':
        lines = [x for x in lines if x.upper() != 'PUBLICATIONS']
        title = '\n'.join(lines[:1])[:500]
    else:
        clean = []
        for line in lines:
            if re.search(r'^(section\s*1|introduction|abstract|fhwa publication|fhwa contact|company details|材料與|一、)', line, re.I):
                break
            if re.search(r'^(sds no|page \d|for more information|or visit|http|www\.|nist special publication|february \d|\d+$)', line, re.I):
                continue
            clean.append(line)
            if re.search(r'user guide|user manual', line, re.I):
                break
            if len(clean) >= 8:
                break
        title = '\n'.join(clean)[:500]
        for i, line in enumerate(lines[:30]):
            if re.search(r'(annual|sustainability) report|年報|永續報告', line, re.I):
                start = i - 1 if i and re.fullmatch(r'Annual and', lines[i - 1], re.I) else i
                title = '\n'.join(lines[start:i + 1])[:500]
                break
    toc, toc_pages = [], []
    for p in readable[:10]:
        ls = [x.strip() for x in p['text'].splitlines() if x.strip()]
        entries = [x for x in ls if re.search(r'\.{3,}|…{2,}', x)]
        if re.search(r'(?im)^\s*(table of contents|contents|目錄)\s*$', p['text']):
            entries = ls
        if len(entries) >= 3:
            toc.extend(entries)
            toc_pages.append(p['page'])
    body_parts, body_pages, remaining = [], [], 1500
    for page in readable:
        part = page['text'][:remaining]
        body_parts.append(part)
        body_pages.append(page['page'])
        remaining -= len(part)
        if remaining <= 0:
            break
    body = '\n'.join(body_parts)
    if lines and len(lines[0]) > 160:
        title = ''
    candidates = [
        ('title', title, [first['page']], 'heuristic title candidate; inspect before trusting'),
        ('contents', '\n'.join(toc)[:1500], toc_pages, 'detected contents lines within first ten nonempty pages'),
        ('body', body, body_pages, 'first 1500 body characters; may repeat title'),
    ]
    return [{'stage': name, 'text': text, 'source_pages': ids, 'extraction_note': note}
            for name, text, ids, note in candidates if text.strip()]


def top(scores):
    order = sorted(scores, key=scores.get, reverse=True)
    return order[0], scores[order[0]], scores[order[0]] - scores[order[1]]


@spaces.GPU(duration=30)
def classify(text, use_reranker):
    if not text or not text.strip():
        raise gr.Error('請輸入 1–12000 字元的文字 / Provide 1-12000 characters')
    text = text[:12000]
    started = time.perf_counter()
    descs = [LABELS[k] for k in LABEL_NAMES]
    vectors = encode(descs)
    label, scores, trace = None, {}, []
    for stage in stages([{'page': 1, 'text': text}], 'txt'):
        vector = encode([stage['text']])[0]
        scores = {k: _dot(vector, v) for k, v in zip(LABEL_NAMES, vectors)}
        candidate, score, gap = top(scores)
        trace.append(f"{stage['stage']}:embedding score={score:.3f} gap={gap:.3f}")
        if score >= .8 and gap >= .02:
            label = candidate
            break
        if stage['stage'] == 'body' and use_reranker:
            tokenizer, model = _load_reranker()
            inputs = tokenizer([[d, stage['text']] for d in descs], padding=True,
                                truncation='only_second', max_length=512, return_tensors='pt')
            with torch.inference_mode():
                values = model(**inputs).logits.reshape(-1).tolist()
            scores = dict(zip(LABEL_NAMES, values))
            candidate, score, gap = top(scores)
            trace.append(f"body:reranker score={score:.3f} gap={gap:.3f}")
            if score >= 0 and gap >= 1:
                label = candidate
    elapsed = time.perf_counter() - started
    verdict = label or '（棄權 abstain：證據不足 insufficient evidence）'
    scores_text = '\n'.join(f'{k}: {v:.4f}' for k, v in sorted(scores.items(), key=lambda kv: -kv[1]))
    trace_text = '\n'.join(trace)
    note = (f'耗時 {elapsed:.2f} 秒。開發用固定門檻（0.8/0.02，重排 0/1），未校準、未獨立驗證；'
            f'只檢視你貼上的片段，沒有 OCR，不會存檔。 / {elapsed:.2f}s. Fixed developmental thresholds, '
            f'not calibrated or independently validated; only the supplied excerpt is inspected, no OCR, nothing is stored.')
    return verdict, scores_text, trace_text, note


with gr.Blocks(title='水泥文件用途分類 Demo') as demo:
    gr.Markdown(
        '# 水泥文件用途分類（真實模型示範）\n'
        '多語言 E5 檢索（標題→目錄→內容分階段判斷）＋可選 BGE 內容重排；固定開發用門檻，未經校準或獨立驗證，僅供技術展示。\n\n'
        '原始碼／完整專案：https://github.com/pososos/QR-code-design'
    )
    text_in = gr.Textbox(label='輸入文字（最多 12,000 字元） / Input text (max 12,000 chars)', lines=8,
                          placeholder='貼上文件標題／目錄／正文片段…')
    use_reranker = gr.Checkbox(label='內容階段啟用重排（BGE reranker，較慢） / Enable rerank on body stage (slower)', value=False)
    btn = gr.Button('分類 Classify', variant='primary')
    label_out = gr.Textbox(label='候選分類 Prediction')
    scores_out = gr.Textbox(label='各類分數 Scores', lines=8)
    trace_out = gr.Textbox(label='階段追蹤 Trace', lines=4)
    note_out = gr.Textbox(label='備註 Note', lines=2)
    btn.click(classify, inputs=[text_in, use_reranker],
              outputs=[label_out, scores_out, trace_out, note_out], api_name='predict')

if __name__ == '__main__':
    demo.launch()
