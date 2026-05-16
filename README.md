# Ariadna

> Hilo que guía por el laberinto del conocimiento acumulado.

**⚠ Prototipo en desarrollo activo.** Servidor MCP de RAG sobre un corpus YouTube saneado, integrado con Mattermost AI plugin. Pipeline operativo end-to-end; refactor multi-proyecto en plan (no ejecutado todavía).

El usuario interactúa con cualquier LLM (GPT, Claude, Grok, Gemini, local) en Mattermost; al fondo, el MCP server resuelve consultas semánticas sobre la wiki estructurada y los chunks RAG del corpus.

![Arquitectura: HOT path (consulta realtime) y COLD path (generación de conocimiento)](docs/images/architecture.png)

## Qué es y qué no es

- ✅ **Es:** un servidor MCP read-only que expone un corpus saneado a cualquier LLM compatible
- ✅ **Es:** una arquitectura de dos flujos — consulta hot (RAG) y generación cold (extractor LLM offline)
- ✅ **Es:** **prototipo** funcional sobre un corpus específico (YouTube de Proxy), con plan de generalización multi-proyecto
- ❌ **No es:** un wrapper alrededor de un LLM concreto — el LLM es intercambiable
- ❌ **No es:** una solución end-to-end — necesitas un cliente MCP (ej. Mattermost AI plugin v2.0.0-rc1+)
- ❌ **No es:** producción — orquestación todavía manual, sin CI, sin observabilidad sistemática

## Arquitectura en una frase

**El corpus es el activo, MCP es el contrato, el LLM es reemplazable.** Detalle en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Capas de evolución (Karpathy "LLM Wiki")

```
LAYER 0  —  Raw chunks (Qdrant + BGE-M3): fuente de verdad indexada
LAYER 1  —  Wiki estructurada en markdown (wiki/): páginas por entidad/concepto/autor/obra
LAYER 2  —  Grafo emergente: el conjunto de wikilinks + relations[] tipadas ES el grafo
LAYER 3  —  Scope.md: contrato editorial entre corpus crudo y wiki (qué entra y por qué)
```

Cada capa se añade encima sin romper las anteriores, y se accede vía el mismo cliente MCP. El extractor LLM (sub-agente in-loop con scope.md como guía) construye y mantiene la wiki sin firma humana en el camino feliz. Roadmap completo en [docs/PHASES.md](docs/PHASES.md).

## Estado actual (2026-05-16)

| Componente | Estado |
|---|---|
| Layer 0 — RAG dense BGE-M3 + Qdrant + MCP server | ✅ Operativo |
| Reranker cross-encoder + retrieval indirecto via citations | ✅ Operativo |
| Layer 1 — Wiki estructurada | ✅ **223 páginas** (78 conceptos, 15 autores, 73 obras, 56 syntheses) |
| Pipeline push-based extractor LLM (Karpathy) | ✅ **296 / 296 vídeos procesados** (100% del corpus) |
| Semantic recovery (LLM judge sobre discarded) | ✅ Cache idempotente con `applied_at` flag, 119 high matches aplicados |
| Integración Mattermost AI plugin | ✅ Validada (per-tool approval, ngrok tunnel) |
| **Refactor multi-tenant** (Project + research queue) | 🟡 Spec aprobada + plan 9 chunks, **ejecución pendiente** |
| Cold path con voluntarios + ingesta multi-formato (PDF, HTML, papers) | ⏳ Spec separada futura |
| Despliegue producción (Hetzner, URL fija, observabilidad) | ⏳ Pendiente |

Estado vivo en [docs/NEXT_SESSION.md](docs/NEXT_SESSION.md).

## Roadmap próxima fase: multi-tenant

Ariadna nació mono-corpus (canal Proxy YouTube). La siguiente fase la convierte en plataforma multi-proyecto, donde cada proyecto (tesis, gadgets, investigación de sueños, etc.) tiene su scope + wiki + cola de ingesta propios, compartiendo infraestructura.

**Decisiones cerradas durante brainstorming (2026-05-16):**

- Single Qdrant collection + `project_id` en payload (no collection-per-project)
- Single SQLite `data/ariadna.db` con todo el estado relacional
- Defaults editoriales en `wiki/_meta/*_default.*`, overrides en `projects/<slug>/_meta/*.*`
- Relation types: core globales + extensions per-proyecto
- MCP gana tools write: `create_project`, `add_to_research_queue`, `cancel_request`
- Workers que procesan la cola = scope futuro, desacoplados del MCP
- Cross-project wikilinks/relations NO en MVP

Specs:
- [docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md](docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md) (858 líneas)
- [docs/superpowers/plans/2026-05-16-multi-project-and-research-queue.md](docs/superpowers/plans/2026-05-16-multi-project-and-research-queue.md) (9 chunks, ≈6400 líneas)
- [docs/AGENT_HANDOFF_2026-05-16.md](docs/AGENT_HANDOFF_2026-05-16.md) — handoff a sesión ejecutora

## Requisitos

- Python 3.13+
- GPU con CUDA recomendable para indexado rápido (BGE-M3 funciona en CPU pero más lento)
- Qdrant embebido en disco via `qdrant-client` (no requiere servidor separado)
- Claude Code CLI (`claude`) autenticado con Anthropic Max — para extractor LLM offline
- Corpus fuente generado por proyecto separado [ProxySummaries](https://github.com/Sangaroth/ProxySummaries) con estructura `<categoría>/<vídeo>/{summary.md, meta.json}`

## Instalación

```bash
git clone https://github.com/Sangaroth/ariadna.git
cd ariadna
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Uso (camino corto)

### 1. Indexar el corpus

```bash
.venv/bin/python scripts/index_wiki_to_qdrant.py
```

Genera embeddings BGE-M3 de las wikis y los persiste en `data/qdrant/` (gitignored).

### 2. Levantar el MCP server

```bash
.venv/bin/python -m ariadna.mcp_server
# Escucha en http://0.0.0.0:8080/mcp (ARIADNA_MCP_HOST / ARIADNA_MCP_PORT)
```

### 3. Exponer al exterior (desarrollo)

```bash
ngrok http 8080
# https://abc123.ngrok-free.app/mcp → http://localhost:8080/mcp
```

### 4. Integrar con Mattermost

Guía paso a paso en [docs/INTEGRACION_MATTERMOST.md](docs/INTEGRACION_MATTERMOST.md):

- Plugin **Agents v2.0.0-rc1+** (per-tool approval policy es bloqueante para UX)
- System Console → Agents → MCP Servers → Server URL: `https://<your-tunnel>/mcp`
- Tools tab → política `Auto Run (DM)` en las tools que uses

### 5. Consultar desde CLI (sin Mattermost)

```bash
curl -s -X POST http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_corpus","arguments":{"query":"sombra junguiana","top_k":3}}}'
```

## Tools MCP expuestas

- **`search_corpus(query, top_k=5, category=None, playlist=None)`** — búsqueda híbrida con reranker cross-encoder + retrieval indirecto vía wiki citations. Devuelve `{wiki_pages, raw_chunks, retrieval_metadata}` con `mode_recommended`. Wiki entries llevan `match_via ∈ {semantic, citation, citation_video, both}`. Schema: [docs/RESPONSE_FLOW.md §10](docs/RESPONSE_FLOW.md#10-schema-autoritativo-vigente-desde-2026-04-30)
- **`get_wiki_page(page_id, include_citations=False)`** — página wiki completa. Por defecto trima sección "## Citations" (provenance al corpus, puede ser KB enteros que no aportan a razonamiento conceptual). Pasa `include_citations=True` para incluirla.
- **`get_video_summary(video_id)`** — chunks completos de un vídeo en orden cronológico
- **`list_videos(category=None, playlist=None)`** — listado filtrado de vídeos del corpus

## Pipeline cold (generación de wiki)

```bash
# Procesar batch de vídeos del corpus
.venv/bin/python scripts/extract_video_themes.py --run-id batch_X --limit 20

# Reanudar un run interrumpido
.venv/bin/python scripts/extract_video_themes.py --resume batch_X

# Aggregator manual sobre un run existente (sin re-llamar LLM)
.venv/bin/python scripts/extract_video_themes.py --aggregate batch_X

# Semantic recovery sobre discarded históricos (LLM judge sobre top-K cosine)
.venv/bin/python scripts/semantic_recovery.py --apply --min-cosine 0.60
```

El extractor invoca Claude Opus 4.7 (vía suscripción Max) y emite JSON estructurado por vídeo (entities, pending_updates, thesis_candidates, discarded). Aggregator fusiona en colas de revisión. Schema-tolerant: ignora keys nuevos sin romper. Detalle en [docs/EXTRACTION_PIPELINE.md](docs/EXTRACTION_PIPELINE.md) y [docs/PIPELINE_REFACTOR_2026_05_02.md](docs/PIPELINE_REFACTOR_2026_05_02.md).

## Estructura del repositorio

```
ariadna/
├── README.md
├── pyproject.toml
├── ariadna/                          — código fuente
│   ├── config.py                     — paths, modelo, Qdrant, MCP_HOST/PORT
│   ├── parsers.py                    — markdown → Chunk dataclass
│   ├── embeddings.py                 — wrapper BGE-M3
│   ├── storage.py                    — wrapper Qdrant embedded
│   ├── reranker.py                   — cross-encoder rerank
│   ├── search.py                     — Searcher con retrieval indirecto + 2-pass citations
│   ├── semantic_recovery.py          — LLM judge sobre discarded + cache idempotente
│   └── mcp_server.py                 — FastMCP server (4 tools)
├── scripts/
│   ├── extract_video_themes.py       — extractor LLM con sub-agente in-loop (Karpathy)
│   ├── apply_pending_updates.py      — aplica diff-style ops con anchor literal único
│   ├── compile_wiki_pages.py         — sync shadow_wiki → wiki real
│   ├── build_wiki_db.py              — genera data/wiki.db (citations table)
│   ├── index_wiki_to_qdrant.py       — indexa páginas wiki en Qdrant
│   ├── scan_mentions_ledger.py       — pasada 1 recovery (sub-string match)
│   └── semantic_recovery.py          — pasada 2 recovery (CLI thin wrapper)
├── wiki/                             — base de conocimiento (223 pages)
│   ├── concepts/                     — 78 conceptos
│   ├── authors/                      — 15 autores canónicos
│   ├── entities/works/               — 73 obras
│   ├── synthesis/                    — 56 páginas síntesis (cross-cuts)
│   └── _meta/
│       ├── scope.md                  — contrato editorial v0.3
│       ├── canonical_whitelist.json  — figuras canónicas con auto_promote
│       ├── relation_types.json       — tipos relations[] permitidos
│       ├── semantic_recovery_cache.json  — cache LLM judge (236 entries, applied_at)
│       └── extraction_runs/          — JSONs commiteados (memoria operativa LLM)
├── docs/
│   ├── ARCHITECTURE.md               — argumentación de diseño
│   ├── PHASES.md                     — roadmap por capas
│   ├── EXTRACTION_PIPELINE.md        — pipeline push-based
│   ├── PIPELINE_REFACTOR_2026_05_02.md — refactor v0.3 (16 secciones)
│   ├── RESPONSE_FLOW.md              — schema autoritativo MCP
│   ├── INTEGRACION_MATTERMOST.md     — guía cliente
│   ├── NEXT_SESSION.md               — estado vivo del proyecto
│   ├── AGENT_HANDOFF_2026-05-16.md   — handoff multi-tenant
│   └── superpowers/
│       ├── specs/2026-05-16-multi-project-and-research-queue-design.md
│       └── plans/2026-05-16-multi-project-and-research-queue.md
├── tests/
├── data/qdrant/                      — vector DB persistente (gitignored)
└── data/wiki.db                      — SQLite citations table (gitignored, regenerable)
```

## Limitaciones conocidas (estado prototipo)

- **Mono-corpus**: hoy todo el código asume el canal Proxy. Refactor a multi-tenant planificado.
- **Orquestación manual**: arrancar MCP, ngrok, monitorizar run del extractor — sin script wrapper único.
- **Sin observabilidad sistemática**: logs en `logs/`, métricas ad-hoc, no dashboards.
- **Coste extractor**: Claude Opus 4.7 vía suscripción Max (incluido, sin gasto extra) — pero limita paralelismo.
- **Cold path manual**: nuevos vídeos requieren `ProxySummaries` corriendo en otro proyecto + lanzamiento manual de `extract_video_themes.py`. La cola de investigación con workers desacoplados es spec futura.
- **Idempotencia con caveats**: el cache `semantic_recovery_cache.json` usa `applied_at` flag; reset = borrar cache (decisión deliberada para no auditar estado del wiki tras edición humana).
- **Citations sección al pie**: 5-7 KB por wiki hub. El MCP las trima por defecto en `get_wiki_page` (opt-in via `include_citations=True`).

## Documentación clave

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — argumentación de diseño: por qué desacoplar MCP del LLM, por qué dos flujos
- **[docs/PHASES.md](docs/PHASES.md)** — roadmap por fases con criterios de salto
- **[docs/NEXT_SESSION.md](docs/NEXT_SESSION.md)** — estado vivo, decisiones, bugs conocidos, comandos útiles
- **[docs/RESPONSE_FLOW.md](docs/RESPONSE_FLOW.md)** — schema autoritativo MCP con ejemplos JSON completos
- **[docs/INTEGRACION_MATTERMOST.md](docs/INTEGRACION_MATTERMOST.md)** — guía paso a paso del cliente
- **[docs/EXTRACTION_PIPELINE.md](docs/EXTRACTION_PIPELINE.md)** — pipeline push-based base
- **[docs/PIPELINE_REFACTOR_2026_05_02.md](docs/PIPELINE_REFACTOR_2026_05_02.md)** — refactor v0.3 completo
- **[docs/WIKI_GENERATION.md](docs/WIKI_GENERATION.md)** — pipeline de wiki estructurada con KG emergente
- **[docs/TAXONOMY_PROPOSAL.md](docs/TAXONOMY_PROPOSAL.md)** — schema multi-fuente futuro (papers, libros, podcasts)
- **[docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md](docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md)** — spec multi-tenant aprobada
- **[wiki/README.md](wiki/README.md)** — base de conocimiento navegable

## Licencia

[MIT](LICENSE).
