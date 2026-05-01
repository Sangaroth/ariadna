"""Cross-encoder reranker sobre top-N de retrieval dense.

Validado en pilot v2 (2026-05-01): rescata chunks que dense entierra en
posiciones 6-18 ante queries adversariales (coloquial, paráfrasis lejanas).
Detalle en docs/eval/results_v2.md.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from sentence_transformers import CrossEncoder

from ariadna.config import RERANKER_MAX_LENGTH, RERANKER_MODEL_NAME

log = logging.getLogger(__name__)


def _default_text_for_chunk(c: dict[str, Any]) -> str:
    """theme + content del chunk -- mismo formato que recibe el LLM downstream."""
    return f"{c.get('theme', '')}\n{c.get('content', '')}"


class Reranker:
    """Wrapper sobre BGE-reranker-v2-m3 (cross-encoder multilingüe)."""

    def __init__(
        self,
        model_name: str = RERANKER_MODEL_NAME,
        max_length: int = RERANKER_MAX_LENGTH,
    ) -> None:
        log.info("Cargando reranker %s (max_length=%d)...", model_name, max_length)
        self.model = CrossEncoder(model_name, max_length=max_length)
        log.info("Reranker listo.")

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int | None = None,
        text_fn: Callable[[dict[str, Any]], str] | None = None,
    ) -> list[dict[str, Any]]:
        """Re-puntua candidates con cross-encoder y devuelve ordenados.

        Mutación: cada candidate gana un campo 'rerank_score' (float).
        El campo 'score' original (cosine de dense) se preserva.

        Args:
            query: texto de la pregunta del usuario.
            candidates: lista de dicts con al menos 'theme' y 'content' (o usa text_fn).
            top_k: si se pasa, recorta a los top_k tras reordenar.
            text_fn: cómo extraer el texto de cada candidate. Por defecto theme+content.

        Returns:
            Misma lista (mutada) ordenada por rerank_score desc, opcionalmente recortada.
        """
        if not candidates:
            return []
        text_fn = text_fn or _default_text_for_chunk
        pairs = [[query, text_fn(c)] for c in candidates]
        scores = self.model.predict(pairs, show_progress_bar=False)
        for c, s in zip(candidates, scores, strict=True):
            c["rerank_score"] = float(s)
        candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
        if top_k is not None:
            candidates = candidates[:top_k]
        return candidates
