#!/usr/bin/env python3
"""Migra los puntos de Qdrant (colección proxy_corpus) al PAYLOAD UNIVERSAL,
in-place con set_payload (NO re-embed → vectores intactos, scores idénticos).

Requiere el MCP server PARADO (Qdrant embedded tiene lock exclusivo).

Para cada RAW chunk (tiene video_id; source_type != wiki_page) añade:
  project_id='proxy', source_id='youtube:<vid>', source_type='youtube_video',
  position={timestamp_seconds,timestamp_str}, position_url, cite_markdown,
  title_breadcrumb, chunk_id semántico, chunk_type='analysis',
  domain[]/domain_primary (OpenAlex), source_file_hash=NULL,
  embedding_model, schema_version. Conserva campos legacy (video_id, category...).

Para cada WIKI point (source_type=wiki_page) añade project_id='proxy' + domain[]
(desde page_domains). Mantiene source_type=wiki_page (centinela de lane en search.py).

NO cambia el ID entero del punto (sigue siendo sha256(video_id_ts)) → el baseline
funcional sigue válido. Resume-safe: salta puntos que ya tienen source_id/project_id.

Reclasificación de dominio (determinista, CERO LLM):
  - Si el chunk está citado por ≥1 página wiki → hereda domain_primary/domain[] de
    esas páginas (clasificación fina ya curada en frontmatter).
  - Si no → mapa LEGACY_TO_OPENALEX por la categoría legacy del chunk.

Uso:
    python scripts/migrate_raw_chunks_to_universal.py --dry-run
    python scripts/migrate_raw_chunks_to_universal.py
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

EMBEDDING_MODEL = "BAAI/bge-m3:1024:dense:v1"

# Mapa grueso categoría legacy → dominio OpenAlex (fallback cuando el chunk no
# está citado por ninguna wiki que ya tenga dominio fino curado).
LEGACY_TO_OPENALEX = {
    "psicología": "social.psychology",
    "psicologia": "social.psychology",
    "filosofía y teoría": "humanities.philosophy",
    "filosofia y teoria": "humanities.philosophy",
    "mitología y religión": "humanities.religion",
    "mitologia y religion": "humanities.religion",
    "análisis de obra": "arts.literature",
    "analisis de obra": "arts.literature",
    "cultura y actualidad": "interdisciplinary.cultural_studies",
}
DEFAULT_DOMAIN = "interdisciplinary.cultural_studies"


def _fmt_ts(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class DomainResolver:
    """Resuelve domain[]/domain_primary de un chunk: herencia wiki o mapa legacy."""

    def __init__(self, ariadna_db: Path, project_id: str):
        self.conn = sqlite3.connect(f"file:{ariadna_db}?mode=ro", uri=True)
        self.project_id = project_id

    def resolve(self, video_id: str, ts: int, category: str | None) -> tuple[list[str], str]:
        source_id = f"youtube:{video_id}"
        page_ids = [r[0] for r in self.conn.execute(
            "SELECT DISTINCT page_id FROM citations WHERE project_id=? AND source_id=? AND position_key=?",
            (self.project_id, source_id, str(ts)),
        )]
        domains: list[str] = []
        primary: str | None = None
        for pid in page_ids:
            row = self.conn.execute(
                "SELECT domain_primary FROM pages WHERE project_id=? AND page_id=?",
                (self.project_id, pid)).fetchone()
            if row and row[0]:
                primary = primary or row[0]
                domains.append(row[0])
            for (d,) in self.conn.execute(
                "SELECT domain FROM page_domains WHERE project_id=? AND page_id=?",
                (self.project_id, pid)):
                domains.append(d)
        if not primary:
            primary = LEGACY_TO_OPENALEX.get((category or "").strip().lower(), DEFAULT_DOMAIN)
            domains = [primary]
        # dedup preservando orden, primary primero
        domains = [primary] + [d for d in domains if d != primary]
        return list(dict.fromkeys(domains)), primary

    def page_domains(self, page_id: str) -> list[str]:
        return [r[0] for r in self.conn.execute(
            "SELECT domain FROM page_domains WHERE project_id=? AND page_id=?",
            (self.project_id, page_id))]

    def close(self):
        self.conn.close()


def run(ariadna_db: Path, project_id: str, dry_run: bool) -> int:
    from ariadna.storage import CorpusStore

    store = CorpusStore(vector_dim=1024)
    client = store.client
    coll = store.collection_name
    resolver = DomainResolver(ariadna_db, project_id)

    total = store.count()
    print(f"colección={coll} total_puntos={total} (dry_run={dry_run})")

    n_raw = n_wiki = n_skip = n_other = 0
    dom_counter: Counter = Counter()
    inherited = 0
    sample_raw = sample_wiki = None
    offset = None
    BATCH = 512
    while True:
        points, offset = client.scroll(
            collection_name=coll, limit=BATCH, offset=offset,
            with_payload=True, with_vectors=False)
        for p in points:
            pl = p.payload or {}
            stype = pl.get("source_type")
            if stype == "wiki_page":
                # WIKI point
                if pl.get("project_id") and pl.get("domain"):
                    n_skip += 1
                    continue
                page_id = pl.get("page_id")
                doms = resolver.page_domains(page_id) if page_id else []
                payload = {"project_id": project_id}
                if doms:
                    payload["domain"] = doms
                if not dry_run:
                    client.set_payload(collection_name=coll, payload=payload, points=[p.id])
                n_wiki += 1
                if sample_wiki is None:
                    sample_wiki = {"id": p.id, "page_id": page_id, **payload}
            elif pl.get("video_id") is not None:
                # RAW chunk
                if pl.get("source_id"):  # ya migrado
                    n_skip += 1
                    continue
                vid = pl["video_id"]
                ts = int(pl.get("timestamp_seconds") or 0)
                ts_str = pl.get("timestamp") or _fmt_ts(ts)
                vtitle = pl.get("video_title") or vid
                yurl = pl.get("youtube_url") or f"https://youtu.be/{vid}?t={ts}"
                domains, primary = resolver.resolve(vid, ts, pl.get("category"))
                cited = bool(pl.get("category") and primary not in LEGACY_TO_OPENALEX.values())
                if domains and primary not in (LEGACY_TO_OPENALEX.get((pl.get("category") or "").strip().lower()), DEFAULT_DOMAIN):
                    inherited += 1
                dom_counter[primary] += 1
                payload = {
                    "project_id": project_id,
                    "source_id": f"youtube:{vid}",
                    "source_type": "youtube_video",
                    "position": {"timestamp_seconds": ts, "timestamp_str": ts_str},
                    "position_url": yurl,
                    "cite_markdown": f"[{vtitle} ({ts_str})]({yurl})",
                    "title_breadcrumb": f"{vtitle} > {ts_str}",
                    "chunk_id": f"youtube:{vid}#{ts}",
                    "chunk_type": "analysis",
                    "domain": domains,
                    "domain_primary": primary,
                    "source_file_hash": None,
                    "embedding_model": EMBEDDING_MODEL,
                    "schema_version": "2.0.0",
                }
                if not dry_run:
                    client.set_payload(collection_name=coll, payload=payload, points=[p.id])
                n_raw += 1
                if sample_raw is None:
                    sample_raw = {"id": p.id, **{k: payload[k] for k in
                                  ("source_id", "position", "domain_primary", "cite_markdown")}}
            else:
                n_other += 1
        if offset is None:
            break

    resolver.close()
    print(f"\nraw chunks {'a migrar' if dry_run else 'migrados'}: {n_raw}")
    print(f"wiki points {'a taggear' if dry_run else 'taggeados'}: {n_wiki}")
    print(f"saltados (ya migrados): {n_skip}  |  otros/desconocidos: {n_other}")
    print(f"dominios primary (top 10): {dom_counter.most_common(10)}")
    print(f"raw chunks con dominio fino heredado de wiki: {inherited}")
    if sample_raw:
        print(f"sample raw: {sample_raw}")
    if sample_wiki:
        print(f"sample wiki: {sample_wiki}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=Path("data/ariadna.db"))
    p.add_argument("--project", default="proxy")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    return run(args.db, args.project, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
