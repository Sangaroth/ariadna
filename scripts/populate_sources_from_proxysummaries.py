#!/usr/bin/env python3
"""Puebla las tablas GLOBALES `projects(proxy)`, `sources` y `source_projects`
de data/ariadna.db a partir del corpus YouTube cacheado en ProxySummaries.

Cada vídeo (un meta.json) se convierte en 1 fila de `sources` con
source_id = "youtube:<video_id>" y source_type = "youtube_video". La metadata
específica del tipo (channel, duración, playlist, categoría) va en
`type_metadata` (JSON). `source_file_hash` queda NULL: YouTube no archiva blob
(la fuente vive cacheada en ProxySummaries; decisión spec §9.1).

NO toca data/wiki.db ni Qdrant. Idempotente (INSERT OR REPLACE / OR IGNORE).
Prerequisito de migrate_wiki_db_to_global (las citations referencian source_id).

Uso:
    python scripts/populate_sources_from_proxysummaries.py
    python scripts/populate_sources_from_proxysummaries.py --db data/ariadna.db --corpus ../ProxySummaries/data/playlists
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ID = "proxy"
PROJECT_NAME = "Proxy YouTube corpus"


def _iso_date(yyyymmdd: str) -> str | None:
    """20211221 -> 2021-12-21. Devuelve None si no parsea."""
    s = (yyyymmdd or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s or None


def populate(db_path: Path, corpus_path: Path) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        # 1. Proyecto proxy (idempotente).
        conn.execute(
            "INSERT OR IGNORE INTO projects(project_id, name, description, created_at, schema_version) "
            "VALUES (?, ?, ?, ?, '2.0.0')",
            (PROJECT_ID, PROJECT_NAME, "Canal YouTube de Proxy (corpus semilla)", now),
        )

        metas = sorted(corpus_path.glob("**/meta.json"))
        n_sources = 0
        seen_ids: set[str] = set()
        for meta_file in metas:
            meta = json.loads(meta_file.read_text())
            vid = meta.get("video_id")
            if not vid:
                continue
            source_id = f"youtube:{vid}"
            if source_id in seen_ids:
                continue  # mismo vídeo reclasificado en 2 dirs: una sola fuente
            seen_ids.add(source_id)

            # playlist = directorio padre del vídeo bajo playlists/
            try:
                playlist = meta_file.parent.parent.name
            except Exception:
                playlist = ""

            type_metadata = {
                "youtube_id": vid,
                "channel": meta.get("channel"),
                "duration_seconds": meta.get("duration"),
                "playlist": playlist,
                "category": meta.get("category"),  # 5 categorías legacy (informativo; el dominio OpenAlex vive en chunks/wiki)
                "transcript_source": "proxysummaries",
            }
            conn.execute(
                "INSERT OR REPLACE INTO sources "
                "(source_id, source_type, title, language, publication_date, canonical_url, "
                " abstract, confidence_source, ingest_method, source_file_hash, type_metadata, "
                " schema_version, created_at) "
                "VALUES (?, 'youtube_video', ?, 'es', ?, ?, NULL, 'transcript', "
                "        'proxysummaries', NULL, ?, '2.0.0', ?)",
                (
                    source_id,
                    meta.get("title") or vid,
                    _iso_date(meta.get("upload_date")),
                    meta.get("url"),
                    json.dumps(type_metadata, ensure_ascii=False),
                    now,
                ),
            )
            conn.execute(
                "INSERT OR IGNORE INTO source_projects(source_id, project_id, ingested_at) VALUES (?, ?, ?)",
                (source_id, PROJECT_ID, now),
            )
            n_sources += 1

        conn.commit()

        n_sp = conn.execute(
            "SELECT COUNT(*) FROM source_projects WHERE project_id=?", (PROJECT_ID,)
        ).fetchone()[0]
        n_total_sources = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        return {
            "meta_files": len(metas),
            "sources_inserted": n_sources,
            "sources_total": n_total_sources,
            "source_projects": n_sp,
        }
    finally:
        conn.close()


def check_citation_coverage(db_path: Path, wiki_db: Path) -> dict:
    """Comprueba que todos los video_id citados en wiki.db tienen su source en ariadna.db.
    (Solo informativo; wiki.db es read-only.)"""
    if not wiki_db.exists():
        return {"wiki_db": "ausente", "uncovered": []}
    wconn = sqlite3.connect(wiki_db)
    try:
        cited = {r[0] for r in wconn.execute("SELECT DISTINCT video_id FROM citations")}
    except sqlite3.OperationalError:
        return {"wiki_db": "sin tabla citations", "uncovered": []}
    finally:
        wconn.close()
    aconn = sqlite3.connect(db_path)
    try:
        have = {r[0].split("youtube:")[1] for r in aconn.execute(
            "SELECT source_id FROM sources WHERE source_type='youtube_video'")}
    finally:
        aconn.close()
    uncovered = sorted(cited - have)
    return {"cited_videos": len(cited), "uncovered": uncovered}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=Path("data/ariadna.db"))
    p.add_argument("--corpus", type=Path, default=None,
                   help="ruta a ProxySummaries/data/playlists (default: config.DEFAULT_CORPUS_PATH)")
    p.add_argument("--wiki-db", type=Path, default=Path("data/wiki.db"))
    args = p.parse_args()

    corpus = args.corpus
    if corpus is None:
        from ariadna.config import DEFAULT_CORPUS_PATH
        corpus = Path(DEFAULT_CORPUS_PATH)
    if not corpus.exists():
        print(f"ERROR: corpus no encontrado en {corpus}", file=sys.stderr)
        return 2

    stats = populate(args.db, corpus)
    print(f"sources poblados: {stats['sources_inserted']} (de {stats['meta_files']} meta.json); "
          f"sources_total={stats['sources_total']}, source_projects(proxy)={stats['source_projects']}")

    cov = check_citation_coverage(args.db, args.wiki_db)
    if cov.get("uncovered"):
        print(f"⚠ {len(cov['uncovered'])} video_id citados en wiki.db SIN source: {cov['uncovered'][:10]}...")
        return 1
    print(f"✓ cobertura de citas: {cov.get('cited_videos', 0)} video_id citados, todos con source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
