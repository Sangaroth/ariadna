#!/usr/bin/env python3
"""Migra el contenido de data/wiki.db (mono-proyecto, YouTube-céntrico) a las
tablas PER-PROJECT de data/ariadna.db bajo project_id='proxy', generalizando las
citations al modelo universal (source_id + position JSON + position_url + position_key).

Mapeo:
  pages, aliases, body_wikilinks, relations  → idénticos + project_id='proxy'
  relation_types_canonical (wiki.db sin project_id) → core global (project_id=NULL)
  citations (page_id, video_id, timestamp_seconds, title, url) →
     (project_id='proxy', page_id,
      source_id      = 'youtube:'||video_id,
      position_key   = str(timestamp_seconds),
      position       = {"timestamp_seconds": ts},
      position_url   = url,                       (ya es youtu.be/ID?t=SECS)
      cite_markdown  = '['||title||']('||url||')',(title ya trae el '(mm:ss)')
      title          = title)

ATTACH read-only sobre wiki.db: NO lo modifica. NO toca Qdrant. Idempotente
(INSERT OR REPLACE). Prerequisito: populate_sources_from_proxysummaries (los
source_id youtube:<id> deben existir en `sources`).

Uso:
    python scripts/migrate_wiki_db_to_global.py
    python scripts/migrate_wiki_db_to_global.py --db data/ariadna.db --wiki-db data/wiki.db --project proxy
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def migrate(db_path: Path, wiki_db: Path, project_id: str) -> dict:
    conn = sqlite3.connect(f"file:{db_path}", uri=True)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"ATTACH DATABASE 'file:{wiki_db}?mode=ro' AS old")

        # 1. pages PRIMERO (las demás tablas tienen FK a pages).
        conn.execute(
            """INSERT OR REPLACE INTO pages
               (project_id, page_id, page_type, canonical_name, domain_primary,
                file_path, last_compiled, sources_count, review_status, body_md, indexed_at)
               SELECT ?, page_id, page_type, canonical_name, domain_primary,
                      file_path, last_compiled, sources_count, review_status, body_md, indexed_at
               FROM old.pages""",
            (project_id,),
        )

        # 2. aliases
        conn.execute(
            "INSERT OR REPLACE INTO aliases (project_id, page_id, alias) "
            "SELECT ?, page_id, alias FROM old.aliases",
            (project_id,),
        )

        # 3. body_wikilinks
        conn.execute(
            "INSERT OR REPLACE INTO body_wikilinks (project_id, page_id, target_page_id) "
            "SELECT ?, page_id, target_page_id FROM old.body_wikilinks",
            (project_id,),
        )

        # 4. relations (sin FK a to_page_id por diseño)
        conn.execute(
            "INSERT OR REPLACE INTO relations (project_id, from_page_id, type, to_page_id, note, weight) "
            "SELECT ?, from_page_id, type, to_page_id, note, weight FROM old.relations",
            (project_id,),
        )

        # 5. relation_types_canonical → CORE global (project_id NULL)
        conn.execute(
            "INSERT OR REPLACE INTO relation_types_canonical "
            "(project_id, type, description, inverse, from_types_csv, to_types_csv) "
            "SELECT NULL, type, description, inverse, from_types_csv, to_types_csv "
            "FROM old.relation_types_canonical"
        )

        # 6. citations GENERALIZADAS. Solo las que apuntan a una page existente
        #    (FK); en la práctica todas, pero filtramos por robustez.
        conn.execute(
            """INSERT OR REPLACE INTO citations
               (project_id, page_id, source_id, position_key, position, position_url, cite_markdown, title)
               SELECT ?,
                      c.page_id,
                      'youtube:' || c.video_id,
                      CAST(c.timestamp_seconds AS TEXT),
                      json_object('timestamp_seconds', c.timestamp_seconds),
                      c.url,
                      '[' || COALESCE(c.title, '') || '](' || c.url || ')',
                      c.title
               FROM old.citations c
               WHERE c.page_id IN (SELECT page_id FROM old.pages)""",
            (project_id,),
        )

        conn.commit()

        def cnt(table: str, where: str = "") -> int:
            return conn.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]

        stats = {
            "pages": cnt("pages", f"WHERE project_id='{project_id}'"),
            "aliases": cnt("aliases", f"WHERE project_id='{project_id}'"),
            "body_wikilinks": cnt("body_wikilinks", f"WHERE project_id='{project_id}'"),
            "relations": cnt("relations", f"WHERE project_id='{project_id}'"),
            "relation_types_core": cnt("relation_types_canonical", "WHERE project_id IS NULL"),
            "citations": cnt("citations", f"WHERE project_id='{project_id}'"),
        }
        # Comparación con wiki.db (fuente).
        src = {
            "pages": conn.execute("SELECT COUNT(*) FROM old.pages").fetchone()[0],
            "aliases": conn.execute("SELECT COUNT(*) FROM old.aliases").fetchone()[0],
            "body_wikilinks": conn.execute("SELECT COUNT(*) FROM old.body_wikilinks").fetchone()[0],
            "relations": conn.execute("SELECT COUNT(*) FROM old.relations").fetchone()[0],
            "relation_types_core": conn.execute("SELECT COUNT(*) FROM old.relation_types_canonical").fetchone()[0],
            "citations": conn.execute(
                "SELECT COUNT(*) FROM old.citations WHERE page_id IN (SELECT page_id FROM old.pages)"
            ).fetchone()[0],
        }
        # Cobertura: ¿todo source_id youtube:<id> de citations está en `sources`?
        orphan_sources = conn.execute(
            """SELECT COUNT(DISTINCT c.source_id) FROM citations c
               WHERE c.project_id=? AND c.source_id NOT IN (SELECT source_id FROM sources)""",
            (project_id,),
        ).fetchone()[0]
        return {"target": stats, "source": src, "orphan_citation_sources": orphan_sources}
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=Path("data/ariadna.db"))
    p.add_argument("--wiki-db", type=Path, default=Path("data/wiki.db"))
    p.add_argument("--project", default="proxy")
    args = p.parse_args()

    if not args.wiki_db.exists():
        print(f"ERROR: {args.wiki_db} no existe", file=sys.stderr)
        return 2

    r = migrate(args.db, args.wiki_db, args.project)
    print(f"migración wiki.db → ariadna.db (project={args.project}):")
    ok = True
    for k, tgt in r["target"].items():
        src = r["source"][k]
        match = "✓" if tgt == src else "✗"
        if tgt != src:
            ok = False
        print(f"  {match} {k}: target={tgt}  source={src}")
    if r["orphan_citation_sources"]:
        print(f"  ✗ {r['orphan_citation_sources']} source_id de citations SIN fila en `sources` "
              f"(correr populate_sources primero)")
        ok = False
    else:
        print(f"  ✓ todos los source_id de citations resuelven contra `sources`")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
