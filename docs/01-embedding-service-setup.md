# Embedding 服務架設筆記

> 目的：第二階段 AI 助理第一步，架設 `multilingual-e5-large-instruct` 的 Modal embedding 推論服務。供複習用。

## 1. 環境準備

```bash
pip install modal        # 官方 CLI/SDK，PyPI 套件名就是 modal
modal setup               # 瀏覽器登入授權，產生 token 存在本機 ~/.modal.toml
pip install fastapi       # 本機也要裝，因為 modal serve/deploy 會先用本機 Python 解析整支檔案
```

**`modal setup` 在做什麼**：讓「你的電腦」跟「Modal 平台」互相認得對方，之後下 `modal serve`/`modal deploy`/`modal secret` 等指令才有權限。這跟後面的 API key 是兩件不同的事（見第 4 節）。

**GPU 功能需要付款方式**：第一次用 `gpu="T4"` 跑 `modal serve` 時，如果帳號沒掛信用卡會報錯：
```
Please add a payment method to use T4 GPU functions.
```
要去 Modal 網站 Billing 頁面加卡片才能繼續，即使 Modal 有免費額度也一樣要求掛卡。

## 2. 產生 API Key 並存成 Modal Secret

這組 key 不是 Modal 平台的東西，是**我們自己發明**用來保護 embedding API 的密碼（見第 4 節解釋）。

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
複製輸出的字串，拿去建立 secret：
```bash
modal secret create embedding-api-key EMBEDDING_API_KEY=<剛剛產生的字串>
```

⚠️ **這串字串只會在你產生的那一刻看到一次**，Modal 基於安全考量不會讓你把已建立的 secret 內容讀回來。要自己存一份（筆記、密碼管理工具），不要只存在終端機的捲動歷史裡。如果忘記存，只能重新產生一組新的，用 `--force` 覆蓋舊的 secret：
```bash
modal secret create embedding-api-key EMBEDDING_API_KEY=<新字串> --force
```
覆蓋後要回到 `modal serve` 的終端機按 `Ctrl+C` 重新啟動，才會讀到新值。

## 3. 選模型與固定 revision

模型：`intfloat/multilingual-e5-large-instruct`（MIT 授權，1024 維向量）。

規格要求固定 commit hash（不要用會變動的 `main`），避免之後 repo 被竄改、載入到被換掉的權重：
- 去 Hugging Face 模型頁 → `Files and versions` → 複製最新 commit 的 40 字元 hash
- 用之前最好先確認那個 commit 改了什麼（可以看 commit 頁面的 diff），確保不是可疑的變更
- 即使那個 commit 只改了 README，也完全可以用——因為 HF repo 是 git，任何 commit 都代表當下完整的 repo 狀態（含權重檔案）

目前用的 revision：`274baa43b0e13e37fafa6428dbc7938e62e5c439`

## 4. 兩種「驗證/key」的差別（常搞混，要記住）

| | `modal setup` 的 token | `embedding-api-key`（`EMBEDDING_API_KEY`） |
| --- | --- | --- |
| 驗證對象 | 你的電腦 ↔ Modal 平台 | 任何呼叫方 ↔ 我們自己寫的 API |
| 存放位置 | 本機 `~/.modal.toml` | Modal Secret（容器內變成環境變數） |
| 用途 | 讓你有權限部署/管理 Modal 上的資源 | 擋掉沒有這組密碼的人亂打你的公開 endpoint（避免白嫖 GPU） |
| 跟誰無關 | 跟 API 要不要驗證使用者無關 | 跟你有沒有登入 Modal CLI 無關 |

`modal serve`/`modal deploy` 印出來的網址旁邊會標 `(unauthenticated)`，意思是「Modal 平台本身沒有在前面多加一層驗證」，**不代表我們自己程式裡寫的 key 檢查沒有用** —— 那是我們自己在 `embed()` 函式裡用 `hmac.compare_digest` 做的，跟 Modal 平台層級的標籤是兩回事。

## 5. `embedding_app.py` 的程式碼要點

### `serve` 跟 `deploy` 的差別

| | `modal serve` | `modal deploy` |
| --- | --- | --- |
| 用途 | 開發測試 | 正式上線 |
| 網址 | 暫時的 | 固定的 |
| 關掉終端機 | 部署跟著消失 | 留在雲端持續運作（閒置縮到 0，不計費） |
| 改檔案 | 自動重新載入 | 要重新執行 `deploy` 才會更新 |

### 曾經抓到的 5 個問題跟修法

1. **authorization 讀錯位置**：FastAPI 的路徑函式裡，簡單型別參數沒特別宣告的話，預設當成 query parameter，不是 header。原本寫 `authorization: str = None` 根本讀不到 `Authorization` header，驗證永遠失敗。
   → 改成 `authorization: str = Header(None)`，比較字串要用 `hmac.compare_digest`（固定時間比較，防 timing attack），不要直接用 `!=`。

2. **E5 前綴沒區分查詢/文件**：`multilingual-e5-*-instruct` 系列，查詢要加指令前綴（`Instruct: {任務說明}\nQuery: {問題}`），文件段落不加前綴，這樣檢索品質才會準。
   → API 多加 `kind`（`"query"` 或 `"passage"`）欄位，依照種類決定要不要加前綴。
   → **待確認**：前綴格式是憑記憶寫的，要去 model card 對一次官方範例程式碼確認完全一致。

3. **沒有正規化**：`.encode()` 預設不會把向量正規化成單位長度。
   → 加 `normalize_embeddings=True`，這樣之後 pgvector 用 cosine 或內積算距離結果會一致，內積運算也比 cosine 省算力。

4. **冷啟動要重新下載模型**：原本 `load_model` 是容器啟動時才向 Hugging Face 下載模型（約 2GB），每次冷啟動都要等。
   → 寫一個 `download_model()` 函式，接在 `image.pip_install(...).run_function(download_model)`，build image 的時候就把權重下載進 image 裡，冷啟動直接讀本機磁碟，不用等網路。

5. **沒有限制輸入數量**：沒限制一次傳多少 `texts`，大量請求可能把 GPU 記憶體塞爆。
   → 加 `MAX_BATCH = 64`，超過直接回 422。

## 6. 完整程式碼（目前版本）

```python
import hmac
import os

import modal
from fastapi import Header, HTTPException

app = modal.App("leave-system-inference-embedding")

MODEL_NAME = "intfloat/multilingual-e5-large-instruct"
MODEL_REVISION = "274baa43b0e13e37fafa6428dbc7938e62e5c439"
TASK_DESCRIPTION = "根據使用者的問題，找出最相關的公司規章段落"
MAX_BATCH = 64


def download_model():
    from sentence_transformers import SentenceTransformer

    SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION)


image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "sentence-transformers==3.0.1",
        "torch==2.3.1",
        "fastapi[standard]",
    )
    .run_function(download_model)
)


@app.cls(
    image=image,
    gpu="T4",
    secrets=[modal.Secret.from_name("embedding-api-key")],
    scaledown_window=60,
)
class Embedder:
    @modal.enter()
    def load_model(self):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION)

    @modal.fastapi_endpoint(method="POST")
    def embed(self, request: dict, authorization: str = Header(None)):
        expected = f"Bearer {os.environ['EMBEDDING_API_KEY']}"
        if not authorization or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="Unauthorized")

        kind = request.get("kind", "passage")
        texts = request.get("texts", [])
        if not texts:
            raise HTTPException(status_code=422, detail="texts 不可為空")

        if len(texts) > MAX_BATCH:
            raise HTTPException(status_code=422, detail=f"一次最多 {MAX_BATCH} 筆")

        if kind == "query":
            texts = [f"Instruct: {TASK_DESCRIPTION}\nQuery: {t}" for t in texts]
        # kind == "passage" 不加前綴，這是 multilingual-e5-*-instruct 系列的慣例

        embeddings = self.model.encode(texts, normalize_embeddings=True).tolist()
        return {"embeddings": embeddings, "model": MODEL_NAME}
```

## 7. 測試方式

```powershell
# 不帶 key，應該 401
curl.exe -X POST "<modal serve 印出的網址>" -H "Content-Type: application/json" -d '{"texts": ["test"], "kind": "passage"}'

# 帶正確 key，應該回傳向量
curl.exe -X POST "<modal serve 印出的網址>" -H "Content-Type: application/json" -H "Authorization: Bearer <你的EMBEDDING_API_KEY>" -d '{"texts": ["test"], "kind": "passage"}'
```

## 8. 待辦 / 還沒做的事

- [x] 用 `Invoke-RestMethod` 實際驗證「不帶 key 回 401、帶 key 成功回傳向量」（Windows 沒有內建 `curl.exe` 時改用這個）
- [ ] 去 model card 核對 E5-instruct 的前綴格式是否跟程式碼裡寫的一致
- [ ] dev/prod 用不同的 Modal 環境與不同組 key（目前只有一個 dev 用的 secret）
- [ ] 之後才做：對話模型（Gemma 4）部署、後端串接、`leave-system-backend` 那邊的 migration 與檢索邏輯
