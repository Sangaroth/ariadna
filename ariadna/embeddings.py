"""Wrapper de BGE-M3 para embeddings densos via sentence-transformers.

Solo dense. Sparse (BM25/SPLADE/BGE-M3 sparse) evaluado en pilot 2026-05-01
y descartado: no aporta sobre dense puro en este corpus pre-distilled.
La precision adicional la da el reranker cross-encoder (ariadna/reranker.py).
Detalle en docs/RERANKER.md.
"""

from __future__ import annotations

import logging
from typing import Iterable

import numpy as np
from sentence_transformers import SentenceTransformer

from ariadna.config import EMBED_BATCH_SIZE, EMBED_DEVICE, EMBED_DIM, EMBED_MODEL_NAME

log = logging.getLogger(__name__)


class DenseEmbedder:
    """Encapsula BGE-M3 para embedding de textos."""

    def __init__(
        self,
        model_name: str = EMBED_MODEL_NAME,
        device: str = EMBED_DEVICE,
    ) -> None:
        log.info("Cargando modelo de embeddings %s en %s...", model_name, device)
        self.model = SentenceTransformer(model_name, device=device)
        self.dim = self.model.get_sentence_embedding_dimension() or EMBED_DIM
        log.info("Modelo cargado. Dimension: %d", self.dim)

    def embed(
        self,
        texts: list[str] | Iterable[str],
        batch_size: int = EMBED_BATCH_SIZE,
        show_progress: bool = True,
    ) -> np.ndarray:
        """Embedding normalizado (norma 1) para similaridad coseno."""
        if not isinstance(texts, list):
            texts = list(texts)
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        )
        return embeddings.astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """Embedding de una query individual."""
        return self.embed([query], batch_size=1, show_progress=False)[0]
