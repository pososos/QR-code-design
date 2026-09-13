# 實測紀錄（2026-09-11）

- 六項 pytest 測試通過，包含去重、來源追溯、條件請求、解析品質、標註、模型訓練／預測往返與失敗紀錄。
- 測試用模型只在暫存資料上驗證功能，非領域成效報告。models/ 尚未建立真實資料模型。
- NIST 工具指南與 FHWA 兩份文件通過初步解析，共 3 份。
- NIST 水化研究與台泥 2022 永續報告有字元／字型問題，標記 needs_review，共 2 份。
- Cemex 回傳存取挑戰頁，標記 blocked_content，不當作訓練資料；之後爬蟲會直接拒收同類頁面。
- IEA robots.txt HTTP 403，未下載文件。
- 早先 web_csrc 連結內容其實為國際中橡 2023 報告，已更正來源 ID、標記 out_of_scope 並保留稽核資料。sources.json 已改為 web_tcc 的台泥 2022 報告。
- 台泥 2022 已下載並以文字確認文件身分。檔案超過預設 25 MiB，需使用 --max-mb 50。
- 瀏覽器已驗證清冊與文字預覽。QR 使用目前瀏覽器網址，localhost 不支援手機跨裝置存取。
- 本機服務：.venv/Scripts/python.exe -m uvicorn cement.api:app --host 127.0.0.1 --port 8000
- 本次最終測試因預設暫存目錄權限問題改用新專案暫存目錄，命令為：pytest -q -p no:cacheprovider --basetemp=data/test-final-20260911。後續使用新的目錄名稱，避免覆寫已有測試暫存。

尚未驗證：分類準確率、TB 級吞吐、OCR、跨文件關係與向量檢索。

## 2026-09-12 弱標籤原型

九項測試通過（原六項＋新三項），有兩項套件棄用警告；無測試失敗。實際執行既有 7 筆：guidance candidate 1（FHWA PLC），abstain 2（NIST manual 類別衝突、FHWA SCM 證據不足），skipped 4。輸出 data/reports/weak_labels_latest.json 與 weak_labels 表。未新增人工 label、未訓練真實模型，候選精確率未驗證。


## 2026-09-12 審核與資料集草稿

13 項測試通過，兩項套件棄用警告。匯出 3 份可解析文件審核包；資料集草稿 1 候選、6 排除、5 項阻擋，training_ready=false。沒有人工標籤或模型新增。測試包含過期／衝突匯入全批拒絕、重跑冪等、人工標籤保護及弱標籤版本排除。


## 2026-09-12 第二批公開資料擴充

新增 8 來源、6 下载成功、2 有界失敗；全庫 13 文件，parsed 8。補 AES 相依後两份 Heidelberg 報告定向解析成功。弱候選 5、棄權 3、排除 5；人工標註 0。審核包 8 份，資料集草稿 5 候選、8 排除、13 blockers，training_ready=false。

pytest -q -p no:cacheprovider 配置新獨立 basetemp：14 passed，2 個既有相依套件棄用警告。新增測試確認 --document-id 不改動其他文件。此為功能驗證，未量測分類準確率、TB 吞吐或成本節省。詳見 docs/資料擴充20260912.md。

## 人工閱讀包（2026-09-12）

新增 cement/review_pack.py，將既有審核 JSON 分成逐份含頁碼全文與精簡 answers.json。實際輸出 data/reviews/reading-pack-20260912-01/，8 份文件、人工欄位保持空白；原始審核包與資料庫未改動。入口為該目錄 README.md。

此為 D-002 審核工作流程的呈現改善，沿用既有獨立人工評估與群組隔離依據；不是新的比例、模型或有效性決策，未主張提高標註品質。工作包不呈現弱標籤建議／證據，避免自動候選直接影響填寫。全文仍需人判讀，未分組資料不自動決定 split。

15 項功能測試通過；新增測試涵蓋精簡欄位匯入、空白跳過、原檔保護、不顯示弱建議及全文 HTML 轉義。首次測試發現 Windows 預設 cp950 讀取問題，測試改為明確 UTF-8 後通過。仍零人工真值，沒有新增模型。

## 輔助審核 UI（2026-09-12）

完成 /review 片段／全文預覽、用途單選、跳過及儲存下一份。新增 review GET/POST API，與 CLI 共用 import_rows 稽核。人工真值未代填；16 項測試通過。操作與限制見 README_技術維護.md「輔助審核頁面」。此節取代舊版「沒有審核 API／UI」描述；混合訓練仍未完成。

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


## 第二批資源擴充（2026-09-13）
新增15份設備手冊、5份試驗報告、13份原始TXT量測記錄可解析，另10份目錄排除。全庫360、parsed288；455份合格獨立樣本仍未齊，本批英文。TXT由已核對ZIP有界匯入，來源與同實驗家族見data/reports/experiment-members-20260913.json，不能跨split拆開。新增TXT解析與429同次爬蟲主機暫停，25項測試通過。Humboldt本輪已限流，不立即另起程序重試。詳見 [收集實測](docs/配額資源蒐集20260913.md) 第二批章節。


## 第三批資源擴充（2026-09-13）
新增78份英文量測TXT、1份中文實測、3份中文材料使用PDF可解析；1份掃描待OCR、2入口排除。全庫445，parsed370；不是455合格樣本只差10份，仍有用途、群組與人工審核缺口。Hannover七實驗室共91份TXT屬同研究家族，不跨split任意拆開。新增collect_fatigue_labs及參數化封包匯入、完整預檢，三個已核對封包採10MiB單檔上限，總量仍25MiB。26項測試通過。最新collection-third／dataset-third／quota-third報告，細節見 [收集實測](docs/配額資源蒐集20260913.md) 第三批。


## 第四批與課堂筆記授權（2026-09-13）
使用者允許手稿筆記納入課堂筆記、講義與投影片，來源子類另標記；取代早先僅未完成草稿限制。config/source-subtypes.json→API source_metadata→審核頁顯示，不是人工標籤。課程群組與OCR限制保留。全庫491、parsed392；候選檔案研究37／手冊18／指引42／SDS55／產業31／實驗97／筆記19，配額仍未齊。semantic-labels與term_mapping升v3，尚未重跑模型或弱標註，旧指標只適用舊定義。26測試及JS語法通過，8011重啟。最新collection-balance-fourth-final及quota-fourth審核包；詳見 [收集實測](docs/配額資源蒐集20260913.md) 第四批。


## D-007 選樣偏差修正（2026-09-13）
使用者目標為公司／專案混合資料夾＋研究團隊資料庫（1+3，未指定比例）。停止以用途搜尋補配額作為評估來源；舊公共資料僅開發候選，不能重新宣稱新盲測。現庫513含中斷第五批已下載22份，未解析；無執行中爬蟲。來源高度綁定用途已稽核，見sampling-bias-20260913.json；未做近似重複／捷徑模型實測。新增local_inventory與evaluation_intake支援本機固定快照、全檔案清冊、固定seed、拒收曝光內容與用途欄位；尚需使用者提供真實資料快照路徑，未建代表性測試集。30項測試通過。研究依據、限制及操作見 [選樣偏差與混合資料庫評估](docs/選樣偏差與混合資料庫評估.md)。

## D-008 雙軌推進執行（2026-09-13）

軌道一：pytest -q -p no:cacheprovider --basetemp=data/test-d008-track1-20260913，30 passed（與 D-007 相同數量，確認可重現），2 個既有相依套件棄用警告，無新增測試。

軌道二：`cement.train --holdout-sources wra-concrete-zh,heidelberg-2022,nist-vcctl-1173,nist-kinetics-abstract-en,tcc-sds-zh`，7 訓練／5 測試（每類各留一來源），macro-F1 0.4。兩份中文測試文件（guidance、safety）被誤判為訓練集中唯一的中文類別 research；一份英文 research 測試文件被誤判為訓練集英文樣本最多的 guidance。n=12、每類訓練樣本僅1–2份，僅證明流程可運作並小樣本重現既有跨語言警語，非成效證據。輸出保存於 models/evaluation.json 與 data/reports/track2-source-isolated-diagnosis-20260913.json。詳見 [軌道二來源隔離小樣本診斷](docs/軌道二來源隔離小樣本診斷20260913.md)。

## 關鍵字索引、處理政策與圖譜候選（2026-09-13）

pytest -q -p no:cacheprovider --basetemp=data/test-d008-track3-full-20260913：37 passed（原30＋新增 tests/test_search_index.py、tests/test_graph_extract.py 共7項），2 個既有相依套件棄用警告。

本機環境無可用 Node，無法比照先前批次做獨立 JS 語法檢查；改為啟動 `uvicorn cement.api:app --host 127.0.0.1 --port 8011`，以瀏覽器實機操作驗證：`POST /api/search/reindex` 對 392 份 parsed 文件建索引；管理頁關鍵字搜尋框查「hydration」正確回傳跨標籤結果，含未標註（待確認）文件；`POST /api/graph/extract` 對既有 392 份 parsed 文件產生 77 筆因果詞候選；/graph 頁面填審核者後點「接受」，畫面即時剩 76 筆 pending，API 查詢確認該筆已轉 accepted 且保留 reviewer 與內容。未修改既有人工標籤、review.py 或 dataset 邏輯；本次資料庫狀態為本機開發用（data/ 未進 Git）。

## Git 狀態核對（2026-09-13）

`git -c safe.directory='D:/QR code design' log` 回報 branch 'master' 尚無任何 commit；`git status` 顯示全部檔案為 untracked。即本機三天以來的所有程式與文件變更目前只存在工作目錄，從未提交。另清除本次診斷中誤建的 0 byte 根目錄 catalog.sqlite（與 data/catalog.sqlite 正式資料庫無關）。本輪僅核對狀態與清理殘留檔，未執行 git add／commit，是否建立首個 commit 留待使用者決定。

依使用者確認建立首個 commit（`7f64891`）：僅本機 repo-local 設定 `user.name=pososos`／`user.email=annyjpc@gmail.com`（未動全域設定）；`git add -A` 前逐一核對 92 個待加入檔案（`git add -A -n` 全量列出並抽查最大檔案 `sources.json` 113KB），確認皆為程式／設定／文件／測試，沒有 `data/`／`models/` 下的任何蒐集文件或模型檔（已被 `.gitignore` 排除）。commit 後依使用者提供的網址新增 remote origin（`https://github.com/pososos/QR-code-design.git`，push 前以 `git ls-remote` 確認該 repo 目前為空、無衝突風險）並推送 master 分支成功。

## 分頁、版本失效管理與跨文件候選關聯（2026-09-13）

pytest -q -p no:cacheprovider：44 passed（原37＋新增 tests/test_pagination.py 4 項、tests/test_graph_extract.py 新增 3 項），2 個既有相依套件棄用警告。

本機以既有 513 份庫（392 parsed）重啟服務實測：`GET /api/documents?limit=3` 回傳 `X-Total-Count: 513` 且僅回 3 筆；`POST /api/graph/extract` 對現有 pending 候選正常運作（初次遷移時因 `extraction_jobs` 缺 `document_id` 欄位觸發 `sqlite3.OperationalError`，已用 `PRAGMA table_info` 偵測後 `ALTER TABLE` 補欄位修復，修復後重試成功、pytest 44 項仍全過）；以 API 直接接受兩筆候選並建立一筆 `same_event_candidate` 關聯後，`/graph` 頁面以瀏覽器 DOM 查詢確認 SVG 正確畫出 2 個 `<rect>` 節點與 1 條 `<line>` 連線（畫面截圖因瀏覽器分頁背景執行不穩定而改用 DOM／API 交叉驗證，非省略驗證）。未修改既有人工標籤、review.py 或 dataset 邏輯。

## D-006 深化、時間軸與本機語意檢索（2026-09-13）

pytest -q -p no:cacheprovider：54 passed（原44＋新增 tests/test_graph_store.py 5 項、tests/test_vector_search.py 5 項；test_pipeline.py 既有訓練/預測測試擴充斷言涵蓋 registry／calibration／predict-log，未增加測試數）。

真實模型推論實測（非 mock，本機 CPU）：`POST /api/search/semantic-reindex` 對 392 份 parsed 文件建置 E5-small embedding 快取，耗時約 61 秒；`GET /api/search/semantic?q=hydration+kinetics+of+cement+paste` 前五名結果主題相關（NIST 水化動力學／水泥漿模型論文），管理頁語意搜尋切換鈕操作得到一致結果。管理頁分頁：513 份、每頁 50、共 11 頁，上一頁／下一頁與頁碼正確更新。

`/graph` 頁面掃描出 281 筆規則式實體候選（config/entity-gazetteer.json）；把兩份不同文件的「NIST」候選分別連結到同一個新建實體後，`/api/graph/entities/{id}/mentions` 正確回報「2 處提及、2 個文件版本」，證實跨文件實體對齊實際運作。過程中發現一個真實前端 bug：實體連結成功後畫面重繪順序寫反（先重畫候選清單、後更新實體快取），導致新建實體不會立即出現在其他候選的「連到既有實體」下拉選單，需再操作一次才顯示；已修正為先 `loadEntities()` 再 `loadMentions()`，修正後重新整理頁面驗證選單正確顯示新實體。

從一筆已接受候選拆出 Event 與 Outcome 節點，建立 `has_outcome` 正式關係（assertion_mode=explicit_in_source，引用該候選 evidence_id）成功；建立 tag「shrinkage／收縮」與其 broader 為「drying shrinkage／乾燥收縮」成功；在 Event 節點填 `event_time=day 7` 後，`/timeline` 頁面正確把它列入「已知事件時間」區塊、與「抓取時間」區塊（101 筆，含截斷提示）分開顯示。rerank 路徑（bge-reranker）本次僅程式與 mock 測試驗證，未在瀏覽器實測（預期單次查詢需十幾秒，超出本輪互動測試時間）。詳見 [知識圖譜深化與語意檢索](docs/知識圖譜深化與語意檢索20260913.md)，含完整限制聲明。


## 公開展示頁重新設計（2026-09-13）
依使用者要求，以「用途→互動使用→技術架構」重設 docs/index.html，樣式及行為拆至 docs/showcase.css、docs/showcase.js，無新增前端相依套件。首屏說明文件分類／人工確認／知識整理用途；七類教學示例、即時命中數、零命中／同分棄權、人工修正與後續處理建議在瀏覽器運行，確認僅存當次頁面、不寫本機資料庫。架構五階段可點選查看輸入／輸出／技術／原始碼，區分自訓基準、離線 E5 級聯實驗與公開簡化規則。保留7筆公開文件靜態快照與搜尋，移除原頁對未取得來源的概括描述。公開網址及 QR 不變；此次僅工作目錄修改，未推送部署。

驗證：node --check 通過；使用既有 Playwright＋無頭 Edge 驗證七類教學例、兩種棄權、人工修正、空輸入停用、重設、架構切換、搜尋及組合篩選，無 pageerror。390px viewport 無水平溢出；桌面1440px及手機截圖保存 data/reports/showcase-desktop.png、showcase-mobile.png。初次測試發現衝突例命中不平衡，修正後上述檢查通過。截圖檢視工具受沙箱 helper 故障阻擋，未完成截圖人工視覺核對。未改 Python、分類資料或人工標籤；未重跑後端54項測試，頁上54為既有歷史快照。


## 展示頁檔案上傳與模型說明（2026-09-13）
公開頁新增瀏覽器本機檔案讀取：PDF、UTF-8 TXT／MD／CSV，10 MiB 上限，前12,000字元；PDF最多前10頁，不含OCR。以固定PDF.js 4.10.38解析，模組／worker／Apache授權存docs/vendor/pdfjs，來源 https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/ ，API參考 https://mozilla.github.io/pdf.js/examples/ （本輪查核官方範例）。文件內容不送伺服器、不寫正式清冊。載入失敗清除舊結果；切換示例、重設或手動編輯使舊非同步結果失效。上傳後仍使用頁面簡化關鍵詞規則，不宣稱呼叫E5或自訓模型。
架構說明改用「多語言檢索模型把文件與用途描述轉向量找候選、重排模型逐對比較內容與候選」，保留標題優先及重排僅用於內容的設計。本機實驗與公開規則能力分開。
node語法與無頭Edge實測通過：文字檔、真實文字PDF、截斷、非法UTF-8、空檔、不支援副檔名、超大檔、損毀PDF、重設與模型說明。未改後端／資料，未推送公開頁。


## 系統架構圖展示（2026-09-13）
展示頁技術區新增明確架構：A公開GitHub Pages瀏覽器層、B本機JavaScript介面→HTTP/JSON→FastAPI→用途分類／雙路檢索／知識整理→SQLite及檔案儲存、C用途分類模型離線實驗。另畫CLI批次資料準備，標明非自動佇列、公開頁無本機API連線，圖譜使用SQLite並非另有圖資料庫。補上分類與檢索分離、人工證據關卡、新文件衍生資料更新的設計理由。保留可點選模組詳情與上傳體驗。此次為現有設計呈現，不改模型策略或後端。
驗證：無頭Edge檢查架構分層、三個服務區塊、模組切換；1440／390px皆無水平溢出。手機架構截圖data/reports/system-architecture-mobile.png。未推送公開頁。


## QR、真實模型試用與流程自動化（2026-09-13）
使用者確認展示驗收完成。README加入docs/assets/showcase-qr.svg並推送5074716。新增獨立cement.demo_api（8023）與inference，僅提供有界文字推論、單請求鎖及靜態頁；真實自訓／E5／內容BGE皆實測HTTP200。公開GitHub Pages仍無模型運算，按鈕依同站能力啟用，送出前明示文字傳送。
新增cement.evaluation：就緒檢查、21份未代填的來源分散開發審核包、排除訓練曝光／過期審核的舊holdout比較。有效比較僅3份，不能宣稱七類成效；有效train/test membership仍不足，2:8混合訓練未完成。
新增cement.pipeline：已下載文件逐份解析→FTS→弱候選→圖譜候選，可選語意索引；狀態／日誌／resume、每步2次上限、600秒timeout與全資料根鎖。實跑22份解析＋3階段全部完成，修復search.reindex交易內巢狀連線鎖定。全庫513、parsed414、人工label12不變。此次未更新語意快取；不自動爬網或訓練。
59項測試與瀏覽器模型試用通過。免費部署D-009：HF CPU Basic新建運算Space需付費方案；免費ZeroGPU需驗證email且帳號超過30天，僅Gradio，資格／移植尚待確認；Render512MB不推薦E5＋重排。詳細研究、路徑、命令、實測與限制見 [模型試用評估與自動流程](docs/模型試用評估與自動流程20260913.md)。保留根目錄不明來源的qr-code.svg未納入提交。


## 部署後展示頁排版整理（2026-09-14）
依使用者最新部署與內容重新整理：上傳／文字置左、真實模型試用置右；關鍵詞規則及人工確認改為可展開比较；架構優先顯示GitHub Pages→HF ZeroGPU→SSE結果，本機完整架構與模組詳情保留於折疊區。成果置於範例清冊之前，12份人工查核表為主、81份LLM一致性診斷另展開；保留數據，修正75%涵蓋率不是全方法最高的矛盾，區分LLM留出一致性與獨立人工真值。頁尾標註數量依最新交接更新414（402LLM＋12人工）；舊7筆範例維持歷史快照。未改推論API、模型參數或資料。
驗證：JS語法、上傳TXT、人工確認、模組切換、範例搜尋，1440／768／390px無水平溢出；HF可用狀態在本輪排版測試採mock，未消耗GPU推論額度或重測模型成效。實際檢視桌面互動與手機成果截圖後，調整手機表格欄寬及標題對齊。截圖位於data/reports/layout-20260914-*.png。本輪未推送。
