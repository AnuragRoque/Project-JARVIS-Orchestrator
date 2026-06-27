"""Text embedding via a local sentence-transformers model.

The model runs entirely on-device (no network at inference time; only the
first-ever load may download weights). We lazily construct it so importing this
module is cheap and never fails when the optional dependency is missing.
"""
from __future__ import annotations

import threading

from ..logging_setup import get_logger

log = get_logger("semantic.embedder")

DEFAULT_MODEL = "all-MiniLM-L6-v2"  # 384-dim, small & fast


def dependencies_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


class Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()
        self._dim: int | None = None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                log.info("Loading embedding model %s…", self.model_name)
                self._model = SentenceTransformer(self.model_name)
                self._dim = self._model.get_sentence_embedding_dimension()
                log.info("Embedding model ready (dim=%d)", self._dim)
        return self._model

    @property
    def dim(self) -> int:
        self._ensure_model()
        return self._dim or 384

    def encode(self, texts: list[str]):
        """Return an (N, dim) float32 numpy array of L2-normalised vectors."""
        import numpy as np
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        model = self._ensure_model()
        vecs = model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vecs.astype("float32")

    def encode_one(self, text: str):
        return self.encode([text])[0]
