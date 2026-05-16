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
    -- Nota intencional: NO hay FK sobre (project_id, to_page_id). Las relations pueden
    -- apuntar a páginas todavía NO compiladas (e.g. mito-lunar, peter-pan-1953-film):
    -- es el mecanismo que usa el validador para señalar "wikilinks rotos = candidatos
    -- a próximo batch". Si añadiéramos FK destruiríamos esa señal. Las relations
    -- dangling se reportan vía query, no por integridad referencial.
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
    source_id         TEXT NOT NULL,                -- antes 'video_id'; renombrado
                                                    -- para acomodar paper DOI, web URL hash,
                                                    -- PDF fingerprint, etc.
    timestamp_seconds INTEGER NOT NULL DEFAULT 0,   -- segundos para youtube;
                                                    -- 0 o offset para otros tipos
    title             TEXT,
    url               TEXT NOT NULL,
    PRIMARY KEY (project_id, page_id, source_id, timestamp_seconds),
    FOREIGN KEY (project_id, page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
);
CREATE INDEX idx_citations_source ON citations(source_id);
-- Permite citation lookup cross-project: SELECT page_id, project_id FROM citations WHERE source_id=?

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

### 4.2.1 FSM completo de `research_queue.status`

```
              add_to_research_queue
                       │
                       ▼
                   ┌─────────┐
                   │ pending │◀─────┐
                   └─────────┘      │
                       │            │ retry (worker, retry_count < max_retries)
        worker acquires│            │
        (UPDATE..RETURNING)         │
                       ▼            │
                  ┌────────────┐    │
                  │ processing │    │
                  └────────────┘    │
                       │            │
       ┌───────────────┼────────────┼──────────┐
       │               │            │          │
       ▼               ▼            ▼          ▼
   ┌──────┐        ┌────────┐   ┌────────┐  ┌───────────┐
   │ done │        │ failed │   │ failed │  │ cancelled │
   └──────┘        │ retry  │──▶│  perm  │  └───────────┘
                   │ count< │   │ count= │
                   │ max    │   │ max    │
                   └────────┘   └────────┘

cancel_request(id):  pending → cancelled  ✓
                     failed  → cancelled  ✓ (descarta del retry pool)
                     processing → cancelled  ✗ (no-op, deja al worker terminar)
                     done/cancelled → cancelled  ✗ (no-op, ya terminal)
```

**Reglas de transición**:

- `pending → processing`: lock optimista del worker (`UPDATE ... WHERE status='pending' RETURNING *`); `picked_up_at=now()`, `assigned_worker=<wid>`.
- `processing → done`: worker termina con éxito; `completed_at=now()`, `error_msg=NULL`.
- `processing → failed`: worker captura excepción; `error_msg=<traceback breve>`, `retry_count++`.
  - Si `retry_count < max_retries` (default `max_retries=3` constante del worker, no en SQLite): worker mueve a `pending` tras backoff exponencial (60s, 300s, 900s). Resetea `picked_up_at=NULL`, `assigned_worker=NULL`.
  - Si `retry_count == max_retries`: queda en `failed` permanente. Solo intervención manual o `cancel_request` lo saca.
- `pending → cancelled` (por `cancel_request`): pone `completed_at=now()`, `error_msg='cancelled by user: <reason>'`.
- `failed → cancelled` (por `cancel_request`): mismo efecto; saca el item del retry pool de manera explícita.
- `processing → cancelled`: **no permitido**. `cancel_request` sobre item processing devuelve `{previous_status: 'processing', current_status: 'processing', message: 'cannot cancel item currently being processed; let it finish or fail naturally'}`. Decisión: cancelar mid-process puede dejar Qdrant/wiki inconsistente; preferimos esperar a que el worker termine.
- `done | cancelled → *`: terminales. Cualquier `cancel_request` o intento de transición es no-op idempotente.

**`max_retries` no se versiona en SQLite** (es constante de los workers, no del modelo de datos). Si en el futuro queremos retry policies per-proyecto, se añade columna `max_retries_override` a `projects`. YAGNI hoy.

**Retry manual**: NO existe tool MCP `retry_request` en el MVP. Si un usuario quiere reintentar un `failed perm`, manualmente actualiza SQLite: `UPDATE research_queue SET status='pending', retry_count=0 WHERE request_id=?`. La complejidad de exponer una tool conversacional para esto no se justifica en MVP.

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
│   ├── relation_types_ext.json    # {"types": []} (expectativa común)
│   ├── INDEX.md                    # placeholder con nombre del proyecto
│   └── extraction_runs/            # directorio vacío
└── wiki/                            # directorio vacío
    ├── concepts/                   # subdirs creados también por create_project,
    ├── authors/                    # con .gitkeep dentro para versionarse.
    ├── entities/                   # Permite que git pueda registrar el proyecto
    │   ├── works/                  # sin pages compiladas todavía.
    │   └── institutions/
    └── synthesis/
```

Decisión: `create_project` crea los subdirs (`concepts/`, `authors/`, etc.) **vacíos con `.gitkeep`** desde el primer momento. Alternativa "crear cuando aparezca la primera page" rechazada porque (a) acopla `create_project` a saber qué tipos hay, (b) un proyecto recién creado debe poder commiteárse aunque esté vacío, (c) la consistencia es valiosa para que `validate_wiki_relations` no tenga edge case "subdir no existe todavía".

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

    seed_from_templates + inherit_from son **mutuamente excluyentes**.
    Si ambos se pasan (True + non-None), devuelve error INCOMPATIBLE_OPTIONS
    sin crear nada. Lógica: cada uno define un "padre" distinto del que copiar;
    elegir uno explícitamente evita ambigüedad.

    Devuelve: {project_id, paths_created, message}
    Errores: SLUG_INVALID, SLUG_DUPLICATE, INHERIT_FROM_NOT_FOUND, INCOMPATIBLE_OPTIONS
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
    desempata por `pages.indexed_at` ascendente (el más antiguo gana) y devuelve
    además metadata.projects_with_this_id: list[str] con todos los proyectos
    que tienen ese page_id, ordenados por indexed_at. El agente Mattermost
    puede pedir explícitamente cada uno con un get_wiki_page subsecuente.
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

**Política de precedencia caller vs detector**:

- `source_type=None` (omitido por caller) → MCP aplica `detect_source_type(url)` y guarda el resultado.
- `source_type=<valor>` explícito → MCP **respeta al caller sin warning**, aunque difiera del detector. Filosofía: el caller (LLM agente con contexto de la conversación) sabe más que el sniffer regex.
- El **worker** que procesa el item PUEDE sobrescribir `source_type` en SQLite si su análisis más profundo discrepa (ej. URL web que redirige a un PDF, o un PDF que resulta ser slides en vez de paper). El override del worker registra evento en `error_msg` o `metadata` para audit trail, no devuelve error.

Esto resuelve el caso "explicit-disagrees-with-detector" deterministicamente: caller manda en write-time; worker manda en process-time.

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
    # Transacción atómica: si algo falla, la tabla queda con el estado anterior intacto.
    # Evita ventana donde otros procesos lean tabla vacía.
    with db:  # implicit BEGIN ... COMMIT/ROLLBACK
        db.execute("DELETE FROM relation_types_canonical")
        core = json.load(open("wiki/_meta/relation_types_core.json"))
        core_type_names = {t["type"] for t in core["types"]}
        for t in core["types"]:
            db.execute(
                "INSERT INTO relation_types_canonical(project_id, type, description, "
                "inverse, from_types_csv, to_types_csv) VALUES (NULL, ?, ?, ?, ?, ?)",
                (t["type"], t.get("description"), t.get("inverse"),
                 ",".join(t.get("from", [])), ",".join(t.get("to", []))),
            )
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
                db.execute(
                    "INSERT INTO relation_types_canonical(...) VALUES (?, ?, ...)",
                    (project_id, t["type"], ...),
                )
```

La transacción explícita previene que otros procesos (workers leyendo el grafo) vean tabla vacía durante el reload. Con WAL mode + transaction, los readers ven la tabla pre-DELETE hasta que el commit es atómico.

**Manejo de JSON malformado**: si cualquier `relation_types_ext.json` es JSON inválido, `json.load()` lanza `JSONDecodeError` que se propaga fuera del `with db:` block. El rollback automático preserva el estado anterior de la tabla `relation_types_canonical` intacto. El startup del MCP server falla loudly con stacktrace claro indicando el archivo culpable — esto es **intencional**: un proyecto con ext malformado es deuda editorial que debe corregirse antes de levantar el server, no silenciarse con un try/except per-file que dejaría reload parcial.

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
9. **Crear `data/ariadna.db`** con schema completo de sección 4.1 (incluye `journal_mode=WAL`).
10. **INSERT INTO projects** la fila Proxy antes de migrar contenido (las FKs lo exigen):
    ```sql
    INSERT INTO projects(project_id, name, description, created_at)
    VALUES ('proxy', 'Proxy YouTube corpus',
            'Canal YouTube de Proxy: análisis arquetípico, mitología, psicología junguiana',
            '<read from existing wiki.db indexed_at MIN, fallback to now()>');
    ```
11. **Migrar contenido `data/wiki.db` → `data/ariadna.db` vía ATTACH** con columnas explícitas por tabla (script `scripts/migrate_wiki_db_to_global.py`):
    ```sql
    ATTACH DATABASE 'data/wiki.db' AS old;

    -- pages: añade project_id='proxy' como primera columna; resto idéntico
    INSERT INTO pages (project_id, page_id, page_type, canonical_name, domain_primary,
                       file_path, last_compiled, sources_count, review_status,
                       body_md, indexed_at)
    SELECT 'proxy', page_id, page_type, canonical_name, domain_primary,
           file_path, last_compiled, sources_count, review_status,
           body_md, indexed_at
    FROM old.pages;

    -- aliases: hoy tiene (page_id, alias); nuevo tiene (project_id, page_id, alias)
    INSERT INTO aliases (project_id, page_id, alias)
    SELECT 'proxy', page_id, alias FROM old.aliases;

    -- relations: hoy (from_page_id, type, to_page_id, note, weight)
    INSERT INTO relations (project_id, from_page_id, type, to_page_id, note, weight)
    SELECT 'proxy', from_page_id, type, to_page_id, note, weight FROM old.relations;

    -- body_wikilinks: hoy (page_id, target_page_id)
    INSERT INTO body_wikilinks (project_id, page_id, target_page_id)
    SELECT 'proxy', page_id, target_page_id FROM old.body_wikilinks;

    -- citations: hoy (page_id, video_id, timestamp_seconds, title, url) → renombramos
    -- video_id a source_id en el nuevo schema (ver sección 4.1 nota citations)
    INSERT INTO citations (project_id, page_id, source_id, timestamp_seconds, title, url)
    SELECT 'proxy', page_id, video_id, timestamp_seconds, title, url FROM old.citations;

    -- relation_types_canonical (core): a partir de wiki/_meta/relation_types_core.json
    -- (no se migra desde old.relation_types_canonical para garantizar consistencia
    -- con el archivo JSON, que es la fuente de verdad)
    -- Se rellena en startup del MCP server, no en migración.

    DETACH DATABASE old;
    ```
    Tras verificación de conteos (pages_count, citations_count, etc. coinciden con `wiki.db` originales), elimina `data/wiki.db` original (`git rm`).
12. **Backfill Qdrant**: `scripts/migrate_qdrant_project_id.py` itera la colección y hace `set_payload({project_id: "proxy"})` a cada punto que **NO** tenga ya `project_id`. Resume-safe vía:
    ```python
    # Scroll filtrando puntos SIN project_id (resume si script murió a mitad)
    res = client.scroll(
        collection_name="ariadna_corpus",
        scroll_filter=Filter(must=[IsEmptyCondition(is_empty=PayloadField(key="project_id"))]),
        limit=500, with_payload=False, with_vectors=False,
    )
    # set_payload por batch hasta agotar
    ```
    Idempotente por construcción. ~6442 puntos en minutos.

    **Estabilidad de Qdrant IDs**: el ID Qdrant (`chunk_id_int`) NO cambia durante
    la migración — sigue siendo `hash(video_id + timestamp_seconds)` sin incluir
    project_id. Solo el payload gana la nueva key. Esto garantiza que el baseline
    capturado en `data/baseline_pre_migration.json` (que serializa chunk_ids)
    siga siendo comparable post-migración.
13. **Actualizar paths hardcoded** en archivos Python (ver tabla 8.2).
14. **Crear módulo `ariadna/project_config.py`** (sección 7.1).
15. **Eliminar tools `get_video_summary` y `list_videos`** de `ariadna/mcp_server.py` + helper `CorpusStore.list_videos()` de `ariadna/storage.py`.
16. **Smoke test post-migración**: `python scripts/test_hybrid.py` + `python scripts/verify_phase1.py` + verificar `wiki/` vacío excepto `wiki/_meta/*_default.*` y `wiki/_meta/relation_types_core.json`.
17. **Commit unitario**: `refactor(projects): migrate to multi-project layout, proxy as first tenant`.

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

**Baseline pre-migración** (capturado antes de tocar nada por `scripts/capture_baseline.py`):

- Lista de N=10 queries canónicas (`["sombra junguiana", "mito polar", "Tolkien", "hieros gamos", ...]`).
- Para cada query, hace `search_corpus(query=q, top_k=5, top_k_wiki=2)` y serializa a JSON los `chunk_ids`, `page_ids`, scores cosine, mode_recommended.
- Archivo `data/baseline_pre_migration.json` versionado en git para comparación posterior.

**Checks ejecutables post-migración** (`scripts/verify_phase1.py` los ejecuta secuencialmente, exit 0 si todos pasan):

- [ ] **Igualdad funcional**: ejecuta las mismas 10 queries y compara contra `data/baseline_pre_migration.json`. Pass si: mismo conjunto de `chunk_ids` en top-5 (orden puede variar levemente por re-vectorización), todas las queries devuelven al menos 1 `wiki_page` si lo hacían antes, ningún `mode_recommended` cambia entre `wiki_dominant`/`balanced`/`raw_with_warning`. Documentar tolerancia: scores cosine pueden diferir hasta ±0.01.
- [ ] **Filtro por proyecto**: `search_corpus(query="sombra", project="proxy")` devuelve idéntico resultado a `search_corpus(query="sombra")` (todos los puntos son `proxy`, filtro es no-op).
- [ ] **Proyecto inexistente**: `search_corpus(query="X", project="non_existent")` devuelve `{"error": "PROJECT_NOT_FOUND", "code": "PROJECT_NOT_FOUND"}`. Verificado con curl al endpoint MCP.
- [ ] **get_wiki_page**: `get_wiki_page("shadow-archetype", project="proxy")` y `get_wiki_page("shadow-archetype")` devuelven mismo `body_md`. Verificado por hash.
- [ ] **Smoke test existente**: `python scripts/test_hybrid.py` exit 0 (5/5 verde).
- [ ] **SQLite count**: `SELECT COUNT(*) FROM projects` = 1; `SELECT COUNT(*) FROM pages WHERE project_id='proxy'` = conteo pre-migración del `wiki.db` original (capturado en baseline).
- [ ] **Qdrant tagged**: `client.count(filter=Filter(must_not=[IsEmptyCondition(is_empty=PayloadField(key='project_id'))]))` = `client.count()` (todos los puntos tienen `project_id`).
- [ ] **Recursos globales**: `ls wiki/_meta/` muestra `relation_types_core.json` + 4 archivos `*_default.*`. Lectura del `relation_types_core.json` da exactamente 30 tipos (los actuales).
- [ ] **Run activo resume**: tras parar el run actual y migrar, `python scripts/extract_video_themes.py --resume pilot_sonnet_20260509 --project=proxy --dry-run` discovera los 178 vídeos del run, reconoce `done=N` desde `projects/proxy/_meta/extraction_runs/pilot_sonnet_20260509/state.json`, y sale sin error.
- [ ] **Rebuild scoped**: `python scripts/build_wiki_db.py --project=proxy` reconstruye el subset SQLite de Proxy en <5s (los 183+ páginas), termina con `relations=1102` igual que pre-migración.
- [ ] **Validador**: `python scripts/validate_wiki_relations.py --project=proxy` exit 0.

Notas operativas:

- El script `scripts/capture_baseline.py` se escribe **antes** de hacer la migración (esa es la primera task del plan de implementación).
- El script `scripts/validate_wiki_relations.py` ya existe en el repo y se adapta en la migración para aceptar `--project`.

### Fase 2 — Tools MCP de cola (sin workers)

**Criterio binario**: la cola es operacional desde Mattermost; los items se acumulan pero no se procesan (es esperado, los workers son fase futura).

**Checks ejecutables** (`scripts/verify_phase2.py`):

- [ ] `create_project(slug="test_e", name="Test E")` devuelve `{project_id: "test_e", paths_created: [...]}`. Verificable: `ls projects/test_e/_meta/` muestra `relation_types_ext.json`, `INDEX.md`, `extraction_runs/`; `ls projects/test_e/wiki/` muestra subdirs `concepts/ authors/ entities/works/ entities/institutions/ synthesis/` con `.gitkeep`.
- [ ] `create_project(slug="test_e", ...)` repetido devuelve `{"error": "...", "code": "SLUG_DUPLICATE"}`.
- [ ] `create_project(slug="Test_E", ...)` devuelve `code: "SLUG_INVALID"`. Idem `TEST`, `test e`, `-test`, `123abc`, `test--`.
- [ ] `create_project(slug="test_combo", seed_from_templates=True, inherit_from="proxy")` devuelve `code: "INCOMPATIBLE_OPTIONS"`. Cero estado creado.
- [ ] `create_project(slug="test_templates", seed_from_templates=True)` crea `projects/test_templates/_meta/{scope.md, topic_filters.json, subagent_prompt.md, canonical_whitelist.json}` con contenido idéntico (byte-a-byte) a `wiki/_meta/*_default.*`.
- [ ] `create_project(slug="test_inherit", inherit_from="proxy")` crea archivos en `projects/test_inherit/_meta/` con contenido idéntico a `projects/proxy/_meta/*` (los overrides de Proxy).
- [ ] `add_to_research_queue(project="proxy", source_url="https://youtu.be/dQw4w9WgXcQ")` devuelve `{request_id: <uuid>, detected_source_type: "youtube", status: "pending", was_duplicate: false}`.
- [ ] `add_to_research_queue(project="proxy", source_url="https://arxiv.org/abs/2301.00001")` devuelve `detected_source_type: "paper"`.
- [ ] `add_to_research_queue(project="proxy", source_url="https://example.com/doc.pdf")` → `pdf`.
- [ ] `add_to_research_queue(project="proxy", source_url="https://example.com/")` → `web`.
- [ ] `add_to_research_queue(project="proxy", source_url="not-a-url")` → `unknown`.
- [ ] Llamada duplicada (misma project+url, pending) devuelve `was_duplicate: true` con el mismo `request_id`.
- [ ] `add_to_research_queue(project="proxy", source_url="https://x.com", source_type="youtube")` respeta al caller: guarda `source_type='youtube'` sin warning aunque el detector hubiera dicho `web`.
- [ ] `list_research_queue(project="proxy", status="pending")` devuelve los items insertados; `total_matching` coincide con `COUNT(*)`.
- [ ] `list_research_queue(project=None, status="all")` devuelve todos cross-project.
- [ ] `list_research_queue(status="invalid_status")` devuelve `code: "INVALID_STATUS"`.
- [ ] `cancel_request(request_id=<pending>)` → `previous_status: "pending", current_status: "cancelled"`. Verificable via `SELECT status FROM research_queue WHERE request_id=?`.
- [ ] `cancel_request(request_id=<cancelled>)` → no-op idempotente, `previous_status == current_status == "cancelled"`.
- [ ] `cancel_request(request_id=<inexistente>)` → `code: "REQUEST_NOT_FOUND"`.
- [ ] `list_projects()` devuelve `[{project_id: "proxy", n_pages: 183+, n_chunks: 6259, n_queue_pending: 4}, ...]`. Conteos derivados de queries en vivo, no cacheados.
- [ ] Tools retiradas: `get_video_summary` y `list_videos` NO aparecen en `tools/list` del MCP. Verificable con curl.
- [ ] El system prompt de Ariadna en Mattermost se actualiza para mencionar las nuevas tools (out-of-CI; checklist manual post-deploy con runbook).

### 9.1 Out of scope (specs futuras)

- Workers de procesamiento (YouTube, papers, web, pdf) → **spec separada por tipo**
- Cross-project wikilinks/relations → si aparece necesidad, **spec menor independiente**
- Tool conversacional `customize_project_scope` → si demanda real → spec
- `delete_project` con UI confirmación → si demanda → spec
- Hot-reload tool MCP (`reload_config`) → si demanda → spec
- Tool `archive_project(slug, reason)` que setea `archived_at` → si demanda → spec menor

**Nota sobre `archived_at`**: la columna existe en `projects` desde Fase 1 (sección 4.1) para no requerir ALTER TABLE futuro. En MVP nadie la setea ni la lee — es campo reservado. `list_projects(include_archived=False)` por default filtra `WHERE archived_at IS NULL`; con `include_archived=True` los muestra. Esto deja la puerta abierta sin comprometer alcance.

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Migración no atómica deja sistema en estado intermedio inconsistente | Pre-flight checks; un solo commit; backup wiki/ por si acaso; rollback es `git reset --hard HEAD` |
| Run activo (`pilot_sonnet_20260509`) en progreso durante migración | Migración requiere extract_video_themes parado; el run debe terminar o pausarse antes. Verificar con `pgrep` |
| SQLite global lock contention con multi-worker (fase futura) | WAL mode desde Fase 1; multiple readers concurrent; writes son sub-segundo |
| El agente Mattermost cachea schema viejo de tools | Refresh Tools manual tras deploy (documentado en runbook post-migración) |
| Extensions de relation_types colisionan con core silenciosamente | Validación explícita en startup del server: `ConfigError` si colisión, refuse to start |
| Backfill Qdrant tarda más de lo esperado y falla | Idempotente vía filter `must_not=[IsEmpty(project_id)]`: re-ejecutar continúa por los puntos sin tag |
| Backfill Qdrant mid-flight con server/worker escribiendo nuevos puntos | Pre-flight check 1 (server parado) cubre el MCP. Adicional: durante la ventana de migración, NO ejecutar extract_video_themes ni ningún worker. Documentado en runbook: "Durante la migración, todo lo que escribe a Qdrant debe estar parado" |
| `seed_from_templates` introduce divergencia silenciosa cuando se modifica el default global | `scripts/audit_project_overrides.py` (sección 10.1) detecta copias que no divergen y las marca como ruido |
| Cliente Mattermost cachea schema viejo de tools tras deploy | Documentar en runbook: "tras deploy, Refresh Tools en Mattermost Agents settings". Tool `get_video_summary` / `list_videos` retiradas devuelven `TOOL_NOT_FOUND` claro hasta refresh |

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
