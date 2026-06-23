"""Factory de backends de inferencia: local (sentence-transformers) | api (HTTP).

Punto único donde se decide qué embedder/reranker construir, según config (o un
override explícito, útil para el bench). Si el metering está activo, envuelve el
backend resultante para contar tokens/tiempo/coste y simular latencia de red.

`local` mantiene el comportamiento previo idéntico (DenseEmbedder / Reranker).
"""

from __future__ import annotations

import logging
from typing import Any

from ariadna import config

log = logging.getLogger(__name__)


def _maybe_meter_embedder(inner: Any, metering: bool | None, sim_latency_ms: float | None) -> Any:
    enabled = config.METERING_ENABLED if metering is None else metering
    if not enabled:
        return inner
    from ariadna.metering import MeteredEmbedder, get_meter

    lat = config.SIM_LATENCY_MS if sim_latency_ms is None else sim_latency_ms
    return MeteredEmbedder(inner, get_meter(), lat)


def _maybe_meter_reranker(inner: Any, metering: bool | None, sim_latency_ms: float | None) -> Any:
    enabled = config.METERING_ENABLED if metering is None else metering
    if not enabled:
        return inner
    from ariadna.metering import MeteredReranker, get_meter

    lat = config.SIM_LATENCY_MS if sim_latency_ms is None else sim_latency_ms
    return MeteredReranker(inner, get_meter(), lat)


def make_embedder(
    backend: str | None = None,
    *,
    metering: bool | None = None,
    sim_latency_ms: float | None = None,
) -> Any:
    backend = backend or config.EMBED_BACKEND
    if backend == "api":
        from ariadna.backends.api import ApiEmbedder

        inner: Any = ApiEmbedder()
    elif backend == "local":
        from ariadna.embeddings import DenseEmbedder

        inner = DenseEmbedder()
    elif backend == "onnx":
        from ariadna.backends.onnx import OnnxEmbedder

        inner = OnnxEmbedder()
    else:
        raise ValueError(f"EMBED_BACKEND desconocido: {backend!r} (usa 'local', 'onnx' o 'api')")
    # La sim-latency del meter solo modela API sobre backend LOCAL; en 'api' la
    # latencia es real (red) y no debe sumarse de mentira.
    meter_lat = sim_latency_ms if backend == "local" else 0.0
    return _maybe_meter_embedder(inner, metering, meter_lat)


def make_reranker(
    backend: str | None = None,
    *,
    metering: bool | None = None,
    sim_latency_ms: float | None = None,
) -> Any:
    backend = backend or config.RERANK_BACKEND
    if backend == "api":
        from ariadna.backends.api import ApiReranker

        inner: Any = ApiReranker()
    elif backend == "local":
        from ariadna.reranker import Reranker

        inner = Reranker()
    elif backend == "sim":
        from ariadna.backends.sim import SimReranker

        lat = config.SIM_LATENCY_MS if sim_latency_ms is None else sim_latency_ms
        inner = SimReranker(lat or 200.0)
    else:
        raise ValueError(f"RERANK_BACKEND desconocido: {backend!r} (usa 'local', 'api' o 'sim')")
    # En 'sim' la latencia la inyecta SimReranker; en 'api' la pone la red real.
    # El meter solo añade sim-latency cuando el backend es local.
    sim_latency_ms = sim_latency_ms if backend == "local" else 0.0
    return _maybe_meter_reranker(inner, metering, sim_latency_ms)
