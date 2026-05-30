"""Gestión de proyectos: create_project + list_projects (lógica, sin MCP).

Aislado del server para que el worker (F7) y los tests lo reusen. Escribe la
tabla GLOBAL `projects` de ariadna.db y crea el árbol `projects/<slug>/` en disco.
Contrato: spec §5.3 + §6.1/§6.2.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ariadna.config import PROJECT_ROOT

ARIADNA_DB = PROJECT_ROOT / "data" / "ariadna.db"
PROJECTS_DIR = PROJECT_ROOT / "projects"
GLOBAL_META = PROJECT_ROOT / "wiki" / "_meta"

SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}[a-z0-9]$")

# Subdirs de wiki/ que create_project siembra con .gitkeep (spec §5.3).
WIKI_SUBDIRS = ["concepts", "authors", "entities/works", "entities/institutions", "synthesis"]

# Defaults globales → nombre de override per-proyecto (seed_from_templates).
SEED_FILES = {
    "scope_default.md": "scope.md",
    "topic_filters_default.json": "topic_filters.json",
    "subagent_prompt_default.md": "subagent_prompt.md",
    "canonical_whitelist_default.json": "canonical_whitelist.json",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _err(code: str, msg: str) -> dict:
    return {"error": msg, "code": code}


def _project_row_exists(conn: sqlite3.Connection, slug: str) -> bool:
    return conn.execute("SELECT 1 FROM projects WHERE project_id=?", (slug,)).fetchone() is not None


def create_project(
    slug: str,
    name: str,
    description: str = "",
    seed_from_templates: bool = False,
    inherit_from: str | None = None,
    db_path: Path = ARIADNA_DB,
) -> dict:
    """Crea un proyecto vacío (tabla projects + árbol projects/<slug>/).

    seed_from_templates e inherit_from son mutuamente excluyentes. Devuelve
    {project_id, paths_created, message} o {error, code}. No crea nada si valida mal.
    """
    if not SLUG_RE.match(slug or ""):
        return _err("SLUG_INVALID", f"slug {slug!r} no cumple ^[a-z][a-z0-9-]{{1,40}}[a-z0-9]$")
    if seed_from_templates and inherit_from:
        return _err("INCOMPATIBLE_OPTIONS", "seed_from_templates e inherit_from son mutuamente excluyentes")

    proj_dir = PROJECTS_DIR / slug
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        if _project_row_exists(conn, slug) or proj_dir.exists():
            return _err("SLUG_DUPLICATE", f"el proyecto {slug!r} ya existe")
        if inherit_from is not None:
            parent_meta = PROJECTS_DIR / inherit_from / "_meta"
            if not _project_row_exists(conn, inherit_from) or not parent_meta.is_dir():
                return _err("INHERIT_FROM_NOT_FOUND", f"proyecto base {inherit_from!r} no existe")

        created: list[str] = []

        def mk(path: Path) -> None:
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path.relative_to(PROJECT_ROOT)))

        # _meta/ + extraction_runs/
        meta_dir = proj_dir / "_meta"
        mk(meta_dir)
        mk(meta_dir / "extraction_runs")
        # wiki/ + subdirs con .gitkeep
        for sub in WIKI_SUBDIRS:
            d = proj_dir / "wiki" / sub
            d.mkdir(parents=True, exist_ok=True)
            (d / ".gitkeep").write_text("", encoding="utf-8")
            created.append(str((d / ".gitkeep").relative_to(PROJECT_ROOT)))

        # relation_types_ext.json + INDEX.md placeholders
        (meta_dir / "relation_types_ext.json").write_text('{"types": []}\n', encoding="utf-8")
        (meta_dir / "INDEX.md").write_text(f"# {name}\n\n_Proyecto {slug} — sin páginas compiladas todavía._\n", encoding="utf-8")
        created += [
            str((meta_dir / "relation_types_ext.json").relative_to(PROJECT_ROOT)),
            str((meta_dir / "INDEX.md").relative_to(PROJECT_ROOT)),
        ]

        # seed_from_templates: copia defaults globales (quitando _default).
        if seed_from_templates:
            for src_name, dst_name in SEED_FILES.items():
                src = GLOBAL_META / src_name
                if src.exists():
                    shutil.copyfile(src, meta_dir / dst_name)
                    created.append(str((meta_dir / dst_name).relative_to(PROJECT_ROOT)))
        # inherit_from: copia los overrides (archivos top-level) del proyecto base.
        elif inherit_from is not None:
            parent_meta = PROJECTS_DIR / inherit_from / "_meta"
            for f in sorted(parent_meta.iterdir()):
                if f.is_file():
                    shutil.copyfile(f, meta_dir / f.name)
                    created.append(str((meta_dir / f.name).relative_to(PROJECT_ROOT)))

        conn.execute(
            "INSERT INTO projects (project_id, name, description, created_at) VALUES (?,?,?,?)",
            (slug, name, description, _now()),
        )
        conn.commit()
        return {
            "project_id": slug,
            "paths_created": created,
            "message": f"proyecto {slug!r} creado ({len(created)} rutas)",
        }
    finally:
        conn.close()


def list_projects(include_archived: bool = False, db_path: Path = ARIADNA_DB, store=None) -> dict:
    """Devuelve {projects: [{project_id, name, description, n_pages, n_chunks,
    n_queue_pending, created_at, archived_at}]}.

    n_chunks = puntos Qdrant del proyecto si se pasa `store` (CorpusStore); si no,
    cae al nº de fuentes ingeridas (source_projects) como proxy DB-only.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        where = "" if include_archived else " WHERE archived_at IS NULL"
        rows = conn.execute(
            f"SELECT project_id, name, description, created_at, archived_at FROM projects{where} ORDER BY created_at"
        ).fetchall()
        out = []
        for pid, name, desc, created, archived in rows:
            n_pages = conn.execute("SELECT COUNT(*) FROM pages WHERE project_id=?", (pid,)).fetchone()[0]
            n_pending = conn.execute(
                "SELECT COUNT(*) FROM research_queue WHERE project_id=? AND status='pending'", (pid,)).fetchone()[0]
            if store is not None:
                n_chunks = store.count_by_project(pid)
            else:
                n_chunks = conn.execute(
                    "SELECT COUNT(*) FROM source_projects WHERE project_id=?", (pid,)).fetchone()[0]
            out.append({
                "project_id": pid, "name": name, "description": desc,
                "n_pages": n_pages, "n_chunks": n_chunks,
                "n_queue_pending": n_pending,
                "created_at": created, "archived_at": archived,
            })
        return {"projects": out}
    finally:
        conn.close()
