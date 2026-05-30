# Ariadna

> Hilo que guía por el laberinto del conocimiento acumulado.

**⚠ Prototipo en desarrollo activo.** Servidor MCP que da memoria de largo plazo a cualquier LLM, sobre corpus de conocimiento saneado y organizado por proyectos. Integrado con el plugin Agents de Mattermost.

---

## 1. La idea, en cristiano

Imagina que cualquier LLM (GPT, Claude, Grok, Gemini, uno local…) pudiera consultar **una biblioteca de conocimiento curado** en lugar de improvisar desde lo que recuerda de su entrenamiento. Ariadna es esa biblioteca, expuesta a través de un protocolo estándar (MCP) que el LLM entiende.

Cuatro ideas bastan para entenderlo:

**1. Es conocimiento para un LLM genérico, no un chatbot.**
Ariadna no responde a nadie directamente. Es un *servidor* al que el LLM le pregunta. El LLM sigue siendo quien razona y redacta; Ariadna solo le pasa material fiable y trazable. Cambia de LLM cuando quieras: el conocimiento se queda.

**2. El conocimiento son dos cosas, agrupadas por proyecto.**
- **IdeaBlocks** — unidades pequeñas que capturan *una idea clara*, ancladas a su cita exacta (timestamp de vídeo, página de PDF). Es lo que el LLM recupera por búsqueda semántica: el RAG. Concepto inspirado en [Blockify](https://blockify.ai): optimizar texto desordenado en bloques atómicos y trazables.
- **Wiki** — páginas estructuradas que destilan, deduplican y conectan esos IdeaBlocks (conceptos, autores, obras, síntesis), entrelazadas en un grafo. Es la capa donde la compresión y la limpieza se hacen explícitas.

Y todo eso vive dentro de un **proyecto**: una tesis, un canal de YouTube, una investigación sobre sueños, un atlas de papers… Cada proyecto tiene su propio corpus, su wiki y su alcance editorial, compartimentados.

**3. El proyecto lo decide el contexto de trabajo del LLM.**
Según en qué esté trabajando el LLM, consulta sobre un proyecto concreto. Pero puede **cruzar la búsqueda entre varios proyectos a la vez**, o lanzarla **contra todos** cuando un concepto atraviesa dominios. Coste cero: es un filtro, no copias de datos.

```
buscar("hieros gamos",  proyecto="proxy")              # solo un proyecto
buscar("alostasis",     proyecto=["proxy", "tesis"])   # unión de varios
buscar("realismo cognitivo")                           # todos (por defecto)
```

**4. Se le pide que incorpore material nuevo, y va a una cola.**
Mediante comandos, el LLM (o tú) puede pedir **integrar un recurso nuevo** — un vídeo, un PDF, un paper por DOI, un blog… El recurso queda **en cola**, y un proceso de fondo lo descarga, lo resume, lo convierte en IdeaBlocks + wiki, y lo indexa. La consulta es instantánea (camino *hot*); la ingesta es asíncrona (camino *cold*).

> **Arquitectura en una frase:** *el corpus es el activo, MCP es el contrato, el LLM es reemplazable.*

---

## 2. Los tres sustantivos clave

| Concepto | Qué es | Dónde vive |
|---|---|---|
| **Proyecto** | Unidad de compartimentación: corpus + wiki + alcance editorial propios. Comparten infraestructura, pero los datos están aislados (`project_id`). | `projects/<slug>/` |
| **IdeaBlock** | Unidad pequeña de *una idea clara*, anclada a su cita (timestamp/página) e indexada vectorialmente (BGE-M3 + Qdrant). Concepto tomado de [Blockify](https://blockify.ai). En Ariadna nacen ya semi-destilados (provienen de *summaries* temáticos, no de transcripción cruda). Internamente: `GenericChunk`. | Qdrant + `data/ariadna.db` |
| **Wiki** | La capa donde la destilación se completa: páginas markdown que dedup­lican y conectan los IdeaBlocks por entidad/concepto/autor/obra, con `relations[]` tipadas que forman un grafo navegable. | `projects/<slug>/wiki/` |

Búsqueda **específica** cuando importa el alcance de un dominio; **cross-all** cuando una idea cruza dominios.

---

## 3. Las capas de conocimiento (modelo "LLM Wiki" de Karpathy)

```
LAYER 0  —  IdeaBlocks crudos (Qdrant + BGE-M3): fuente de verdad indexada
LAYER 1  —  Wiki estructurada en markdown: páginas por entidad/concepto/autor/obra
LAYER 2  —  Grafo emergente: el conjunto de wikilinks + relations[] tipadas ES el grafo
LAYER 3  —  scope.md: contrato editorial entre corpus crudo y wiki (qué entra y por qué)
```

Cada capa se añade encima sin romper las anteriores, y se accede vía el mismo cliente MCP. El extractor LLM (sub-agente in-loop con `scope.md` como guía) construye y mantiene la wiki sin firma humana en el camino feliz. Roadmap por capas en [docs/PHASES.md](docs/PHASES.md).

---

## 4. Arquitectura técnica

![Arquitectura: HOT path (query realtime) + COLD path (workers) + Multi-tenant (proyectos compartimentados con búsqueda cruzada)](docs/images/architecture-multi-tenant.png)

Dos flujos desacoplados:

- **HOT (consulta, <500 ms)** — el LLM llama a `search_corpus`; el MCP recupera IdeaBlocks + páginas wiki candidatas (con `body_snippet`), rerankea y devuelve material trazable. El LLM filtra y profundiza solo en lo que necesita vía `get_wiki_page`.
- **COLD (ingesta, asíncrona)** — recursos encolados → descarga → resumen → extracción de IdeaBlocks y wiki → indexado. Hoy: adaptadores `youtube` y `paper`, summarizer nativo, y bypass *bring-your-own-summary* (un gestor de canal puede encolar material ya resumido).

**Decisiones de diseño cerradas:**

- Un solo Qdrant collection + `project_id` en el payload (no collection-per-project).
- Un solo SQLite `data/ariadna.db` (15 tablas, WAL) con todo el estado relacional.
- Aislamiento **total** por proyecto (wiki/chunks/citations/authors llevan `project_id`); **solo el archivo de fuentes es global**.
- Defaults editoriales en `wiki/_meta/*_default.*`; overrides en `projects/<slug>/_meta/`.
- Filtro `project` polimórfico `str | list[str] | None` → cross-search a N proyectos, coste cero.

> Diagrama mono-corpus anterior (histórico): [docs/images/architecture.png](docs/images/architecture.png) · Compartimentación multi-proyecto: [docs/images/multi-tenant-compartimentation.png](docs/images/multi-tenant-compartimentation.png)

Argumentación completa en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 5. Estado actual (2026-05-30)

El refactor a multi-proyecto **ya está ejecutado y verificado** (Fases 0–6.4). El sistema opera por proyectos; queda el worker que vacía la cola (F7) y el primer proyecto-papers end-to-end (F8).

| Componente | Estado |
|---|---|
| Layer 0 — RAG dense BGE-M3 + Qdrant + reranker cross-encoder | ✅ Operativo |
| Layer 1 — Wiki estructurada (proyecto `proxy`) | ✅ **222 páginas** · ~6.259 IdeaBlocks · 329 fuentes |
| Layer 2 — Grafo tipado (`relations[]`) | ✅ Operativo |
| **Modelo universal de referencias** (youtube/paper/pdf/web/blog) | ✅ Adaptadores + `source_archive` + summarizer nativo |
| **Multi-proyecto** (aislamiento por `project_id`, búsqueda cruzada) | ✅ **Operativo y verificado** |
| **7 tools MCP** (incl. crear proyecto + cola de ingesta) | ✅ Operativo |
| Integración Mattermost AI plugin | ✅ Validada (per-tool approval, ngrok) |
| **Worker de ingesta** (vacía la cola: descarga→resumen→wiki→index) | 🟡 Pendiente (F7) |
| Segundo proyecto E2E (`atlas-teleosemantico`, papers vía DOI) | 🟡 Pendiente (F8) |
| Despliegue producción (Hetzner, URL fija, observabilidad) | ⏳ Pendiente |

Estado vivo y detallado en [docs/NEXT_SESSION.md](docs/NEXT_SESSION.md).

---

## 6. Tools MCP expuestas

**Consulta (read):**

- **`search_corpus(query, top_k=5, top_k_wiki=2, project=None, category=None, playlist=None)`** — búsqueda híbrida con reranker + retrieval indirecto vía wiki citations. `project` acepta `str | list | None` (None = todos los proyectos). Devuelve `{wiki_pages, raw_chunks, retrieval_metadata}` con `mode_recommended` y `projects_seen`. Las `wiki_pages` traen `body_snippet` (~800 chars: H1 + primer H2 + tesis central) + `relations[]` tipadas. Schema: [docs/RESPONSE_FLOW.md §10](docs/RESPONSE_FLOW.md#10-schema-autoritativo-vigente-desde-2026-04-30).
- **`get_wiki_page(page_id, project=None, include_citations=False)`** — página wiki completa. Por defecto trima la sección `## Citations` (provenance que puede ser KB enteros); `include_citations=True` para recuperarla. Cross-all: desempata por `indexed_at` y expone `projects_with_this_id`.

**Gestión de proyectos y cola (write):**

- **`create_project(slug, ...)`** — crea un proyecto nuevo (seed desde plantillas o herencia de otro).
- **`list_projects(include_archived=False)`** — lista proyectos con su nº de IdeaBlocks.
- **`add_to_research_queue(...)`** — encola un recurso nuevo (vídeo/pdf/paper/web…). Idempotente; autodetecta el tipo de fuente.
- **`list_research_queue(...)`** — estado de la cola de ingesta.
- **`cancel_request(request_id, reason="")`** — cancela una petición (FSM `pending|failed → cancelled`).

> Nota: las tools `get_video_summary` y `list_videos` (mono-corpus) fueron **retiradas** en el refactor universal. Si actualizas un cliente Mattermost ya conectado, haz **Refresh Tools**.

---

## 7. Ejemplo de flujo (request real)

Usuario en Mattermost: _"¿Cómo conecta la alostasis con el wokismo?"_

```
1. El plugin dispara: search_corpus(query="alostasis wokismo")
   → MCP responde en <500ms con:
       - wiki_pages[]: candidatas con body_snippet (~800 chars c/u)
       - raw_chunks[] (IdeaBlocks): con cite_markdown
       - retrieval_metadata.mode_recommended: "balanced"

2. El LLM lee snippets + relations[] tipadas, identifica las 2 pages clave:
       - get_wiki_page("alostasis-y-apagon-organico")        → body completo
       - get_wiki_page("woke-narrativa-postmoderna-moral")   → body completo

3. El LLM cruza ambas pages y cita IdeaBlocks con timestamps clicables:
       "El wokismo no sería la alostasis, sino una mala gestión psíquica de
        la alostasis... → [Wokismo para Wokes (1:25:25)](https://youtu.be/...)"
```

El `body_snippet` permite filtrar entre N páginas antes de invocar `get_wiki_page` solo en las 1-3 que de verdad necesita. Para queries cross-conceptuales, eso ahorra ~95% de tokens vs servir bodies completos.

**Coste medido (gpt-5.4-mini, mayo 2026 — $0.75/M in + $4.50/M out):**

| Config Mattermost AI plugin | Coste/query | Anual @ 100q/d |
|---|---|---|
| Reasoning Medium + Native Web Search ON | $0.12 | $4.400 |
| **Reasoning Low + Web Search OFF (recomendado)** | **$0.01** | **$365** |

12x de diferencia. El reasoning Medium añade ~10-15K tokens de chain-of-thought (cobrados como output); bajarlo a Low los reduce a ~1-3K sin pérdida apreciable para RAG + síntesis con citas. Web Search OFF garantiza honestidad epistémica (el bot solo razona desde el corpus).

**Settings recomendados** (Mattermost AI plugin → Agents → tu bot): Web Search **off**, Reasoning **Low**, input token limit 150000, streaming timeout 120s.

---

## 8. Instalación y uso (camino corto)

**Requisitos:** Python 3.13+ · GPU CUDA recomendable (BGE-M3 va en CPU, más lento) · Qdrant embebido en disco (sin servidor separado) · Claude Code CLI autenticado para el extractor LLM offline.

```bash
git clone https://github.com/Sangaroth/ariadna.git
cd ariadna
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

```bash
# 1. Indexar la wiki de un proyecto en Qdrant (server PARADO: lock embedded)
.venv/bin/python scripts/index_wiki_to_qdrant.py --project proxy

# 2. Levantar el MCP server (--warm precarga el searcher)
.venv/bin/python -m ariadna.mcp_server --warm
# Escucha en http://0.0.0.0:8080/mcp (ARIADNA_MCP_HOST / ARIADNA_MCP_PORT)

# 3. Exponer al exterior (desarrollo)
ngrok http 8080

# 4. Consultar desde CLI (sin Mattermost)
curl -s -X POST http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_corpus","arguments":{"query":"sombra junguiana","top_k":3}}}'
```

**Integrar con Mattermost** (guía: [docs/INTEGRACION_MATTERMOST.md](docs/INTEGRACION_MATTERMOST.md)): plugin **Agents v2.0.0-rc1+** (per-tool approval es bloqueante para UX) → System Console → Agents → MCP Servers → Server URL `https://<tu-tunnel>/mcp` → Tools tab → política `Auto Run (DM)`.

---

## 9. Pipeline cold (generación de wiki)

```bash
# Reconstruir las tablas wiki de un proyecto en ariadna.db (puede correr con el server vivo)
.venv/bin/python scripts/build_wiki_db.py --project proxy

# Extractor LLM (YouTube, motor heredado — intacto por decisión de parity)
.venv/bin/python scripts/extract_video_themes.py --run-id batch_X --limit 20
.venv/bin/python scripts/extract_video_themes.py --resume batch_X      # reanudar
.venv/bin/python scripts/semantic_recovery.py --apply --min-cosine 0.60 # recovery

# Validar el grafo de relaciones de un proyecto
.venv/bin/python scripts/validate_wiki_relations.py --project proxy
```

Dos motores tras la misma interfaz de adaptador: **YouTube** (heredado, `extract_video_themes.py`, sub-agente in-loop) y **papers** (extractor LEAN nuevo, `ariadna/extract/paper.py`: 1 llamada LLM/paper → páginas JSON → materialización determinista con citas `[title, p.N](doi#page=N)`). Detalle en [docs/EXTRACTION_PIPELINE.md](docs/EXTRACTION_PIPELINE.md) y [docs/PIPELINE_REFACTOR_2026_05_02.md](docs/PIPELINE_REFACTOR_2026_05_02.md).

---

## 10. Estructura del repositorio

```
ariadna/
├── ariadna/                          — código fuente
│   ├── config.py · project_config.py — paths, modelo, Qdrant, ProjectConfig
│   ├── sources/                      — modelo universal de fuentes
│   │   ├── base.py · registry.py     — SourceAdapter Protocol + detección de tipo
│   │   ├── youtube.py · paper.py     — adaptadores por tipo de fuente
│   ├── summarize/                    — summarizer nativo (PDF→summary.md p.NN)
│   ├── extract/paper.py              — extractor LEAN de papers (1 LLM call)
│   ├── source_archive.py             — almacén content-addressable de fuentes
│   ├── projects.py · research_queue.py — gestión de proyectos + cola de ingesta
│   ├── parsers.py · embeddings.py · storage.py · reranker.py · search.py
│   ├── semantic_recovery.py          — LLM judge sobre discarded + cache idempotente
│   └── mcp_server.py                 — FastMCP server (7 tools)
├── scripts/                          — index/build/migrate/verify/extract
├── projects/<slug>/                  — datos por proyecto (aislados)
│   ├── wiki/                         — concepts · authors · entities/works · synthesis
│   └── _meta/                        — scope.md · whitelist · relation_types_ext · runs
├── wiki/_meta/                       — defaults globales (relation_types_core + plantillas)
├── data/
│   ├── ariadna.db                    — SQLite, 15 tablas, estado relacional (gitignored)
│   ├── qdrant/                       — vector DB persistente (gitignored)
│   └── sources/                      — archivo content-addressable de fuentes
└── docs/                             — ARCHITECTURE · PHASES · RESPONSE_FLOW · …
```

---

## 11. Qué es y qué no es

- ✅ **Es** un servidor MCP read-mostly que expone corpus saneado a cualquier LLM compatible.
- ✅ **Es** una arquitectura de dos flujos: consulta *hot* (RAG) e ingesta/generación *cold*.
- ✅ **Es** multi-proyecto: corpus compartimentados con búsqueda cruzada opt-in.
- ❌ **No es** un wrapper de un LLM concreto — el LLM es intercambiable.
- ❌ **No es** una solución end-to-end — necesitas un cliente MCP (ej. Mattermost AI plugin v2.0.0-rc1+).
- ❌ **No es** producción — orquestación manual, sin CI, sin observabilidad sistemática.

**Limitaciones conocidas (estado prototipo):**

- **Worker de ingesta pendiente (F7)**: la cola (`add_to_research_queue`) acepta peticiones, pero el proceso que las vacía (descarga→resumen→wiki→index) aún no está implementado.
- **Orquestación manual**: arrancar MCP, ngrok, monitorizar runs — sin wrapper único.
- **Sin observabilidad sistemática**: logs en `logs/`, métricas ad-hoc, sin dashboards.
- **Coste extractor**: Claude Opus vía suscripción Max (incluido, sin gasto extra) — pero limita paralelismo.
- **Idempotencia con caveats**: `semantic_recovery_cache.json` usa flag `applied_at`; reset = borrar cache.

---

## 12. Documentación clave

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — por qué desacoplar MCP del LLM, por qué dos flujos
- **[docs/PHASES.md](docs/PHASES.md)** — roadmap por fases con criterios de salto
- **[docs/NEXT_SESSION.md](docs/NEXT_SESSION.md)** — estado vivo, decisiones, quirks, comandos útiles
- **[docs/RESPONSE_FLOW.md](docs/RESPONSE_FLOW.md)** — schema autoritativo MCP con ejemplos JSON
- **[docs/INTEGRACION_MATTERMOST.md](docs/INTEGRACION_MATTERMOST.md)** — guía paso a paso del cliente
- **[docs/EXTRACTION_PIPELINE.md](docs/EXTRACTION_PIPELINE.md)** · **[docs/PIPELINE_REFACTOR_2026_05_02.md](docs/PIPELINE_REFACTOR_2026_05_02.md)** — pipelines
- **[docs/WIKI_GENERATION.md](docs/WIKI_GENERATION.md)** — wiki estructurada con grafo emergente
- **[docs/TAXONOMY_PROPOSAL.md](docs/TAXONOMY_PROPOSAL.md)** — modelo multi-fuente (papers, libros, podcasts)
- **[docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md](docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md)** — spec multi-proyecto

## Licencia

[MIT](LICENSE).
