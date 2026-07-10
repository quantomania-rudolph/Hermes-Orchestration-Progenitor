"""Local embedding backend for Hermes RAG (NoLlama has no embed API)."""

from __future__ import annotations

import numpy as np

from hermes_config import EMBED_MODEL_DEFAULT

_ST_MODEL = None


def _get_model():
    global _ST_MODEL
    if _ST_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for RAG embeddings: "
                "pip install sentence-transformers"
            ) from exc
        _ST_MODEL = SentenceTransformer(EMBED_MODEL_DEFAULT)
    return _ST_MODEL


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    if isinstance(vectors, np.ndarray):
        return vectors.astype(np.float32).tolist()
    return [np.asarray(v, dtype=np.float32).tolist() for v in vectors]


def embed_query(text: str) -> np.ndarray:
    vec = np.asarray(embed_texts([text])[0], dtype=np.float32)
    norm = float(np.linalg.norm(vec))
    if norm <= 0:
        raise ValueError("embedding returned zero vector")
    return vec / norm
