"""CLI de indexado: parsea corpus, calcula embeddings, inserta en Qdrant.

Uso:
    ariadna-index                       # usa corpus default
    ariadna-index --source /path/to/playlists
    ariadna-index --recreate            # borra coleccion y re-indexa todo
    ariadna-index --dry-run             # parsea pero no indexa (solo cuenta)
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import time
from pathlib import Path

from ariadna.config import DEFAULT_CORPUS_PATH
from ariadna.embeddings import DenseEmbedder
from ariadna.parsers import Chunk, iter_corpus, parse_summary_file
from ariadna.storage import CorpusStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ariadna.index")


def chunk_id_int(chunk: Chunk) -> int:
    """ID entero estable para Qdrant a partir del chunk_id string (video_id+ts)."""
    return int(hashlib.sha256(chunk.chunk_id.encode("utf-8")).hexdigest()[:15], 16)


def build(
    corpus_path: Path,
    recreate: bool = False,
    batch_size: int = 64,
    dry_run: bool = False,
) -> None:
    """Parsea corpus + embeddings + upsert a Qdrant."""
    log.info("Corpus: %s", corpus_path)
    log.info("Parseando summary.md files...")

    all_chunks: list[Chunk] = []
    video_count = 0
    for summary, meta, playlist in iter_corpus(corpus_path):
        chunks = parse_summary_file(summary, meta, playlist)
        if chunks:
            video_count += 1
            all_chunks.extend(chunks)

    log.info("Parseados %d videos → %d chunks totales", video_count, len(all_chunks))

    if dry_run:
        log.info("Dry-run: no se indexa. Breakdown por categoria:")
        from collections import Counter
        cats = Counter(c.category for c in all_chunks)
        for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
            log.info("  %-25s %d", cat, count)
        return

    if not all_chunks:
        log.warning("Corpus vacio, nada que indexar.")
        return

    # Embeddings
    log.info("Inicializando modelo de embeddings...")
    embedder = DenseEmbedder()

    log.info("Calculando embeddings para %d chunks...", len(all_chunks))
    start = time.time()
    texts = [c.full_text for c in all_chunks]
    vectors = embedder.embed(texts, batch_size=batch_size)
    elapsed = time.time() - start
    log.info(
        "Embeddings listos: %d vectores de dim %d en %.1fs (%.0f chunks/s)",
        len(vectors),
        vectors.shape[1],
        elapsed,
        len(vectors) / elapsed,
    )

    # Storage
    store = CorpusStore(vector_dim=vectors.shape[1])
    store.ensure_collection(recreate=recreate)

    log.info("Insertando en Qdrant en batches de %d...", batch_size)
    n = len(all_chunks)
    start = time.time()
    for i in range(0, n, batch_size):
        batch_chunks = all_chunks[i : i + batch_size]
        batch_vectors = vectors[i : i + batch_size]
        ids = [chunk_id_int(c) for c in batch_chunks]
        payloads = [c.to_payload() for c in batch_chunks]
        store.upsert_batch(ids, batch_vectors, payloads)
        if (i // batch_size) % 10 == 0:
            log.info("  progreso: %d/%d", min(i + batch_size, n), n)

    elapsed = time.time() - start
    log.info("Indexado completo en %.1fs. Total en coleccion: %d puntos", elapsed, store.count())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Indexa el corpus de ProxySummaries en Qdrant via BGE-M3."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_CORPUS_PATH,
        help="Ruta a data/playlists/ (default: ProxySummaries sibling)",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Borra la coleccion existente antes de indexar",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Batch size para embeddings + upsert",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo parsea, no indexa",
    )
    args = parser.parse_args()

    build(
        corpus_path=args.source,
        recreate=args.recreate,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
