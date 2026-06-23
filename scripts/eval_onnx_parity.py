"""¿Degrada el ONNX int8 mis resultados? Comparación fp32 (torch) vs ONNX int8.

Mide sobre el ÍNDICE DE PRODUCCIÓN (data/qdrant) y el eval con ground-truth:

  - parity coseno (query fp32 vs int8): fidelidad del vector. ~1.0 = idéntico.
  - overlap@K: ¿el retrieval devuelve los mismos chunks?
  - overlap@PREFETCH (20): el dato decisivo. Si ~1.0, el reranker recibe los
    MISMOS candidatos -> cero degradación downstream, da igual el rerank.
  - recall@K y MRR del chunk fuente: fp32 vs int8 (¿pierde aciertos?).
  - latencia y RAM de cada backend.

El índice se construyó con fp32, así que esto mide el escenario real de desplegar
ONNX int8 SOLO en la query (sin reindexar). Las queries del eval son adversariales
crudas (en prod el plugin las reformula): el recall absoluto saldrá bajo, pero lo
que importa aquí es el DELTA fp32 -> int8.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

import numpy as np

from ariadna.config import PROJECT_ROOT

EVAL_FILES = [
    PROJECT_ROOT / "data" / "eval" / "queries_eval_v1.jsonl",
    PROJECT_ROOT / "data" / "eval" / "queries_eval_v2.jsonl",
]
PREFETCH = 20  # = RERANKER_PREFETCH_N: la ventana que ve el reranker
KS = (5, PREFETCH)


def _rss_mb() -> float:
    for line in open("/proc/self/status"):
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024.0
    return -1.0


def _load_queries() -> list[dict]:
    qs: list[dict] = []
    for f in EVAL_FILES:
        if f.exists():
            qs += [json.loads(ln) for ln in f.read_text().splitlines() if ln.strip()]
    return qs


def _ids(results: list[dict]) -> list[str]:
    # Id único robusto: el índice mezcla raw chunks (chunk_id) y wiki pages
    # (page_id). Sin esto, las wiki pages colapsan a None y rompen el overlap.
    out = []
    for r in results:
        uid = r.get("chunk_id") or r.get("page_id") or r.get("file_path")
        out.append(uid if uid is not None else f"_score:{r.get('score')}")
    return out


def main() -> int:
    os.environ.setdefault("ARIADNA_EMBED_DEVICE", "cpu")
    import logging

    logging.basicConfig(level=logging.ERROR)

    from ariadna.backends.onnx import OnnxEmbedder
    from ariadna.embeddings import DenseEmbedder
    from ariadna.storage import CorpusStore

    queries = _load_queries()
    print("=" * 68)
    print("ARIADNA · parity fp32 (torch) vs ONNX int8 — degradación")
    print("=" * 68)
    print(f"queries eval: {len(queries)}   índice: producción (data/qdrant)   prefetch={PREFETCH}")

    rss0 = _rss_mb()
    t = time.perf_counter()
    onnx = OnnxEmbedder()
    onnx_load = time.perf_counter() - t
    rss_onnx = _rss_mb()

    t = time.perf_counter()
    fp32 = DenseEmbedder(device="cpu")
    fp32_load = time.perf_counter() - t
    rss_both = _rss_mb()

    store = CorpusStore()

    print("-" * 68)
    print(f"{'backend':<14}{'RAM modelo':>14}{'carga (s)':>12}")
    print(f"{'ONNX int8':<14}{rss_onnx - rss0:>12.0f} MB{onnx_load:>12.1f}")
    print(f"{'torch fp32':<14}{rss_both - rss_onnx:>12.0f} MB{fp32_load:>12.1f}")
    print("-" * 68)

    parities: list[float] = []
    lat_fp: list[float] = []
    lat_on: list[float] = []
    overlap = {k: [] for k in KS}
    recall_fp = {k: 0 for k in KS}
    recall_on = {k: 0 for k in KS}
    rr_fp: list[float] = []  # reciprocal rank @ prefetch
    rr_on: list[float] = []
    rank_changes = 0

    for q in queries:
        text = q["query"]
        gold = q.get("source_chunk_id")

        t = time.perf_counter()
        v_fp = fp32.embed_query(text)
        lat_fp.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        v_on = onnx.embed_query(text)
        lat_on.append((time.perf_counter() - t) * 1000)

        parities.append(float(np.dot(v_fp, v_on)))  # ambos normalizados

        res_fp = store.search(v_fp, top_k=PREFETCH)
        res_on = store.search(v_on, top_k=PREFETCH)
        ids_fp = _ids(res_fp)
        ids_on = _ids(res_on)

        if ids_fp[:5] != ids_on[:5]:
            rank_changes += 1

        for k in KS:
            sfp, son = set(ids_fp[:k]), set(ids_on[:k])
            overlap[k].append(len(sfp & son) / k)
            if gold in ids_fp[:k]:
                recall_fp[k] += 1
            if gold in ids_on[:k]:
                recall_on[k] += 1

        def _rr(ids: list[str]) -> float:
            return 1.0 / (ids.index(gold) + 1) if gold in ids else 0.0

        rr_fp.append(_rr(ids_fp))
        rr_on.append(_rr(ids_on))

    n = len(queries)
    print("PARITY DEL VECTOR (coseno query fp32 vs int8):")
    print(f"  media {statistics.mean(parities):.5f}   min {min(parities):.5f}   "
          f"max {max(parities):.5f}")
    print()
    print("OVERLAP DE RESULTADOS (mismos chunks devueltos):")
    for k in KS:
        tag = "  (= ventana reranker)" if k == PREFETCH else ""
        print(f"  overlap@{k:<3} media {statistics.mean(overlap[k]) * 100:6.2f}%{tag}")
    print(f"  queries con cambio en el top-5: {rank_changes}/{n}")
    print()
    print("RECALL DEL CHUNK FUENTE (ground-truth) — fp32 vs int8:")
    for k in KS:
        print(f"  recall@{k:<3}  fp32 {recall_fp[k]}/{n}   int8 {recall_on[k]}/{n}   "
              f"Δ {recall_on[k] - recall_fp[k]:+d}")
    print(f"  MRR@{PREFETCH}    fp32 {statistics.mean(rr_fp):.4f}   "
          f"int8 {statistics.mean(rr_on):.4f}   Δ {statistics.mean(rr_on) - statistics.mean(rr_fp):+.4f}")
    print()
    print("LATENCIA embed_query (CPU):")
    print(f"  fp32  media {statistics.mean(lat_fp):6.1f} ms   p50 {statistics.median(lat_fp):6.1f} ms")
    print(f"  int8  media {statistics.mean(lat_on):6.1f} ms   p50 {statistics.median(lat_on):6.1f} ms")
    speedup = statistics.mean(lat_fp) / statistics.mean(lat_on) if statistics.mean(lat_on) else 0
    print(f"  speedup int8: {speedup:.2f}x")
    print("=" * 68)
    print("Lectura: overlap@20 ~100% => el reranker ve los mismos candidatos =>")
    print("resultado final idéntico. Recall Δ=0 => no pierde aciertos del eval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
