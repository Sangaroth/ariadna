#!/usr/bin/env python3
"""Construye un índice SQLite derivado del directorio wiki/.

Principio: las páginas .md son la fuente de verdad. data/wiki.db es un índice
mecánico reconstruible. Si DB y .md divergen, gana .md (rebuild = ~5 segundos).
Cero curación humana del DB.

Uso:
    python scripts/build_wiki_db.py                       # rebuild full
    python scripts/build_wiki_db.py --check               # rebuild + asserts
    python scripts/build_wiki_db.py --query backlinks <page_id>
    python scripts/build_wiki_db.py --query drift         # wikilinks no declarados
    python scripts/build_wiki_db.py --query broken        # relations.to inexistentes
    python scripts/build_wiki_db.py --query citations <video_id>
    python scripts/build_wiki_db.py --query stats

Schema:
    pages          (page_id PK, page_type, canonical_name, domain_primary, file_path,
                    last_compiled, sources_count, review_status, body_md, indexed_at)
    aliases        (page_id, alias)
    relations      (from_page_id, type, to_page_id, note, weight)
    body_wikilinks (page_id, target_page_id)        -- todos los [[X]] del cuerpo
    citations      (page_id, video_id, timestamp_seconds, title, url)
    relation_types_canonical (type PK, description, inverse, from_types_csv, to_types_csv)

NOTA: el parser de frontmatter duplica la lógica de scripts/index_wiki_to_qdrant.py
y scripts/validate_wiki_relations.py. Refactor a módulo compartido pendiente cuando
los tres usen el DB como fuente.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys

import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

WIKI_DIR = REPO / "wiki"
DB_PATH = REPO / "data" / "wiki.db"
RELATION_TYPES_PATH = WIKI_DIR / "_meta" / "relation_types.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ariadna.wiki_db")

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([a-z0-9][a-z0-9_-]*)(?:\|[^\]]+)?\]\]")
RELATIONS_BLOCK_RE = re.compile(r"^relations:\s*\n((?:\s+-\s*[^\n]+\n)+)", re.MULTILINE)
RELATION_LINE_RE = re.compile(r"^\s+-\s*\{(.+)\}\s*$")
KV_RE = re.compile(r"(\w+)\s*:\s*([^,}]+?)(?=\s*,|\s*$)")
YT_CITATION_RE = re.compile(
    r"\[([^\]]+)\]\(https?://(?:www\.)?youtu\.be/([a-zA-Z0-9_-]+)(?:\?t=(\d+))?\)"
)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pages (
    page_id        TEXT PRIMARY KEY,
    page_type      TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    domain_primary TEXT,
    file_path      TEXT NOT NULL,
    last_compiled  TEXT,
    sources_count  INTEGER,
    review_status  TEXT,
    body_md        TEXT NOT NULL,
    indexed_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS aliases (
    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
    alias   TEXT NOT NULL,
    PRIMARY KEY (page_id, alias)
);
CREATE INDEX IF NOT EXISTS idx_aliases_alias ON aliases(alias);

CREATE TABLE IF NOT EXISTS relations (
    from_page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
    type         TEXT NOT NULL,
    to_page_id   TEXT NOT NULL,
    note         TEXT,
    weight       TEXT,
    PRIMARY KEY (from_page_id, type, to_page_id)
);
CREATE INDEX IF NOT EXISTS idx_relations_to   ON relations(to_page_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(type);

CREATE TABLE IF NOT EXISTS body_wikilinks (
    page_id        TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
    target_page_id TEXT NOT NULL,
    PRIMARY KEY (page_id, target_page_id)
);
CREATE INDEX IF NOT EXISTS idx_body_wikilinks_target ON body_wikilinks(target_page_id);

CREATE TABLE IF NOT EXISTS citations (
    page_id           TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
    video_id          TEXT NOT NULL,
    timestamp_seconds INTEGER NOT NULL DEFAULT 0,
    title             TEXT,
    url               TEXT NOT NULL,
    PRIMARY KEY (page_id, video_id, timestamp_seconds)
);
CREATE INDEX IF NOT EXISTS idx_citations_video ON citations(video_id);

CREATE TABLE IF NOT EXISTS relation_types_canonical (
    type           TEXT PRIMARY KEY,
    description    TEXT,
    inverse        TEXT,
    from_types_csv TEXT,
    to_types_csv   TEXT
);
"""


# --- parsers --------------------------------------------------------------


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
    out: list[dict[str, Any]] = []
    for r in rels:
        if isinstance(r, dict) and "type" in r and "to" in r:
            out.append(r)
    return out


def _extract_body_wikilinks(body: str) -> set[str]:
    return set(WIKILINK_RE.findall(body))


def _extract_citations(body: str) -> list[dict[str, Any]]:
    """Extrae citas a YouTube del body. Captura tanto '→ [title](url)' como inline.

    Deduplica por (video_id, timestamp_seconds): si la misma cita aparece N veces
    en la página (común — un timestamp se cita en varias secciones), se queda con
    el primer title encontrado.
    """
    seen: dict[tuple[str, int], dict[str, Any]] = {}
    for title, video_id, ts in YT_CITATION_RE.findall(body):
        ts_int = int(ts) if ts else 0
        key = (video_id, ts_int)
        if key in seen:
            continue
        url = f"https://youtu.be/{video_id}"
        if ts_int > 0:
            url += f"?t={ts_int}"
        seen[key] = {
            "video_id": video_id,
            "timestamp_seconds": ts_int,
            "title": title.strip(),
            "url": url,
        }
    return list(seen.values())


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
    }


# --- writer ---------------------------------------------------------------


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    return conn


def wipe(conn: sqlite3.Connection) -> None:
    """Borra contenido de las tablas (pero no las relation_types_canonical)."""
    for tbl in ("citations", "body_wikilinks", "relations", "aliases", "pages"):
        conn.execute(f"DELETE FROM {tbl}")


def upsert_page(conn: sqlite3.Connection, page: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT OR REPLACE INTO pages
        (page_id, page_type, canonical_name, domain_primary, file_path,
         last_compiled, sources_count, review_status, body_md, indexed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            page["page_id"], page["page_type"], page["canonical_name"],
            page["domain_primary"], page["file_path"], page["last_compiled"],
            page["sources_count"], page["review_status"], page["body_md"], now,
        ),
    )
    pid = page["page_id"]
    conn.executemany(
        "INSERT OR IGNORE INTO aliases (page_id, alias) VALUES (?, ?)",
        [(pid, a) for a in page["aliases"]],
    )
    conn.executemany(
        """INSERT OR REPLACE INTO relations
           (from_page_id, type, to_page_id, note, weight)
           VALUES (?, ?, ?, ?, ?)""",
        [
            (pid, r["type"], r["to"], r.get("note"), r.get("weight"))
            for r in page["relations"]
        ],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO body_wikilinks (page_id, target_page_id) VALUES (?, ?)",
        [(pid, t) for t in page["body_wikilinks"]],
    )
    conn.executemany(
        """INSERT OR REPLACE INTO citations
           (page_id, video_id, timestamp_seconds, title, url)
           VALUES (?, ?, ?, ?, ?)""",
        [
            (pid, c["video_id"], c["timestamp_seconds"], c["title"], c["url"])
            for c in page["citations"]
        ],
    )


def load_relation_types(conn: sqlite3.Connection) -> int:
    if not RELATION_TYPES_PATH.exists():
        log.warning("relation_types.json no encontrado, salto su carga")
        return 0
    data = json.loads(RELATION_TYPES_PATH.read_text(encoding="utf-8"))
    conn.execute("DELETE FROM relation_types_canonical")
    rows = []
    for type_name, spec in data.get("types", {}).items():
        rows.append((
            type_name,
            spec.get("description"),
            spec.get("inverse"),
            ",".join(spec.get("from") or []),
            ",".join(spec.get("to") or []),
        ))
    conn.executemany(
        """INSERT INTO relation_types_canonical
           (type, description, inverse, from_types_csv, to_types_csv)
           VALUES (?, ?, ?, ?, ?)""",
        rows,
    )
    return len(rows)


def rebuild(db_path: Path = DB_PATH) -> dict[str, int]:
    conn = open_db(db_path)
    try:
        with conn:
            wipe(conn)
            n_types = load_relation_types(conn)
            n_pages = 0
            for md in sorted(WIKI_DIR.rglob("*.md")):
                if md.name == "README.md":
                    continue
                page = parse_wiki_file(md)
                if not page:
                    continue
                upsert_page(conn, page)
                n_pages += 1
        # counts post-commit
        counts = {
            "pages": conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0],
            "aliases": conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0],
            "relations": conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0],
            "body_wikilinks": conn.execute("SELECT COUNT(*) FROM body_wikilinks").fetchone()[0],
            "citations": conn.execute("SELECT COUNT(*) FROM citations").fetchone()[0],
            "relation_types_canonical": n_types,
        }
        return counts
    finally:
        conn.close()


# --- queries presets ------------------------------------------------------


def q_backlinks(conn: sqlite3.Connection, page_id: str) -> list[dict[str, Any]]:
    """Páginas que apuntan a page_id, sea por relations o por wikilink en body."""
    rows = conn.execute(
        """
        SELECT 'relation' AS source, from_page_id AS page, type, note
        FROM relations WHERE to_page_id = ?
        UNION ALL
        SELECT 'body_wikilink' AS source, page_id AS page, NULL, NULL
        FROM body_wikilinks WHERE target_page_id = ?
        ORDER BY page, source
        """,
        (page_id, page_id),
    ).fetchall()
    return [dict(zip(["source", "page", "type", "note"], r)) for r in rows]


def q_broken_targets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """relations.to_page_id que no son pages existentes — candidatos a compilar."""
    rows = conn.execute(
        """
        SELECT to_page_id, COUNT(*) AS incoming, GROUP_CONCAT(DISTINCT from_page_id) AS from_pages
        FROM relations
        WHERE to_page_id NOT IN (SELECT page_id FROM pages)
        GROUP BY to_page_id
        ORDER BY incoming DESC, to_page_id
        """
    ).fetchall()
    return [dict(zip(["to_page_id", "incoming", "from_pages"], r)) for r in rows]


def q_drift(conn: sqlite3.Connection) -> dict[str, list]:
    """Mismatch entre body_wikilinks y relations declaradas."""
    in_body_not_in_relations = conn.execute(
        """
        SELECT bw.page_id, bw.target_page_id
        FROM body_wikilinks bw
        WHERE NOT EXISTS (
            SELECT 1 FROM relations r
            WHERE r.from_page_id = bw.page_id AND r.to_page_id = bw.target_page_id
        )
        ORDER BY bw.page_id, bw.target_page_id
        """
    ).fetchall()
    in_relations_not_in_body = conn.execute(
        """
        SELECT r.from_page_id, r.type, r.to_page_id
        FROM relations r
        WHERE NOT EXISTS (
            SELECT 1 FROM body_wikilinks bw
            WHERE bw.page_id = r.from_page_id AND bw.target_page_id = r.to_page_id
        )
        ORDER BY r.from_page_id, r.to_page_id
        """
    ).fetchall()
    return {
        "in_body_not_in_relations": [
            {"page_id": p, "target": t} for p, t in in_body_not_in_relations
        ],
        "in_relations_not_in_body": [
            {"page_id": p, "type": tp, "target": t}
            for p, tp, t in in_relations_not_in_body
        ],
    }


def q_citations(conn: sqlite3.Connection, video_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT page_id, timestamp_seconds, title, url
           FROM citations
           WHERE video_id = ?
           ORDER BY page_id, timestamp_seconds""",
        (video_id,),
    ).fetchall()
    return [dict(zip(["page_id", "timestamp_seconds", "title", "url"], r)) for r in rows]


def q_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    pages_by_type = dict(conn.execute(
        "SELECT page_type, COUNT(*) FROM pages GROUP BY page_type ORDER BY 2 DESC"
    ).fetchall())
    rels_by_type = dict(conn.execute(
        "SELECT type, COUNT(*) FROM relations GROUP BY type ORDER BY 2 DESC"
    ).fetchall())
    most_cited_videos = [
        dict(zip(["video_id", "n_pages", "n_citations"], r))
        for r in conn.execute(
            """SELECT video_id, COUNT(DISTINCT page_id), COUNT(*)
               FROM citations
               GROUP BY video_id
               ORDER BY 3 DESC
               LIMIT 10"""
        ).fetchall()
    ]
    most_referenced_pages = [
        dict(zip(["page_id", "incoming"], r))
        for r in conn.execute(
            """SELECT to_page_id, COUNT(*) AS n
               FROM relations
               GROUP BY to_page_id
               ORDER BY n DESC
               LIMIT 10"""
        ).fetchall()
    ]
    return {
        "pages_by_type": pages_by_type,
        "relations_by_type": rels_by_type,
        "most_cited_videos": most_cited_videos,
        "most_referenced_pages": most_referenced_pages,
    }


# --- check ----------------------------------------------------------------


def run_checks(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    """Asserts de coherencia. Devuelve (n_failed, lista de mensajes de error)."""
    errors: list[str] = []

    # 1. Toda relation.type debe estar en relation_types_canonical
    bad_types = conn.execute(
        """SELECT DISTINCT r.type
           FROM relations r
           WHERE r.type NOT IN (SELECT type FROM relation_types_canonical)"""
    ).fetchall()
    if bad_types:
        errors.append(
            f"types fuera del canónico: {[t[0] for t in bad_types]}"
        )

    # 2. No debe haber pages duplicadas (PK lo impide, doble check)
    dups = conn.execute(
        "SELECT page_id, COUNT(*) FROM pages GROUP BY page_id HAVING COUNT(*) > 1"
    ).fetchall()
    if dups:
        errors.append(f"page_id duplicados: {dups}")

    # 3. Toda página migrada debe tener al menos 1 relation declarada
    no_rels = conn.execute(
        """SELECT page_id FROM pages
           WHERE page_id NOT IN (SELECT from_page_id FROM relations)
           ORDER BY page_id"""
    ).fetchall()
    if no_rels:
        errors.append(f"páginas sin relations[]: {[r[0] for r in no_rels]}")

    return len(errors), errors


# --- main -----------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Construye / consulta data/wiki.db")
    ap.add_argument("--db", type=Path, default=DB_PATH, help=f"path al SQLite (default {DB_PATH})")
    ap.add_argument("--check", action="store_true", help="rebuild + asserts de coherencia")
    ap.add_argument("--query", nargs="+", help="preset: backlinks <pid> | broken | drift | citations <vid> | stats")
    ap.add_argument("--no-rebuild", action="store_true", help="no reconstruir antes de --query (asume DB ya al día)")
    args = ap.parse_args()

    if not (args.no_rebuild and args.query):
        counts = rebuild(args.db)
        log.info("Rebuild OK: %s", counts)

    if args.check:
        with sqlite3.connect(args.db) as conn:
            n_failed, errs = run_checks(conn)
        if n_failed:
            for e in errs:
                log.error("CHECK FAIL: %s", e)
            return 1
        log.info("Checks: PASS")
        return 0

    if args.query:
        with sqlite3.connect(args.db) as conn:
            preset = args.query[0]
            rest = args.query[1:]
            if preset == "backlinks":
                if not rest:
                    log.error("backlinks requiere <page_id>")
                    return 2
                out: Any = q_backlinks(conn, rest[0])
            elif preset == "broken":
                out = q_broken_targets(conn)
            elif preset == "drift":
                out = q_drift(conn)
            elif preset == "citations":
                if not rest:
                    log.error("citations requiere <video_id>")
                    return 2
                out = q_citations(conn, rest[0])
            elif preset == "stats":
                out = q_stats(conn)
            else:
                log.error("preset desconocido: %s", preset)
                return 2
        print(json.dumps(out, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
