"""Harness de simulación: mide RAM, latencia, tokens y coste API estimado.

Sirve para decidir infraestructura ANTES de contratar nada:
  - RAM real residente del proceso con la combinación de backends elegida.
  - Latencia por etapa (embed / rerank) y end-to-end, p50/p95.
  - Tokens por consulta que se enviarían a una API + coste estimado.
  - Proyección de coste mensual a varios volúmenes de consulta.

Ejemplos:
  # Local puro (lo que corres hoy en GPU), midiendo RAM y latencia:
  CUDA_VISIBLE_DEVICES="" .venv/bin/python -m scripts.bench_backends --device cpu

  # Simular API: backend local + metering + latencia de red de 120ms:
  CUDA_VISIBLE_DEVICES="" .venv/bin/python -m scripts.bench_backends \
      --device cpu --sim-latency-ms 120

  # API real (requiere ARIADNA_API_KEY):
  .venv/bin/python -m scripts.bench_backends --embed-backend api --rerank-backend api
"""

from __future__ import annotations

import argparse
import os
import statistics
import time

DEFAULT_QUERIES = [
    "¿qué dice el corpus sobre la gestión del riesgo y el position sizing?",
    "explica la diferencia entre análisis técnico y fundamental",
    "cómo gestionar las emociones y el miedo al operar",
    "estrategias de entrada y salida en tendencia",
    "qué es el sicofante y cómo afecta a la toma de decisiones",
    "errores comunes de un trader principiante",
    "importancia del backtesting y el journaling",
    "cómo identificar soportes y resistencias relevantes",
]


def _rss_mb() -> float:
    """RSS del proceso actual en MB, leyendo /proc/self/status (sin deps)."""
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024.0
    return -1.0


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((p / 100.0) * (len(s) - 1)))
    return s[k]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--embed-backend", default="local", choices=["local", "onnx", "api"])
    ap.add_argument("--rerank-backend", default="local", choices=["local", "api", "sim"])
    ap.add_argument("--device", default=os.getenv("ARIADNA_EMBED_DEVICE", "cpu"),
                    help="cuda | cpu (solo afecta backend local)")
    ap.add_argument("--sim-latency-ms", type=float, default=0.0,
                    help="latencia de red simulada por llamada (para emular API)")
    ap.add_argument("--n", type=int, default=3, help="repeticiones de la batería de queries")
    ap.add_argument("--warmup", type=int, default=2, help="queries de calentamiento (descartadas)")
    args = ap.parse_args()

    os.environ.setdefault("ARIADNA_EMBED_DEVICE", args.device)

    import logging

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from ariadna import config
    from ariadna.backends import make_embedder, make_reranker
    from ariadna.metering import get_meter
    from ariadna.search import Searcher

    print("=" * 70)
    print("ARIADNA · bench de backends (simulación pre-contratación)")
    print("=" * 70)
    print(f"embed_backend={args.embed_backend}  rerank_backend={args.rerank_backend}  "
          f"device={args.device}  sim_latency={args.sim_latency_ms}ms")
    print(f"precios: embed={config.PRICE_EMBED_PER_MTOK}$/Mtok  "
          f"rerank={config.PRICE_RERANK_PER_MTOK}$/Mtok")
    print("-" * 70)

    rss_start = _rss_mb()
    t_load0 = time.perf_counter()

    # Metering SIEMPRE on en el bench (para contar tokens/coste aunque sea local).
    embedder = make_embedder(args.embed_backend, metering=True, sim_latency_ms=args.sim_latency_ms)
    reranker = make_reranker(args.rerank_backend, metering=True, sim_latency_ms=args.sim_latency_ms)
    searcher = Searcher(embedder=embedder, reranker=reranker)

    load_s = time.perf_counter() - t_load0
    rss_loaded = _rss_mb()

    print(f"RAM antes de cargar:   {rss_start:8.0f} MB")
    print(f"RAM con modelos+store: {rss_loaded:8.0f} MB   (Δ {rss_loaded - rss_start:+.0f} MB)")
    print(f"Tiempo de carga/warm:  {load_s:8.1f} s")
    print("-" * 70)

    # Warmup (no contabiliza en percentiles; reseteamos meter tras él).
    for i in range(args.warmup):
        searcher.search_hybrid(DEFAULT_QUERIES[i % len(DEFAULT_QUERIES)])
    get_meter().reset()

    total_latencies: list[float] = []
    n_queries = 0
    for _ in range(args.n):
        for q in DEFAULT_QUERIES:
            t0 = time.perf_counter()
            searcher.search_hybrid(q)
            total_latencies.append((time.perf_counter() - t0) * 1000.0)
            n_queries += 1

    meter = get_meter()
    embed_ms = [s * 1000 for s in meter.embed_latencies]
    rerank_ms = [s * 1000 for s in meter.rerank_latencies]

    print(f"Consultas medidas: {n_queries}")
    print()
    print(f"{'etapa':<14}{'p50 (ms)':>12}{'p95 (ms)':>12}{'media (ms)':>12}")
    for name, vals in (("embed", embed_ms), ("rerank", rerank_ms), ("end-to-end", total_latencies)):
        if vals:
            print(f"{name:<14}{_pct(vals,50):>12.1f}{_pct(vals,95):>12.1f}{statistics.mean(vals):>12.1f}")
    print("-" * 70)

    # Tokens y coste por consulta.
    embed_tok_q = meter.embed_tokens / n_queries
    rerank_tok_q = meter.rerank_tokens / n_queries
    cost_q = meter.cost_usd() / n_queries
    print(f"tokens/consulta:  embed={embed_tok_q:.0f}   rerank={rerank_tok_q:.0f}   "
          f"total={(embed_tok_q + rerank_tok_q):.0f}")
    print(f"coste API estimado/consulta: ${cost_q:.6f}")
    print("-" * 70)
    print("Proyección coste API (solo inferencia, sin VPS):")
    print(f"{'consultas/día':>16}{'$/mes':>12}{'$/año':>12}")
    for qpd in (100, 500, 1000, 5000):
        monthly = cost_q * qpd * 30
        print(f"{qpd:>16}{monthly:>12.2f}{monthly * 12:>12.2f}")
    print("=" * 70)
    print("Lectura:")
    print(f"  · Local: RAM ~{rss_loaded:.0f} MB residente 24/7 (coste = VPS, inferencia $0).")
    print("  · API:   VPS más pequeño (sin modelos en RAM) + coste de arriba por uso.")
    print("  · El cruce depende de tu volumen real de consultas/día.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
