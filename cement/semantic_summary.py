"""Produce a readable paired development diagnostic from two completed runs."""
import argparse,json,statistics
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--embedding',required=True);ap.add_argument('--reranker',required=True);ap.add_argument('--output',required=True)
    a=ap.parse_args();e=json.loads(Path(a.embedding).read_text(encoding='utf-8'));r=json.loads(Path(a.reranker).read_text(encoding='utf-8'))
    pairs={x['document_id']:x for x in r['rows']}
    lines=['# 多語言語意分類實測','', 'CPU、4 threads；相同前段 1,500 字、雙語類別描述，各模型 tokenizer 上限 512 tokens。分數未校準，沒有自動放行門檻。','',
           '|文件 ID|人工用途|文字審核有效|Embedding|Reranker|規則（相同片段）|','|---|---|---|---|---|---|']
    for x in e['rows']:
        y=pairs[x['document_id']]
        if x['text_hash']!=y['text_hash'] or x['text']!=y['text'] or e['labels_hash']!=r['labels_hash']:
            raise ValueError('Runs have different text/label versions')
        lines.append(f"|{x['document_id'][:12]}|{x['human_label']}|{x['review_current']}|{x['prediction']}|{y['prediction']}|{x['rule'] or '棄權'}|")
    lines+=['','## 有效審核版本的描述性比較','']
    for name,run in [('Embedding',e),('Reranker',r)]:
        eligible=[x for x in run['rows'] if x['human_label'] and x['review_current']]
        correct=sum(x['prediction']==x['human_label'] for x in eligible)
        lines.append(f"- {name}：與人工一致 {correct}/{len(eligible)}；每份推論中位數 {statistics.median(x['seconds'] for x in run['rows']):.3f} 秒；load/download {run['load_download_seconds']:.1f} 秒。")
    lines+=['','人工既有標籤原樣列出；文字已更新但未重新確認者不計入指標。這批曾用於開發觀察，不是獨立測試。五類 Macro-F1 包含可能無有效真值的類別，勿作完整五類成效結論。少量一次 CPU 計時包含批次／快取差異，不是吞吐基準；未量測峰值記憶體。', '', '不修改人工標籤，不訓練模型，不把候選當真值。下載時間、初始化與分類推論分開看；本機 reranker 檔案下載時間未計入其 load_seconds。']
    with Path(a.output).open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')

if __name__=='__main__':main()
