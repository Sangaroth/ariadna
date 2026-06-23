"""Backends de inferencia vía HTTP (embeddings + rerank).

Embeddings: endpoint OpenAI-compatible (POST {base}/embeddings) — sirve para
DeepInfra, y casi cualquier proveedor que exponga la API de OpenAI.
Rerank: endpoint estilo DeepInfra inference (query + documents -> scores).

Los vectores se L2-normalizan en cliente para casar con los del índice local
(DenseEmbedder normaliza con norma 1 para coseno). Si tu proveedor ya devuelve
normalizado, normalizar de nuevo es idempotente.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable

import httpx
import numpy as np

from ariadna import config
from ariadna.config import EMBED_DIM
from ariadna.rerank_text import default_text_for_chunk as _default_text_for_chunk

log = logging.getLogger(__name__)


def _l2_normalize(arr: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (arr / norms).astype(np.float32)


class ApiEmbedder:
    """Embeddings vía endpoint OpenAI-compatible. Misma interfaz que DenseEmbedder."""

    def __init__(self) -> None:
        if not config.API_KEY:
            log.warning("ARIADNA_API_KEY vacío: el backend api fallará al llamar al proveedor.")
        self.dim = EMBED_DIM
        self._url = f"{config.API_BASE_URL.rstrip('/')}/embeddings"
        self._headers = {"Authorization": f"Bearer {config.API_KEY}"}
        log.info("ApiEmbedder: %s (modelo %s)", self._url, config.API_EMBED_MODEL)

    def embed(
        self,
        texts: list[str] | Iterable[str],
        batch_size: int = 64,
        show_progress: bool = False,
    ) -> np.ndarray:
        texts = list(texts)
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            resp = httpx.post(
                self._url,
                headers=self._headers,
                json={"model": config.API_EMBED_MODEL, "input": chunk},
                timeout=config.API_TIMEOUT_S,
            )
            resp.raise_for_status()
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            out.extend(d["embedding"] for d in data)
        return _l2_normalize(np.asarray(out, dtype=np.float32))

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed([query], batch_size=1)[0]


class ApiReranker:
    """Rerank vía endpoint HTTP (query + documents -> scores). Interfaz = Reranker."""

    def __init__(self) -> None:
        if not config.API_KEY:
            log.warning("ARIADNA_API_KEY vacío: el backend api fallará al llamar al proveedor.")
        self._url = config.API_RERANK_URL
        self._headers = {"Authorization": f"Bearer {config.API_KEY}"}
        log.info("ApiReranker: %s", self._url)

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int | None = None,
        text_fn: Callable[[dict[str, Any]], str] | None = None,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []
        tf = text_fn or _default_text_for_chunk
        docs = [tf(c) for c in candidates]
        # DeepInfra inference espera "queries" (lista) + "documents"; devuelve "scores".
        resp = httpx.post(
            self._url,
            headers=self._headers,
            json={"queries": [query], "documents": docs},
            timeout=config.API_TIMEOUT_S,
        )
        resp.raise_for_status()
        body = resp.json()
        # DeepInfra inference devuelve {"scores": [...]}; toleramos variantes comunes.
        scores = body.get("scores") or body.get("results") or body.get("data")
        if scores and isinstance(scores[0], dict):
            scores = [s.get("score", s.get("relevance_score", 0.0)) for s in scores]
        for c, s in zip(candidates, scores, strict=True):
            c["rerank_score"] = float(s)
        candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
        if top_k is not None:
            candidates = candidates[:top_k]
        return candidates
