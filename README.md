# Ariadna

> Hilo que guía por el laberinto del conocimiento acumulado.

Asistente conversacional con acceso a un corpus de vídeos analíticos via **Model Context Protocol (MCP)**. El usuario interactúa con cualquier LLM (GPT, Claude, Gemini, modelo local) en Mattermost; al fondo, un servidor MCP en Python resuelve consultas semánticas sobre el corpus indexado.

![Arquitectura: HOT path (consulta realtime) y COLD path (generación de conocimiento)](docs/images/architecture.png)

## Qué es y qué no es

- ✅ **Es:** un servidor MCP read-only que expone un corpus saneado a cualquier LLM compatible
- ✅ **Es:** una arquitectura de dos flujos — consulta hot (RAG) y generación cold (workers asíncronos)
- ✅ **Es:** una base sobre la que construir KAG, LLM Wiki, entity index sin reescribir el corpus
- ❌ **No es:** un wrapper alrededor de un LLM concreto — el LLM es intercambiable
- ❌ **No es:** una solución end-to-end — necesitas un cliente MCP (ej. Mattermost AI plugin)

## Arquitectura en una frase

**El corpus es el activo, MCP es el contrato, el LLM es reemplazable.** Detalle en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tres capas de evolución

```
LAYER 1 (hoy)  —  RAG dense BGE-M3 sobre chunks temáticos en Qdrant
LAYER 2 (B)    —  Entity index + co-ocurrencia para cross-reference por entidad
LAYER 3 (E)    —  LLM Wiki compilado en cold path para queries conceptuales
```

Cada capa se añade encima sin romper las anteriores. Roadmap completo en [docs/PHASES.md](docs/PHASES.md).

## Estado del proyecto

| Fase | Estado |
|---|---|
| **A.1** — Layer 1 RAG dense + MCP server + integración Mattermost | ✅ Cerrada (2026-04-23) |
| **A.2** — Sparse BM25, threshold, reranker, prompt lateral | Backlog |
| **B** — Entity index | Pendiente |
| **C** — Despliegue producción (Hetzner, URL fija) | Pendiente |
| **D** — Cold path con voluntarios | Pendiente |
| **E** — LLM Wiki compilado | Pendiente |

Estado vivo en [docs/SESSION_CONTEXT.md](docs/SESSION_CONTEXT.md).

## Requisitos

- Python 3.13+
- GPU con CUDA recomendable para indexado rápido (BGE-M3 funciona en CPU pero más lento)
- Qdrant embebido en disco via `qdrant-client` (no requiere servidor separado)
- Corpus fuente con estructura `<categoría>/<vídeo>/{summary.md, meta.json}`

## Instalación

```bash
git clone https://github.com/sangaroth-ux/ariadna.git
cd ariadna
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Uso

### 1. Indexar el corpus

```bash
ariadna-index --source /path/to/corpus/playlists
```

Genera embeddings con BGE-M3 y los persiste en `data/qdrant/` (gitignored).

### 2. Ejecutar el servidor MCP

```bash
./scripts/run_server.sh
# o equivalente:
ariadna-server --host 0.0.0.0 --port 8765 --warm
```

### 3. Exponer al exterior (desarrollo)

```bash
./scripts/run_tunnel.sh   # ngrok http 8765
```

Para producción ver [docs/PHASES.md#fase-c--despliegue-producción-hetzner](docs/PHASES.md#fase-c--despliegue-producción-hetzner).

### 4. Integrar con Mattermost

Guía paso a paso en [docs/INTEGRACION_MATTERMOST.md](docs/INTEGRACION_MATTERMOST.md). Resumen:

- Plugin **Agents v2.0.0-rc1+** (per-tool approval policy es bloqueante para UX)
- System Console → Agents → MCP Servers → Server URL: `https://<your-tunnel-or-domain>/mcp`
- Tools tab → política `Auto Run (DM)` en cada tool

### 5. Consultar desde CLI (sin Mattermost)

```bash
ariadna-search "que dice el canal sobre el hieros gamos"
```

O via HTTP al servidor ya corriendo (no bloquea Qdrant):

```bash
curl -s -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_corpus","arguments":{"query":"sombra junguiana","top_k":3}}}'
```

## Tools MCP expuestas (Layer 1)

- **`search_corpus(query, top_k=5, category=None, playlist=None)`** — búsqueda semántica con filtros opcionales por categoría/playlist
- **`get_video_summary(video_id)`** — chunks completos de un vídeo en orden cronológico
- **`list_videos(category=None, playlist=None)`** — listado filtrado de vídeos del corpus

## Estructura del repositorio

```
ariadna/
├── pyproject.toml
├── README.md
├── LICENSE
├── ariadna/                  — código fuente (~935 líneas)
│   ├── config.py             — paths, modelo, Qdrant settings
│   ├── parsers.py            — markdown → Chunk dataclass
│   ├── embeddings.py         — wrapper BGE-M3
│   ├── storage.py            — wrapper Qdrant
│   ├── search.py             — Searcher + CLI
│   ├── build_index.py        — CLI de indexado
│   └── mcp_server.py         — FastMCP server
├── scripts/
│   ├── run_server.sh         — arranca MCP server
│   ├── run_tunnel.sh         — expone via ngrok
│   └── test_mcp_call.sh      — test directo via curl
├── docs/
│   ├── ARCHITECTURE.md       — argumentación de diseño (decoupling, hot/cold)
│   ├── PHASES.md             — roadmap por capas
│   ├── SESSION_CONTEXT.md    — estado vivo, decisiones, quirks
│   ├── INTEGRACION_MATTERMOST.md — guía cliente
│   ├── run_pipeline.md       — pipeline técnico paso a paso
│   └── images/architecture.png   — infografía hot/cold
├── tests/
└── data/qdrant/              — vector DB persistente (gitignored)
```

## Documentación

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — argumentación de diseño: por qué desacoplar MCP del LLM, por qué dos flujos, por qué la taxonomía importa más que la tecnología
- **[docs/TAXONOMY_PROPOSAL.md](docs/TAXONOMY_PROPOSAL.md)** — propuesta abierta de schema, tags, entities, vocabulary.json controlado e ingesta multi-formato con [markitdown](https://github.com/microsoft/markitdown). Doc vivo, no cerrado
- **[docs/PHASES.md](docs/PHASES.md)** — roadmap completo de las 5 fases (A→E) y criterios para saltar de una a otra
- **[docs/SESSION_CONTEXT.md](docs/SESSION_CONTEXT.md)** — estado vivo del proyecto, decisiones tomadas, bugs conocidos, comandos útiles
- **[docs/run_pipeline.md](docs/run_pipeline.md)** — pipeline técnico end-to-end (corpus → parser → embedding → Qdrant → MCP → LLM)
- **[docs/INTEGRACION_MATTERMOST.md](docs/INTEGRACION_MATTERMOST.md)** — guía paso a paso de integración con el cliente Mattermost

## Licencia

[MIT](LICENSE).
