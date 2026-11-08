import os
import modal
from fastapi import Header, HTTPException
import hmac

app = modal.App("leave-system-inference-embedding")

MODEL_NAME = "intfloat/multilingual-e5-large-instruct"
MODEL_REVISION =  "274baa43b0e13e37fafa6428dbc7938e62e5c439"
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
    scaledown_window=60
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