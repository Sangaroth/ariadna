#!/usr/bin/env python3
"""Reconstruye las tablas wiki PER-PROJECT de data/ariadna.db desde el filesystem.

Principio: las páginas .md son la fuente de verdad. Las tablas wiki de ariadna.db
(`pages`, `aliases`, `relations`, `body_wikilinks`, `citations`, `page_domains`,
`authors`, `author_aliases`, `author_sources`) son un índice mecánico
reconstruible. Si DB y .md divergen, gana .md (rebuild = ~5 segundos). Cero
curación humana del DB.

Source-agnostic: las citas se extraen del cuerpo iterando `citation_link_re()` de
TODOS los adaptadores registrados (youtube, paper…), y se escriben al modelo
universal (`source_id` + `position` JSON + `position_key` + `position_url` +
`cite_markdown`). Añadir un tipo de fuente = añadir un adaptador, sin tocar esto.

NO toca las tablas GLOBALES (projects, sources, source_files, source_projects) ni
`research_queue`. El proyecto debe existir en `projects` (lo crea create_project).

Uso:
    python scripts/build_wiki_db.py --project proxy           # rebuild full
    python scripts/build_wiki_db.py --project proxy --check   # rebuild + asserts
    python scripts/build_wiki_db.py --project proxy --query backlinks <page_id>
    python scripts/build_wiki_db.py --project proxy --query broken
    python scripts/build_wiki_db.py --project proxy --query drift
    python scripts/build_wiki_db.py --project proxy --query citations <source_id|video_id>
    python scripts/build_wiki_db.py --project proxy --query stats
    python scripts/build_wiki_db.py --project proxy --db /tmp/test.db   # destino alt
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys

import yaml
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ariadna.project_config import ProjectConfig  # noqa: E402
from ariadna.sources.registry import iter_adapters  # noqa: E402

DB_PATH = REPO / "data" / "ariadna.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ariadna.wiki_db")

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([a-z0-9][a-z0-9_-]*)(?:\|[^\]]+)?\]\]")

# Serialización JSON compacta idéntica a SQLite json_object (sin espacios) — para
# que la columna `citations.position` sea byte-idéntica a la que dejó la migración.
_COMPACT = {"separators": (",", ":"), "ensure_ascii": False}


# --- parsers (regex legacy: reproduce wiki.db → migración byte a byte) -----


def _parse_yaml_list(fm_text: str, key: str) -> list[str]:
    pattern = rf"^{re.escape(key)}:\s*\n((?:\s*-\s*[^\n]+\n)+)"
    m = re.search(pattern, fm_text, re.MULTILINE)
    if not m:
        return []
    items: list[str] = []
    for line in m.group(1).splitlines():
        v = line.strip().lstrip("-").strip().strip('"').strip("'")
        if not v:
            continue
        wl = WIKILINK_RE.match(v)
        items.append(wl.group(1) if wl else v)
    return items


def _parse_scalar(fm_text: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*([^\n]+)$", fm_text, re.MULTILINE)
    if not m:
        return None
    val = m.group(1).strip().strip('"').strip("'")
    if val.lower() == "null" or val == "":
        return None
    return val


def _parse_int(fm_text: str, key: str) -> int | None:
    raw = _parse_scalar(fm_text, key)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_relations(fm_text: str) -> list[dict[str, Any]]:
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return []
    rels = fm.get("relations") or []
    return [r for r in rels if isinstance(r, dict) and "type" in r and "to" in r]


def _extract_body_wikilinks(body: str) -> set[str]:
    return set(WIKILINK_RE.findall(body))


def _extract_citations(body: str) -> list[dict[str, Any]]:
    """Extrae citas del cuerpo iterando los adaptadores registrados.

    Modelo universal: dedup por (source_id, position_key) conservando el PRIMER
    título (misma semántica que el _extract_citations YouTube-céntrico anterior).
    """
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for adapter in iter_adapters():
        for m in adapter.citation_link_re().finditer(body):
            ref = adapter.parse_citation_match(m)
            key = (ref.source_id, ref.position.key)
            if key in seen:
                continue
            seen[key] = {
                "source_id": ref.source_id,
                "position_key": ref.position.key,
                "position": json.dumps(ref.position.as_json_dict(), **_COMPACT),
                "position_url": ref.position_url,
                "cite_markdown": ref.cite_markdown,
                "title": ref.title,
            }
    return list(seen.values())


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v).strip()]


def parse_wiki_file(md_path: Path) -> dict[str, Any] | None:
    text = md_path.read_text(encoding="utf-8")
    fm = FRONTMATTER_RE.match(text)
    if not fm:
        log.warning("skip (no frontmatter): %s", md_path.relative_to(REPO))
        return None
    fm_text = fm.group(1)
    body = text[fm.end():]

    page_id = _parse_scalar(fm_text, "page_id")
    page_type = _parse_scalar(fm_text, "page_type")
    canonical_name = _parse_scalar(fm_text, "canonical_name")
    if not page_id or not page_type or not canonical_name:
        log.warning("skip (incomplete frontmatter): %s", md_path.relative_to(REPO))
        return None

    # Frontmatter YAML para page_domains/authors (reproduce populate_authors_from_wiki).
    try:
        fm_yaml = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm_yaml = {}
    if not isinstance(fm_yaml, dict):
        fm_yaml = {}

    return {
        "page_id": page_id,
        "page_type": page_type,
        "canonical_name": canonical_name,
        "domain_primary": _parse_scalar(fm_text, "domain_primary"),
        "file_path": str(md_path.relative_to(REPO)),
        "last_compiled": _parse_scalar(fm_text, "last_compiled"),
        "sources_count": _parse_int(fm_text, "sources_count"),
        "review_status": _parse_scalar(fm_text, "review_status"),
        "body_md": body.strip(),
        "aliases": _parse_yaml_list(fm_text, "aliases"),
        "relations": _parse_relations(fm_text),
        "body_wikilinks": sorted(_extract_body_wikilinks(body)),
        "citations": _extract_citations(body),
        # domains: primary_domains[] (multi-valor OpenAlex) o domain[]
        "page_domains": list(dict.fromkeys(
            _as_list(fm_yaml.get("primary_domains")) or _as_list(fm_yaml.get("domain"))
        )),
        "fm_yaml": fm_yaml,
    }


# --- writer ---------------------------------------------------------------


def open_db(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise SystemExit(
            f"ERROR: {path} no existe. Ejecuta scripts/init_ariadna_db.py primero."
        )
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _assert_project_exists(conn: sqlite3.Connection, project_id: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM projects WHERE project_id=?", (project_id,)
    ).fetchone()
    if row is None:
        raise SystemExit(
            f"ERROR: project_id={project_id!r} no existe en `projects`. "
            f"Créalo (create_project) antes de indexar su wiki."
        )


def wipe_project(conn: sqlite3.Connection, project_id: str) -> None:
    """Borra las filas wiki PER-PROJECT del proyecto. Las globales NO se tocan.

    pages cascada a aliases/relations/body_wikilinks/page_domains/citations.
    authors es FK a projects (no a pages) → borrado explícito (cascada sus *_aliases/_sources).
    """
    conn.execute("DELETE FROM authors WHERE project_id=?", (project_id,))
    conn.execute("DELETE FROM pages WHERE project_id=?", (project_id,))


def upsert_page(conn: sqlite3.Connection, project_id: str, page: dict[str, Any], now: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO pages
           (project_id, page_id, page_type, canonical_name, domain_primary, file_path,
            last_compiled, sources_count, review_status, body_md, indexed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            project_id, page["page_id"], page["page_type"], page["canonical_name"],
            page["domain_primary"], page["file_path"], page["last_compiled"],
            page["sources_count"], page["review_status"], page["body_md"], now,
        ),
    )
    pid = page["page_id"]
    conn.executemany(
        "INSERT OR IGNORE INTO aliases (project_id, page_id, alias) VALUES (?,?,?)",
        [(project_id, pid, a) for a in page["aliases"]],
    )
    conn.executemany(
        """INSERT OR REPLACE INTO relations
           (project_id, from_page_id, type, to_page_id, note, weight) VALUES (?,?,?,?,?,?)""",
        [(project_id, pid, r["type"], r["to"], r.get("note"), r.get("weight"))
         for r in page["relations"]],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO body_wikilinks (project_id, page_id, target_page_id) VALUES (?,?,?)",
        [(project_id, pid, t) for t in page["body_wikilinks"]],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO page_domains (project_id, page_id, domain) VALUES (?,?,?)",
        [(project_id, pid, d) for d in page["page_domains"]],
    )
    conn.executemany(
        """INSERT OR REPLACE INTO citations
           (project_id, page_id, source_id, position_key, position, position_url, cite_markdown, title)
           VALUES (?,?,?,?,?,?,?,?)""",
        [(project_id, pid, c["source_id"], c["position_key"], c["position"],
          c["position_url"], c["cite_markdown"], c["title"]) for c in page["citations"]],
    )


def populate_authors(conn: sqlite3.Connection, project_id: str, page: dict[str, Any]) -> None:
    """Reproduce populate_authors_from_wiki: authors/author_aliases/author_sources."""
    if page["page_type"] != "author":
        return
    pid = page["page_id"]
    fm = page["fm_yaml"]
    orcid = fm.get("orcid")
    orcid = None if orcid in (None, "null", "", "None") else str(orcid)
    wikidata = fm.get("wikidata_id")
    wikidata = None if wikidata in (None, "null", "") else str(wikidata)
    conn.execute(
        """INSERT OR REPLACE INTO authors
           (project_id, author_id, canonical_name, given_names, family_name,
            orcid, wikidata_id, birth_year, death_year, page_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            project_id, pid, fm.get("canonical_name") or pid,
            fm.get("given_names"), fm.get("family_name"), orcid, wikidata,
            fm.get("birth_year") if isinstance(fm.get("birth_year"), int) else None,
            fm.get("death_year") if isinstance(fm.get("death_year"), int) else None,
            pid,
        ),
    )
    for alias in dict.fromkeys(_as_list(fm.get("aliases"))):
        conn.execute(
            "INSERT OR IGNORE INTO author_aliases(project_id, author_id, alias) VALUES (?,?,?)",
            (project_id, pid, alias),
        )
    # author_sources subject_of: source_id distintos de las citations de la página author.
    for (src_id,) in conn.execute(
        "SELECT DISTINCT source_id FROM citations WHERE project_id=? AND page_id=?",
        (project_id, pid),
    ).fetchall():
        conn.execute(
            "INSERT OR IGNORE INTO author_sources(project_id, author_id, source_id, role) "
            "VALUES (?,?,?,'subject_of')",
            (project_id, pid, src_id),
        )


def _iter_relation_types(data: Any):
    """Itera (type_name, spec) tolerando `types` como dict {name: spec} o lista
    [{type, ...}]. relation_types_core.json usa dict; los *_ext.json usan lista."""
    types = data.get("types") if isinstance(data, dict) else None
    if isinstance(types, dict):
        yield from types.items()
    elif isinstance(types, list):
        for item in types:
            if isinstance(item, dict) and item.get("type"):
                yield item["type"], item


def load_relation_types_core(conn: sqlite3.Connection, project_id: str) -> int:
    """Carga relation_types_core.json (global, project_id=NULL) + ext per-project."""
    cfg = ProjectConfig(project_id)
    n = 0
    core_path = cfg.relation_types_core
    if core_path.exists():
        data = json.loads(core_path.read_text(encoding="utf-8"))
        conn.execute("DELETE FROM relation_types_canonical WHERE project_id IS NULL")
        for type_name, spec in _iter_relation_types(data):
            conn.execute(
                """INSERT INTO relation_types_canonical
                   (project_id, type, description, inverse, from_types_csv, to_types_csv)
                   VALUES (NULL,?,?,?,?,?)""",
                (type_name, spec.get("description"), spec.get("inverse"),
                 ",".join(spec.get("from") or []), ",".join(spec.get("to") or [])),
            )
            n += 1
    else:
        log.warning("relation_types_core.json no encontrado en %s", core_path)
    ext_path = cfg.relation_types_ext
    if ext_path.exists():
        data = json.loads(ext_path.read_text(encoding="utf-8"))
        conn.execute("DELETE FROM relation_types_canonical WHERE project_id=?", (project_id,))
        for type_name, spec in _iter_relation_types(data):
            conn.execute(
                """INSERT OR REPLACE INTO relation_types_canonical
                   (project_id, type, description, inverse, from_types_csv, to_types_csv)
                   VALUES (?,?,?,?,?,?)""",
                (project_id, type_name, spec.get("description"), spec.get("inverse"),
                 ",".join(spec.get("from") or []), ",".join(spec.get("to") or [])),
            )
    return n


def rebuild(db_path: Path, project_id: str) -> dict[str, int]:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cfg = ProjectConfig(project_id)
    wiki_dir = cfg.wiki_root
    conn = open_db(db_path)
    try:
        _assert_project_exists(conn, project_id)
        with conn:
            wipe_project(conn, project_id)
            n_types = load_relation_types_core(conn, project_id)
            n_pages = 0
            parsed: list[dict[str, Any]] = []
            for md in sorted(wiki_dir.rglob("*.md")):
                if md.name == "README.md":
                    continue
                page = parse_wiki_file(md)
                if not page:
                    continue
                upsert_page(conn, project_id, page, now)
                parsed.append(page)
                n_pages += 1
            # authors tras citations (subject_of deriva de citations ya insertadas).
            for page in parsed:
                populate_authors(conn, project_id, page)

        def cnt(tbl: str) -> int:
            return conn.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE project_id=?", (project_id,)
            ).fetchone()[0]

        return {
            "pages": cnt("pages"),
            "aliases": cnt("aliases"),
            "relations": cnt("relations"),
            "body_wikilinks": cnt("body_wikilinks"),
            "page_domains": cnt("page_domains"),
            "citations": cnt("citations"),
            "authors": cnt("authors"),
            "author_aliases": cnt("author_aliases"),
            "author_sources": cnt("author_sources"),
            "relation_types_core": n_types,
        }
    finally:
        conn.close()


# --- queries presets (project-scoped) -------------------------------------


def q_backlinks(conn: sqlite3.Connection, project_id: str, page_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT 'relation' AS source, from_page_id AS page, type, note
           FROM relations WHERE project_id=? AND to_page_id=?
           UNION ALL
           SELECT 'body_wikilink' AS source, page_id AS page, NULL, NULL
           FROM body_wikilinks WHERE project_id=? AND target_page_id=?
           ORDER BY page, source""",
        (project_id, page_id, project_id, page_id),
    ).fetchall()
    return [dict(zip(["source", "page", "type", "note"], r)) for r in rows]


def q_broken_targets(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT to_page_id, COUNT(*) AS incoming, GROUP_CONCAT(DISTINCT from_page_id) AS from_pages
           FROM relations
           WHERE project_id=? AND to_page_id NOT IN (SELECT page_id FROM pages WHERE project_id=?)
           GROUP BY to_page_id ORDER BY incoming DESC, to_page_id""",
        (project_id, project_id),
    ).fetchall()
    return [dict(zip(["to_page_id", "incoming", "from_pages"], r)) for r in rows]


def q_drift(conn: sqlite3.Connection, project_id: str) -> dict[str, list]:
    in_body = conn.execute(
        """SELECT bw.page_id, bw.target_page_id FROM body_wikilinks bw
           WHERE bw.project_id=? AND NOT EXISTS (
             SELECT 1 FROM relations r WHERE r.project_id=bw.project_id
               AND r.from_page_id=bw.page_id AND r.to_page_id=bw.target_page_id)
           ORDER BY bw.page_id, bw.target_page_id""",
        (project_id,),
    ).fetchall()
    in_rel = conn.execute(
        """SELECT r.from_page_id, r.type, r.to_page_id FROM relations r
           WHERE r.project_id=? AND NOT EXISTS (
             SELECT 1 FROM body_wikilinks bw WHERE bw.project_id=r.project_id
               AND bw.page_id=r.from_page_id AND bw.target_page_id=r.to_page_id)
           ORDER BY r.from_page_id, r.to_page_id""",
        (project_id,),
    ).fetchall()
    return {
        "in_body_not_in_relations": [{"page_id": p, "target": t} for p, t in in_body],
        "in_relations_not_in_body": [{"page_id": p, "type": tp, "target": t} for p, tp, t in in_rel],
    }


def q_citations(conn: sqlite3.Connection, project_id: str, source: str) -> list[dict[str, Any]]:
    # Acepta source_id completo (youtube:ID) o un video_id desnudo (→ youtube:ID).
    source_id = source if ":" in source else f"youtube:{source}"
    rows = conn.execute(
        """SELECT page_id, position_key, position, title, position_url FROM citations
           WHERE project_id=? AND source_id=? ORDER BY page_id, position_key""",
        (project_id, source_id),
    ).fetchall()
    return [dict(zip(["page_id", "position_key", "position", "title", "position_url"], r)) for r in rows]


def q_stats(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    pages_by_type = dict(conn.execute(
        "SELECT page_type, COUNT(*) FROM pages WHERE project_id=? GROUP BY page_type ORDER BY 2 DESC",
        (project_id,)).fetchall())
    rels_by_type = dict(conn.execute(
        "SELECT type, COUNT(*) FROM relations WHERE project_id=? GROUP BY type ORDER BY 2 DESC",
        (project_id,)).fetchall())
    most_cited = [dict(zip(["source_id", "n_pages", "n_citations"], r)) for r in conn.execute(
        """SELECT source_id, COUNT(DISTINCT page_id), COUNT(*) FROM citations
           WHERE project_id=? GROUP BY source_id ORDER BY 3 DESC LIMIT 10""",
        (project_id,)).fetchall()]
    most_ref = [dict(zip(["page_id", "incoming"], r)) for r in conn.execute(
        """SELECT to_page_id, COUNT(*) AS n FROM relations WHERE project_id=?
           GROUP BY to_page_id ORDER BY n DESC LIMIT 10""",
        (project_id,)).fetchall()]
    return {
        "pages_by_type": pages_by_type,
        "relations_by_type": rels_by_type,
        "most_cited_sources": most_cited,
        "most_referenced_pages": most_ref,
    }


# --- check ----------------------------------------------------------------


def run_checks(conn: sqlite3.Connection, project_id: str) -> tuple[int, list[str]]:
    errors: list[str] = []
    # 1. Toda relation.type debe estar en el canónico (core global + ext del proyecto).
    bad_types = conn.execute(
        """SELECT DISTINCT r.type FROM relations r
           WHERE r.project_id=? AND r.type NOT IN (
             SELECT type FROM relation_types_canonical
             WHERE project_id IS NULL OR project_id=?)""",
        (project_id, project_id),
    ).fetchall()
    if bad_types:
        errors.append(f"types fuera del canónico: {[t[0] for t in bad_types]}")
    # 2. page_id duplicados (PK lo impide; doble check).
    dups = conn.execute(
        "SELECT page_id, COUNT(*) FROM pages WHERE project_id=? GROUP BY page_id HAVING COUNT(*)>1",
        (project_id,)).fetchall()
    if dups:
        errors.append(f"page_id duplicados: {dups}")
    # 3. Toda página debe declarar al menos 1 relation.
    no_rels = conn.execute(
        """SELECT page_id FROM pages WHERE project_id=? AND page_id NOT IN (
             SELECT from_page_id FROM relations WHERE project_id=?) ORDER BY page_id""",
        (project_id, project_id)).fetchall()
    if no_rels:
        errors.append(f"páginas sin relations[]: {[r[0] for r in no_rels]}")
    return len(errors), errors


# --- main -----------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Construye / consulta las tablas wiki de ariadna.db")
    ap.add_argument("--project", required=True, help="slug del proyecto (p.ej. proxy)")
    ap.add_argument("--db", type=Path, default=DB_PATH, help=f"path al SQLite (default {DB_PATH})")
    ap.add_argument("--check", action="store_true", help="rebuild + asserts de coherencia")
    ap.add_argument("--query", nargs="+",
                    help="preset: backlinks <pid> | broken | drift | citations <src> | stats")
    ap.add_argument("--no-rebuild", action="store_true", help="no reconstruir antes de --query")
    args = ap.parse_args()

    if not (args.no_rebuild and args.query):
        counts = rebuild(args.db, args.project)
        log.info("Rebuild OK (project=%s): %s", args.project, counts)

    if args.check:
        with sqlite3.connect(args.db) as conn:
            n_failed, errs = run_checks(conn, args.project)
        if n_failed:
            for e in errs:
                log.error("CHECK FAIL: %s", e)
            return 1
        log.info("Checks: PASS")
        return 0

    if args.query:
        with sqlite3.connect(args.db) as conn:
            preset, rest = args.query[0], args.query[1:]
            if preset == "backlinks":
                if not rest:
                    log.error("backlinks requiere <page_id>"); return 2
                out: Any = q_backlinks(conn, args.project, rest[0])
            elif preset == "broken":
                out = q_broken_targets(conn, args.project)
            elif preset == "drift":
                out = q_drift(conn, args.project)
            elif preset == "citations":
                if not rest:
                    log.error("citations requiere <source_id|video_id>"); return 2
                out = q_citations(conn, args.project, rest[0])
            elif preset == "stats":
                out = q_stats(conn, args.project)
            else:
                log.error("preset desconocido: %s", preset); return 2
        print(json.dumps(out, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
