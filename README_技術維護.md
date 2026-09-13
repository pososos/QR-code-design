# README_技術維護 — 檔案檢索 WIKI

更新日期：2026-09-11。設計見 [總體架構](README_總體架構.md)，接續需求見 [AGENTS.md](AGENTS.md)，歷史實測見 [VALIDATION.md](VALIDATION.md)。以下描述現行程式，不表示已完成所有產品規劃。

## 快速檢索

| 要做的事 | 先看檔案／入口 | 注意事項 |
|---|---|---|
| 新增公開來源 | [sources.json](sources.json)、[crawl.py](cement/crawl.py) | 核對實際內容、網域、robots、授權 |
| 改限速／大小／連結發現 | [crawl.py](cement/crawl.py) | Crawler.wait、fetch、run、main |
| 查重／資料表／清冊 | [store.py](cement/store.py) | connect、event、documents |
| 修 PDF／HTML 解析 | [parse.py](cement/parse.py) | main；保留頁碼，重解析用 --retry |
| 改文字取樣 | [parse.py](cement/parse.py) | sample 同時被訓練、預覽、預測使用 |
| 改用途類別 | [store.py](cement/store.py)、[api.py](cement/api.py)、[index.html](cement/static/index.html) | LABELS、Label Literal、前端 labels 目前分開定義，須同步 |
| 改模型／評估切分 | [train.py](cement/train.py) | Pipeline、holdout-sources、evaluation.json |
| 改 API | [api.py](cement/api.py) | FastAPI；線上 /docs |
| 改管理頁／QR 顯示 | [index.html](cement/static/index.html)、[api.py](cement/api.py) | 前端為單一 HTML 與原生 JS |
| 執行回歸測試 | [test_pipeline.py](tests/test_pipeline.py) | 暫存示例，不是真實模型評估 |
| 重現套件 | [requirements.lock.txt](requirements.lock.txt) | requirements.txt 為版本範圍 |
| 查歷史異常 | [VALIDATION.md](VALIDATION.md)、data/catalog.sqlite | events 表與 /api/events |

## 目錄 WIKI

```text
D:/QR code design/
  AGENTS.md                    工作入口、需求、決策與交接
  README.md                    文件導覽
  README_總體架構.md            設計概念
  README_技術維護.md            維護索引
  VALIDATION.md                實測快照
  sources.json                 公開來源設定
  requirements.txt             依賴版本範圍
  requirements.lock.txt        已安裝版本清單
  .gitignore                   排除環境、資料與模型
  cement/
    __init__.py                Python 套件入口
    store.py                   SQLite 清冊
    crawl.py                   爬蟲 CLI
    parse.py                   解析 CLI／文字取樣
    train.py                   訓練 CLI
    api.py                     FastAPI
    search.py                  關鍵字索引、處理政策、文件關係
    graph_extract.py           規則式因果詞候選抽取與審核
    static/index.html          管理頁（含關鍵字搜尋）
    static/graph.html          圖譜候選審核頁
  tests/test_pipeline.py       整合與功能測試
  tests/test_search_index.py   搜尋、政策、關係測試
  tests/test_graph_extract.py  圖譜候選抽取與審核測試
  data/                        執行產物，不進 Git
    raw/<sha256>.pdf|html       去重後原文
    text/<sha256>.json          [{page: 1, text: ...}, ...]
    catalog.sqlite             清冊與事件
    parse-warnings.log         曾手動導出的解析警告
  models/                      真實模型訓練後才產生
    classifier.joblib
    evaluation.json
  .venv/                       本機 Python 環境
```

## 環境與啟動

在專案根目錄執行 PowerShell 命令。程式目前多處以工作目錄解析相對路徑，不從其他位置啟動。

```powershell
Set-Location -LiteralPath 'D:\QR code design'
.venv/Scripts/python.exe -m uvicorn cement.api:app --host 127.0.0.1 --port 8000
```

本機頁面：http://127.0.0.1:8000/；API 文件：http://127.0.0.1:8000/docs 。Ctrl+C 停止服務。改 Python 後需重啟；HTML 在重新載入頁面時重新讀取。不要假設前一對話啟動的程序仍在。

新環境建立方式（需要可用 Python）：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
```

本機系統 python/py 曾不存在；已用下列 runtime 建立 .venv：

```powershell
& 'C:/Users/annyj/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m venv .venv
```

此 runtime 路徑是本機歷史記錄，換機或更新後先核對。一般開發可安裝 requirements.txt；正式重現用 lock 清單。requirements.lock.txt 是 pip freeze，沒有套件雜湊鎖定。

CEMENT_DATA 可改資料根目錄，需在程序啟動前設定；models/ 和 sources.json 不隨此變數搬移。現有資料表存有 path/text_path，搬移舊資料必須一併核對路徑，不能只改環境變數。

## 爬蟲操作

```powershell
.venv/Scripts/python.exe -m cement.crawl --source fhwa-scm --max-files 1
.venv/Scripts/python.exe -m cement.crawl --max-files 3
.venv/Scripts/python.exe -m cement.crawl --source tcc-2022 --max-files 1 --max-mb 50
.venv/Scripts/python.exe -m cement.parse
```

| CLI 參數 | 預設 | 意義 |
|---|---|---|
| --config | sources.json | JSON 設定清單 |
| --source | 全部來源 | 只執行指定 id；未知 id 報錯 |
| --max-files | 10 | 每來源的唯一排程 URL 上限，包含入口／失敗 URL；不是成功文件數，也不包含 robots 與 redirect 額外 HTTP 次數 |
| --delay | 2 | 每站間隔秒數；CLI 最低 1 秒，並尊重較長 crawl-delay |
| --max-mb | 25 | 單次文件內容上限，單位 MiB |

設定欄位：

| 欄位 | 用途 |
|---|---|
| id | 來源識別；亦為訓練 holdout 分組鍵，不是自動的機構群組 |
| url | 起始 HTTPS 網址 |
| allowed_hosts | 完整主機名稱清單；redirect 也受限制 |
| max_depth | 0 只取入口，1 可追入口連結一層 |
| link_pattern | 連結網址＋文字的正規表示式；預設匹配 .pdf |
| suggested_label | 建議用途，非訓練真值 |
| license | 人工記錄權利資訊，不自動判定再散布資格 |

新增來源：先確認公開網址與內容，再設定主機及深度；用 --source 與小上限抓取，查看 events、預覽文字與身分，最後人工標註。不要將成功 HTTP 回應直接視為成功資料。

robots 200 解析規則、404 視為無規則，其餘狀態或讀取失敗停止該 URL；不追 robots redirect。PDF 以 %PDF- 開頭判斷，HTML 檢查 Content-Type。爬蟲只下載 PDF/HTML，無 JS 渲染、登入、OCR 或通用檔案上傳。

失敗通常被捕捉後記入 events，因此 CLI exit code=0 不保證全部成功。標準輸出 saved 也可能只是同內容重新取得，請看 document hash 與解析狀態。

## 去重與增量語意

- 末層 URL 有舊 ETag／Last-Modified 時送條件請求；304 記 unchanged。
- 入口連結發現頁重新取得以發現連結，不直接以 304 跳過。
- 内容 SHA-256 作 documents.id；同內容多 URL 指向同文件。
- 同 URL 有新內容時新增文件、更新 sources.document_id；舊 raw 與 documents 保留。
- 這不是完整版本歷史：sources.url 只保留目前指向，舊文件可能失去來源列，events 只提供有限線索。
- 修改設定中的 source_id／license／suggested_label 不會經目前 upsert 自動回填既有來源列；須設計遷移，勿假設設定修改即改歷史資料。
- 沒有片段增量、搬移／刪除同步、自動重試排程或模型版本失效管理。
- body 以串流讀取但在記憶體累積到大小上限；原始文件第一次需完整讀取。解析也讀全部頁，取樣在其後發生。

## 資料表與狀態

| 表 | 主鍵／欄位 | 用途 |
|---|---|---|
| documents | id；path、kind、title、text_path、status、label、created_at | 去重後文件與人工標籤 |
| sources | url；source_id、document_id、etag、modified、license、suggested_label、checked_at | 目前來源對應與下載條件 |
| events | id；url、status、detail、created_at | 最近抓取與解析錯誤 |
| document_text_fts | FTS5；document_id、title、body | 關鍵字全文索引，需手動 reindex；見 cement/search.py |
| processing_policy | document_id；policy、reason、set_by、updated_at | 處理政策，與 label 分開，須明確設定 |
| document_relations | id；from_id、to_id、relation_type、note、created_by、created_at | 版本／系列／引用關係，須明確宣告 |
| extraction_jobs | id；document_version_id、extractor_version、schema_version、status、created_at | 圖譜候選抽取批次；見 cement/graph_extract.py |
| graph_candidates | id；job_id、document_version_id、node_type、quote、cue_phrase、evidence_id、assertion_mode、review_status、reviewer、note | 因果詞句候選，pending 需人工接受／拒絕 |

目前沒有正式 migration 系統、外鍵約束或圖譜資料表。SQLite CURRENT_TIMESTAMP 為 UTC；UI 未做台北時區轉換。不要將 created_at／checked_at 当成出版日期；304 分支目前也未刷新 sources.checked_at。

| status | 意義／處理 |
|---|---|
| downloaded | 尚待解析 |
| parsed | 文字長度及粗略品質檢查通過；不保證內容正確 |
| needs_ocr | 全文少於 40 字元；僅啟發式，不保證一定是掃描件 |
| needs_review | 任一頁異常控制字元比例 >0.5%；人工檢查，不訓練 |
| blocked_content | 存取挑戰頁；不訓練 |
| parse_error | 解析例外，詳 events |
| out_of_scope | 人工排除領域外文件；--retry 仍跳過 |

```powershell
.venv/Scripts/python.exe -m cement.parse --retry
```

預設只解析 downloaded；--retry 重做除 out_of_scope 外的所有快取文件。重解析不重新下載，也不修改人工 label。不要為了訓練而直接把品質異常狀態改成 parsed。

備份時停止寫入程序，整組備份 data/；SQLite 與 raw/text 的路径需一致。保留人工標註、來源更正和排除紀錄。

## 訓練與預測

1. UI 預覽文字，依主要用途標註；可清回 null。
2. 擴充跨來源、跨版型樣本，人工將近似版本留在同組。
3. 指定測試來源（以下 source_a/source_b 必須換成實際 id）：

```powershell
.venv/Scripts/python.exe -m cement.train --holdout-sources source_a,source_b
```

只使用 label 非空且 status=parsed 的文件。任一來源落在 holdout，整份文件歸測試；剩餘歸訓練。訓練至少兩類、測試非空且類別集合相同，否則停止。source_id 可細至單份文件，不能據此宣稱完整的跨機構隔離。

參數：TF-IDF 字元 2–4 gram、max_features=60000、sublinear_tf=true；LogisticRegression max_iter=1000、class_weight=balanced、random_state=42。

輸出模型與 evaluation.json；報告含 classification_report、confusion_matrix、classes、train_ids、test_ids、holdout_sources、sklearn_version。訓練會覆寫固定檔名，重要模型先保留版本。沒有自動模型登錄、校準或延遲測量。

API 每次預測重新載入本機 joblib；不接收上傳 pickle，勿載入不可信模型。前端目前沒有預測操作表單，可用 /docs。

## API 索引

| 方法／路徑 | 輸入與輸出 |
|---|---|
| GET / | 管理頁 |
| GET /api/documents | 文件含來源列表；尚未分頁 |
| GET /api/events | 最新 100 筆事件 |
| PUT /api/documents/{doc_id}/label | JSON {"label":"research"} 或 null；未知文件 404、非法值 422 |
| GET /api/documents/{doc_id}/text | 約 18,000 字元的首中尾文字預覽；未知文件 404 |
| POST /api/predict | JSON {"text":"..."}，1–100000 字元；回 label、scores、review_required=true；無模型 409 |
| GET /api/qr?url=... | HTTP(S) 網址最長 500 字元，回 SVG；不發出外部請求 |
| GET /api/search?q=...&limit= | FTS5 全文關鍵字搜尋，涵蓋全部 parsed 文件，不以 label 篩選；query 空白 400 |
| POST /api/search/reindex | 從目前 parsed 文件重建索引；需在新增/重解析文件後手動呼叫 |
| GET／PUT /api/documents/{doc_id}/policy | 處理政策（unset/fast_track/standard/deprioritized/excluded），須明確 set_by，不會由分類自動推定 |
| POST /api/relations、GET /api/documents/{doc_id}/relations | 文件版本關係（supersedes/same_series/cites），需明確 created_by；不會依日期自動推定 |
| GET /graph | 圖譜候選審核頁 |
| GET /api/graph/candidates?status= | 列出候選（預設 pending） |
| POST /api/graph/extract | 對既有 parsed 文件跑規則式因果詞候選抽取（見下節） |
| POST /api/graph/candidates/{id}/review | 人工接受／拒絕候選 |
| GET /docs | 自動 API 操作文件 |

沒有上傳、爬蟲啟動、訓練啟動或使用者管理 API。標註 API 可以替非 parsed 文件寫 label，但 train 仍排除它們。清冊與單文件 API 目前載入全表；這是規模化待改善項。搜尋、政策與關係 API 見下節「關鍵字索引、處理政策與圖譜候選審核（2026-09-13）」，此前「沒有…關係、搜尋」的描述已過時。

## 測試與排錯

```powershell
.venv/Scripts/python.exe -m pytest -q
```

六項測試涵蓋網域限制、內容去重與來源追溯、解析／標註／無模型回應／QR、條件請求、錯誤紀錄、暫存資料訓練與預測，以及異常文字排除。測試使用假網路回應及暫存示例；真實來源成效看 VALIDATION.md，不用測試分數對外宣稱準確率。

| 現象 | 處理入口 |
|---|---|
| python 找不到 | 使用 .venv/Scripts/python.exe |
| robots 403／disallow | 查看 events，保留失敗；換可用公開來源，不繞過限制 |
| saved 但內容是驗證頁 | 預覽文字，blocked_content；擴充挑戰頁辨識，勿訓練 |
| download size limit exceeded | 明確確認文件大小後調 --max-mb；台泥 2022 用 50 |
| PDF 字型警告／亂碼 | 檢查逐頁文字與 needs_review；fontTools 缺失只是其中一項線索，未修復前勿宣稱正常 |
| 訓練報類別不足 | 補真實標註與獨立 holdout，不讓資料穿越切分 |
| /api/predict 409 | 尚無可信訓練模型，先完成訓練 |
| 手機 QR 無法開啟 | localhost 指向手機本身；跨裝置需可達位址與後續權限設計 |
| sandbox helper 啟動失敗 | 工具環境問題；依權限規則處理，不修改應用程式繞過 |
| pytest 暫存權限失敗 | 使用全新專案暫存目錄，關閉 cacheprovider，見下例 |
| git 報 detected dubious ownership | 目錄擁有者與目前使用者不同（環境差異）；每次指令加 `git -c safe.directory='D:/QR code design' <command>`，不要用 `git config --global --add safe.directory` 永久修改全域設定 |

```powershell
$testTemp = 'data/test-' + [guid]::NewGuid().ToString('N')
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp=$testTemp
```

basetemp 必須是新的測試專用路徑，pytest 可能清理既有該目錄；不要指向 data/ 本身或任何原文／人工標註目錄。不要重用 VALIDATION.md 裡的舊測試目錄。

## 維護同步規則

- 需求與範圍改動：AGENTS.md；設計取捨：總體架構；命令／檔案／API／schema 改動：本 WIKI。
- 實測更新 VALIDATION.md，標明日期、資料規模、失敗與未測項。
- 不為文件重整重訓模型或重抓資料。只改文件時檢查連結、路徑、命令與內容一致性。
- 新增分類需同步後端 Literal、前端 labels、store.LABELS、資料策略與文件。
- 目前不含 OCR、全文向量庫、LLM、關係圖、自動排程、登入或 TB 級效能保障。

## 爬蟲 Skill 與程式解說

本機 Skill：C:/Users/annyj/.codex/skills/cement-crawl/SKILL.md。操作流程、函式解說與來源範例見 [爬蟲邏輯與使用](docs/爬蟲邏輯與使用.md)。核心程式仍為 cement/crawl.py；Skill 不在專案 Git 內，換機需重新建立或搬移 Skill，專案說明與程式則可隨 repo 交接。


## 待實作：2:8 弱標籤資料流程

名詞映射、資料欄位、切分與加權訓練規劃見 [訓練資料2比8規劃](docs/訓練資料2比8規劃.md)。目前沒有映射分類器或弱標籤資料表；現行 train.py 未變。


## 已實作：名詞映射與弱標籤候選（2026-09-12）

此節更新先前「尚無映射分類器／弱標籤資料表」的歷史描述。

- [config/term_mapping.json](config/term_mapping.json)：版本化領域詞、各用途 strong/support/search_terms、min_score=4、min_margin=2；皆為未校準初值。
- [cement/weaklabel.py](cement/weaklabel.py)：load_rules、classify、ensure_schema、run、main。
- [tests/test_weaklabel.py](tests/test_weaklabel.py)：各類證據、字界、衝突／引用／重複行、冪等、人工保護與版本追蹤。

```powershell
.venv/Scripts/python.exe -X utf8 -m cement.weaklabel --queries
.venv/Scripts/python.exe -X utf8 -m cement.weaklabel
```

第一條只印搜尋詞，不連線／不寫庫；第二條处理已有 parsed 且人工 label 為空的文件，保存 weak_labels 與 data/reports/weak_labels_latest.json。自訂規則使用 --rules 路徑。

規則每個唯一 strong 命中得 3 分，support 每項 1 分至多 3 分；需領域命中、至少一項 strong 及 support、總分與差距達門檻，且無多類符合才產生 candidate。其餘 abstain；人工或品質排除者 skipped。字元 NFKC／大小寫／空白正規化，ASCII 詞有字界；跨行短語未合併，可能漏判。內容衝突棄權，不按比例硬分。

weak_labels 由 weaklabel.ensure_schema 建立（非 store.connect），欄位為 assignment_id、document_id、origin、rule_version、rule_hash、text_hash、label、decision、reason、scores_json、evidence_json、domain_json、review_status、created_at。仍無正式 migration 系統。origin=term_mapping、review_status=pending；候選不等於人工真值。規則與文字 hash 一起辨識產物，規則變更留下歷史。

沒有審核 API、分組切分表、加權混合訓練或自動搜尋。train.py 仍只吃人工 label。後續建 dataset builder 時需排除失效規則／文字版本並以人工標籤優先。

研究與比例決策見 [弱監督比例研究](docs/弱監督比例研究.md)。

## 決策依據的維護方式

使用者要求（2026-09-12）：重要設計先找研究依據，無直接研究則依現有資料設計。規則見 [AGENTS.md](AGENTS.md)，目前 D-001 與來源摘要見 [總體架構](README_總體架構.md)。

每次新增／修訂決策保存：

| 欄位 | 要寫的內容 |
|---|---|
| 決策 ID／日期／狀態 | 例如 D-001；暫定、已驗證或被取代 |
| 問題與方案 | 目標、採用方案、未採替代方案與理由 |
| 研究依據 | 原始來源連結、查核日期、讀取範圍、可支持的結論與限制 |
| 證據類型 | 直接研究、間接研究、本地實測或工程假設，不能混用 |
| 本地資料 | 資料規模、來源／版本、實驗設定、結果與失敗 |
| 驗證與重評 | 指標、評估資料隔離方式、何時維持／調整／回退 |
| 實作位置 | 受影響程式、設定與文件連結 |

沒有直接研究時補記搜尋範圍、尚不確定之處與以現有資料取捨的理由。不要寫不存在的實驗或尚未量测的成本節省。

目前 min_score=4、min_margin=2、strong=3 分、support 最多 3 分，皆是未校準工程初值。修改應保留規則版本與 hash，記錄驗證結果；不能以「遵循研究」作為未提供依據的解釋。

本輪只更新決策文件，核對文件連結與程式碼區塊，不重抓資料或重訓模型。

## 人工審核與資料集草稿（2026-09-12）

新增 [cement/review.py](cement/review.py)、[cement/dataset.py](cement/dataset.py) 與 [tests/test_review_dataset.py](tests/test_review_dataset.py)。命令、審核欄位、review_log/dataset_membership 表、限制見 [操作指南](docs/人工審核與資料集.md)。此節取代先前『沒有分組切分表』的描述；仍無審核 API 或混合訓練。dataset_membership 尚未被舊 train.py 使用，draft_only/training_ready 刻意固定為草稿／false，不能直接拿來宣稱訓練就緒。


## 第二批來源與定向解析（2026-09-12）

- [本批來源](config/sources-expansion-20260912.json)：8 個直接來源；source_group_hint 僅供參考，不自動設定 membership。
- [擴充紀錄](docs/資料擴充20260912.md)：來源網址、失敗、統計、D-003 與產物 WIKI。
- requirements.txt 改用 pypdf[crypto]>=5,<7；requirements.lock.txt 已更新。
- cement.parse 的 --document-id 指定完整文件 SHA256；既有非 downloaded 狀態需搭配 --retry，out_of_scope 仍跳過。

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
.venv/Scripts/python.exe -m cement.crawl --config config/sources-expansion-20260912.json --max-files 1
.venv/Scripts/python.exe -m cement.parse --retry --document-id 8552b7e8a434a69a2a603e424d0b6ce70c70bd6c10ee7a2bce856a2cca8f230f
```

本次審核包 data/reviews/batch-20260912-02.json 有 8 份；匯入方式見人工審核指南。重跑匯出時使用新檔名，保留既有批次。Holcim robots 301 與 FHWA 大於 25 MiB 已記錄，程式不繞過；NIST 研究 PDF 待 OCR。14 項測試通過。

## 精簡人工標註工作包（2026-09-12）

[cement/review_pack.py](cement/review_pack.py) 將匯出的全文 JSON 轉成離線 Markdown 閱讀文件及精簡標註 JSON。無新增套件；目錄必須不存在，防止覆寫已填內容。既有 label/reviewer 等欄位原樣保留，不自動產生人審結果。

```powershell
.venv/Scripts/python.exe -m cement.review_pack --input data/reviews/batch-20260912-02.json --output data/reviews/reading-pack-20260912-01
# 上述目錄已產生；重跑請另取新目錄。
# 人工讀完逐份全文，填寫 answers.json 後：
.venv/Scripts/python.exe -m cement.review import --input data/reviews/reading-pack-20260912-01/answers.json
# 匯入成功後以新檔名輸出資料集草稿：
.venv/Scripts/python.exe -m cement.dataset --output data/reports/dataset-after-human-01.json
```

入口 data/reviews/reading-pack-20260912-01/README.md；document-001.md 至 document-008.md 為含頁碼全文。answers.json 保留 document_id/text_hash/current_label，人工填 label、reviewer、note、group_id、split。只修改後五欄；空白 label 不匯入。既有匯入器仍核對文字版本與群組衝突。不得將已用於開發的本批宣稱為盲測集。

本輪 15 項測試通過（兩個既有相依棄用警告）。工作包是解析文字快照，無法取代原 PDF 的圖表與版面檢查；若文字不足以判讀，保留空白。沒有修改 train.py 或啟用混合訓練。

## 加速標註評估（2026-09-12）

使用者要求評估比逐份人工標註更快速可靠的方式。研究、適用限制與驗證設計見 [加速標註方案評估](docs/加速標註方案評估.md)。D-004 為提案：優先多證據程式化弱標註＋衝突審核＋分層隨機抽驗，可選有限 LLM 教師，主動學習待有模型及足夠資料後比較。沒有研究證明本案可無條件取代人工或固定最佳比例；2:8 維持規劃，獨立人工評估另計。

本輪僅研究及文件更新，未新增標籤、API 標註呼叫或訓練；既有人工工作包保持。新流程須保留真值／弱標籤區別，不能以此提案绕過未完成的弱標籤抽驗。

## 輔助審核頁面（2026-09-12）

已新增 /review（cement/static/review.html），工作台首頁有入口。列出 parsed 文件，預設顯示有文字的首／中／末頁各最多 1,800 字及原頁碼；可選全文，全文為所有解析頁，圖表仍需來源原檔。五类用途單選；暫不確定可跳過，不寫入標籤。表單在頁面切換時保留暫填內容，重新整理不保留。

填寫審核者、文件群組、資料用途與可選理由後，按「儲存並下一份」寫入資料庫。既有群組／split 凍結。既有 label 會顯示；不呈現弱標籤建議。測試／驗證集不可使用已參與開發文件。

GET /api/review/{doc_id}?full=false|true 回傳頁碼內容、text_hash、current_label 與 membership。POST /api/review 使用 ReviewSubmission，透過 cement.review.import_rows 與 CLI 共用驗證／原子寫入：文字過期、群組衝突回傳 409，欄位不合法 422。舊首頁直接 label API 仍存在；完整審核請使用新入口。

本機啟動：`.venv/Scripts/python.exe -m uvicorn cement.api:app --host 127.0.0.1 --port 8011`，開啟 http://127.0.0.1:8011/review 。僅本機工具，未發布，沒有新增身份驗證。16 項測試通過、JavaScript 語法檢查通過；瀏覽器確認 8 份清單、片段及分類表單。實際儲存測試使用隔離資料庫，沒有替真實文件標註。本次沿用 D-002；1,800 字與三處取樣為可逆 UI 初值，不是研究證實最佳值。

## 審核快捷操作與數量（2026-09-12）

/review 新增複製目前片段／全文（含頁碼）、pososos 審核者與「分類測試」文件群組的候選及快捷按鈕；仍可自行輸入，既有凍結群組不能被快捷按鈕更改。這些是選項，不代表已有人審。

各分類顯示需求／已計入／剩餘，資料用途選擇後顯示該 split 配額，未選則合計。沿用 dataset.build：每類訓練人工 10＋弱 40、驗證人工 5、測試人工 10，總計 65；各配額剩餘分別計算再加總，超額人工不抵弱標籤缺額。GET /api/review-progress 讀取現有草稿 targets；未審核弱候選與失效 membership 不計入。全域群組檢查／訓練尚未就緒仍另計，數量不是可訓練保證。儲存後更新數量。17 項測試與 JS 語法檢查通過。未變更既有目標或研究決策。

## 首批人工判讀結果（2026-09-12）

使用者回報已判斷 8 份，幾乎可從標題或擷取片段中的關鍵字判斷。資料庫核對 reviewer=pososos 的 8 份已儲存：manual 2、industry 2、safety 2、research 1、guidance 1。先前「零人工真值」快照已過時。

既有規則的 5 份候選與人工結果有 4 份一致、1 份不一致，另 3 份棄權。不一致的是 FHWA-HRT-23-104: Portland Limestone Cement：人工 research、規則 guidance。保留人工判斷，不自動覆寫；後續應釐清研究與工程指引的分類邊界。這是同批開發資料的描述性比較，不是獨立測試準確率。審核 note 空白，系統未記錄判讀耗時或實際閱讀範圍，因此不能聲稱已測出片段分類正確率或成本節省。

使用者觀察支持先試驗「文件內容標題／首頁文字＋局部片段，證據不足再擴展全文」的分階段輸入；目前僅作本地假設，沿用 D-004 提案，沒有研究宣稱八份可證實泛化。PDF metadata title 多份為空，且部分與正文用途不一致，不能只用清冊 title 欄位。現行解析仍讀全文，預覽節錄不等於已降低 PDF 解析成本。

已產出 data/reports/dataset-after-human-20260912-01.json；仍為草稿、training_ready=false。下一個驗證應以這批作開發，比較首頁／片段／全文的規則輸出與人工結果，保存證據及讀取字量；另收獨立來源檢驗泛化。未修改規則或模型，未覆寫人工標籤。

## 人工修正與棄權分析（2026-09-12）

依使用者更正 Portland Limestone Cement 為 guidance，已透過既有稽核匯入器寫入並保存理由；人工 research 現為 0。三份棄權中兩份由全文旁支主題造成多類衝突，一份因缺少 support 完整詞命中。保持規則不變改用前三個非空頁，前兩份轉為與人工一致的候選，另一份仍棄權。詳見 [三份棄權分析](docs/三份棄權分析.md)。這是本地開發資料診斷，正式規則未修改，不是獨立成效驗證。

## D-005 多語言檢索分類（2026-09-12，提案）

評估 embedding＋reranker 可作類別描述／代表範例分類；五類先比較 embedding 全類別與 reranker 全類別，之後才評估按難例啟用。無須全量向量庫。相關性不是用途真值，直接使用預訓練模型不等於自訓；後續可凍結 encoder 自訓分類頭。研究來源、成本、增量快取與資料限制見 [多語言檢索分類評估](docs/多語言檢索分類評估.md)。本輪未安裝或訓練模型，未修改規則／資料標籤。

## 中英文來源擴充（2026-09-12）

使用者要求來源同時包含中文與英文；後續收集與評估需按語言及用途檢查缺口，不能以同一文件翻譯本充作獨立樣本。

本批 6 來源，5 下載成功、1 因國土管理署 robots HTTP 302 停止。成功取得中文台泥安全資料表、中文建研所混凝土收縮研究摘要頁、中文水利署結構用混凝土規範頁、英文 NIST 水灰比／水化研究摘要頁、英文 NIST Drying/hydration PDF。最後一份僅封面 617 字，後九頁無文字，已從 parsed 改 needs_review 並記錄品質事件，不列可審核樣本。兩份研究網頁是摘要，不冒稱全文；HTML 尚有導覽文字，應改善正文提取後再作片段模型比較。

來源可重跑設定為 config/sources-bilingual-20260912.json 與 config/sources-bilingual-followup-20260912.json，已併入 sources.json。language_hint 為來源設定提示；data/reports/bilingual-sources-20260912.json 記錄本次正文語言抽查與內容範圍，未新增資料庫語言欄位，也未代填人工用途。新資料有中文 3、英文 1 份通過現行解析檢查；人工仍需判讀。

全庫 18 份：parsed 12、needs_review 3、needs_ocr 1、blocked_content 1、out_of_scope 1。既有八份人工標籤保留；新四份尚未標註。data/reviews/bilingual-new-only-20260912.json 為僅新四份審核包；batch-bilingual-20260912.json 為 12 份完整匯出。審核頁重新整理可見新文件。本輪沿用既有爬蟲與弱規則，未更改模型或執行測試套件；未安裝 embedding/reranker。下一步先處理 HTML 導覽干擾，再做 D-005 離線比較；中英文五類分布仍未補齊。

cement-crawl 全域 Skill 仍有舊入口名稱，但使用者已要求合併，實際以本專案 AGENTS.md 為準；本輪未修改全域 Skill。

## HTML 正文清理（2026-09-12）

新增 parse.extract_html：按已核對的 NIST / ABRI / WRA 主機選正文區，保留分行。ABRI 同時擷取 CCMS_Content 與 page-footer，避免漏掉摘要；已知版型缺區塊則報錯。保留包住正文的 ASP.NET form，避免清除整份文件。此為原始 HTML 結構的本地實測修正，不新增模型選擇研究結論。

三份網頁已定向重解析，原文保存在 data/text-history/*-before-body-clean.json。首次執行曾因 form 祖先被移除產生空正文，已修復並補測，最終三份皆 parsed；以 data/reports/html-body-clean-final-20260912.json 為最終結果，早期報告保留失敗記錄。19 項測試通過。

使用者已完成新增文件標註，這次讀取發現三份網頁也已有人審。保留所有人工 label，不代為確認新文字；三份文字 hash 改變，membership 需經 UI 重新確認儲存後才恢復有效。既有開啟頁面會以版本衝突阻止過期提交，請重新選取文件。最終審核包 batch-body-clean-final-20260912.json；dataset-body-clean-20260912.json 保存失效檢查。先前 batch-body-clean-20260912.json 是修復前中間產物，不作最新審核入口。

未安裝語意模型；下一階段才做類別描述 embedding／reranker 比較。原始下載保留，清理不改人工用途與資料切分。

## 語意模型實測與圖譜銜接（2026-09-12）

已完成 E5-small 與 bge-reranker-v2-m3 十二份離線比較，固定 revision／雙語類別描述／前 1,500 字／512 tokens，CPU 4 threads。有效審核九份兩模型皆 7/9 與人工一致，兩份手冊仍誤判。三份正文更新的人工標籤保留但不計指標；reranker 對這兩份研究摘要的預測與舊人工標籤一致，但尚不作有效评估。CPU 每份中位數 E5 0.106 秒、reranker 3.837 秒；少量單次實測，不是泛化準確率或 TB 吞吐。暫不推薦全量 reranker。詳見 docs/語意分類實測20260912.md 與 docs/語意分類實驗操作.md。

新增 cement/semantic_benchmark.py、semantic_summary.py、config/semantic-labels.json、semantic-models.json，requirements-semantic.txt／requirements-semantic.lock.txt；原工作台相依檔保留。模型檔位於 data/model-cache 與 data/reranker-fixed，約數 GB，未建向量庫。Hub reranker 下載停滯後改用相同 revision HTTPS 串流完成。20 項功能測試通過；模型已實際推論，未自訓、未寫入正式 label 或正式預測 API。

使用者追加知識圖譜須連結事件、原因、結果／結論，並可延伸 tag。D-006 依 PROV-O、SKOS 與事件時間／因果研究作設計，詳見 docs/知識圖譜銜接設計.md。原文因果主張與模型推論、時間前後、語意相似分開；tag 支援雙語別名、上位／相關概念與版本。現行較早「知識圖譜留待後續」不代表禁止這次明確要求的銜接設計。

已新增 config/graph-contract.json（設計契約，非驗證器）、cement/graph_handoff.py，匯出 data/reports/graph-handoff-20260912.json：12 文件版本、19 帶 hash／頁碼／字元定位的原文片段，全部引文定位核對通過。事件／關係／tag 尚未抽取，空陣列不代表完整圖譜。CLI：`.venv/Scripts/python.exe -m cement.graph_handoff --output data/reports/new-graph-input.json`。輸出禁止覆寫；用途分類不是唯一抽取閘門。下一步先改善手冊與研究／指引邊界，再實作單文件事件主張候選與證據審核；跨文件合併、因果驗證、圖 UI 尚未完成。

## 標題 → 目錄 → 內容與級聯門檻（2026-09-12）

使用者明確要求判斷順序為標題、目錄、最後內容，避免大量正文干擾。已新增 cement/staged_classification.py 離線流程，各階段獨立 embedding → 未達門檻才 reranker → 再未達才下階段 → 最後棄權；沒有正式自動套用最佳門檻。

最終 data/reports/staged-02：96 組門檻。有效九份標題 embedding 9/9、標題 reranker 5/9；E5 0.75／差距0 全部直接採 embedding，9/9、零 reranker；E5 0.8／0.02＋reranker logit0／差距1 為6/9、三誤判、六次 reranker（全部12份）。嚴格0.9／0.1＋2／2為三一致、一誤判、五棄權。這是同批調參，不能稱跨語言五類泛化準確率；有效研究類仍缺，原三份失效審核保留但不計指標。

詳見 docs/標題優先與級聯門檻實測.md。22 項測試通過；人工標籤與線上 API 不變。下一階段必須維持標題優先方向，但對模糊標題應保留目錄／正文升級與棄權；尚未驗證的新路由不可宣稱已完成。圖譜抽取仍需要按關係證據追加正文，分類少讀不等於圖譜可以只讀標題。

## 七類用途與僅內容重排（2026-09-12）

使用者要求 reranker 放在內容階段，新增實驗記錄 experiment_log 與手稿筆記 manuscript_notes。已同步 store、API、兩個頁面、閱讀包、語意描述與詞彙規則（v2）；原人工標籤保留。新路由為標題 E5 → 目錄 E5 → 內容 E5 → 僅內容 reranker → 棄權；缺標題／目錄可略過。reranker 是否提升內容分類仍需實測，不把需求描述當研究成效結論。

已跑七類 96 組，data/reports/staged-seven-body-reranker-01/；有效九份：E5 0.75/差距0 時9一致、0棄權、0次重排；0.8/0.02＋重排0/1時8一致、0誤判、1棄權，全部12份共3次內容重排；0.9/0.1＋2/2時1一致、8棄權。僅作同批開發診斷，與前版同時改了類別數及路由，不能視為單變量因果實驗。兩個新類無人工真值，不能聲稱七類準確率。已確認所有標題／目錄階段沒有 reranker 分數。

23 項測試通過，JS 語法通過；localhost:8011 已重啟，重新整理可見七類。沿用每類65份規劃，總需求455，新類目前剩餘各65；此為配額延伸，非研究最佳值。詳見 docs/七類用途與內容階段重排.md。手稿筆記不等於必須手寫，掃描手寫 OCR 未實作。圖譜上實驗記錄可提供條件／事件／量測，手稿主張保留草稿與推測狀態。


## 配額收集實測（2026-09-13）
全庫317份，parsed255；本批可解析PDF候選研究37、工程指引38、產業27、SDS52，尚非人工確認或獨立樣本。455份未蒐集齊，手冊／實驗記錄／筆記缺口最大。僅後兩類獲准擴至土木／建材，另註domain。MIT筆記因掃描／印刷插頁需OCR或品質審查；iGEM日誌robots403未下載。新增兩個來源發現腳本及唯讀稽核報告，配置已合併sources.json。詳見 [配額資源蒐集實測](docs/配額資源蒐集20260913.md)。23項測試通過，未動人工標籤或訓練。


## 第二批資源擴充（2026-09-13）
新增15份設備手冊、5份試驗報告、13份原始TXT量測記錄可解析，另10份目錄排除。全庫360、parsed288；455份合格獨立樣本仍未齊，本批英文。TXT由已核對ZIP有界匯入，來源與同實驗家族見data/reports/experiment-members-20260913.json，不能跨split拆開。新增TXT解析與429同次爬蟲主機暫停，25項測試通過。Humboldt本輪已限流，不立即另起程序重試。詳見 [收集實測](docs/配額資源蒐集20260913.md) 第二批章節。


## 第三批資源擴充（2026-09-13）
新增78份英文量測TXT、1份中文實測、3份中文材料使用PDF可解析；1份掃描待OCR、2入口排除。全庫445，parsed370；不是455合格樣本只差10份，仍有用途、群組與人工審核缺口。Hannover七實驗室共91份TXT屬同研究家族，不跨split任意拆開。新增collect_fatigue_labs及參數化封包匯入、完整預檢，三個已核對封包採10MiB單檔上限，總量仍25MiB。26項測試通過。最新collection-third／dataset-third／quota-third報告，細節見 [收集實測](docs/配額資源蒐集20260913.md) 第三批。


## 第四批與課堂筆記授權（2026-09-13）
使用者允許手稿筆記納入課堂筆記、講義與投影片，來源子類另標記；取代早先僅未完成草稿限制。config/source-subtypes.json→API source_metadata→審核頁顯示，不是人工標籤。課程群組與OCR限制保留。全庫491、parsed392；候選檔案研究37／手冊18／指引42／SDS55／產業31／實驗97／筆記19，配額仍未齊。semantic-labels與term_mapping升v3，尚未重跑模型或弱標註，旧指標只適用舊定義。26測試及JS語法通過，8011重啟。最新collection-balance-fourth-final及quota-fourth審核包；詳見 [收集實測](docs/配額資源蒐集20260913.md) 第四批。


## D-007 選樣偏差修正（2026-09-13）
使用者目標為公司／專案混合資料夾＋研究團隊資料庫（1+3，未指定比例）。停止以用途搜尋補配額作為評估來源；舊公共資料僅開發候選，不能重新宣稱新盲測。現庫513含中斷第五批已下載22份，未解析；無執行中爬蟲。來源高度綁定用途已稽核，見sampling-bias-20260913.json；未做近似重複／捷徑模型實測。新增local_inventory與evaluation_intake支援本機固定快照、全檔案清冊、固定seed、拒收曝光內容與用途欄位；尚需使用者提供真實資料快照路徑，未建代表性測試集。30項測試通過。研究依據、限制及操作見 [選樣偏差與混合資料庫評估](docs/選樣偏差與混合資料庫評估.md)。

## 關鍵字索引、處理政策與圖譜候選審核（2026-09-13）

依 [D-008](README_總體架構.md#d-008-雙軌推進與配額延後2026-09-13) 軌道一與 AGENTS.md 待辦（關鍵字索引／處理政策／版本管理、D-006 後續），新增不需要新人工標註即可推進的基礎設施。

**關鍵字索引**（[cement/search.py](cement/search.py)）：SQLite FTS5 對全部 status=parsed 文件的 title＋全文建索引，`search()` 不依 label 篩選，避免分類分數／標籤成為唯一檢索閘門（未標註文件也可搜到）。新增文件或重解析後需手動 `POST /api/search/reindex` 或 CLI 重建，索引不會自動跟著寫入即時更新。

```powershell
.venv/Scripts/python.exe -m cement.search reindex
.venv/Scripts/python.exe -m cement.search query "hydration" --limit 10
```

**處理政策**：`processing_policy` 表與 `set_policy`/`get_policy`，policy 限 unset/fast_track/standard/deprioritized/excluded，須明確 `set_by`，不會由 label 或分類分數自動推定；對應 `GET`/`PUT /api/documents/{doc_id}/policy`。

**文件版本／系列關係**：`document_relations` 表與 `add_relation`/`relations_for`，relation_type 限 supersedes/same_series/cites，須明確 `created_by`，不接受「日期較新即取代」之類的自動推論；對應 `POST /api/relations`、`GET /api/documents/{doc_id}/relations`。

**D-006 圖譜候選（單文件，規則式）**（[cement/graph_extract.py](cement/graph_extract.py)）：重用 `graph_handoff.build()` 的既有原文片段，用中英文因果詞（導致／造成／因此／由於／引起／因而／due to／results in／leads to／caused by／because of／contributes to）比對句子，產生 assertion_mode=explicit_in_source 的 Claim 候選，全部從 pending 起算，須人工於 `/graph` 頁面或 API 接受／拒絕；重跑同一文件版本只覆蓋該版本尚未審核的 pending 候選，已接受／拒絕的紀錄保留。這只是「候選句子」，還沒有拆成 docs/知識圖譜銜接設計.md 的 Event/Condition/Outcome/claims_cause 關係，含因果詞不代表已證實因果。

```powershell
.venv/Scripts/python.exe -m cement.graph_extract extract
.venv/Scripts/python.exe -m cement.graph_extract list --status pending
```

本機以既有 513 份庫（392 parsed）實測：reindex 索引 392 份、跨語言／跨標籤關鍵字搜尋在瀏覽器驗證可用；extract 對現有 parsed 文件產生 77 筆候選，於 /graph 頁面接受 1 筆後在 API 與畫面均正確歸類為 accepted、剩餘 76 筆仍為 pending。管理頁新增搜尋框與「開啟圖譜候選審核」連結；審核頁未變動。37 項 pytest（含新增 7 項）通過；沒有可用的 Node 環境做獨立 JS 語法檢查，改以啟動本機服務並在瀏覽器實際操作管理頁搜尋、圖譜候選列表與接受操作驗證。未修改既有標籤、review.py 或 dataset 邏輯。
