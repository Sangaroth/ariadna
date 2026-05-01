"""Pilot RRF: fusion dense+sparse BGE-M3 vs dense-solo.

Aislado del corpus de produccion:
  - Usa coleccion 'proxy_corpus_eval' en data/qdrant_eval/ (no toca data/qdrant/)
  - No requiere parar el MCP server
  - Borrable sin impacto: rm -rf data/qdrant_eval/

Pipeline:
  1. Parse corpus (mismo parser que produccion).
  2. Embed dense+sparse via FlagEmbedding BGE-M3.
  3. Indexa en Qdrant local con named vectors.
  4. Corre las 10 queries de data/eval/queries_eval_v1.jsonl con dense-solo y RRF.
  5. Guarda comparacion lado a lado en data/eval/results_v1.md.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
from FlagEmbedding import BGEM3FlagModel
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Fusion,
    FusionQuery,
    PointStruct,
    Prefetch,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)
from tqdm import tqdm

from ariadna.config import DEFAULT_CORPUS_PATH, PROJECT_ROOT
from ariadna.parsers import parse_corpus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("eval_pilot")

EVAL_QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant_eval"
EVAL_COLLECTION = "proxy_corpus_eval"
QUERIES_PATH = PROJECT_ROOT / "data" / "eval" / "queries_eval_v1.jsonl"
RESULTS_PATH = PROJECT_ROOT / "data" / "eval" / "results_v1.md"
DENSE_DIM = 1024
TOP_K = 5
PREFETCH_N = 20
BATCH_SIZE = 12


def sparse_dict_to_qdrant(weights: dict) -> SparseVector:
    """{token_id_str: weight_float} -> SparseVector(indices, values)."""
    if not weights:
        return SparseVector(indices=[0], values=[0.0])
    items = [(int(k), float(v)) for k, v in weights.items()]
    indices, values = zip(*items, strict=True)
    return SparseVector(indices=list(indices), values=list(values))


def build_index(client: QdrantClient, model: BGEM3FlagModel) -> int:
    """Recrea la coleccion y reindexa todos los chunks."""
    log.info("Borrando coleccion previa si existe...")
    if client.collection_exists(EVAL_COLLECTION):
        client.delete_collection(EVAL_COLLECTION)

    log.info("Creando coleccion con named vectors {dense, sparse}...")
    client.create_collection(
        collection_name=EVAL_COLLECTION,
        vectors_config={"dense": VectorParams(size=DENSE_DIM, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams())},
    )

    log.info("Parseando corpus...")
    chunks = parse_corpus(DEFAULT_CORPUS_PATH)
    log.info("Total chunks: %d", len(chunks))

    log.info("Embebiendo dense+sparse por lotes (batch=%d)...", BATCH_SIZE)
    point_id = 0
    for i in tqdm(range(0, len(chunks), BATCH_SIZE), desc="embed+upsert"):
        batch = chunks[i : i + BATCH_SIZE]
        texts = [c.full_text for c in batch]
        out = model.encode(
            texts,
            batch_size=len(batch),
            max_length=512,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        dense_vecs = out["dense_vecs"]
        sparse_weights = out["lexical_weights"]

        points = []
        for chunk, dvec, swts in zip(batch, dense_vecs, sparse_weights, strict=True):
            point_id += 1
            payload = chunk.to_payload()
            payload["chunk_id"] = chunk.chunk_id
            points.append(
                PointStruct(
                    id=point_id,
                    vector={
                        "dense": dvec.astype(np.float32).tolist(),
                        "sparse": sparse_dict_to_qdrant(swts),
                    },
                    payload=payload,
                )
            )
        client.upsert(collection_name=EVAL_COLLECTION, points=points)

    final_count = client.count(EVAL_COLLECTION).count
    log.info("Coleccion lista. Chunks indexados: %d", final_count)
    return final_count


def search_dense_only(
    client: QdrantClient, q_dense: np.ndarray, top_k: int = TOP_K
) -> list[dict[str, Any]]:
    res = client.query_points(
        collection_name=EVAL_COLLECTION,
        query=q_dense.astype(np.float32).tolist(),
        using="dense",
        limit=top_k,
        with_payload=True,
    ).points
    return [{"score": float(p.score), **(p.payload or {})} for p in res]


def search_rrf(
    client: QdrantClient,
    q_dense: np.ndarray,
    q_sparse: SparseVector,
    top_k: int = TOP_K,
    prefetch_n: int = PREFETCH_N,
) -> list[dict[str, Any]]:
    res = client.query_points(
        collection_name=EVAL_COLLECTION,
        prefetch=[
            Prefetch(
                query=q_dense.astype(np.float32).tolist(),
                using="dense",
                limit=prefetch_n,
            ),
            Prefetch(
                query=q_sparse,
                using="sparse",
                limit=prefetch_n,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
        with_payload=True,
    ).points
    return [{"score": float(p.score), **(p.payload or {})} for p in res]


def format_chunk_md(rank: int, chunk: dict[str, Any], source_chunk_id: str) -> str:
    is_source = "  **<- chunk fuente**" if chunk.get("chunk_id") == source_chunk_id else ""
    title = chunk.get("video_title", "?")
    ts = chunk.get("timestamp", "?")
    cat = chunk.get("category", "?")
    theme = chunk.get("theme", "")
    content = (chunk.get("content") or "").strip()
    snippet = content[:280] + ("..." if len(content) > 280 else "")
    return (
        f"**{rank}.** `score={chunk['score']:.4f}` | *{cat}* | {title} [{ts}]{is_source}\n"
        f"   {theme}\n"
        f"   {snippet}\n"
    )


def run_pilot(client: QdrantClient, model: BGEM3FlagModel) -> None:
    queries = [json.loads(line) for line in QUERIES_PATH.read_text().splitlines() if line.strip()]
    log.info("Queries cargadas: %d", len(queries))

    md_parts: list[str] = [
        "# Pilot RRF -- resultados v1\n\n",
        f"**Top-K**: {TOP_K} | **Prefetch por lane**: {PREFETCH_N} | **Modelo**: BGE-M3 (dense+sparse)\n\n",
        f"**Coleccion**: `{EVAL_COLLECTION}` (aislada en `data/qdrant_eval/`)\n\n",
        "Cada query muestra resultados de **dense-solo** vs **RRF (dense+sparse)**.\n",
        "El chunk marcado como `<- chunk fuente` es del que se genero la query "
        "(referencia, no obligatoriamente la 'mejor' respuesta).\n\n---\n",
    ]

    for q in queries:
        log.info("Query %s: %s", q["query_id"], q["query"][:60])
        emb = model.encode(
            [q["query"]],
            max_length=256,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        q_dense = emb["dense_vecs"][0]
        q_sparse = sparse_dict_to_qdrant(emb["lexical_weights"][0])

        dense_results = search_dense_only(client, q_dense, top_k=TOP_K)
        rrf_results = search_rrf(client, q_dense, q_sparse, top_k=TOP_K)

        src = q["source_chunk_id"]
        md_parts.append(f"\n## {q['query_id']} -- *{q['query_type']}* -- {q['category']}\n\n")
        md_parts.append(f"> **{q['query']}**\n\n")
        md_parts.append(f"_Hipotesis: {q.get('rationale', '')}_\n\n")

        md_parts.append("### Dense-solo\n\n")
        for i, c in enumerate(dense_results, 1):
            md_parts.append(format_chunk_md(i, c, src) + "\n")

        md_parts.append("### RRF (dense+sparse)\n\n")
        for i, c in enumerate(rrf_results, 1):
            md_parts.append(format_chunk_md(i, c, src) + "\n")

        d_pos = next(
            (i for i, c in enumerate(dense_results, 1) if c.get("chunk_id") == src), None
        )
        r_pos = next(
            (i for i, c in enumerate(rrf_results, 1) if c.get("chunk_id") == src), None
        )
        md_parts.append(
            f"_Posicion del chunk fuente -- dense: {d_pos or 'fuera top-5'} | "
            f"RRF: {r_pos or 'fuera top-5'}_\n\n---\n"
        )

    RESULTS_PATH.write_text("".join(md_parts), encoding="utf-8")
    log.info("Resultados guardados en %s", RESULTS_PATH)


def main() -> None:
    log.info("Cargando BGE-M3 (FlagEmbedding, fp16)...")
    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

    EVAL_QDRANT_PATH.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(EVAL_QDRANT_PATH))

    if not client.collection_exists(EVAL_COLLECTION):
        build_index(client, model)
    else:
        n = client.count(EVAL_COLLECTION).count
        log.info("Coleccion %s ya existe (%d chunks). Saltando indexacion.", EVAL_COLLECTION, n)

    run_pilot(client, model)
    log.info("Listo.")


if __name__ == "__main__":
    main()
