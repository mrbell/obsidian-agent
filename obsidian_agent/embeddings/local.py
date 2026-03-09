from __future__ import annotations

from sentence_transformers import SentenceTransformer

from obsidian_agent.embeddings.base import Embedder


class LocalEmbedder(Embedder):
    """sentence-transformers embedder using all-MiniLM-L6-v2 (384-dim, ~80MB).

    Model weights are downloaded from Hugging Face on first use and cached
    locally. Subsequent runs require no network access.
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vectors]

    @property
    def dimension(self) -> int:
        return 384
