"""Metering de inferencia: cuenta tokens, mide tiempos y estima coste API.

Objetivo: poder *simular en local* lo que costaría delegar embeddings/rerank a
una API (DeepInfra/Jina/etc.) ANTES de contratar nada. Envolviendo el backend
local con MeteredEmbedder/MeteredReranker obtienes, por consulta:
  - tokens que se enviarían a la API,
  - coste estimado (tokens x precio),
  - latencia real de inferencia (+ latencia de red simulada opcional).

El tokenizer es el de BGE-M3 (mismo para embedder y reranker, ambos m3). Pesa
unos MB (solo el tokenizer, sin los pesos del modelo), así que estimar coste en
modo api-puro tampoco carga el modelo en RAM.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import numpy as np

from ariadna import config
from ariadna.rerank_text import default_text_for_chunk as _default_text_for_chunk

log = logging.getLogger(__name__)

# --- Tokenizer compartido (lazy) ---
_tokenizer = None


def _get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        from transformers import AutoTokenizer

        log.info("Metering: cargando tokenizer %s para contar tokens...", config.EMBED_MODEL_NAME)
        _tokenizer = AutoTokenizer.from_pretrained(config.EMBED_MODEL_NAME)
    return _tokenizer


def count_tokens(text: str) -> int:
    return len(_get_tokenizer().encode(text, add_special_tokens=True))


def _sleep_sim(latency_ms: float) -> None:
    """Inyecta latencia de red simulada (para sentir el round-trip de una API)."""
    if latency_ms > 0:
        time.sleep(latency_ms / 1000.0)


@dataclass
class Meter:
    """Acumula métricas a través de todas las llamadas de inferencia."""

    embed_calls: int = 0
    embed_texts: int = 0
    embed_tokens: int = 0
    embed_seconds: float = 0.0
    rerank_calls: int = 0
    rerank_pairs: int = 0
    rerank_tokens: int = 0
    rerank_seconds: float = 0.0
    # Muestras por-llamada (segundos) para percentiles.
    embed_latencies: list[float] = field(default_factory=list)
    rerank_latencies: list[float] = field(default_factory=list)

    def record_embed(self, n_texts: int, n_tokens: int, seconds: float) -> None:
        self.embed_calls += 1
        self.embed_texts += n_texts
        self.embed_tokens += n_tokens
        self.embed_seconds += seconds
        self.embed_latencies.append(seconds)

    def record_rerank(self, n_pairs: int, n_tokens: int, seconds: float) -> None:
        self.rerank_calls += 1
        self.rerank_pairs += n_pairs
        self.rerank_tokens += n_tokens
        self.rerank_seconds += seconds
        self.rerank_latencies.append(seconds)

    def cost_usd(self) -> float:
        return (
            self.embed_tokens / 1e6 * config.PRICE_EMBED_PER_MTOK
            + self.rerank_tokens / 1e6 * config.PRICE_RERANK_PER_MTOK
        )

    def reset(self) -> None:
        self.__init__()  # type: ignore[misc]

    def snapshot(self) -> dict[str, Any]:
        return {
            "embed_calls": self.embed_calls,
            "embed_texts": self.embed_texts,
            "embed_tokens": self.embed_tokens,
            "embed_seconds": round(self.embed_seconds, 4),
            "rerank_calls": self.rerank_calls,
            "rerank_pairs": self.rerank_pairs,
            "rerank_tokens": self.rerank_tokens,
            "rerank_seconds": round(self.rerank_seconds, 4),
            "est_cost_usd": self.cost_usd(),
        }


_GLOBAL_METER = Meter()


def get_meter() -> Meter:
    return _GLOBAL_METER


class MeteredEmbedder:
    """Envuelve cualquier embedder (local o api) midiendo tokens/tiempo/coste."""

    def __init__(self, inner: Any, meter: Meter | None = None, sim_latency_ms: float = 0.0) -> None:
        self.inner = inner
        self.meter = meter or get_meter()
        self.sim_latency_ms = sim_latency_ms

    @property
    def dim(self) -> int:
        return self.inner.dim

    def embed(self, texts: list[str] | Iterable[str], **kwargs: Any) -> np.ndarray:
        texts = list(texts)
        toks = sum(count_tokens(t) for t in texts)
        t0 = time.perf_counter()
        out = self.inner.embed(texts, **kwargs)
        _sleep_sim(self.sim_latency_ms)
        self.meter.record_embed(len(texts), toks, time.perf_counter() - t0)
        return out

    def embed_query(self, query: str) -> np.ndarray:
        toks = count_tokens(query)
        t0 = time.perf_counter()
        out = self.inner.embed_query(query)
        _sleep_sim(self.sim_latency_ms)
        self.meter.record_embed(1, toks, time.perf_counter() - t0)
        return out


class MeteredReranker:
    """Envuelve cualquier reranker (local o api) midiendo tokens/tiempo/coste.

    Tokens de rerank = suma sobre candidatos de (tokens(query) + tokens(doc)),
    que es como facturan los rerankers cross-encoder por API.
    """

    def __init__(self, inner: Any, meter: Meter | None = None, sim_latency_ms: float = 0.0) -> None:
        self.inner = inner
        self.meter = meter or get_meter()
        self.sim_latency_ms = sim_latency_ms

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
        q_tokens = count_tokens(query)
        toks = sum(q_tokens + count_tokens(tf(c)) for c in candidates)
        t0 = time.perf_counter()
        out = self.inner.rerank(query, candidates, top_k=top_k, text_fn=text_fn)
        _sleep_sim(self.sim_latency_ms)
        self.meter.record_rerank(len(candidates), toks, time.perf_counter() - t0)
        return out
