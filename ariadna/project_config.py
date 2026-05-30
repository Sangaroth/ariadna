"""Resolución de rutas y configuración editorial POR PROYECTO.

Layout (decisión: nada legacy, todo bajo projects/<slug>/):

    projects/<slug>/
        wiki/        concepts/ authors/ entities/{works,institutions}/ synthesis/
        _meta/       scope.md, topic_filters.json, canonical_whitelist.json,
                     subagent_prompt.md, relation_types_ext.json, extraction_runs/,
                     semantic_recovery_cache.json, INDEX.md, ...

    wiki/_meta/      (GLOBAL, compartido por todos los proyectos)
        relation_types_core.json          # ~30 tipos universales
        scope_default.md                  # plantillas editables (override→default)
        topic_filters_default.json
        subagent_prompt_default.md
        canonical_whitelist_default.json

Resolución override→default: si projects/<slug>/_meta/<name> existe, se usa; si no,
wiki/_meta/<stem>_default.<ext>. relation_types = core global + ext per-proyecto.
"""

from __future__ import annotations

from pathlib import Path

from ariadna.config import PROJECT_ROOT

PROJECTS_DIR = PROJECT_ROOT / "projects"
GLOBAL_META = PROJECT_ROOT / "wiki" / "_meta"
RELATION_TYPES_CORE = GLOBAL_META / "relation_types_core.json"

DEFAULT_PROJECT = "proxy"


class ProjectConfig:
    """Rutas y archivos de configuración de un proyecto."""

    def __init__(self, project_id: str = DEFAULT_PROJECT):
        self.project_id = project_id
        self.root = PROJECTS_DIR / project_id
        self.wiki_root = self.root / "wiki"
        self.meta_dir = self.root / "_meta"
        self.extraction_runs = self.meta_dir / "extraction_runs"
        # Sumarios persistidos (IdeaBlocks): el paso CARO/no-determinista del pipeline.
        # Persistirlos permite re-ejecutar extract/index sin re-sumarizar. Ver ideablocks.py.
        self.summaries_dir = self.root / "summaries"

    # --- resolución override→default ---------------------------------------
    def _resolve(self, name: str) -> Path:
        local = self.meta_dir / name
        if local.exists():
            return local
        stem, _, ext = name.rpartition(".")
        return GLOBAL_META / f"{stem}_default.{ext}"

    @property
    def scope(self) -> Path:
        return self._resolve("scope.md")

    @property
    def topic_filters(self) -> Path:
        return self._resolve("topic_filters.json")

    @property
    def canonical_whitelist(self) -> Path:
        return self._resolve("canonical_whitelist.json")

    @property
    def subagent_prompt(self) -> Path:
        return self._resolve("subagent_prompt.md")

    # --- archivos sin default (per-proyecto puro) --------------------------
    @property
    def relation_types_core(self) -> Path:
        return RELATION_TYPES_CORE

    @property
    def relation_types_ext(self) -> Path:
        return self.meta_dir / "relation_types_ext.json"

    @property
    def semantic_recovery_cache(self) -> Path:
        return self.meta_dir / "semantic_recovery_cache.json"

    @property
    def processed_videos(self) -> Path:
        return self.meta_dir / "processed_videos.json"

    @property
    def index_md(self) -> Path:
        return self.meta_dir / "INDEX.md"

    def exists(self) -> bool:
        return self.root.is_dir()

    def __repr__(self) -> str:
        return f"ProjectConfig({self.project_id!r}, root={self.root})"


def list_project_ids() -> list[str]:
    """Slugs de proyectos existentes (subdirs de projects/ con wiki/)."""
    if not PROJECTS_DIR.is_dir():
        return []
    return sorted(
        p.name for p in PROJECTS_DIR.iterdir()
        if p.is_dir() and (p / "wiki").is_dir()
    )
