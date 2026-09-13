---
title: Cement Purpose Classifier Demo
emoji: 🧱
colorFrom: gray
colorTo: orange
sdk: gradio
sdk_version: 5.9.1
app_file: app.py
pinned: false
license: mit
---

# 水泥文件用途分類 Demo（ZeroGPU）

這是 [水泥知識文件工作台](https://github.com/pososos/QR-code-design) 的獨立模型試用 Space，只提供分類推論，不含清冊、標註或爬蟲功能，不存任何輸入。

方法：多語言 E5（intfloat/multilingual-e5-small）做標題→目錄→內容分階段檢索，內容階段可選 BAAI/bge-reranker-v2-m3 重排。門檻是固定的開發用值（0.8/0.02，重排 0/1），沒有校準也沒有獨立驗證，只是把本機已做過的實驗連成一個可以按的展示。

## 部署方式

1. 建立 Space 時選 SDK = Gradio、Hardware = ZeroGPU。
2. 把本資料夾（`app.py`、`requirements.txt`、本檔）內容推到 Space 的 repo 根目錄：

```powershell
# 在 D:\QR code design\hf_space 目錄下
hf auth login
git init
git remote add space https://huggingface.co/spaces/<你的帳號>/<space名稱>
git add app.py requirements.txt README.md
git commit -m "Add cement purpose classifier demo"
git push space main
```

（或用 `hf upload <你的帳號>/<space名稱> . .` 上傳整個資料夾，效果相同，不需要另外 git init。）

3. 等待 Space 建置完成（第一次要下載 E5 與 reranker 模型，可能需要幾分鐘）。
4. 打開 `https://huggingface.co/spaces/<你的帳號>/<space名稱>` 確認可以輸入文字並得到分類結果。
5. 把 Space 的 API 網址（`https://<你的帳號>-<space名稱>.hf.space`，注意帳號與名稱中的底線/大寫會被正規化成小寫連字號，實際網址以 Space 頁面右下角「Use via API」顯示的為準）回報給我，我再把 `docs/showcase.js` 接上這個端點，讓公開展示頁在偵測到這個 Space 可連線時顯示「呼叫真實模型」的選項。
