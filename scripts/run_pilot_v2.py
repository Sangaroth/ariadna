"""Pilot v2: dense vs RRF vs dense20+reranker.

Reusa la coleccion proxy_corpus_eval (creada por run_eval_pilot.py) -- no reindexa.
Anade BGE-reranker-v2-m3 sobre top-20 de dense -> top-5.
Corre 15 queries: 10 v1 + 5 adversariales v2.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
from FlagEmbedding import BGEM3FlagModel
from sentence_transformers import CrossEncoder
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Fusion,
    FusionQuery,
    Prefetch,
    SparseVector,
)

from ariadna.config import PROJECT_ROOT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pilot_v2")

EVAL_QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant_eval"
EVAL_COLLECTION = "proxy_corpus_eval"
QUERIES_V1 = PROJECT_ROOT / "data" / "eval" / "queries_eval_v1.jsonl"
QUERIES_V2 = PROJECT_ROOT / "data" / "eval" / "queries_eval_v2.jsonl"
RESULTS_PATH = PROJECT_ROOT / "data" / "eval" / "results_v2.md"
TOP_K = 5
PREFETCH_N = 20


def sparse_dict_to_qdrant(weights: dict) -> SparseVector:
    if not weights:
        return SparseVector(indices=[0], values=[0.0])
    items = [(int(k), float(v)) for k, v in weights.items()]
    indices, values = zip(*items, strict=True)
    return SparseVector(indices=list(indices), values=list(values))


def search_dense(client: QdrantClient, q_dense: np.ndarray, top_k: int) -> list[dict[str, Any]]:
    res = client.query_points(
        collection_name=EVAL_COLLECTION,
        query=q_dense.astype(np.float32).tolist(),
        using="dense",
        limit=top_k,
        with_payload=True,
    ).points
    return [{"score": float(p.score), **(p.payload or {})} for p in res]


def search_rrf(
    client: QdrantClient, q_dense: np.ndarray, q_sparse: SparseVector, top_k: int
) -> list[dict[str, Any]]:
    res = client.query_points(
        collection_name=EVAL_COLLECTION,
        prefetch=[
            Prefetch(query=q_dense.astype(np.float32).tolist(), using="dense", limit=PREFETCH_N),
            Prefetch(query=q_sparse, using="sparse", limit=PREFETCH_N),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
        with_payload=True,
    ).points
    return [{"score": float(p.score), **(p.payload or {})} for p in res]


def search_dense_reranked(
    client: QdrantClient,
    reranker: CrossEncoder,
    query: str,
    q_dense: np.ndarray,
    top_k: int,
) -> list[dict[str, Any]]:
    """Dense top-20 -> rerank con cross-encoder -> top-5."""
    candidates = search_dense(client, q_dense, top_k=PREFETCH_N)
    if not candidates:
        return []
    pairs = [[query, f"{c.get('theme', '')}\n{c.get('content', '')}"] for c in candidates]
    scores = reranker.predict(pairs, batch_size=PREFETCH_N, show_progress_bar=False)
    for c, s in zip(candidates, scores, strict=True):
        c["rerank_score"] = float(s)
    candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
    out = []
    for c in candidates[:top_k]:
        c["score"] = c.pop("rerank_score")
        out.append(c)
    return out


def fmt_chunk(rank: int, chunk: dict[str, Any], src: str) -> str:
    is_src = "  **<- chunk fuente**" if chunk.get("chunk_id") == src else ""
    title = chunk.get("video_title", "?")
    ts = chunk.get("timestamp", "?")
    cat = chunk.get("category", "?")
    theme = chunk.get("theme", "")
    content = (chunk.get("content") or "").strip()
    snippet = content[:240] + ("..." if len(content) > 240 else "")
    return (
        f"**{rank}.** `{chunk['score']:.4f}` | *{cat}* | {title} [{ts}]{is_src}\n"
        f"   {theme}\n   {snippet}\n"
    )


def main() -> None:
    log.info("Cargando BGE-M3 (embedder)...")
    embedder = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
    log.info("Cargando BGE-reranker-v2-m3 (cross-encoder)...")
    reranker = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)

    client = QdrantClient(path=str(EVAL_QDRANT_PATH))
    if not client.collection_exists(EVAL_COLLECTION):
        raise SystemExit(
            "Coleccion proxy_corpus_eval no existe. Ejecuta antes scripts/run_eval_pilot.py"
        )
    log.info("Coleccion lista (%d chunks).", client.count(EVAL_COLLECTION).count)

    queries_v1 = [json.loads(l) for l in QUERIES_V1.read_text().splitlines() if l.strip()]
    queries_v2 = [json.loads(l) for l in QUERIES_V2.read_text().splitlines() if l.strip()]
    queries = queries_v1 + queries_v2
    log.info("Queries totales: %d (v1=%d, v2=%d)", len(queries), len(queries_v1), len(queries_v2))

    md = [
        "# Pilot v2 -- Dense vs RRF vs Dense+Reranker\n\n",
        f"**Top-K**: {TOP_K} | **Prefetch**: {PREFETCH_N} | ",
        "**Modelos**: BGE-M3 (dense+sparse) + BGE-reranker-v2-m3\n\n",
        "Tres lanes por query: **Dense** (BGE-M3 solo), **RRF** (dense+sparse fusion), ",
        "**Reranker** (dense top-20 -> cross-encoder -> top-5).\n",
        "Las queries q11-q15 son **adversariales** (coloquial, paráfrasis lejanas).\n\n---\n",
    ]

    summary_rows = []

    for q in queries:
        log.info("Query %s: %s", q["query_id"], q["query"][:60])
        emb = embedder.encode(
            [q["query"]],
            max_length=256,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        q_dense = emb["dense_vecs"][0]
        q_sparse = sparse_dict_to_qdrant(emb["lexical_weights"][0])

        dense_res = search_dense(client, q_dense, top_k=TOP_K)
        rrf_res = search_rrf(client, q_dense, q_sparse, top_k=TOP_K)
        rerank_res = search_dense_reranked(client, reranker, q["query"], q_dense, top_k=TOP_K)

        src = q["source_chunk_id"]

        # Posicion del chunk fuente en cada lane (mirando top-20 para reranker)
        d_pos = next((i for i, c in enumerate(dense_res, 1) if c.get("chunk_id") == src), None)
        rrf_pos = next((i for i, c in enumerate(rrf_res, 1) if c.get("chunk_id") == src), None)
        rk_pos = next((i for i, c in enumerate(rerank_res, 1) if c.get("chunk_id") == src), None)

        # Tambien posicion en dense top-20 (para entender que tenia que rescatar el reranker)
        dense_top20 = search_dense(client, q_dense, top_k=PREFETCH_N)
        d20_pos = next((i for i, c in enumerate(dense_top20, 1) if c.get("chunk_id") == src), None)

        summary_rows.append(
            {
                "qid": q["query_id"],
                "type": q["query_type"],
                "d20": d20_pos,
                "d": d_pos,
                "rrf": rrf_pos,
                "rk": rk_pos,
            }
        )

        md.append(f"\n## {q['query_id']} -- *{q['query_type']}* -- {q['category']}\n\n")
        md.append(f"> **{q['query']}**\n\n")
        md.append(f"_Hipótesis: {q.get('rationale', '')}_\n\n")
        md.append(
            f"_Posición chunk fuente_: dense20={d20_pos or 'fuera'} | "
            f"dense5={d_pos or 'fuera'} | RRF5={rrf_pos or 'fuera'} | "
            f"reranker5={rk_pos or 'fuera'}\n\n"
        )

        md.append("### Dense top-5\n\n")
        for i, c in enumerate(dense_res, 1):
            md.append(fmt_chunk(i, c, src) + "\n")

        md.append("### RRF top-5\n\n")
        for i, c in enumerate(rrf_res, 1):
            md.append(fmt_chunk(i, c, src) + "\n")

        md.append("### Dense+Reranker top-5\n\n")
        for i, c in enumerate(rerank_res, 1):
            md.append(fmt_chunk(i, c, src) + "\n")

        md.append("---\n")

    # Resumen comparativo al principio
    summary_md = ["\n## Resumen comparativo\n\n"]
    summary_md.append(
        "| Query | Tipo | dense top-20 | dense top-5 | RRF top-5 | Reranker top-5 |\n"
    )
    summary_md.append("|---|---|---|---|---|---|\n")
    for r in summary_rows:
        summary_md.append(
            f"| {r['qid']} | {r['type']} | "
            f"{r['d20'] or '—'} | {r['d'] or '—'} | "
            f"{r['rrf'] or '—'} | {r['rk'] or '—'} |\n"
        )
    md.insert(6, "".join(summary_md) + "\n---\n")

    RESULTS_PATH.write_text("".join(md), encoding="utf-8")
    log.info("Resultados guardados en %s", RESULTS_PATH)


if __name__ == "__main__":
    main()
