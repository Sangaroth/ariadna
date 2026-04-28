# Session context — continuidad de conversacion

> Documento autogenerado para continuar la implementacion de Ariadna en una nueva sesion de Claude Code.
> Captura: estado actual, decisiones tomadas, proximos pasos, quirks conocidos.
> **Ultima actualizacion:** 2026-04-23 (tarde — Sprint 1 cerrado tras validacion en DM)

---

## Estado actual (resumen ejecutivo)

**Fase A Sprint 1 — CERRADA.** Validacion en DM con Ariadna completada con calidad notable. Todos los criterios de exito cumplidos.

- Corpus indexado: 288 videos → 6036 chunks en Qdrant (72MB local)
- Servidor MCP validado end-to-end: HTTP local + ngrok + Mattermost + LLM tool-use real
- 3 tools en Mattermost con politica **Auto Run (DM)** (sin Accept/Reject manual):
  `search_corpus`, `get_video_summary`, `list_videos`
- Plugin Mattermost Agents **actualizado a v2.0.0-rc6** (desde v1.7.2) — upgrade necesario para obtener el selector per-tool de politica de aprobacion (introducido en v2.0.0-rc1, PR #520). Plugin ID sigue siendo `mattermost-ai`, upgrade in-place.
- URL ngrok activa (volatil): `https://<your-ngrok-id>.ngrok-free.app/mcp`
- Proxima fase a decidir: B (entity index) o C (despliegue Hetzner con URL fija).

---

## Contexto del proyecto Ariadna

**Que es:** asistente conversacional en Mattermost (`<your-mattermost-instance>`) con acceso al corpus del canal Proxy (288 videos analiticos de mitologia, psicologia, filosofia, analisis de obra, cultura). Integracion via **Model Context Protocol (MCP)** con el plugin AI de Mattermost.

**Corpus upstream:** `<PROXYSUMMARIES_ROOT>/data/playlists/` — generado por el proyecto ProxySummaries (288 carpetas de video con `summary.md` + `meta.json`).

**Documento de diseño completo:** [<PROXYSUMMARIES_ROOT>/docs/knowledge-architecture-research.md](../../ProxySummaries/docs/knowledge-architecture-research.md) (750+ lineas: RAG vs KAG vs LLM Wiki vs Second Brain, decisiones arquitectonicas, comparativas).

**Seccion "in development" en ProxySummaries CLAUDE.md:** avisa a futuros Claude que el trabajo MCP/RAG esta en diseño y ProxySummaries es upstream estable.

---

## Arquitectura elegida

### Tres capas (diseño, solo Layer 1 implementada)

```
LAYER 1 (IMPLEMENTADA) — RAG hibrido sobre chunks tematicos
  BGE-M3 embeddings (local, GPU) + Qdrant
  
LAYER 2 (Fase B, futura) — Entity index
  vocabulary.json + co-ocurrencia
  
LAYER 3 (Fase C, opcional) — Wiki compilado
  Paginas concepto via cold path (Claude Code overnight)
```

### Decisiones tomadas

| Decision | Eleccion | Razon |
|----------|----------|-------|
| Hosting | A (local) → B (Hetzner server aparte) | Test rapido local, luego servidor ligero |
| Embeddings | BGE-M3 local en RTX 3080 | $0, privado, dim 1024, dense+sparse nativo |
| Vector DB | Qdrant embedded | Hibrido nativo, filtros potentes, portable |
| Package mgr | uv | Rapido, moderno |
| LLM sintesis | OpenAI via Mattermost AI plugin | Ya configurado, MCP nativo |
| LLM cold (futuro) | Claude Code CLI cuota Max | Coste marginal $0 |
| Transport MCP | streamable-http | Soportado por Mattermost 11.2+ |
| Exposicion local | ngrok (free plan) | Simple; URL cambia en restart |
| Sparse retrieval | POSPUESTO | Dense-only basta para Sprint 1; añadir si precision flaquea |

### Hot path vs cold path

- **Hot (realtime):** API OpenAI via Mattermost AI → MCP tools → Qdrant → respuesta
- **Cold (async):** cola SQLite → worker nocturno con `claude -p` → escribe a Obsidian vault → notifica via webhook. **No implementado aun**, Fase C.

---

## Estructura del codigo

```
<PROJECT_ROOT>/
├── pyproject.toml          — deps via uv, entry points ariadna-index / -server / -search
├── .python-version         — 3.13
├── README.md               — overview + quickstart
├── ariadna/                — 935 lineas Python
│   ├── config.py           — paths, modelo, Qdrant, YouTube URLs
│   ├── parsers.py          — regex-based parser de summary.md → Chunk dataclass
│   ├── embeddings.py       — DenseEmbedder wrapper BGE-M3 via sentence-transformers
│   ├── storage.py          — CorpusStore wrapper Qdrant (upsert, search, scroll)
│   ├── search.py           — Searcher + CLI ariadna-search
│   ├── build_index.py      — CLI ariadna-index (parse → embed → upsert)
│   └── mcp_server.py       — FastMCP con 3 tools, streamable-http en /mcp
├── data/qdrant/            — 72MB indexado (gitignored)
├── scripts/
│   ├── run_server.sh       — arranca servidor en 0.0.0.0:8765
│   └── run_tunnel.sh       — ngrok http 8765
└── docs/
    ├── INTEGRACION_MATTERMOST.md   — guia paso a paso UI + prompt actualizado
    └── SESSION_CONTEXT.md          — ESTE ARCHIVO
```

### Puntos de entrada clave

- **Indexar corpus:** `ariadna-index` o `python -m ariadna.build_index --recreate`
- **CLI de busqueda:** `ariadna-search "query"` o `python -m ariadna.search "query" --top-k 5`
- **Servidor MCP:** `ariadna-server` o `./scripts/run_server.sh`
- **Tunel:** `./scripts/run_tunnel.sh`

---

## Metricas de rendimiento validadas

**Indexado en RTX 3080:**
- Parseo 6036 chunks: <1s
- Embeddings BGE-M3: 31s (195 chunks/s)
- Insert Qdrant: 55s
- **Total: 86s** nothing → fully indexed

**Query latency:** <200ms end-to-end (embed query + retrieval + serialize)

**Retrieval quality (scores coseno):**
- Queries golden probadas: "hieros gamos" (0.55), "sombra junguiana" (0.57), "transhumanismo" (0.61), "Lovecraft" (0.67), "teoria de la mente" filtrado por categoria (0.59)
- Todos resultados semanticamente relevantes + URLs YouTube clicables + metadata completa

---

## Estado de integracion Mattermost

**Servidor de Mattermost:** `<your-mattermost-instance>` (MM 11.6 Entry, Docker en Hetzner)

**Plugin Agents:** v2.0.0-rc6 (actualizado 2026-04-23 desde v1.7.2)
- Feature clave del upgrade: selector per-tool de politica de aprobacion (`ask` / `auto_run_in_dm` / `auto_run_everywhere`), no existia en v1.x
- Breaking changes absorbidos: config migrada de `config.json` a BD, Bifrost LLM gateway, defaults cambiados (MCP enabled, Responses API por defecto, native tools)
- Plugin ID invariante: `mattermost-ai` → upgrade in-place, config conservada

**Agente configurado:**
- Nombre: Ariadna, username `ariadna`
- AI Service: `mattermost-matty-dev` (OpenAI, gpt-5.4-mini)
- `Enable Tools: verdadero`
- `Use Responses API: verdadero` (activado en upgrade)
- `Reasoning: Enable` activado (mejora tool-use + cross-reference)
- `Render AI-generated links: verdadero`
- Debug: `Enable LLM Trace` y `Enable Token Usage Logging` = verdadero

**MCP config:**
- `Enable MCP Client: verdadero`
- `Enable Mattermost MCP Server (HTTP)`: falso (no lo necesitamos)
- `Enable Embedded Server`: ya no visible en Configuration tab de v2 → se gestiona por tool en Tools tab. 14/14 tools del servidor Mattermost embebido desactivadas individualmente (no aportan, introducirian ruido)
- MCP Server 1 Server URL: `https://<your-ngrok-id>.ngrok-free.app/mcp` (volatil, cambia en cada `run_tunnel.sh`)
- Headers: vacios (sin auth en Fase A)
- **OJO quirk:** si se añade una fila de header vacia (ni name ni value), da error `invalid header field name ""`. Solucion: borrar la fila con papelera.

**Tools tab (Agents → Tools):**
- MCP Server 1 → Connected, 3/3 tools enabled, **Auto Run (DM)** en las 3
  - `search_corpus` → Auto Run (DM)
  - `get_video_summary` → Auto Run (DM)
  - `list_videos` → Auto Run (DM)
- Mattermost (embedded) → 0/14 tools enabled (desactivadas)

---

## Validacion calidad — RESULTADOS (2026-04-23)

### Criterios de exito (todos cumplidos)

- [x] Tools registradas en Mattermost
- [x] Ariadna invoca `search_corpus` con buenos argumentos (query + category filter) automaticamente
- [x] Cita videos + timestamps reales (verificado, no alucinados) — clicables con `Render links: verdadero`
- [x] Distingue corpus vs conocimiento general vs interpretacion (usa etiquetas "explicito en el corpus" / "mi inferencia es")
- [x] Admite no saber cuando corpus no lo tiene (query de control Champions 2026 pasada)
- [x] Cross-reference entre videos + lateral search hacia conceptos adyacentes

### Queries de evaluacion ejecutadas

1. **Sintesis compleja (5 puntos, epistemicamente marcados):** "mito moderno en la cultura contemporanea (Lovecraft, superheroes, ciencia ficcion, cine)" → Ariadna construyo tesis escalonada citando 10+ videos (Fight Club ausente en esta pasada; ver hallazgo abajo), separando explicito de inferencia, declarando un hueco ("economia cultural del mito como mercancia")
2. **Query de control (fuera de corpus):** "penalti al rebote Champions 2026" → admitio "no encuentro pieza explicita", busco lateral ("cambios de criterio retroactivos"), encontro piezas adyacentes reales y marco su inferencia como tal

### Hallazgos y caveats documentados

- **Recall lateral mejorable:** en la sintesis inicial Ariadna NO cito Fight Club (0.506) ni T5x06 Anime/Warhammer (0.496) pese a que encajaban en "critica al consumismo/posindustrial". Busco solo terminos literales del prompt. Fix propuesto: añadir al system prompt instruccion de busquedas adyacentes antes de declarar huecos.
- **Scores BGE-M3 en este corpus:** rango util 0.35-0.75. "Buen match" >=0.55, "tangencial" 0.45-0.55, "ruido" <0.45. Query sin cobertura real (Champions 2026) devolvio top-5 entre 0.51-0.56 — son matches formales con "canal Proxy" (intros de streams), no match semantico. Posible mejora: threshold >=0.50 en search_corpus antes de devolver al LLM.
- **Citas verificadas:** Poker de Señoros (0.5508) y DANA (0.4307) citadas por Ariadna como adyacentes → existen en corpus con contenido que justifica la analogia. Cero alucinacion en las 2 muestras verificadas.

### Bugs conocidos tras validacion

- **Citation rendering del plugin v2.0.0-rc6:** tokens internos de Responses API (`citeturn0search2`, `【turnN...】`) se filtran como texto plano en el chat en vez de renderizarse como links. El plugin tiene parser para annotations `url_citation` estructuradas pero no filtra las inline. Workaround: endurecer system prompt para forzar SOLO markdown `[titulo](url)` explicito. Reportable en el repo cuando haya tiempo.
- **MCP client not connected (false positive):** tras cambios de config en el agente puede aparecer este error en una invocacion aunque toda la cadena este OK. Fix: Clear Cache + Refresh Tools en System Console → Agents → Tools. Si persiste, toggle del servidor MCP off/on.

### Si algo falla a futuro

- **No invoca tools:** subir modelo de `gpt-5.4-mini` a `gpt-5.4` full; verificar Reasoning enabled y Responses API verdadero
- **Respuestas genericas:** endurecer prompt Ariadna con instruccion explicita "DEBES invocar search_corpus para cualquier pregunta sobre el canal"
- **Error de conexion:** ngrok puede haber rotado URL. Reiniciar tunel, actualizar URL en MCP Server 1, refresh tools
- **Timeouts:** verificar que el servidor local sigue corriendo (terminal 1)

---

## System prompt final para Ariadna

Ya incluido en [INTEGRACION_MATTERMOST.md](./INTEGRACION_MATTERMOST.md#paso-4--actualizar-el-prompt-de-ariadna). Pegarlo tal cual en System Console → Agents → Ariadna → Instrucciones personalizadas si aun no se hizo.

Puntos clave del prompt:
1. Usar tools siempre que la query toque el corpus
2. Citar fuentes con URL + timestamp clicables
3. Tres niveles de confianza (corpus / general / propia) marcados explicitamente
4. Cross-reference activo entre videos
5. Admitir no saber si corpus no devuelve resultados

---

## Fases futuras

### Fase B — Entity index (opcional, si Layer 1 no basta)

- Enriquecer `vocabulary.json` con entidades extraidas + aliases
- Tabla SQLite de co-ocurrencias (entidad, chunk_id, weight)
- Nuevas tools MCP:
  - `list_concept_occurrences(concept, include_aliases)`
  - `cross_reference(concept_a, concept_b)`
  - `get_related_concepts(concept, top_n)`

### Fase C — Despliegue Hetzner (opcion B del plan inicial)

Migrar a servidor separado en Hetzner:
- Servidor ligero (Qdrant + MCP server, sin GPU) — BGE-M3 en CPU para query encoding (~200-500ms, aceptable)
- Indexado sigue corriendo local (RTX 3080)
- Sync: comprimir Qdrant + rsync tras re-indexado
- URL fija (subdominio propio) en vez de ngrok
- Auth: bearer token en header

### Fase D — Cold path (Claude Code overnight)

- Cola SQLite con jobs
- Worker cron nocturno: `claude -p` headless para analisis profundos
- Tool MCP `enqueue_deep_analysis(description, sources)`
- Resultados a Obsidian vault + webhook notification

### Fase E — LLM Wiki compilation

- Paginas concepto sintetizadas desde cold path
- Estructura tipo Second Brain: `entities/`, `concepts/`, `synthesis/`
- Compatible con Obsidian (wikilinks)
- Tool MCP `get_concept_wiki(concept)`

---

## Quirks y troubleshooting conocidos

1. **Mattermost headers vacios:** si se añade una fila sin nombre, falla con `invalid header field name ""`. Solucion: borrar fila completa.

2. **ngrok free plan:** URL cambia en cada restart. Hay que actualizar Server URL en Mattermost y refresh tools. Alternativa Hetzner: URL fija.

3. **`/mcp` suffix:** la URL que se pega en Mattermost debe terminar en `/mcp`. Sin eso no encuentra el endpoint.

4. **sentence-transformers warning:** `get_sentence_embedding_dimension` esta deprecated → usar `get_embedding_dimension` en siguiente iteracion.

5. **Modelo `gpt-5.4-mini`:** OK para evaluacion. Si invoca tools pobremente, subir a full. `Use Responses API: verdadero` ayuda con tool-chaining.

6. **FastMCP stateless:** activado (`stateless_http=True`) para simplicidad. Cada request es independiente. Si en el futuro necesitas streaming/SSE largos, cambiar a `stateless_http=False`.

7. **Qdrant embedded:** path `data/qdrant/`. Solo un proceso puede abrirlo a la vez (`.lock` file). No lanzar indexador y server concurrentemente. Si un proceso Python crashea dejando el `.lock` huerfano, borralo manualmente (`rm data/qdrant/.lock`) antes de relanzar. **Consulta en paralelo sin parar server:** usa la funcion bash `ariadna-q` (ver Comandos utiles) que habla HTTP al servidor MCP ya corriendo — el mismo singleton sirve CLI y MCP sin lock conflict.

8. **ngrok snap + kill -9 denegado:** si ngrok corre como snap (confinado), ni `kill -9` ni `sudo kill -9` pueden matarlo desde fuera del namespace snap. Opciones: cerrar la terminal donde se lanzo, `sudo snap restart ngrok`, o reiniciar la maquina. Si el proceso sigue vivo y el tunel expone el puerto correcto, no hace falta matarlo — se puede reusar.

9. **Plugin Mattermost Agents v1.x vs v2.x:** el selector per-tool de aprobacion (Auto Run DM / Everywhere / Ask) solo existe a partir de v2.0.0-rc1 (2026-04-14). En v1.x el comportamiento es `ask` hardcoded — haria inviable el UX. El upgrade es in-place, plugin ID `mattermost-ai` invariante, pero v2 cambia defaults (MCP enabled, Responses API por defecto) y migra config a BD.

10. **Citation tokens `turn0searchN` filtran cruds:** bug del plugin v2.0.0-rc6 con citas de Responses API. Workaround en prompt del agente: forzar formato markdown `[titulo](url)` explicito y prohibir tokens internos.

11. **"MCP client not connected" false positive:** tras reconfigurar el agente puede aparecer aunque la cadena funcione. Fix: Clear Cache + Refresh Tools en pestaña Tools, o toggle del servidor MCP off/on/Save.

---

## Comandos utiles

```bash
# Entrar al proyecto
cd <PROJECT_ROOT>
source .venv/bin/activate

# Re-indexar
python -m ariadna.build_index --recreate

# Dry-run de parseo (sin embeddings)
python -m ariadna.build_index --dry-run

# Buscar desde CLI
python -m ariadna.search "mi query" --top-k 5
python -m ariadna.search "query" --category "psicología" --json

# Arrancar servidor (foreground)
./scripts/run_server.sh

# Arrancar servidor (background con log)
python -m ariadna.mcp_server --warm > /tmp/ariadna.log 2>&1 &

# Exponer via ngrok (otra terminal)
./scripts/run_tunnel.sh

# Matar servidor
pkill -f "ariadna.mcp_server"

# Test MCP list tools (manual)
curl -s -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Test MCP call tool (manual)
curl -s -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_corpus","arguments":{"query":"hieros gamos","top_k":3}}}'
```

### Consultar en paralelo sin bloquear el servidor

El CLI `python -m ariadna.search` abre Qdrant directamente → si el server MCP esta corriendo, da lock error. Alternativa: consultar por HTTP al propio servidor (mismo singleton, sin conflicto). Pegar en `~/.bashrc`:

```bash
ariadna-q() {
  local query="${1:?Uso: ariadna-q \"query\" [top_k]}"
  local top_k="${2:-5}"
  curl -s -X POST http://127.0.0.1:8765/mcp \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"search_corpus\",\"arguments\":{\"query\":\"${query}\",\"top_k\":${top_k}}}}" \
    | sed -n 's/^data: //p' \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); [print(f"[{i+1}] score={r[\"score\"]:.3f}  {r[\"category\"]}\n    {r[\"video_title\"]}  [{r[\"timestamp\"]}]\n    {r[\"theme\"]}\n    → {r[\"youtube_url\"]}\n") for i,r in enumerate(d["result"]["structuredContent"]["result"])]'
}
```

Uso:
```bash
ariadna-q "hieros gamos" 3
ariadna-q "sombra junguiana en Peter Pan"
```

---

## Para continuar la sesion

Si abres este proyecto en una nueva conversacion de Claude Code, pega este mensaje inicial:

> Soy el mismo usuario. Fase A Sprint 1 de Ariadna **cerrada** (validacion en DM completada con calidad notable, criterios todos cumplidos). Infraestructura: MCP server Python + ngrok + Mattermost plugin Agents v2.0.0-rc6 con tools en Auto Run (DM). Lee `docs/SESSION_CONTEXT.md` para contexto completo (especial atencion a la seccion "Validacion calidad — RESULTADOS" y "Quirks" 9-11 sobre el upgrade del plugin y bugs conocidos). Diseño arquitectonico completo en `../ProxySummaries/docs/knowledge-architecture-research.md`. Proxima decision abierta: atacar Fase B (entity index para mejorar cross-reference), Fase C (despliegue Hetzner con URL fija, quita ngrok), o mejoras incrementales sobre Layer 1 (sparse retrieval BM25, threshold de score, prompt reforzado con busqueda lateral).
