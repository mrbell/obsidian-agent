"""Tests for LocalEmbedder — mocks sentence_transformers to avoid loading weights."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import numpy as np

# ---------------------------------------------------------------------------
# Mock sentence_transformers BEFORE importing LocalEmbedder so the real model
# is never downloaded or loaded during tests.
# ---------------------------------------------------------------------------
_st_mock = MagicMock()
sys.modules.setdefault("sentence_transformers", _st_mock)

from obsidian_agent.embeddings.base import Embedder  # noqa: E402
from obsidian_agent.embeddings.local import LocalEmbedder  # noqa: E402


class TestEmbedderABC:
    def test_local_embedder_is_embedder(self) -> None:
        assert issubclass(LocalEmbedder, Embedder)


class TestLocalEmbedder:
    def _make_embedder(self, n_texts: int = 2, dim: int = 384) -> LocalEmbedder:
        fake = np.zeros((n_texts, dim), dtype="float32")
        _st_mock.SentenceTransformer.return_value.encode.return_value = fake
        return LocalEmbedder()

    def test_dimension(self) -> None:
        embedder = self._make_embedder()
        assert embedder.dimension == 384

    def test_embed_returns_list_of_lists(self) -> None:
        embedder = self._make_embedder(n_texts=2)
        result = embedder.embed(["hello world", "another text"])
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], list)

    def test_embed_correct_vector_length(self) -> None:
        embedder = self._make_embedder(n_texts=3)
        result = embedder.embed(["a", "b", "c"])
        assert all(len(v) == 384 for v in result)

    def test_embed_returns_floats(self) -> None:
        embedder = self._make_embedder(n_texts=1)
        result = embedder.embed(["test sentence"])
        assert all(isinstance(x, float) for x in result[0])

    def test_embed_empty_list_returns_empty(self) -> None:
        embedder = self._make_embedder(n_texts=0)
        result = embedder.embed([])
        assert result == []

    def test_embed_delegates_to_sentence_transformer(self) -> None:
        embedder = self._make_embedder(n_texts=2)
        texts = ["first", "second"]
        embedder.embed(texts)
        # Use assert_called_with (not once) since the mock is module-level and
        # accumulates calls from other tests.
        _st_mock.SentenceTransformer.return_value.encode.assert_called_with(
            texts, convert_to_numpy=True
        )
