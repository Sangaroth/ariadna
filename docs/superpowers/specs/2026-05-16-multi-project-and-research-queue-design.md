# Spec — Multi-project Ariadna + cola de investigación

**Fecha:** 2026-05-16
**Autor:** Sangaroth (con Claude Opus 4.7 en brainstorming)
**Estado:** Draft — pendiente review
**Alcance temporal de esta spec:** Fase 1 (migración + multi-tenancy) y Fase 2 (tools MCP de cola sin workers). Las fases 3-5 (workers de YouTube, papers, web) se cubrirán en specs separadas cuando llegue su momento.

---

## 1. Motivación

Hoy Ariadna sirve un único corpus implícito: el canal YouTube de Proxy. Toda la infraestructura asume `wiki/` como root, `data/wiki.db` como único índice, y `extract_video_themes.py` como único productor de conocimiento. La visión del usuario es extender Ariadna a múltiples corpus heterogéneos conviviendo (gadgets Raspberry, investigación tesis, sueños, desarrollo SW, otros canales YouTube), cada uno con su scope editorial y cuerpo de conocimiento, pero permitiendo consultas cruzadas entre ellos. Adicionalmente, la ingesta de nuevas fuentes debe poder dispararse conversando con el agente Mattermost (Ariadna añade items a una cola; workers desacoplados procesan).

Esta spec define la cimentación: el concepto de `Project` como unidad atómica que combina scope, wiki y cola de ingesta, y los cambios mínimos en el MCP server para soportarlo. Los workers de procesamiento (que consumen la cola) son scope futuro.

## 2. Modelo conceptual

Un **proyecto** es la unidad atómica que combina:

- **Identidad**: slug kebab-case (`proxy`, `tesis-doctorado`, `raspberry-gadget`), nombre display, descripción
- **Scope editorial**: qué entra como conocimiento, qué se descarta como ruido; vocabulario canónico del dominio
- **Cuerpo de conocimiento**: páginas wiki (concepts/authors/entities/synthesis) + chunks raw indexados en Qdrant
- **Cola de ingesta**: items pendientes de ser procesados hacia este proyecto (URLs, DOIs, paths a PDFs, video_ids)

Los proyectos están **aislados conceptualmente** pero **comparten infraestructura**:

- Una sola colección Qdrant para todos los proyectos (filtro nativo por `project_id` en payload)
- Una sola base SQLite `data/ariadna.db` con todo el estado relacional
- Filesystem separado por proyecto (`projects/<slug>/`)
- Recursos editoriales globales por defecto (`wiki/_meta/*_default.*`), con override per-proyecto opcional

### Cross-project queries

`search_corpus` permite scope explícito vía parámetro `project: str | list[str] | None`. Cuando `project=None` (default), busca cross-all sin filtro. La decisión contextual (qué proyecto aplicar cuando el usuario humano no lo especifica) vive en el **system prompt del agente Mattermost**, no en el MCP server.

### Cross-project wikilinks/relations

**NO en el MVP.** Cada wiki es self-contained. Cross-project queries vía search filter cubren el 90% del valor. Si en uso real aparece necesidad de relaciones tipadas cross-project, se añade después con sintaxis `[[proyecto:page]]` en `relations[]` del frontmatter (nunca en wikilinks del cuerpo, para preservar navegación Obsidian local).

## 3. Arquitectura

```
┌─ MCP Server (un solo proceso, multi-tenant) ────────────────────────┐
│  Tools nuevas (write):                                              │
│    create_project, add_to_research_queue, cancel_request            │
│  Tools nuevas (read):                                               │
│    list_projects, list_research_queue                               │
│  Tools modificadas:                                                 │
│    search_corpus, get_wiki_page  → aceptan parámetro `project`      │
│  Tools retiradas:                                                   │
│    get_video_summary, list_videos  (YouTube-specific, obsoletas)    │
└─────────────────────────────────────────────────────────────────────┘
        │ INSERT/SELECT/UPDATE-status (nunca procesa)
        ▼
┌─ SQLite global: data/ariadna.db ────────────────────────────────────┐
│  Tablas:  projects, research_queue,                                 │
│           pages, aliases, relations, body_wikilinks, citations,     │
│           relation_types_canonical                                  │
│  Todas las tablas derivadas de wiki llevan project_id como key      │
└─────────────────────────────────────────────────────────────────────┘
        │ workers polean por (status='pending', type=X, project=Y?)
        ▼
┌─ Workers desacoplados (FUERA de esta spec, scope futuro) ───────────┐
│  CLI binaries separados, lock optimista vía UPDATE ... RETURNING    │
└─────────────────────────────────────────────────────────────────────┘
```

## 4. Schema de datos

### 4.1 SQLite — `data/ariadna.db`

```sql
-- Identidad de proyectos
CREATE TABLE projects (
    project_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    created_at      TEXT NOT NULL,
    archived_at     TEXT,
    config_version  TEXT NOT NULL DEFAULT '1.0'
);

-- Cola de ingesta global (status FSM)
CREATE TABLE research_queue (
    request_id        TEXT PRIMARY KEY,            -- uuid v4
    project_id        TEXT NOT NULL REFERENCES projects(project_id),
    source_url        TEXT NOT NULL,
    source_type       TEXT NOT NULL,
                                                   -- youtube | paper | web | pdf | unknown
    status            TEXT NOT NULL DEFAULT 'pending',
                                                   -- pending | processing | done | failed | cancelled
    priority          INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    picked_up_at      TEXT,
    completed_at      TEXT,
    assigned_worker   TEXT,
    retry_count       INTEGER NOT NULL DEFAULT 0,
    error_msg         TEXT,
    notes             TEXT,
    metadata          TEXT                          -- JSON blob: hints específicos
);
CREATE INDEX idx_queue_status_type ON research_queue(status, source_type);
CREATE INDEX idx_queue_project ON research_queue(project_id);
CREATE UNIQUE INDEX idx_queue_dedup
    ON research_queue(project_id, source_url)
    WHERE status IN ('pending', 'processing');
-- ↑ Idempotencia: misma (project, url) en pending/processing es un solo item

-- Wiki derivada del filesystem
CREATE TABLE pages (
    page_id        TEXT NOT NULL,
    project_id     TEXT NOT NULL REFERENCES projects(project_id),
    page_type      TEXT NOT NULL,                  -- concept | author | entity_work | synthesis
    canonical_name TEXT NOT NULL,
    domain_primary TEXT,
    file_path      TEXT NOT NULL,
    last_compiled  TEXT,
    sources_count  INTEGER,
    review_status  TEXT,
    body_md        TEXT NOT NULL,
    indexed_at     TEXT NOT NULL,
    PRIMARY KEY (project_id, page_id)
);
CREATE INDEX idx_pages_project ON pages(project_id);
CREATE INDEX idx_pages_type ON pages(project_id, page_type);

CREATE TABLE aliases (
    project_id  TEXT NOT NULL,
    page_id     TEXT NOT NULL,
    alias       TEXT NOT NULL,
    PRIMARY KEY (project_id, page_id, alias),
    FOREIGN KEY (project_id, page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
);
CREATE INDEX idx_aliases_alias ON aliases(alias);

CREATE TABLE relations (
    project_id    TEXT NOT NULL,
    from_page_id  TEXT NOT NULL,
    type          TEXT NOT NULL,
    to_page_id    TEXT NOT NULL,
    note          TEXT,
    weight        TEXT,
    PRIMARY KEY (project_id, from_page_id, type, to_page_id),
    FOREIGN KEY (project_id, from_page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
);
CREATE INDEX idx_relations_to   ON relations(project_id, to_page_id);
CREATE INDEX idx_relations_type ON relations(type);

CREATE TABLE body_wikilinks (
    project_id      TEXT NOT NULL,
    page_id         TEXT NOT NULL,
    target_page_id  TEXT NOT NULL,
    PRIMARY KEY (project_id, page_id, target_page_id),
    FOREIGN KEY (project_id, page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
);
CREATE INDEX idx_body_wikilinks_target ON body_wikilinks(project_id, target_page_id);

CREATE TABLE citations (
    project_id        TEXT NOT NULL,
    page_id           TEXT NOT NULL,
    video_id          TEXT NOT NULL,                -- conserva nombre por compat;
                                                    -- generaliza a source_id en spec workers
    timestamp_seconds INTEGER NOT NULL DEFAULT 0,
    title             TEXT,
    url               TEXT NOT NULL,
    PRIMARY KEY (project_id, page_id, video_id, timestamp_seconds),
    FOREIGN KEY (project_id, page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
);
CREATE INDEX idx_citations_video ON citations(video_id);
-- Permite citation lookup cross-project: SELECT page_id, project_id FROM citations WHERE video_id=?

-- Relation types: core globales (project_id=NULL) + extensions per-proyecto
CREATE TABLE relation_types_canonical (
    project_id      TEXT,                           -- NULL = core/global
    type            TEXT NOT NULL,
    description     TEXT,
    inverse         TEXT,
    from_types_csv  TEXT,
    to_types_csv    TEXT,
    PRIMARY KEY (project_id, type)
);
CREATE INDEX idx_reltypes_type ON relation_types_canonical(type);
```

**Modo SQLite:** `journal_mode=WAL` (writers no bloquean readers; múltiples readers concurrentes). Necesario cuando varios workers procesen proyectos distintos en paralelo (scope futuro), pero se activa desde Fase 1 para garantizar comportamiento estable.

### 4.2 Qdrant — colección única `ariadna_corpus`

Cada punto (raw_chunk o wiki_page) lleva `project_id: str` en payload. Sin cambios de schema en Qdrant (es schema-less); solo se añade una key más.

```python
# Antes
{"video_id": "...", "theme": "...", "content": "...", "source_type": "raw_chunk"}

# Después
{"project_id": "proxy", "video_id": "...", "theme": "...", "content": "...", "source_type": "raw_chunk"}
```

**Filtros**:
```python
# Scope a un proyecto:
Filter(must=[FieldCondition(key="project_id", match=MatchValue(value="proxy"))])

# Scope a subset (OR-of):
Filter(must=[Filter(should=[
    FieldCondition(key="project_id", match=MatchValue(value="proxy")),
    FieldCondition(key="project_id", match=MatchValue(value="tesis")),
])])

# Cross-all: sin filtro project_id
```

### 4.3 Modelo de chunk genérico

Schema común con blob específico por tipo:

```python
{
    "chunk_id": str,                               # estable, deterministico
    "project_id": str,
    "source_type": "youtube" | "paper" | "web" | "pdf",
    "source_url": str,
    "content": str,
    "full_text": str,                              # para embedding
    "cite_markdown": str,                          # precomputado por el parser
    "source_metadata": {                           # blob específico:
        # youtube:  timestamp, timestamp_seconds, theme, emoji, video_title, video_id, ...
        # paper:    section, page, paragraph_idx, doi, authors, year, ...
        # web:      extracted_at, h1, h2, ...
        # pdf:      page, paragraph_idx, ...
    }
}
```

Los chunks YouTube actuales se migran a este shape moviendo `timestamp`, `theme`, etc. al sub-dict `source_metadata`.

## 5. Filesystem layout

```
/home/dae/PycharmProjects/ariadna/
├── data/
│   ├── ariadna.db                                  # ÚNICA SQLite global
│   └── qdrant/                                     # single collection
├── projects/                                       # NUEVO top-level
│   └── proxy/                                      # estado actual migrado aquí
│       ├── _meta/
│       │   ├── scope.md                            # override (Proxy tiene scope custom)
│       │   ├── topic_filters.json                  # override
│       │   ├── canonical_whitelist.json            # override
│       │   ├── subagent_prompt.md                  # override (estilo Proxy)
│       │   ├── relation_types_ext.json             # {} vacío (sin extensions)
│       │   ├── extraction_runs/                    # historial de runs Proxy
│       │   └── INDEX.md
│       └── wiki/
│           ├── concepts/ authors/ entities/ synthesis/
│           └── README.md
├── wiki/_meta/                                     # recursos globales del sistema
│   ├── relation_types_core.json                    # ~30 tipos universales
│   ├── scope_default.md                            # plantilla editable
│   ├── topic_filters_default.json                  # plantilla editable
│   ├── subagent_prompt_default.md                  # plantilla editable
│   └── canonical_whitelist_default.json            # {} vacío
└── ariadna/, scripts/, docs/, ...                  # sin cambios estructurales
```

### 5.1 Plantillas editables (defaults)

Los archivos en `wiki/_meta/*_default.*` son **plantillas markdown/JSON versionadas en git**, editables como cualquier archivo. Editar el default propaga automáticamente a todos los proyectos que NO tengan override propio.

### 5.2 Override per-proyecto

Cuando un proyecto necesita configuración editorial distinta del default, crea su archivo en `projects/<slug>/_meta/<name>.<ext>`. La resolución en runtime cae al override si existe, al default si no.

### 5.3 Lo único que `create_project` crea automáticamente

```
projects/<slug>/
├── _meta/
│   ├── relation_types_ext.json    # {} vacío (expectativa común)
│   ├── INDEX.md                    # placeholder con nombre del proyecto
│   └── extraction_runs/            # directorio vacío
└── wiki/                            # directorio vacío
                                     # subdirs concepts/, authors/, etc. se crean
                                     # cuando aparezca la primera page de ese tipo
```

Cero copia de archivos editoriales por defecto. Si el usuario invoca `create_project(seed_from_templates=True)`, entonces sí se copian los `*_default.*` a `projects/<slug>/_meta/*.*` como punto de partida editable.

## 6. Tools MCP

### 6.1 Tools write nuevas

```python
@mcp.tool
def create_project(
    slug: str,
    name: str,
    description: str = "",
    seed_from_templates: bool = False,
    inherit_from: str | None = None,
) -> dict:
    """Crea un proyecto vacío.

    seed_from_templates=True: copia wiki/_meta/*_default.* a projects/<slug>/_meta/*.*
      (quitando el sufijo _default). El proyecto arranca con texto editable
      idéntico al default, que ya empieza a divergir cuando lo edites.

    inherit_from='proxy': copia los archivos de otro proyecto como punto de partida.

    Devuelve: {project_id, paths_created, message}
    Errores: SLUG_INVALID, SLUG_DUPLICATE, INHERIT_FROM_NOT_FOUND
    """

@mcp.tool
def add_to_research_queue(
    project: str,
    source_url: str,
    source_type: str | None = None,
    notes: str = "",
    priority: int = 0,
) -> dict:
    """Añade item a cola.

    source_type=None: auto-detect (youtube/paper/web/pdf/unknown).
    Idempotente: misma (project, source_url) en pending/processing devuelve
    request_id existente con flag was_duplicate=True.

    Devuelve: {request_id, detected_source_type, status, was_duplicate, message}
    Errores: PROJECT_NOT_FOUND, INVALID_URL
    """

@mcp.tool
def cancel_request(request_id: str, reason: str = "") -> dict:
    """Cancela request pending. No-op si ya está processing/done.

    Devuelve: {request_id, previous_status, current_status}
    Errores: REQUEST_NOT_FOUND
    """
```

### 6.2 Tools read nuevas

```python
@mcp.tool
def list_projects(include_archived: bool = False) -> dict:
    """Devuelve {projects: [{project_id, name, description, n_pages, n_chunks,
                              n_queue_pending, created_at, archived_at}]}.
    """

@mcp.tool
def list_research_queue(
    project: str | None = None,
    status: str = "pending",
    source_type: str | None = None,
    limit: int = 50,
) -> dict:
    """status='all' devuelve todos los estados.
    Devuelve {items: [...], total_matching, filters_applied}.
    """
```

### 6.3 Tools existentes modificadas

```python
@mcp.tool
def search_corpus(
    query: str,
    top_k: int = 5,
    top_k_wiki: int = 2,
    project: str | list[str] | None = None,        # ← nuevo, None=cross-all
    category: str | None = None,
    playlist: str | None = None,
    include_filtered: bool = False,
) -> dict:
    """retrieval_metadata.projects_seen: list[str] lista qué project_ids aparecen
    en los resultados (útil para que el agente Mattermost reporte el cruce)."""

@mcp.tool
def get_wiki_page(
    page_id: str,
    project: str | None = None,                    # ← nuevo
) -> dict:
    """project=None: busca page_id cross-all. Si aparece en varios proyectos,
    devuelve el más antiguo + metadata.projects_with_this_id con todos.
    project='proxy': solo busca en Proxy. Error WIKI_PAGE_NOT_FOUND si no existe."""
```

### 6.4 Tools retiradas

`get_video_summary` y `list_videos` se eliminan. Cubrían casos de uso ya servidos por `search_corpus` (drill-down via filter `video_id=X`) y `list_research_queue` (qué se ha procesado).

Si en uso real aparece necesidad de drill-down o listado genérico, se añaden `get_source_summary(source_id, source_type, project)` y `list_sources(source_type, project)` — agnósticas al tipo. Por ahora YAGNI.

### 6.5 Validaciones

- `slug` validado contra regex `^[a-z][a-z0-9-]{1,40}[a-z0-9]$`
- `source_type` validado contra enum: `youtube | paper | web | pdf | unknown`
- Errores devuelven `{error: "...", code: "PROJECT_NOT_FOUND" | ...}` para que el agente actúe

### 6.6 Auto-detect de `source_type`

```python
def detect_source_type(url: str) -> str:
    if 'youtube.com/watch' in url or 'youtu.be/' in url: return 'youtube'
    if 'arxiv.org/' in url: return 'paper'
    if 'doi.org/' in url: return 'paper'
    if url.lower().endswith('.pdf'): return 'pdf'
    if url.startswith('http'): return 'web'
    return 'unknown'
```

El worker que procese puede sobrescribir `source_type` si su análisis más profundo discrepa (ej. URL web que redirige a un PDF).

## 7. Resolución de configuración runtime

### 7.1 `ariadna/project_config.py` (nuevo módulo)

```python
class ProjectConfig:
    """Resuelve recursos editoriales aplicando default + override.
    Stateless: lee filesystem en cada acceso (archivos pequeños, <10ms).
    """

    @staticmethod
    def for_project(project_id: str) -> "ProjectConfig":
        """Falla rápido si project_id no existe en SQLite."""

    def scope_text(self) -> str: ...
    def topic_filters(self) -> dict: ...
    def canonical_whitelist(self) -> list[str]: ...
    def subagent_prompt(self) -> str: ...
    def relation_types(self) -> dict[str, RelationType]:
        """Unión: core (siempre disponibles) + ext del proyecto.
        Si ext colisiona con core: error explícito en startup."""
    def wiki_root(self) -> Path:
        """projects/<slug>/wiki/"""
    def extraction_runs_dir(self) -> Path:
        """projects/<slug>/_meta/extraction_runs/"""
```

### 7.2 Patrón de fallback

```python
def _resolve(project_id: str, name: str) -> Path:
    """name: scope.md | topic_filters.json | subagent_prompt.md | canonical_whitelist.json"""
    local = Path(f"projects/{project_id}/_meta/{name}")
    if local.exists():
        return local
    stem, ext = name.rsplit('.', 1)
    return Path(f"wiki/_meta/{stem}_default.{ext}")
```

### 7.3 Relation types al startup

Al iniciar el MCP server (y al recibir `reload_config` si se implementa en Fase 2):

```python
def reload_relation_types(db: sqlite3.Connection):
    db.execute("DELETE FROM relation_types_canonical")
    core = json.load(open("wiki/_meta/relation_types_core.json"))
    core_type_names = {t["type"] for t in core["types"]}
    for t in core["types"]:
        db.execute("INSERT INTO relation_types_canonical(project_id, type, ...) VALUES (NULL, ?, ...)", ...)
    for project_id in list_active_projects(db):
        ext_path = Path(f"projects/{project_id}/_meta/relation_types_ext.json")
        if not ext_path.exists():
            continue
        ext = json.load(ext_path.open())
        for t in ext.get("types", []):
            if t["type"] in core_type_names:
                raise ConfigError(
                    f"Project {project_id} declares ext type '{t['type']}' "
                    f"that collides with core. Rename or remove."
                )
            db.execute("INSERT ... VALUES (?, ?, ...)", project_id, ...)
```

### 7.4 `ariadna/policy_filters.py` actualizado

Hoy el módulo escanea `wiki/_meta/extraction_runs/` global. Cambia a aceptar `project_id`:

```python
def build_policy_filter_map(
    project_id: str,
    extraction_runs_dir: Path | None = None,  # derivable del project
) -> dict[tuple[str, int], dict]:
    """Escanea projects/<pid>/_meta/extraction_runs/*/*.json"""
```

Coherente con la separación de extraction_runs per-proyecto.

## 8. Migración

### 8.1 Script: `scripts/migrate_to_projects.py`

CLI con `--dry-run` (muestra todo lo que pasaría) y `--commit` (ejecuta).

Pre-flight checks (aborta si falla cualquiera):
1. MCP server parado (`pgrep ariadna.mcp_server` vacío)
2. Lock Qdrant ausente (o solo nuestro al ejecutar)
3. Working tree git limpio (sin cambios sin commitear excepto los del run activo)
4. No hay extracción activa sobre `wiki/` (chequea procesos extract_video_themes)

Pasos:
1. **Backup**: `cp -r wiki/ wiki.backup.YYYYMMDD/` (en gitignore, por si acaso)
2. **Crear estructura**: `mkdir -p projects/proxy/{_meta,wiki}`
3. **Mover wiki Proxy**:
   ```bash
   git mv wiki/concepts projects/proxy/wiki/
   git mv wiki/authors  projects/proxy/wiki/
   git mv wiki/entities projects/proxy/wiki/
   git mv wiki/synthesis projects/proxy/wiki/
   ```
4. **Mover meta Proxy**:
   ```bash
   git mv wiki/_meta/scope.md projects/proxy/_meta/
   git mv wiki/_meta/topic_filters.json projects/proxy/_meta/
   git mv wiki/_meta/canonical_whitelist.json projects/proxy/_meta/
   git mv wiki/_meta/extraction_runs projects/proxy/_meta/
   git mv wiki/_meta/INDEX.md projects/proxy/_meta/
   ```
5. **Promover relation_types**:
   ```bash
   git mv wiki/_meta/relation_types.json wiki/_meta/relation_types_core.json
   ```
6. **Crear placeholders globales** (defaults editables):
   ```
   wiki/_meta/scope_default.md                  # texto genérico
   wiki/_meta/topic_filters_default.json        # regex universal de descarte
   wiki/_meta/subagent_prompt_default.md        # prompt base del sub-agente
   wiki/_meta/canonical_whitelist_default.json  # {}
   ```
7. **Extraer subagent_prompt de extract_video_themes.py**:
   Copia `SUBAGENT_SYSTEM_PROMPT` y `SUBAGENT_SYNTHESIS_SYSTEM_PROMPT` a `projects/proxy/_meta/subagent_prompt.md` (con metadata YAML al inicio: `kind: concept_author_entity_work` y `kind: synthesis`)
8. **Crear `projects/proxy/_meta/relation_types_ext.json` = `{"types": []}`**
9. **Mover SQLite por-proyecto** (transitorio — la BBDD global lo absorbe en paso 11):
   ```bash
   git mv data/wiki.db projects/proxy/data/wiki.db
   # luego este archivo se ELIMINA al final, su contenido se vuelca a data/ariadna.db
   ```
10. **Crear `data/ariadna.db`** con schema completo de sección 4.1
11. **Migrar contenido de `projects/proxy/data/wiki.db` → `data/ariadna.db`**:
    Para cada tabla (pages, aliases, relations, body_wikilinks, citations) hace
    `INSERT INTO data/ariadna.db.<tabla> SELECT 'proxy' as project_id, * FROM wiki.db.<tabla>`.
    Después elimina `projects/proxy/data/` (transitorio).
12. **INSERT INTO projects** la fila Proxy:
    ```sql
    INSERT INTO projects(project_id, name, description, created_at)
    VALUES ('proxy', 'Proxy YouTube corpus',
            'Canal YouTube de Proxy: análisis arquetípico, mitología, psicología junguiana',
            '<original_creation_date_or_now>');
    ```
13. **Backfill Qdrant**: `scripts/migrate_qdrant_project_id.py` itera la colección y hace `set_payload({project_id: "proxy"})` a cada uno de los 6442 puntos. Idempotente. Tarda minutos.
14. **Actualizar paths hardcoded** en archivos Python (ver tabla 8.2)
15. **Crear módulo `ariadna/project_config.py`** (sección 7.1)
16. **Eliminar tools `get_video_summary` y `list_videos`** de `ariadna/mcp_server.py` + helper `CorpusStore.list_videos()` de `ariadna/storage.py`
17. **Smoke test post-migración**: `python scripts/test_hybrid.py` + verificar `wiki/` vacío excepto `wiki/_meta/*_default.*` y `wiki/_meta/relation_types_core.json`
18. **Commit unitario**: `refactor(projects): migrate to multi-project layout, proxy as first tenant`

Cualquier estado intermedio rompe el sistema, por eso es un solo commit grande. Si algo falla a mitad, rollback es `git reset --hard HEAD`.

### 8.2 Paths hardcoded que cambian

| Archivo | Hoy | Después |
|---|---|---|
| `ariadna/search.py` | `wiki_db_path = "data/wiki.db"` | resuelve vía `project_id` → `data/ariadna.db` con WHERE |
| `scripts/build_wiki_db.py` | `WIKI_ROOT = Path("wiki")` | parámetro `--project <slug>` (requerido), usa `ProjectConfig.wiki_root()` |
| `scripts/index_wiki_to_qdrant.py` | itera `wiki/**/*.md` | itera `projects/<slug>/wiki/**`, taggea con project_id |
| `scripts/extract_video_themes.py` | `wiki/_meta/extraction_runs/` | `projects/<slug>/_meta/extraction_runs/` |
| `ariadna/policy_filters.py` | hardcoded path | parámetro `project_id` + `extraction_runs_dir` |
| `ariadna/build_index.py` | `DEFAULT_EXTRACTION_RUNS` global | iterar por proyecto |
| `ariadna/mcp_server.py` | tools sin project param | añade param `project` a tools relevantes |

## 9. Criterios de éxito por fase

### Fase 1 — Migración + multi-tenancy

**Criterio binario**: el sistema **debe seguir funcionando idénticamente** desde la perspectiva del agente Mattermost.

- [ ] `search_corpus(query="sombra")` sin `project` devuelve los mismos resultados que antes
- [ ] `search_corpus(query="sombra", project="proxy")` devuelve los mismos resultados
- [ ] `search_corpus(query="sombra", project="non_existent")` devuelve `error: PROJECT_NOT_FOUND`
- [ ] `get_wiki_page("shadow-archetype", project="proxy")` devuelve la página
- [ ] `get_wiki_page("shadow-archetype")` (sin project) idem
- [ ] `scripts/test_hybrid.py` pasa todos los checks (5/5 verde)
- [ ] `data/ariadna.db` contiene 1 proyecto (`proxy`) con todas sus pages/relations/citations
- [ ] Todos los puntos Qdrant tienen `project_id="proxy"`
- [ ] `wiki/_meta/relation_types_core.json` contiene los 30 tipos canónicos actuales
- [ ] `wiki/_meta/*_default.*` existen y son editables (texto genérico, suficiente para que un proyecto nuevo opere)
- [ ] Validador `scripts/validate_wiki_relations.py --project=proxy` pasa
- [ ] El run activo (`pilot_sonnet_20260509`) puede continuar via `--resume` tras la migración (los paths cambiaron, pero el script ahora apunta a la nueva ubicación)
- [ ] `build_wiki_db.py --project=proxy` reconstruye el subset de SQLite de Proxy en <2s

### Fase 2 — Tools MCP de cola (sin workers)

**Criterio binario**: la cola es operacional desde Mattermost; los items se acumulan pero no se procesan (es esperado, los workers son fase futura).

- [ ] `create_project(slug="test_e", name="Test E")` crea estructura mínima en filesystem + fila en `projects`
- [ ] `create_project(slug="test_e", ...)` con duplicado devuelve `SLUG_DUPLICATE`
- [ ] `create_project(slug="proxy-2", seed_from_templates=True)` copia los 4 archivos default a `projects/proxy-2/_meta/*.*` (sin sufijo `_default`)
- [ ] `create_project(slug="proxy-clone", inherit_from="proxy")` copia los overrides de Proxy
- [ ] `add_to_research_queue(project="proxy", source_url="https://youtu.be/X")` inserta fila pending con `source_type='youtube'`
- [ ] `add_to_research_queue(project="proxy", source_url="https://arxiv.org/abs/Y")` → `source_type='paper'`
- [ ] `add_to_research_queue` duplicada (misma project+url, pending) devuelve `was_duplicate=True`
- [ ] `list_research_queue(project="proxy", status="pending")` devuelve los items
- [ ] `list_research_queue(project=None)` cross-all
- [ ] `cancel_request(request_id=X)` cambia status a `cancelled`, no actúa si ya está `processing`/`done`
- [ ] `list_projects()` devuelve los proyectos con conteos derivados (n_pages, n_chunks, n_queue_pending)
- [ ] Validación de slug rechaza `Test_E`, `TEST`, `test e`, `123-test`
- [ ] El system prompt de Ariadna en Mattermost se actualiza para mencionar las nuevas tools

### 9.1 Out of scope (specs futuras)

- Workers de procesamiento (YouTube, papers, web, pdf) → **spec separada por tipo**
- Cross-project wikilinks/relations → si aparece necesidad, **spec menor independiente**
- Tool conversacional `customize_project_scope` → si demanda real → spec
- `delete_project` con UI confirmación → si demanda → spec
- Hot-reload tool MCP (`reload_config`) → si demanda → spec

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Migración no atómica deja sistema en estado intermedio inconsistente | Pre-flight checks; un solo commit; backup wiki/ por si acaso; rollback es `git reset --hard HEAD` |
| Run activo (`pilot_sonnet_20260509`) en progreso durante migración | Migración requiere extract_video_themes parado; el run debe terminar o pausarse antes. Verificar con `pgrep` |
| SQLite global lock contention con multi-worker (fase futura) | WAL mode desde Fase 1; multiple readers concurrent; writes son sub-segundo |
| El agente Mattermost cachea schema viejo de tools | Refresh Tools manual tras deploy (documentado en runbook post-migración) |
| Extensions de relation_types colisionan con core silenciosamente | Validación explícita en startup del server: `ConfigError` si colisión, refuse to start |
| Backfill Qdrant tarda más de lo esperado y falla | Idempotente: si falla a mitad, re-ejecutar continúa donde quedó |
| `seed_from_templates` introduce divergencia silenciosa cuando se modifica el default global | `scripts/audit_project_overrides.py` (sección 10.1) detecta copias que no divergen y las marca como ruido |

### 10.1 Auditor de overrides

```python
# scripts/audit_project_overrides.py
def audit():
    """Para cada proyecto, compara projects/<slug>/_meta/*.* con su default global.
    Reporta tres categorías:
      - OVERRIDE: el archivo del proyecto difiere del default (intencional)
      - SHADOW: el archivo del proyecto es idéntico al default (ruido — eliminar override)
      - MISSING: el proyecto no tiene archivo, usa default (estado normal)
    """
```

## 11. Definiciones operativas

- **Proyecto**: unidad atómica identificada por `project_id` (slug), con su scope, wiki y cola
- **Default**: archivo en `wiki/_meta/*_default.*` que aplica a cualquier proyecto sin override
- **Override**: archivo en `projects/<slug>/_meta/<name>.*` (sin sufijo `_default`) que sustituye al default para ese proyecto
- **Extension**: tipo de relación declarado en `projects/<slug>/_meta/relation_types_ext.json`, solo aplica dentro del proyecto
- **Core type**: tipo de relación en `wiki/_meta/relation_types_core.json`, disponible globalmente para todos los proyectos
- **Worker**: proceso separado del MCP server que consume items de `research_queue`, procesa según `source_type`, escribe resultados en filesystem + SQLite + Qdrant. **Fuera del alcance de esta spec.**
- **Lock optimista**: pattern `UPDATE ... WHERE status='pending' RETURNING *` que sirve para que un worker reclame un item sin race condition

## 12. Decisiones tomadas y descartadas

| Decisión | Tomada | Descartadas |
|---|---|---|
| Aislamiento Qdrant | Single collection + project_id payload | Collection-per-project (más aislado pero merge manual); híbrido por dominio (over-engineered) |
| SQLite | Una BBDD global `data/ariadna.db` | DB per-proyecto (más aislamiento pero N paths; merge en código para cross-project queries) |
| Relation types | Core global + extensions per-proyecto | Todo per-proyecto (pierde interop); todo global (impone Proxy a otros dominios) |
| Editorial config | Defaults globales editables + override per-proyecto | Replicar plantillas en cada proyecto (ruido); todo per-proyecto (defaults dispersos) |
| Bootstrap proyecto | Tool MCP write `create_project` | CLI manual (más fricción); híbrido draft+confirm (complejidad sin valor) |
| Trigger procesamiento | Workers desacoplados + MCP solo producer | MCP procesa (acopla); cron daemon (infra extra); background async via job_id (complejidad) |
| Cross-project wikilinks/relations | NO en MVP, YAGNI | Sí desde día 1 (sin caso de uso confirmado); sintaxis `[[proj:page]]` (complica validador) |
| Default scope cuando no se especifica | `project=None` = cross-all, decisión en system prompt | Error obligando explícito (fricción); default-project configurable (estado en MCP) |
| Tools YouTube-specific obsoletas | Retirar `get_video_summary`, `list_videos` | Mantener por compat (deuda permanente); generalizar (YAGNI sin demanda) |
| Modelo de chunk para fuentes nuevas | Schema común + `source_metadata` blob | Subclases por tipo (más código); chunk universal solo con cite_markdown (pierde filtros tipados) |

---

**Próximos pasos tras aprobación de esta spec:**

1. Spec review loop (spec-document-reviewer agent)
2. User review de la spec final
3. Implementation plan vía `writing-plans` skill (cubrirá Fase 1 + Fase 2 con tasks atómicos)
4. Implementación en branch separada con tests de Fase 1 → Fase 2
5. Specs separadas posteriores: worker YouTube, worker papers, worker web (fases 3-5)
