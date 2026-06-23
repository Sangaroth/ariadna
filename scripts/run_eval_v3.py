"""Mide recall@k / MRR sobre el eval v3 (gold real) — fp32 (torch) vs ONNX int8.

Responde con números reales a "¿degrada el int8 mis resultados?": el gold de cada
query (video_id, timestamp_seconds) SÍ está en el índice vivo, así que recall@k es
medible. Compara el backend de producción (torch fp32) con el candidato (ONNX int8).
"""

from __future__ import annotations

import json
import os
import statistics
import time

from ariadna.config import PROJECT_ROOT, RERANKER_PREFETCH_N

EVAL = PROJECT_ROOT / "data" / "eval" / "queries_eval_v3.jsonl"
KS = (1, 5, 10, RERANKER_PREFETCH_N)
PREFETCH = RERANKER_PREFETCH_N


def _gold_rank(results: list[dict], vid: str, ts: int) -> int | None:
    """Posición (1-based) del chunk gold en los resultados, o None."""
    for i, r in enumerate(results, 1):
        if r.get("video_id") == vid and r.get("timestamp_seconds") == ts:
            return i
    return None


def _chunk_key(r: dict) -> str:
    return f"{r.get('video_id')}@{r.get('timestamp_seconds')}" if r.get("video_id") else (
        r.get("chunk_id") or r.get("page_id") or f"_s:{r.get('score')}"
    )


def evaluate(name: str, embedder, store, queries: list[dict]) -> dict:
    ranks: list[int | None] = []
    lat: list[float] = []
    id_lists: list[list[str]] = []
    for q in queries:
        t = time.perf_counter()
        v = embedder.embed_query(q["query"])
        lat.append((time.perf_counter() - t) * 1000)
        res = store.search(v, top_k=PREFETCH)
        ranks.append(_gold_rank(res, q["gold_video_id"], q["gold_timestamp_seconds"]))
        id_lists.append([_chunk_key(r) for r in res])
    recall = {k: sum(1 for r in ranks if r is not None and r <= k) for k in KS}
    mrr = statistics.mean(1.0 / r if r else 0.0 for r in ranks)
    return {
        "name": name, "recall": recall, "mrr": mrr,
        "lat_mean": statistics.mean(lat), "lat_p50": statistics.median(lat),
        "ranks": ranks, "id_lists": id_lists,
    }


def main() -> int:
    os.environ.setdefault("ARIADNA_EMBED_DEVICE", "cpu")
    import logging
    logging.basicConfig(level=logging.ERROR)

    from ariadna.backends.onnx import OnnxEmbedder
    from ariadna.embeddings import DenseEmbedder
    from ariadna.storage import CorpusStore

    queries = [json.loads(l) for l in EVAL.read_text().splitlines() if l.strip()]
    store = CorpusStore()
    fp32 = DenseEmbedder(device="cpu")
    int8 = OnnxEmbedder()

    print("=" * 66)
    print(f"EVAL v3 (realista, gold real) — {len(queries)} queries — prefetch={PREFETCH}")
    print("=" * 66)

    r_fp = evaluate("torch fp32", fp32, store, queries)
    r_i8 = evaluate("onnx int8", int8, store, queries)

    n = len(queries)
    print(f"\n{'métrica':<14}{'fp32 (prod)':>14}{'int8':>12}{'Δ':>10}")
    for k in KS:
        a, b = r_fp["recall"][k], r_i8["recall"][k]
        print(f"recall@{k:<7}{a:>8}/{n}{b:>8}/{n}{b - a:>+10}")
    print(f"{'MRR@'+str(PREFETCH):<14}{r_fp['mrr']:>14.4f}{r_i8['mrr']:>12.4f}{r_i8['mrr'] - r_fp['mrr']:>+10.4f}")

    # Overlap del prefetch (lo que ve el reranker)
    overlaps = [
        len(set(a) & set(b)) / PREFETCH
        for a, b in zip(r_fp["id_lists"], r_i8["id_lists"], strict=True)
    ]
    # ¿En cuántas queries int8 pierde el gold que fp32 sí tenía?
    lost = sum(1 for rf, ri in zip(r_fp["ranks"], r_i8["ranks"], strict=True)
               if rf is not None and rf <= PREFETCH and (ri is None or ri > PREFETCH))
    gained = sum(1 for rf, ri in zip(r_fp["ranks"], r_i8["ranks"], strict=True)
                 if ri is not None and ri <= PREFETCH and (rf is None or rf > PREFETCH))
    print(f"\noverlap@{PREFETCH} medio (candidatos al reranker): {statistics.mean(overlaps) * 100:.1f}%")
    print(f"queries donde int8 PIERDE el gold que fp32 tenía: {lost}/{n}")
    print(f"queries donde int8 GANA un gold que fp32 no tenía: {gained}/{n}")
    print(f"\nlatencia embed  fp32 {r_fp['lat_mean']:.1f}ms (p50 {r_fp['lat_p50']:.1f})  "
          f"int8 {r_i8['lat_mean']:.1f}ms (p50 {r_i8['lat_p50']:.1f})")
    print("=" * 66)
    print("recall fp32 alto => eval válido. Δrecall ~0 y overlap alto => int8 no degrada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
