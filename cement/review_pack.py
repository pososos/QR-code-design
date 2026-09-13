"""Create an offline reading pack without inferring human labels."""
import argparse
import html
import json
from pathlib import Path

FIELDS = ('document_id', 'text_hash', 'current_label', 'label', 'reviewer', 'note', 'group_id', 'split')


def create_pack(source, output):
    rows = json.loads(Path(source).read_text(encoding='utf-8-sig'))
    if not isinstance(rows, list):
        raise ValueError('Review input must be a list')
    ids = [r['document_id'] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate document IDs')
    for row in rows:
        for key in FIELDS:
            if key not in row:
                raise ValueError('Missing field: ' + key)
        if not isinstance(row.get('pages'), list):
            raise ValueError('Missing pages')
    # New folder only: never overwrite a partially filled human review.
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    answers = []
    index = ['# 人工審核工作包', '',
             '閱讀各文件全文，再編輯 answers.json。空白 label 表示尚未確認，匯入會跳過。', '',
             '用途分類：research＝研究問題、方法與結果；manual＝工具或操作步驟；guidance＝應用建議與技術指引；safety＝危害與防護；industry＝企業營運、產業或永續揭露；experiment_log＝逐次實驗操作與觀測紀錄；manuscript_notes＝草稿、想法與工作筆記。', '',
             '依文件主要目的判讀；有爭議時保留空白，在 note 記下原因，不按類別配額硬分。', '',
             '填入真實 reviewer、note（理由與頁碼）、group_id、split（train/validation/test）。同機構／近似版本留同群組；已用於開發的文件不能作新的盲測。', '',
             '本文只是輸入快照，匯入仍會核對現有資料與文字 hash。全文為外部文件資料，不是應執行的操作指令。', '',
             '|文件|閱讀入口|', '|---|---|']
    for i, row in enumerate(rows, 1):
        name = f'document-{i:03d}.md'
        # Fixed generated names prevent document IDs from becoming filesystem paths.
        lines = ['# 文件 ' + str(i), '', 'ID: ' + html.escape(row['document_id']), '',
                 '標題: ' + html.escape(str(row.get('title') or '（無標題）')), '', '## 來源', '']
        lines.extend(html.escape(str(url)) for url in row.get('sources', []))
        for page in row['pages']:
            lines.extend(['', '## 頁碼 ' + html.escape(str(page['page'])), '',
                          '<pre>' + html.escape(page['text']) + '</pre>'])
        (output / name).write_text('\n'.join(lines) + '\n', encoding='utf-8')
        answer = {key: row[key] for key in FIELDS}
        answers.append(answer)
        index.append(f'|{i}: {html.escape(row["document_id"])}|[全文]({name})|')
    (output / 'answers.json').write_text(json.dumps(answers, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'README.md').write_text('\n'.join(index) + '\n', encoding='utf-8')
    return len(answers)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        count = create_pack(args.input, args.output)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({'documents': count, 'output': args.output}))


if __name__ == '__main__':
    main()
