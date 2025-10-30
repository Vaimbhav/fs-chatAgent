from __future__ import annotations
from typing import List
from openai import AsyncOpenAI
from agent_app.config import SETTINGS

class Embedder:
    def __init__(self, model: str | None = None):
        if not SETTINGS.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.model = model or SETTINGS.embedding_model
        self.client = AsyncOpenAI(api_key=SETTINGS.openai_api_key)

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        resp = await self.client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]
