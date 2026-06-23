"""¿Aporta el rerank-API (Qwen3) sobre dense-only? Mide sobre eval v3 (gold real).

Pipeline real: embed (ONNX int8) -> dense top-20 -> rerank Qwen3 (DeepInfra API).
Como dense ya mete el gold en top-20 (recall@20=100%), el rerank solo puede AYUDAR
subiendo el gold dentro de esos 20 -> mejor recall@1/@5 y MRR. Si no mejora, no
compensa la dependencia y vamos dense-only.

Requiere ARIADNA_API_KEY (DeepInfra). Ej:
  ARIADNA_API_KEY=$(cat ~/.ariadna_deepinfra_key) .venv/bin/python -m scripts.eval_rerank_v3
"""

from __future__ import annotations

import json
import os
import statistics

from ariadna.config import PROJECT_ROOT, RERANKER_PREFETCH_N

EVAL = PROJECT_ROOT / "data" / "eval" / "queries_eval_v3.jsonl"
PREFETCH = RERANKER_PREFETCH_N
KS = (1, 3, 5, 10)


def _gold_rank(results: list[dict], vid: str, ts: int) -> int | None:
    for i, r in enumerate(results, 1):
        if r.get("video_id") == vid and r.get("timestamp_seconds") == ts:
            return i
    return None


def _metrics(ranks: list[int | None]) -> tuple[dict, float]:
    recall = {k: sum(1 for r in ranks if r is not None and r <= k) for k in KS}
    mrr = statistics.mean(1.0 / r if r else 0.0 for r in ranks)
    return recall, mrr


def main() -> int:
    os.environ.setdefault("ARIADNA_EMBED_DEVICE", "cpu")
    if not os.getenv("ARIADNA_API_KEY"):
        print("ERROR: falta ARIADNA_API_KEY (DeepInfra).")
        return 1
    import logging
    logging.basicConfig(level=logging.ERROR)

    from ariadna.backends.api import ApiReranker
    from ariadna.backends.onnx import OnnxEmbedder
    from ariadna.storage import CorpusStore

    queries = [json.loads(l) for l in EVAL.read_text().splitlines() if l.strip()]
    embedder = OnnxEmbedder()
    reranker = ApiReranker()
    store = CorpusStore()

    print("=" * 60)
    print(f"EVAL v3 rerank: dense-only vs +Qwen3-API — {len(queries)} queries")
    print("=" * 60)

    dense_ranks: list[int | None] = []
    rerank_ranks: list[int | None] = []
    for q in queries:
        v = embedder.embed_query(q["query"])
        cands = store.search(v, top_k=PREFETCH)
        dense_ranks.append(_gold_rank(cands, q["gold_video_id"], q["gold_timestamp_seconds"]))
        reranked = reranker.rerank(q["query"], list(cands), top_k=PREFETCH)
        rerank_ranks.append(_gold_rank(reranked, q["gold_video_id"], q["gold_timestamp_seconds"]))

    n = len(queries)
    rd, md = _metrics(dense_ranks)
    rr, mr = _metrics(rerank_ranks)
    print(f"\n{'métrica':<12}{'dense':>10}{'+rerank':>10}{'Δ':>8}")
    for k in KS:
        print(f"recall@{k:<5}{rd[k]:>7}/{n}{rr[k]:>7}/{n}{rr[k] - rd[k]:>+8}")
    print(f"{'MRR':<12}{md:>10.4f}{mr:>10.4f}{mr - md:>+8.4f}")

    up = sum(1 for d, r in zip(dense_ranks, rerank_ranks, strict=True)
             if d and r and r < d)
    down = sum(1 for d, r in zip(dense_ranks, rerank_ranks, strict=True)
               if d and r and r > d)
    print(f"\nqueries donde el rerank SUBE el gold: {up}/{n}   lo BAJA: {down}/{n}")
    print("=" * 60)
    print("Si Δrecall@1/MRR es claramente +, el rerank aporta. Si ~0, dense-only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
