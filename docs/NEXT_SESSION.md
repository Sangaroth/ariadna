# Prompt de continuidad — Ariadna

> **Cómo usar este archivo:** copia la sección "Prompt para pegar al iniciar nueva sesión" tal cual al asistente al abrir nueva conversación de Claude Code en este repo. El asistente leerá los docs referenciados y arrancará alineado con el estado actual.
>
> **Última actualización:** 2026-04-30 (tras migración a typed relations + cite_markdown fix)

---

## Prompt para pegar al iniciar nueva sesión

```
Soy el mismo usuario. Continuamos el proyecto Ariadna (servidor MCP de RAG sobre
corpus YouTube del canal Proxy, integrado con Mattermost via plugin Agents
v2.0.0-rc6 + ngrok).

Estado al 2026-04-30 (final del día):
- Fase A Sprint 1 CERRADA
- Wiki estructurada: 11 páginas + grafo TIPADO (relations[] en frontmatter)
- relation_types.json v2.0.0 con 28 types canónicos + inversos
- Modo híbrido OPERATIVO en servidor: search_corpus devuelve wiki_pages +
  raw_chunks + retrieval_metadata. Nueva tool get_wiki_page para cross-ref
- cite_markdown pre-renderizado en raw_chunks (mitiga bug citeturn del
  Responses API + plugin Mattermost; arregla parcial — pendiente test final)
- Línea de cobertura sistemática del corpus diseñada y documentada,
  pero LATENTE — pausamos hasta evaluar impacto del modo híbrido en
  queries reales

ANTES DE HACER NADA, lee en este orden:
1. docs/SESSION_CONTEXT.md — estado infra (Mattermost, ngrok, MCP server)
2. docs/NEXT_SESSION.md — este archivo, resumen ejecutivo + próximos pasos
3. docs/CORPUS_COVERAGE_STRATEGY.md — el cambio de enfoque para escalar
   wiki (latente, infraestructura lista)
4. docs/RESPONSE_FLOW.md — los 4 ejemplos del modo híbrido (validados con
   datos reales en sesión del 2026-04-29 — ver "Validación end-to-end" abajo)
5. wiki/_meta/wiki_control.json — registro de páginas compiladas
6. wiki/_meta/coverage_state.json — estado del pipeline de cobertura
   (latente; pipeline_state.phase = "not_started")

Verifica al inicio:
- Si servidor MCP local sigue vivo (ss -tlnp | grep 8765)
- Si la URL ngrok actual coincide con la registrada en SESSION_CONTEXT
- Si la wiki está indexada en Qdrant (count debería ser ~6047 = 6036 raw + 11 wiki):
    curl -s -X POST http://127.0.0.1:8765/mcp \
      -H 'Content-Type: application/json' \
      -H 'Accept: application/json, text/event-stream' \
      -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_corpus","arguments":{"query":"sombra junguiana","top_k":2}}}' \
      | sed -n 's/^data: //p' | python3 -m json.tool | head -30

Pregúntame qué línea quiero retomar antes de proponer trabajo nuevo.
Las opciones están en la sección "Próximas opciones" de docs/NEXT_SESSION.md.
```

---

## Estado actual (resumen ejecutivo)

| Componente | Estado | Notas |
|---|---|---|
| **Layer 0** RAG dense BGE-M3 + Qdrant | ✅ Producción | 6036 chunks raw |
| **Layer 1** Wiki markdown | 🟢 11 páginas | 5 piloto + 5 batch 2 + 1 batch 3 (mito-polar) |
| **Layer 1.5** Wiki vectorizada en Qdrant | ✅ Operativo | 11 wiki_pages, 1 vector focal por página, `source_type=wiki_page` |
| **Layer 2** Grafo tipado (relations[]) | ✅ NUEVO 2026-04-30 | 71 relaciones tipadas; 0 errores validación; 14 wikilinks rotos como warnings |
| **Modo híbrido en MCP** | ✅ Operativo | `search_corpus` → `{wiki_pages, raw_chunks, retrieval_metadata}` con `mode_recommended` |
| **Tool get_wiki_page** | ✅ Operativo | Lee `.md` desde filesystem por `page_id` |
| **cite_markdown en raw_chunks** | 🟡 Parcial | Mitiga citeturn pero plugin sigue mostrando como `citeTitulo (mm:ss)` no clicable |
| **Ranking determinista** | ✅ Operativo | `scripts/rank_wiki_candidates.py` |
| **Validador del grafo** | ✅ NUEVO 2026-04-30 | `scripts/validate_wiki_relations.py` (errores + warnings) |
| **Estrategia cobertura corpus** | 📋 Documentada | Línea B latente, ver §"Próximas opciones" |
| **Fase C** despliegue Hetzner | ⏸️ Pendiente | Independiente |
| **Fase D** cold path workers | ⏸️ Diseñado | Prerrequisito para escalar wiki >50 páginas |

---

## Validación end-to-end del modo híbrido (2026-04-29)

4 queries de prueba contra `http://127.0.0.1:8765/mcp` tras indexar la wiki:

| Test | Query | mode_recommended | wiki_top | raw_top | Resultado |
|---|---|---|---|---|---|
| 1 | "explícame el arquetipo de la sombra junguiana" | `wiki_dominant` | 0.698 | 0.523 | shadow-archetype domina, raw aporta verificación |
| 2 | "qué vídeos hay del canal sobre Tolkien" | `raw_with_warning` | 0.415 | 0.585 | warning explícito; raw devuelve videos reales (Tolkien/dragones, Silmarillion, Excalibur) |
| 3 | `get_wiki_page("mito-polar")` | n/a | n/a | n/a | 10726 chars devueltos correctamente |
| 4 | "cómo conecta sombra con consumismo" | `balanced` | 0.580 | 0.506 | wiki devuelve los 3 conceptos cruzados con `related_concepts` navegables |

**Comportamiento esperado:** los `mode_recommended` se generan correctamente según los thresholds (wiki≥0.65 → dominant; wiki<0.55 → raw_with_warning; intermedio → balanced). Los wikilinks salientes en `related_concepts` permiten al LLM hot decidir si necesita una segunda llamada `get_wiki_page` para cross-reference.

**Pendiente de validación:** uso real desde Mattermost. El system prompt del agente Ariadna NO se ha actualizado todavía — sigue esperando lista plana. Próxima sesión: añadir instrucción en el prompt para que el LLM hot use el modo híbrido correctamente.

---

## Cambios de código

### Sesión 2026-04-30 (typed relations + cite_markdown fix)

| Archivo | Cambio |
|---|---|
| `wiki/_meta/relation_types.json` | v2.0.0 — schema completo: 28 types canónicos con descripción, from/to, inverse. Incluye `contains/contained_in`, `inverts/inverted_by`, `process_of/has_process` añadidos para capturar relaciones reales del corpus |
| `wiki/concepts/*.md`, `wiki/authors/*.md`, etc. | Las 11 páginas migradas: `related_concepts/related_authors/related_works` REEMPLAZADOS por `relations[]` tipadas con `{type, to, [citations], [note], [weight]}`. Cuerpo intacto |
| `scripts/validate_wiki_relations.py` | NUEVO — valida coherencia: type en JSON canónico, page_id sintáctico, presencia de `relations[]`, ausencia de campos legacy. Warnings: wikilinks rotos, from/to inesperados, drift cuerpo↔frontmatter |
| `scripts/index_wiki_to_qdrant.py` | Refactor: `relations[]` reemplaza buckets antiguos en payload Qdrant. Nuevos campos en payload: `relations`, `relation_targets` (sorted set de `to`), `relation_types_present` (sorted set de `type`) — habilitan filtros tipo "todas las páginas que `developed_by: jung-carl-gustav`" |
| `ariadna/search.py` | `cite_markdown` pre-renderizado en `SearchResult.to_compact_dict()` para mitigar bug citeturn del Responses API |
| `ariadna/mcp_server.py` | Descripción de `search_corpus` instruye al LLM a copiar `cite_markdown` literalmente |

### Sesión 2026-04-29 (modo híbrido + ranking determinista)

| Archivo | Cambio |
|---|---|
| `ariadna/storage.py` | Añadido `must_not_filters` a `search()`. Nuevo método `delete_by_filter()` |
| `ariadna/search.py` | Nuevo `Searcher.search_hybrid()` + helper `_wiki_payload_to_compact()`. Thresholds como atributos de clase. `Searcher.search()` ahora excluye `wiki_page` por defecto (compatibilidad CLI) |
| `ariadna/mcp_server.py` | `search_corpus` refactorizada: devuelve `dict` híbrido (NO lista plana). Nueva tool `get_wiki_page(page_id)` |
| `scripts/index_wiki_to_qdrant.py` | NUEVO — indexa wiki como 1 vector focal por página, idempotente vía `delete_by_filter({source_type: wiki_page})` |
| `scripts/rank_wiki_candidates.py` | NUEVO — ranking determinista de candidatos (recurrence + connectivity + domain_diversity) |

**Decisión arquitectónica clave:** la wiki se vectoriza con **1 vector focal por página** (canonical_name + aliases + dominio + primer párrafo de Definición/Perfil + related_concepts). Razón: vectores difusos del cuerpo entero pierden precisión semántica del concepto; el focal captura "qué es X" sin diluirse con manifestaciones, lagunas, fuentes. Iteración futura si hace falta granularidad fina: añadir vectores de sección con `embedding_role: section`.

---

## Decisiones de la sesión (resumen ordenado)

1. **Limpieza de meta-proceso**: las páginas wiki tenían secciones "## Identificación del proceso" y "## Fuentes raw usadas (chunk_ids)" — ruido para lector enciclopédico. Eliminadas en cleanup automático (~18KB removidos). Frontmatter conserva trazabilidad técnica
2. **Ranking determinista** (`scripts/rank_wiki_candidates.py`): primer batch SIN selección humana. Identificó 1 viable (mito-polar). Se compiló estricto.
3. **Crítica del usuario al ranking**: "priorizar por avg_score temático filtra temas centrales, no documenta corpus". 288 videos contienen mil temas, autores, obras. Un video monográfico sobre "reflejo de orientación" tiene mucho peso pero pocos chunks → nunca pasa el filtro.
4. **Nuevo enfoque (LATENTE)**: cobertura combinada — universo de candidatos = entidades extraídas de cada summary.md + wikilinks rotos. Filtros declarativos (`topic_filters.json`) descartan bloques irrelevantes (actualidad política, etc.). Ranking pasa a priorizar orden, no filtrar. Detalle en `docs/CORPUS_COVERAGE_STRATEGY.md`.
5. **Pivote a modo híbrido ANTES de escalar wiki**: para evaluar impacto de las 11 páginas en queries reales antes de invertir en alimentar más wiki. Implementado y validado end-to-end. Líneas A (híbrido) y B (cobertura) son ortogonales.

---

## Backlog técnico (TODOs centralizados)

> **Único sitio para anotar pendientes técnicos.** No crear listas dispersas en otros docs ni TODOs inline en código. Si una idea aparece en discusión y no se ejecuta hoy, va aquí. Reorganizar/cerrar entradas en cada commit.

### Bloqueante / siguiente sesión

- [ ] **Re-indexar wiki en Qdrant** — los payloads cambiaron tras la migración a `relations[]`. Sin re-indexar, el modo híbrido sigue devolviendo `related_concepts/authors/works` antiguos. Comando: `pkill -f ariadna.mcp_server && python scripts/index_wiki_to_qdrant.py && nohup python -m ariadna.mcp_server --port 8765 --warm > /tmp/ariadna.log 2>&1 &`
- [ ] **Validar prompt de Ariadna actualizado en Mattermost** — pegar prompt nuevo (con instrucciones de `cite_markdown` literal), Refresh Tools, probar query "mito polar". Confirmar si los tokens `citeTitulo (mm:ss)` desaparecen y aparecen markdown links clicables
- [ ] **Si tokens persisten:** Plan B documentado — subir modelo de `gpt-5.4-mini` a `gpt-5.4` full en Mattermost (System Console → Agents → Ariadna → AI Service)

### Mejoras al modo híbrido (decidir tras observar uso real)

- [ ] **Tunear threshold `WIKI_DOMINANT_SCORE` (actualmente 0.65)** — observado en sesión: `mito-polar` cae al filo (0.658). Si en uso real se ven `balanced` cuando deberían ser `wiki_dominant`, bajar a 0.60. Vive en `ariadna/search.py:Searcher.WIKI_DOMINANT_SCORE`
- [ ] **`top_k_wiki` default = 1 en lugar de 2** — para queries focales, los wiki_pages 2 y 3 suelen ser ruido. Probar bajarlo en `mcp_server.py:search_corpus`
- [ ] **Threshold mínimo de wiki_score para incluir** — si `wiki_score < 0.50`, no devolver esa página. Filtrar antes de pasar al LLM
- [ ] **Pre-computar `in_wiki_sources` en raw_chunks** — actualmente `null`. Implementación: regex sobre body de cada wiki_page buscando `youtu\.be/<id>\?t=(\d+)`, guardar en payload `raw_chunks_referenced`. Habilita drift detection automática (top-raw NO en wiki = wiki stale) y evita duplicar citas en respuestas
- [ ] **Plan C UX: quitar `youtube_url` del payload de raw_chunks** — dejar solo `cite_markdown`. Sin URL como string separado, el modelo no puede invocar el sistema de annotations del Responses API. Documentado pero no ejecutado todavía (esperar resultados del Plan B antes)

### Granularidad de la wiki indexada

- [ ] **Vectores de sección con `embedding_role: section`** — solo si en uso real se observa que queries sobre subsecciones (ej. "ánima sola" dentro de `anima-archetype`) NO recuperan la página. Iteración futura

### Línea B — cobertura sistemática del corpus (LATENTE)

Toda la infra documentada y stub:
- `docs/CORPUS_COVERAGE_STRATEGY.md` (estrategia)
- `wiki/_meta/topic_filters.json` (filtros declarativos seed)
- `wiki/_meta/coverage_state.json` (esqueleto del estado)

Cuando se active:
- [ ] `scripts/inventory_summaries.py` — popular `coverage_state.inventory.videos[]` desde `<PROXYSUMMARIES_ROOT>/data/playlists/`
- [ ] `scripts/extract_video_themes.py` — parsear summaries por bloques temáticos, LLM-extractor produce candidatos `{page_id, source_video, dominant_concept}`, aplicar topic_filters, acumular en `coverage_state.candidates`
- [ ] Refactor de `scripts/rank_wiki_candidates.py` — universo = candidates de coverage_state (no wikilinks rotos); pasar de filtrar a priorizar
- [ ] Cold path real (Fase D — ariadna NO tiene infra todavía): cola SQLite + workers asíncronos. Prerrequisito antes de procesar 288 videos

### Heurística de tipado retrospectivo del grafo

- [ ] **Re-leer páginas con `review_status: human_reviewed`** y enriquecer `relations[]` con citations, weights y notes más finas. Las páginas actuales tienen relaciones tipadas pero sin citations explícitas en muchos casos
- [ ] **Wikilinks rotos en relations actuales** (catálogo del validador): `mito-solar`, `mito-lunar`, `peter-pan-1953-film`, `matrix-1999-film`, `man-of-steel-2013-film`. Compilar al menos los más demandados (mito-solar/lunar/peter-pan están referenciados desde 3+ páginas)

### Despliegue / ops

- [ ] **Fase C — despliegue Hetzner**: quitar ngrok, URL fija, multi-cliente. Independiente, en cualquier momento. La indexación de wiki + lock de Qdrant ya está pensada para sync rsync desde local
- [ ] **Reportar bug al plugin Mattermost Agents v2.0.0-rc6** sobre tokens `citeturn0...` no parseados a markdown — bug raíz del problema de UX que estamos rodeando con `cite_markdown` precomputado

### Calidad / observabilidad del wiki

- [ ] **Política de promoción de relation types nuevos** — cuando el extractor (Fase D) proponga types fuera del set canónico, anotarlos en `wiki/_meta/relation_types_proposed.json`. Documentado en relation_types.json policy_notes pero el flujo no está implementado
- [ ] **`scripts/validate_wiki_relations.py --strict` en CI** cuando haya CI configurado — para impedir merge de páginas con campos legacy o types inválidos

---

## Próximas opciones

### A — Validar modo híbrido en Mattermost real ⭐ (recomendado)

Pasos concretos:

1. **Verificar URL ngrok**: la wiki indexada está disponible solo si Mattermost apunta al server actual. Verificar en System Console → Agents → MCP Servers que la URL de Server 1 coincida con `pgrep -af ngrok`.
2. **Refresh tools** en Mattermost (Agents → Tools): el contrato de `search_corpus` cambió (devuelve `dict`, no `list`), y aparece una tool nueva `get_wiki_page`. Sin refresh, Mattermost usa schema cacheado.
3. **Actualizar system prompt de Ariadna**: añadir instrucción para usar el modo híbrido. Sugerencia:

   > "search_corpus devuelve `{wiki_pages, raw_chunks, retrieval_metadata}`. Si `retrieval_metadata.mode_recommended == 'wiki_dominant'`, apóyate principalmente en la síntesis de wiki_pages[0].body y cita los raw_chunks como verificación. Si es 'raw_only' o 'raw_with_warning', usa raw_chunks como fuente principal y traslada el warning al usuario. Para cross-reference profunda, usa `get_wiki_page(page_id)` con un page_id de `related_concepts`."

4. **Queries de evaluación** (las mismas que en validación end-to-end pero desde Mattermost DM):
   - "Explícame el arquetipo de la sombra" → debería citar shadow-archetype como síntesis
   - "Cómo conecta sombra con consumismo" → debería navegar wikilinks (posible 2da llamada a `get_wiki_page`)
   - "Qué vídeos hay sobre Tolkien" → debería usar raw, declarar que no hay wiki para Tolkien
   - "Qué dice del reflejo de orientación" (test del caso de la crítica) → ver si el modo híbrido encuentra el material aunque no haya wiki
5. **Documentar observaciones**: anotar en este archivo (sección nueva) los hallazgos: ¿el LLM usa correctamente `mode_recommended`? ¿cita las wiki como fuentes válidas? ¿el cross-reference vía `get_wiki_page` se invoca?

**Beneficio:** datos reales para decidir si hace falta granularidad fina (vectores de sección) o si el modo focal basta. Y para validar si el modo híbrido aporta valor antes de alimentar más wiki.

### B — Iterar wiki por cobertura del corpus

Línea documentada y latente. Solo arrancarla si A demuestra que la wiki sí aporta valor diferencial.

Pasos ordenados (todo pendiente):
1. `scripts/inventory_summaries.py` → poblar `coverage_state.inventory.videos[]` desde `<PROXYSUMMARIES_ROOT>/data/playlists/`
2. `scripts/extract_video_themes.py` → para cada video sin procesar, parsear summary, extraer entidades canónicas, aplicar topic_filters
3. Refactor de `rank_wiki_candidates.py` → consumir `coverage_state.candidates` en lugar de wikilinks rotos; pasar de filtrar a priorizar
4. Cold path real (Fase D) — workers asíncronos para procesar 288 videos sin saturar la sesión interactiva

Detalle completo en [`docs/CORPUS_COVERAGE_STRATEGY.md`](CORPUS_COVERAGE_STRATEGY.md).

### C — Despliegue Hetzner (Fase C)

Quitar ngrok, URL fija, multi-cliente. Independiente, en cualquier momento. La indexación de wiki + lock de Qdrant ya está pensada para sync rsync desde local.

### D — Sprint 2: mejoras Layer 1 RAG

Sparse BM25 (ayuda con nombres propios — Tolkien actual mejoraría), reranker cross-encoder, threshold de score. Beneficio incremental sobre raw_chunks; ortogonal al modo híbrido.

---

## Comandos clave (actualizados)

```bash
# Setup sesión
cd /home/dae/PycharmProjects/ariadna && source .venv/bin/activate

# Verificar infraestructura
ss -tlnp 2>/dev/null | grep 8765        # MCP server vivo?
pgrep -af ngrok                          # túnel vivo?

# Levantar (parar otro server primero — Qdrant lock)
pkill -f "ariadna.mcp_server"
nohup python -m ariadna.mcp_server --port 8765 --warm > /tmp/ariadna.log 2>&1 &

# Re-indexar wiki en Qdrant (server debe estar parado)
python scripts/index_wiki_to_qdrant.py --dry-run   # verifica parsing
python scripts/index_wiki_to_qdrant.py             # indexa

# Re-ejecutar ranking (server debe estar VIVO; el script lee Qdrant via MCP HTTP)
python scripts/rank_wiki_candidates.py

# Test modo híbrido (server vivo)
curl -s -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_corpus","arguments":{"query":"hieros gamos","top_k":3,"top_k_wiki":2}}}'

# Test get_wiki_page
curl -s -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_wiki_page","arguments":{"page_id":"shadow-archetype"}}}'

# Listar tools registradas
curl -s -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

---

## Quirks vivos al 2026-04-29

1. **search_corpus rompe contrato anterior**: ahora devuelve `dict`, no `list`. El plugin Mattermost ve el cambio en el siguiente "Refresh Tools".
2. **CLI `ariadna-search` excluye wiki por defecto** (compatibilidad). Si quieres wiki via CLI, hay que crear un nuevo entry point o usar curl directo.
3. **Lock Qdrant embedded**: indexar wiki requiere parar el server (mismo lock que para `ariadna-index`). Documentado en SESSION_CONTEXT quirk 7.
4. **Server arranca en 8080 sin --port**: config.py default es 8080; run_server.sh override a 8765. Si lanzas con `nohup python -m ariadna.mcp_server`, **siempre añade `--port 8765`**.
5. **`in_wiki_sources` siempre `null`**: el campo está reservado en el schema (RESPONSE_FLOW.md §2.4) pero el indexador actual no extrae los chunk_ids del cuerpo de la wiki para emparejarlos. TODO de iteración futura — habilita drift detection automática.

## Si encuentras algo confuso

- Memoria persistente: `~/.claude/projects/-home-dae-PycharmProjects-ariadna/memory/`
- Diseño arquitectónico completo upstream: `../ProxySummaries/docs/knowledge-architecture-research.md`
- Repo público: https://github.com/sangaroth-ux/ariadna
