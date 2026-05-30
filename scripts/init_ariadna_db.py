#!/usr/bin/env python3
"""Crea `data/ariadna.db` (SQLite, WAL) con el SCHEMA UNIFICADO: multi-tenancy +
modelo de referencias universal (TAXONOMY_PROPOSAL §3 fusionado con spec §4.1).

Es la capa MENOS reversible del proyecto — el schema se sobre-especifica a
propósito (cambiar una categoría/columna cuesta re-procesar todo el corpus).

Reglas de aislamiento (la decisión clave):
  - GLOBAL (dedup/reproducibilidad, NUNCA se sirve como contexto):
      projects, source_files, sources, source_projects, relation_types_canonical(core).
  - PER-PROJECT (llevan project_id en PK, aislados de verdad):
      research_queue, pages, page_domains, aliases, relations, body_wikilinks,
      authors, author_aliases, author_sources, citations.
  El 'Jung' de Proxy y el de otro proyecto son entidades independientes
  (authors es per-project). Lo único compartido es el ARCHIVO de la fuente
  (source_files por hash) y su registro bibliográfico canónico (sources).

Idempotente: CREATE ... IF NOT EXISTS. No siembra datos (eso lo hacen los
scripts de migración/poblado). NO toca data/wiki.db ni Qdrant.

Uso:
    python scripts/init_ariadna_db.py                      # crea data/ariadna.db
    python scripts/init_ariadna_db.py --db /tmp/test.db    # destino alternativo
    python scripts/init_ariadna_db.py --check              # verifica schema + WAL
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

SCHEMA_VERSION = "2.0.0"
DEFAULT_DB = Path("data/ariadna.db")

# --------------------------------------------------------------------------- #
# DDL — orden importa por las FK (padres antes que hijos).
# --------------------------------------------------------------------------- #
SCHEMA_SQL = """
-- ===================== CAPA GLOBAL (identidad + archivo) ==================== --

-- [GLOBAL] Identidad de proyectos.
CREATE TABLE IF NOT EXISTS projects (
    project_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    created_at      TEXT NOT NULL,
    archived_at     TEXT,
    config_version  TEXT NOT NULL DEFAULT '1.0',
    schema_version  TEXT NOT NULL DEFAULT '2.0.0'
);

-- [GLOBAL] Archivo content-addressable. 1 fila por blob físico en
-- data/sources/<hash[:2]>/<hash>.<ext>. El archivo NUNCA se sirve como contexto;
-- existe para dedup y reproducibilidad (un DOI retirado no deja chunks huérfanos).
CREATE TABLE IF NOT EXISTS source_files (
    source_file_hash  TEXT PRIMARY KEY,            -- sha256 del blob crudo
    ext               TEXT NOT NULL,               -- pdf|html|json|vtt|...
    byte_size         INTEGER NOT NULL,
    original_url      TEXT,                         -- de dónde se descargó (puede morir)
    archived_at       TEXT NOT NULL
);

-- [GLOBAL] Registro bibliográfico canónico. 1 fila por documento.
-- source_id es la identidad global <scheme>:<id> (youtube:ID, doi:..., arxiv:..., url:sha256).
-- Un paper compartido entre proyectos tiene UNA fila aquí; la curación editorial
-- (autores como entidades, aliases, dominios) sí es per-project (tabla authors).
CREATE TABLE IF NOT EXISTS sources (
    source_id          TEXT PRIMARY KEY,
    source_type        TEXT NOT NULL,              -- youtube_video|paper|book|book_chapter|web_article|podcast_episode|lecture|thread|note
    title              TEXT NOT NULL,
    language           TEXT,                        -- BCP-47
    publication_date   TEXT,                        -- ISO 8601 parcial OK
    canonical_url      TEXT,
    abstract           TEXT,
    confidence_source  TEXT,                        -- peer_reviewed|preprint|published|self_published|transcript|commentary
    ingest_method      TEXT,                        -- youtube_transcript_api|markitdown|claude_summarizer|proxysummaries|...
    source_file_hash   TEXT REFERENCES source_files(source_file_hash),  -- NULL para youtube (cache ProxySummaries)
    type_metadata      TEXT,                        -- JSON: campos por tipo (channel, duration_seconds, doi, journal, isbn, authors[]...)
    schema_version     TEXT NOT NULL DEFAULT '2.0.0',
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sources_type ON sources(source_type);

-- [GLOBAL+JOIN] Qué proyectos han ingerido cada fuente (uso, no propiedad).
CREATE TABLE IF NOT EXISTS source_projects (
    source_id   TEXT NOT NULL REFERENCES sources(source_id),
    project_id  TEXT NOT NULL REFERENCES projects(project_id),
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (source_id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_source_projects_project ON source_projects(project_id);

-- ===================== COLA DE INGESTA (per-project vía FK) ================= --

CREATE TABLE IF NOT EXISTS research_queue (
    request_id        TEXT PRIMARY KEY,             -- uuid v4
    project_id        TEXT NOT NULL REFERENCES projects(project_id),
    source_url        TEXT NOT NULL,
    source_type       TEXT NOT NULL,                -- youtube|paper|web|pdf|unknown (detectado o explícito)
    status            TEXT NOT NULL DEFAULT 'pending',  -- pending|processing|done|failed|cancelled
    priority          INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    picked_up_at      TEXT,
    completed_at      TEXT,
    assigned_worker   TEXT,
    retry_count       INTEGER NOT NULL DEFAULT 0,
    error_msg         TEXT,
    notes             TEXT,
    metadata          TEXT,                          -- JSON blob: hints específicos
    source_file_hash  TEXT                           -- enlace al blob archivado (FK lógica a source_files)
);
CREATE INDEX IF NOT EXISTS idx_queue_status_type ON research_queue(status, source_type);
CREATE INDEX IF NOT EXISTS idx_queue_project ON research_queue(project_id);
-- Idempotencia: misma (project, url) en pending/processing es un solo item.
CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_dedup
    ON research_queue(project_id, source_url)
    WHERE status IN ('pending', 'processing');

-- ===================== WIKI DERIVADA (todas PER-PROJECT) =================== --

CREATE TABLE IF NOT EXISTS pages (
    page_id        TEXT NOT NULL,
    project_id     TEXT NOT NULL REFERENCES projects(project_id),
    page_type      TEXT NOT NULL,                   -- concept|author|entity_work|entity_institution|synthesis
    canonical_name TEXT NOT NULL,
    domain_primary TEXT,                              -- OpenAlex domain (del frontmatter)
    file_path      TEXT NOT NULL,
    last_compiled  TEXT,
    sources_count  INTEGER,
    review_status  TEXT,
    body_md        TEXT NOT NULL,
    indexed_at     TEXT NOT NULL,
    PRIMARY KEY (project_id, page_id)
);
CREATE INDEX IF NOT EXISTS idx_pages_project ON pages(project_id);
CREATE INDEX IF NOT EXISTS idx_pages_type ON pages(project_id, page_type);

-- domain[] multi-valor (TAXONOMY §4.3). domain_primary va en pages.
CREATE TABLE IF NOT EXISTS page_domains (
    project_id  TEXT NOT NULL,
    page_id     TEXT NOT NULL,
    domain      TEXT NOT NULL,                       -- OpenAlex group.discipline[.school]
    PRIMARY KEY (project_id, page_id, domain),
    FOREIGN KEY (project_id, page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_page_domains_domain ON page_domains(domain);

CREATE TABLE IF NOT EXISTS aliases (
    project_id  TEXT NOT NULL,
    page_id     TEXT NOT NULL,
    alias       TEXT NOT NULL,
    PRIMARY KEY (project_id, page_id, alias),
    FOREIGN KEY (project_id, page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
);
-- Scoped por proyecto: aislamiento total (el alias 'sombra' de un proyecto no
-- colisiona con el de otro).
CREATE INDEX IF NOT EXISTS idx_aliases_alias ON aliases(project_id, alias);

CREATE TABLE IF NOT EXISTS relations (
    project_id    TEXT NOT NULL,
    from_page_id  TEXT NOT NULL,
    type          TEXT NOT NULL,
    to_page_id    TEXT NOT NULL,
    note          TEXT,
    weight        TEXT,
    PRIMARY KEY (project_id, from_page_id, type, to_page_id),
    FOREIGN KEY (project_id, from_page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
    -- Intencional: SIN FK sobre (project_id, to_page_id). Las relations pueden
    -- apuntar a páginas aún NO compiladas (mito-lunar, peter-pan-1953-film...):
    -- es la señal que usa el validador para "wikilinks rotos = candidatos a
    -- próximo batch". Añadir FK destruiría esa señal.
);
CREATE INDEX IF NOT EXISTS idx_relations_to   ON relations(project_id, to_page_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(type);

CREATE TABLE IF NOT EXISTS body_wikilinks (
    project_id      TEXT NOT NULL,
    page_id         TEXT NOT NULL,
    target_page_id  TEXT NOT NULL,
    PRIMARY KEY (project_id, page_id, target_page_id),
    FOREIGN KEY (project_id, page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_body_wikilinks_target ON body_wikilinks(project_id, target_page_id);

-- ===================== AUTHOR ENTITY MODEL (PER-PROJECT) =================== --

-- author_id es el slug per-project; el mismo Jung en otro proyecto es otra fila.
-- Distinto de sources.type_metadata.authors (autores bibliográficos crudos de Crossref).
CREATE TABLE IF NOT EXISTS authors (
    project_id      TEXT NOT NULL REFERENCES projects(project_id),
    author_id       TEXT NOT NULL,                   -- slug: jung-carl-gustav
    canonical_name  TEXT NOT NULL,
    given_names     TEXT,
    family_name     TEXT,
    orcid           TEXT,                             -- identidad global cuando existe (NO único: cross-walk opcional)
    wikidata_id     TEXT,
    birth_year      INTEGER,
    death_year      INTEGER,
    page_id         TEXT,                             -- FK lógica a pages(project_id,page_id) si tiene página (page_type=author)
    PRIMARY KEY (project_id, author_id)
);
CREATE INDEX IF NOT EXISTS idx_authors_orcid    ON authors(orcid);
CREATE INDEX IF NOT EXISTS idx_authors_wikidata ON authors(wikidata_id);

CREATE TABLE IF NOT EXISTS author_aliases (
    project_id  TEXT NOT NULL,
    author_id   TEXT NOT NULL,
    alias       TEXT NOT NULL,
    PRIMARY KEY (project_id, author_id, alias),
    FOREIGN KEY (project_id, author_id) REFERENCES authors(project_id, author_id) ON DELETE CASCADE
);

-- La distinción crítica as_author_of vs as_subject_of (TAXONOMY §3.2).
-- source_id apunta al registro GLOBAL `sources`; el rol es la relación PER-PROJECT.
CREATE TABLE IF NOT EXISTS author_sources (
    project_id  TEXT NOT NULL,
    author_id   TEXT NOT NULL,
    source_id   TEXT NOT NULL,                        -- → sources.source_id (global)
    role        TEXT NOT NULL,                        -- 'author_of' | 'subject_of'
    PRIMARY KEY (project_id, author_id, source_id, role),
    FOREIGN KEY (project_id, author_id) REFERENCES authors(project_id, author_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_author_sources_source ON author_sources(source_id);

-- ===================== CITATIONS GENERALIZADA (PER-PROJECT) ================ --

-- Cita wiki→fuente, generalizada de YouTube-céntrico (video_id/timestamp) a
-- position polimórfico. position_key es el localizador serializado estable
-- (SQLite no indexa JSON en PK): youtube -> str(timestamp_seconds); paper -> "p7" / "p7s3.2".
CREATE TABLE IF NOT EXISTS citations (
    project_id    TEXT NOT NULL,
    page_id       TEXT NOT NULL,
    source_id     TEXT NOT NULL,                      -- youtube:<id> | doi:<...>  (→ sources global)
    position_key  TEXT NOT NULL,                      -- discriminador estable para PK
    position      TEXT NOT NULL,                      -- JSON: {"timestamp_seconds":323} | {"page":7,"section":"3.2"}
    position_url  TEXT NOT NULL,                      -- URL clicable (youtu.be/ID?t=323 | doi.org/...#page=7)
    cite_markdown TEXT,                                -- precomputado: "[Título (mm:ss)](url)" — el LLM lo copia literal
    title         TEXT,
    PRIMARY KEY (project_id, page_id, source_id, position_key),
    FOREIGN KEY (project_id, page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_citations_source ON citations(source_id);

-- ===================== RELATION TYPES (core global + ext) ================== --

CREATE TABLE IF NOT EXISTS relation_types_canonical (
    project_id      TEXT,                             -- NULL = core/global
    type            TEXT NOT NULL,
    description     TEXT,
    inverse         TEXT,
    from_types_csv  TEXT,
    to_types_csv    TEXT,
    PRIMARY KEY (project_id, type)
);
CREATE INDEX IF NOT EXISTS idx_reltypes_type ON relation_types_canonical(type);
"""

# Tablas esperadas (para --check). Debe coincidir con los CREATE TABLE de arriba.
EXPECTED_TABLES = {
    "projects", "source_files", "sources", "source_projects", "research_queue",
    "pages", "page_domains", "aliases", "relations", "body_wikilinks",
    "authors", "author_aliases", "author_sources", "citations",
    "relation_types_canonical",
}


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def check_db(db_path: Path) -> int:
    if not db_path.exists():
        print(f"✗ {db_path} no existe", file=sys.stderr)
        return 1
    conn = sqlite3.connect(db_path)
    try:
        journal = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        conn.close()

    ok = True
    if journal.lower() != "wal":
        print(f"✗ journal_mode={journal} (esperado wal)")
        ok = False
    else:
        print(f"✓ journal_mode=wal")

    missing = EXPECTED_TABLES - tables
    extra = tables - EXPECTED_TABLES
    if missing:
        print(f"✗ faltan tablas: {sorted(missing)}")
        ok = False
    else:
        print(f"✓ {len(EXPECTED_TABLES)} tablas presentes")
    if extra:
        print(f"  (tablas extra inesperadas: {sorted(extra)})")

    print(f"  tablas: {sorted(tables)}")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--check", action="store_true", help="solo verificar schema + WAL")
    args = p.parse_args()

    if args.check:
        return check_db(args.db)

    init_db(args.db)
    print(f"ariadna.db initialized at {args.db} (WAL mode, schema v{SCHEMA_VERSION})")
    return check_db(args.db)


if __name__ == "__main__":
    sys.exit(main())
