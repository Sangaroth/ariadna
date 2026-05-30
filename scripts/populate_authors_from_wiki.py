#!/usr/bin/env python3
"""Puebla las tablas PER-PROJECT `page_domains`, `authors`, `author_aliases` y
`author_sources` de data/ariadna.db parseando el frontmatter YAML de las páginas
wiki (que YA es TAXONOMY-compliant: primary_domains[], orcid, wikidata_id,
given_names/family_name, birth/death_year).

Mapeo:
  page_domains   ← primary_domains[] (o domain[]) de CADA página
  authors        ← páginas page_type=author (author_id = page_id)
  author_aliases ← aliases[] de la página author
  author_sources ← role='subject_of' derivado de las citations de la página author
                   (las fuentes que la página cita = donde el autor es SUJETO de análisis).
                   role='author_of' NO se puebla: el frontmatter solo guarda un
                   CONTADOR (as_author_of_sources: 6), no la lista de source_id.
                   Se rellenará cuando se ingieran las obras del autor (Fase papers).

Itera las `pages` ya migradas (project='proxy') y lee su file_path. NO toca
Qdrant ni wiki.db. Idempotente.

Prerequisito: migrate_wiki_db_to_global (pages + citations ya pobladas).

Uso:
    python scripts/populate_authors_from_wiki.py
    python scripts/populate_authors_from_wiki.py --db data/ariadna.db --project proxy --repo .
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import yaml


def _frontmatter(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v).strip()]


def populate(db_path: Path, project_id: str, repo: Path) -> dict:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        pages = conn.execute(
            "SELECT page_id, page_type, file_path FROM pages WHERE project_id=?",
            (project_id,),
        ).fetchall()

        n_domains = n_authors = n_aliases = n_author_sources = 0
        missing_files: list[str] = []

        for page_id, page_type, file_path in pages:
            md_path = repo / file_path
            if not md_path.exists():
                missing_files.append(file_path)
                continue
            fm = _frontmatter(md_path)

            # page_domains: primary_domains[] (multi-valor OpenAlex) o domain[]
            domains = _as_list(fm.get("primary_domains")) or _as_list(fm.get("domain"))
            for d in dict.fromkeys(domains):  # dedup preservando orden
                conn.execute(
                    "INSERT OR IGNORE INTO page_domains(project_id, page_id, domain) VALUES (?,?,?)",
                    (project_id, page_id, d),
                )
                n_domains += 1

            if page_type != "author":
                continue

            # authors (author_id = page_id)
            orcid = fm.get("orcid")
            orcid = None if orcid in (None, "null", "", "None") else str(orcid)
            wikidata = fm.get("wikidata_id")
            wikidata = None if wikidata in (None, "null", "") else str(wikidata)
            conn.execute(
                "INSERT OR REPLACE INTO authors "
                "(project_id, author_id, canonical_name, given_names, family_name, "
                " orcid, wikidata_id, birth_year, death_year, page_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    project_id, page_id,
                    fm.get("canonical_name") or page_id,
                    fm.get("given_names"), fm.get("family_name"),
                    orcid, wikidata,
                    fm.get("birth_year") if isinstance(fm.get("birth_year"), int) else None,
                    fm.get("death_year") if isinstance(fm.get("death_year"), int) else None,
                    page_id,
                ),
            )
            n_authors += 1

            for alias in dict.fromkeys(_as_list(fm.get("aliases"))):
                conn.execute(
                    "INSERT OR IGNORE INTO author_aliases(project_id, author_id, alias) VALUES (?,?,?)",
                    (project_id, page_id, alias),
                )
                n_aliases += 1

            # author_sources subject_of: source_id distintos de las citations de la página
            src_ids = conn.execute(
                "SELECT DISTINCT source_id FROM citations WHERE project_id=? AND page_id=?",
                (project_id, page_id),
            ).fetchall()
            for (src_id,) in src_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO author_sources(project_id, author_id, source_id, role) "
                    "VALUES (?,?,?,'subject_of')",
                    (project_id, page_id, src_id),
                )
                n_author_sources += 1

        conn.commit()

        totals = {
            "page_domains": conn.execute(
                "SELECT COUNT(*) FROM page_domains WHERE project_id=?", (project_id,)).fetchone()[0],
            "authors": conn.execute(
                "SELECT COUNT(*) FROM authors WHERE project_id=?", (project_id,)).fetchone()[0],
            "author_aliases": conn.execute(
                "SELECT COUNT(*) FROM author_aliases WHERE project_id=?", (project_id,)).fetchone()[0],
            "author_sources": conn.execute(
                "SELECT COUNT(*) FROM author_sources WHERE project_id=?", (project_id,)).fetchone()[0],
        }
        return {"totals": totals, "missing_files": missing_files,
                "author_pages": n_authors, "pages_seen": len(pages)}
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=Path("data/ariadna.db"))
    p.add_argument("--project", default="proxy")
    p.add_argument("--repo", type=Path, default=Path("."), help="raíz del repo (para resolver file_path)")
    args = p.parse_args()

    r = populate(args.db, args.project, args.repo)
    t = r["totals"]
    print(f"poblado desde frontmatter (project={args.project}, {r['pages_seen']} páginas):")
    print(f"  page_domains: {t['page_domains']}")
    print(f"  authors: {t['authors']} (páginas page_type=author)")
    print(f"  author_aliases: {t['author_aliases']}")
    print(f"  author_sources (subject_of): {t['author_sources']}")
    if r["missing_files"]:
        print(f"  ⚠ {len(r['missing_files'])} file_path no encontrados: {r['missing_files'][:5]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
