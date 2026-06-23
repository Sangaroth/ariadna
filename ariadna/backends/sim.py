"""Backend de simulación: emula la latencia de una API SIN modelo ni red real.

Sirve para medir el end-to-end de 'embed local + rerank API' antes de contratar:
el rerank no ejecuta el cross-encoder (que en CPU tarda ~4.4s) sino que solo
inyecta la latencia de red de 1 call y devuelve los candidatos por su score
dense original. Mide TODO el pipeline real (embed, qdrant, wiki, formato) más
la latencia que tendría el único POST de rerank a la API.
"""

from __future__ import annotations

import time
from typing import Any, Callable


class SimReranker:
    """Rerank simulado: 1 'call' = sleep(sim_latency); orden = score dense."""

    def __init__(self, sim_latency_ms: float = 200.0) -> None:
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
        if self.sim_latency_ms > 0:
            time.sleep(self.sim_latency_ms / 1000.0)  # 1 round-trip de red, no N
        for c in candidates:
            c["rerank_score"] = float(c.get("score", 0.0))
        candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
        if top_k is not None:
            candidates = candidates[:top_k]
        return candidates
