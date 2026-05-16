# Prompt de continuidad — Ariadna

> **Cómo usar este archivo:** copia la sección "Prompt para pegar al iniciar nueva sesión" tal cual al asistente al abrir nueva conversación de Claude Code en este repo. El asistente leerá los docs referenciados y arrancará alineado con el estado actual.
>
> **Última actualización:** 2026-05-16 madrugada (sesión maratón: fixes pipeline + spec multi-tenancy aprobada + plan implementation Chunk 1 + agente cron programado 05:30). Doc maestro del refactor en marcha: [`docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md`](superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md).

---

## Prompt para pegar al iniciar nueva sesión

```
Soy el mismo usuario. Continuamos el proyecto Ariadna (servidor MCP de RAG
sobre corpus YouTube del canal Proxy, integrado con Mattermost via plugin
Agents v2.0.0-rc6 + ngrok).

Estado al 2026-05-16 (madrugada — sesión maratón cerrada):

ÚLTIMO TRABAJO HECHO HOY (sesión que terminó ~04:25):
1. Reparado venv tras retirada de python3.13 del sistema (uv sync → 3.13.7
   uv-managed; uv.lock ahora versionado)
2. Bug fix CRÍTICO de parser relations[]: 3 scripts (build_wiki_db,
   validate_wiki_relations, index_wiki_to_qdrant) usaban regex que solo
   matcheaba flow YAML inline `- {type:X, to:Y}`. Las 162 páginas escritas
   en block YAML estándar (yaml.safe_dump del sub-agente) se ignoraban
   silenciosamente → grafo tipado congelado en 11 seed durante 2 semanas.
   Fix: yaml.safe_load. Resultado: 71 → 1102 relations en SQLite.
   Reindexed Qdrant (494 vectores wiki).
3. Feature policy_filter tag-and-keep: build_index ahora lee
   blocks_filtered_by_topic_filters del per-video JSON y propaga
   `policy_filter` al payload Qdrant; search.py por defecto excluye
   tagged via IsEmptyCondition; nuevo kwarg `include_filtered=False`
   en search_corpus MCP tool. 18 chunks tagged hoy. Resuelve asimetría
   Layer 0 vs Layer 1 (la wiki descartaba politiqueo pero los chunks
   raw aparecían en searches semánticos).
4. Brainstorming + spec multi-tenancy COMPLETO (Project como unidad
   atómica: scope + wiki + cola). Spec aprobada en 3 iteraciones de
   spec-document-reviewer. 858 líneas. Cubre Fase 1 (migración) y
   Fase 2 (tools MCP de cola). Workers son specs futuras.
5. Plan implementation arrancado: Chunk 1 escrito (pre-migration tooling:
   capture_baseline + verifier skeletons) aprobado por plan-reviewer.
   Chunks 2-9 PENDIENTES.

WIKI ACTUAL:
- 183 páginas (concepts 61, authors 12, entities/works 65, synthesis 43,
  entities/institutions 0)
- data/wiki.db con 183 pages, 1102 relations, 1361 body_wikilinks,
  3201 citations (refrescado)
- Qdrant: 6442 puntos = 6259 raw_chunks + 183 wiki_pages focal vectors

CORPUS YouTube:
- 322 vídeos en ProxySummaries
- 135-145 procesados en run pilot_sonnet_20260509 (variable según último
  state.json al pararse el run)
- 43 pendientes del universo del run (178 vídeos seleccionados)
- ~88 pendientes del corpus total (Twitch + psicología-101 + algunos
  podcast están a 0% por ahora)
- Run pilot_sonnet_20260509 PARADO esta madrugada (PID 1534814 + sub-agente
  killeados); para retomarlo:
    python scripts/extract_video_themes.py --resume pilot_sonnet_20260509

AGENTE CRON PROGRAMADO (importante):
- A las 05:30 del 2026-05-16 dispara automáticamente
  scripts/resume_plan_chunks_2_9.sh
- Lanza claude -p autónomo con el prompt de
  scripts/agent_resume_prompt.md
- Trabaja en docs/ exclusivamente (escribe Chunks 2-9 del plan de
  implementación multi-tenancy, con review loop por chunk)
- Self-removing del crontab tras ejecutar
- Si te encuentras esto post-05:30, revisa:
    git log --oneline -20
    cat docs/AGENT_HANDOFF_2026-05-16.md      # si terminó OK
    cat docs/AGENT_BLOCKED.md 2>/dev/null      # si se atascó
    tail -200 logs/agent_*.log
- Si pre-05:30 y quieres cancelar: crontab -r

DOCS CLAVE A LEER:
1. docs/NEXT_SESSION.md — este archivo, resumen ejecutivo
2. docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md
   — spec maestra del refactor en curso (sección 12 tabla decisiones cerradas)
3. docs/superpowers/plans/2026-05-16-multi-project-and-research-queue.md
   — plan de implementación (al menos Chunk 1; agente cron añade 2-9)
4. docs/PIPELINE_REFACTOR_2026_05_02.md — pipeline v0.3 (sigue vigente)
5. wiki/_meta/scope.md — alcance editorial
6. wiki/_meta/canonical_whitelist.json

VERIFICACIONES AL ARRANCAR:
- ¿Agente cron terminó? cat docs/AGENT_HANDOFF_2026-05-16.md 2>/dev/null
- ¿Está bloqueado? cat docs/AGENT_BLOCKED.md 2>/dev/null
- Procesos vivos: ps -ef | grep -E "extract_video|claude.*resume.*pilot"
- Wiki size: find wiki -name "*.md" -not -path "*_meta*" | wc -l
- SQLite: python -c "import sqlite3; c=sqlite3.connect('data/wiki.db');
  print(c.execute('SELECT COUNT(*) FROM pages').fetchone(),
        c.execute('SELECT COUNT(*) FROM relations').fetchone())"
- Git history: git log --oneline -20

LÍNEAS DE TRABAJO POSIBLES (pregúntame cuál antes de proponer):
A) Si el agente cron terminó OK con Chunks 2-9 escritos: arrancar
   implementación con executing-plans o subagent-driven-development.
   Antes: spec dice que requiere parar el run de extracción y server
   MCP — pre-flight checks documentados en plan Chunk 1.
B) Si el agente cron se atascó: leer AGENT_BLOCKED.md, desbloquear el
   chunk problemático, continuar.
C) Retomar el run pilot_sonnet_20260509 con --resume si quieres avanzar
   más wiki antes del refactor (43 pendientes).
D) Otra cosa: pregúntame.

Pregúntame qué línea quiero retomar antes de proponer trabajo nuevo.
```

---

## Estado actual (resumen ejecutivo)

| Componente | Estado | Notas |
|---|---|---|
| **Layer 0** RAG dense BGE-M3 + Qdrant | ✅ Producción | 6036 chunks raw |
| **Layer 1** Wiki markdown | 🟢 11 páginas seed | 5 piloto + 5 batch 2 + 1 batch 3 (mito-polar). Crece via barrido push-based |
| **Layer 1.5** Wiki vectorizada en Qdrant | ✅ Operativo | 1 vector focal por página, `source_type=wiki_page` |
| **Layer 2** Grafo tipado (relations[]) | ✅ Operativo | relation_types.json v2.0.0 con 28 types canónicos + inversos |
| **Modo híbrido en MCP** | ✅ Operativo | `search_corpus` con 3 lanes (raw semántica, wiki semántica focal, wiki indirecta vía citations) |
| **Tools MCP** | ✅ 4 tools | search_corpus, get_wiki_page, get_video_summary, list_videos |
| **3ª capa Karpathy** (scope + whitelist) | ✅ NUEVO 2026-05-02 | scope.md v0.2 + canonical_whitelist.json v0.1 |
| **Extract pipeline push-based** | ✅ NUEVO 2026-05-02 | extract_video_themes.py con index slim + Read on-demand. Cache cross-call con `--resume` confirmado |
| **Apply pipeline diff-style** | ✅ NUEVO 2026-05-02 | apply_pending_updates.py con 4 ops + anchor único + auto-commit |
| **Overnight orchestrator** | ✅ NUEVO 2026-05-02 | overnight_run.py con stop crítico + housekeeping git autónomo |
| **Incremental wrapper** | ✅ NUEVO 2026-05-02 | extract_incremental.py + processed_videos.json |
| **Compile pipeline (promote_queue → páginas nuevas)** | ❌ NO implementado | `compile_wiki_pages.py` pendiente. Promote_queue acumula candidatos sin compilar |
| **Validador del grafo** | ✅ Operativo | `scripts/validate_wiki_relations.py` |
| **Cross-encoder reranker** | ✅ Operativo | `scripts/rank_wiki_candidates.py` actualizado al contrato hybrid de search_corpus |
| **Fase C** despliegue Hetzner | ⏸️ Pendiente | Independiente |
| **Fase D** cold path workers | ✅ Implementado parcialmente | overnight_run.py es la primera versión "cold path". markitdown para multi-formato pendiente |

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

### Sesión 2026-04-30 noche (cierre del bloqueante + smoke test + SQLite + retrieval indirecto)

| Archivo | Cambio |
|---|---|
| `ariadna/search.py` | (1) `_wiki_payload_to_compact()` actualizado a esquema `relations[]` (cambio de contrato — campos legacy `related_concepts/authors/works` eliminados del output MCP). (2) **Retrieval indirecto vía citations**: `Searcher.__init__` abre `data/wiki.db` (read-only, fallback grácil si no existe). `_lookup_wiki_via_citations()` para chunks raw con `score >= 0.55`, JOIN contra tabla `citations` para encontrar wiki pages que los citan. `_fetch_wiki_pages_from_db()` construye dicts compactos shape-equivalentes a Qdrant para entradas que solo entraron vía citation. `_merge_wiki_lanes()` funde semántica + citation con flag `match_via: "semantic" \| "citation" \| "both"` y `matched_via_chunks[]` cuando aplica. Sustituye limpiamente la idea descartada de section vectors (cero índice semántico extra). (3) `in_wiki_sources` en raw_chunks ya no es null — se popula desde el mismo lookup. (4) **FIX category-blindness de la lane indirecta**: cuando el LLM/usuario pasa `category` o `playlist`, el filtro se aplica a raw_results visibles pero NO a la "semilla" del citation lookup. `search_hybrid` hace un raw search separado sin filtros para alimentar la lane indirecta. La wiki es category-blind por diseño (taxonomía OpenAlex propia) y debe seguir siéndolo cuando entra vía citations — antes el filtro silenciaba el mecanismo. Bug detectado en producción cuando Ariadna añadió `category="psicología"` a una query sobre psicoanálisis: el chunk citante (Orfeo y Eurídice, categoría "filosofía") quedó fuera, jung-carl-gustav no apareció. Cubierto por nuevo check `citation_survives_category` en smoke test |
| `scripts/test_hybrid.py` | NUEVO + ampliado — smoke test end-to-end del MCP server vivo. 8 checks: tools/list, wiki_primary, raw_with_warning, balanced, **wiki_via_citation** (query "Tarzan se conoce a si mismo a traves de Jane" → jung-carl-gustav surface vía citation), **citation_survives_category** (query con category="psicología" sigue trayendo wiki vía citation aunque el chunk citante esté en otra categoría), **in_wiki_sources poblado**, get_wiki_page. Exit 1 si cualquier check falla |
| `scripts/build_wiki_db.py` | NUEVO — índice SQLite derivado de `wiki/**/*.md` en `data/wiki.db`. Schema: `pages, aliases, relations, body_wikilinks, citations, relation_types_canonical`. Reconstruible (~1s para 11 páginas) — fuente de verdad sigue siendo el filesystem. Cero curación manual del DB. CLI: `--check` (sanity asserts) y `--query backlinks/broken/drift/citations/stats` |
| `.gitignore` | añadidas `data/wiki.db*` |
| Qdrant `data/qdrant/` | 11 wiki_pages re-insertados con esquema `relations[]`. Total colección: 6047 |
| `data/wiki.db` (nuevo) | 11 páginas, 59 aliases, 71 relations, 51 body_wikilinks, 160 citations, 30 relation_types canónicos |

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

## Convenciones de escritura wiki

> **Regla central:** las páginas wiki son **contenido enciclopédico sobre el corpus Proxy**, no diario del proceso de construcción. Cuerpo limpio, sin auto-referencias al sistema RAG ni al pipeline de compilación.

### Vocabulario PROHIBIDO en el cuerpo de las páginas

Estas frases ensucian la página y delatan el proceso de construcción al lector:

- `"este batch"`, `"de este batch"`, `"en este batch"`, `"del batch"`
- `"estos chunks"`, `"los chunks recuperados"`, `"top-15"`, `"top-N"`
- `"discovery via Qdrant"`, `"cold path"`, `"extractor"`, `"summary.md completo"`
- `"Sprint 1"`, `"Sprint 2"`, `"validación previa de Sprint N"`, `"sucesivas iteraciones"`
- `"del piloto"`, `"compilada en batch X"`, `"en el primer batch piloto"`
- `"wikilinks emergente"`, `"el grafo emergente activado"`
- `"este compilado"`, `"este material recuperado"`
- Blockquotes iniciales tipo `> Página piloto compilada via Qdrant...`
- Secciones `## Identificación del proceso (auditable)` o `## Fuentes raw usadas (chunk_ids)` — la trazabilidad vive en frontmatter + `wiki_control.json`, no en el cuerpo

### Cómo reformular lagunas correctamente

Las lagunas deben hablar **del corpus**, no del proceso de extracción:

❌ MAL: *"Fight Club no aparece en el top-15 de este batch pese a ser el caso canónico — el discovery via Qdrant trajo Peter Pan con más fuerza"*
✅ BIEN: *"Fight Club como caso canónico de la sombra apenas se desarrolla en esta página, pese a ser referencia explícita del canal en otros vídeos"*

❌ MAL: *"no aparece en estos chunks"*
✅ BIEN: *"el canal lo menciona en otros vídeos pero no lo sistematiza"* / *"no se desarrolla en el material analizado"*

❌ MAL: *"esta laguna ya fue identificada en validación previa de Sprint 1"*
✅ BIEN: (eliminar la frase — el Sprint es metadata del proceso, no del contenido)

### Qué SÍ va dónde

| Tipo de info | Lugar correcto |
|---|---|
| `compiler`, `last_compiled`, `review_status`, `schema_version` | Frontmatter (no se renderiza como contenido) |
| Métricas de compilación (chunks únicos, top_score, sources_used_count) | `wiki/_meta/wiki_control.json` |
| Razones de descarte de bloques | `wiki/_meta/coverage_state.json:filtered_blocks_log[]` |
| Estado del pipeline de cobertura | `wiki/_meta/coverage_state.json:pipeline_state` |
| Lista de candidatos pendientes y ranking | `wiki/_meta/next_batch_ranking.json` |
| Backlog de pendientes técnicos | esta sección "Backlog técnico" |
| **Cuerpo de las páginas .md** | **Solo prosa enciclopédica + wikilinks contextuales + citas a YouTube. Nada más.** |

### Verificación

```bash
grep -rnE "este batch|del batch|estos chunks|del piloto|Sprint [0-9]|discovery via Qdrant|wikilinks emergente|sucesivas iteraciones|cold path real" wiki/ | grep -v "_meta/\|README\|.obsidian"
```

Cero resultados ⇒ páginas limpias. Cualquier match es deuda técnica a reparar antes del siguiente commit.

---

## Backlog técnico (TODOs centralizados)

> **Único sitio para anotar pendientes técnicos.** No crear listas dispersas en otros docs ni TODOs inline en código. Si una idea aparece en discusión y no se ejecuta hoy, va aquí. Reorganizar/cerrar entradas en cada commit.

### Bloqueante / siguiente sesión

- [x] **Re-indexar wiki en Qdrant** — hecho 2026-04-30 noche tras detectar que el reader `ariadna/search.py:_wiki_payload_to_compact()` devolvía `related_concepts: []` aunque el indexador escribía `relations[]`. Fix: reader actualizado a esquema nuevo (`relations`, `relation_targets`, `relation_types_present`) + 11 wiki_pages re-insertados (total Qdrant = 6047). Smoke test `scripts/test_hybrid.py` cubre regresión: 5/5 verde
- [ ] **Validar prompt de Ariadna actualizado en Mattermost** — pegar prompt nuevo (con instrucciones de `cite_markdown` literal **y** uso de `relations[]` tipadas con `{type, to}` para navegación), Refresh Tools, probar query "mito polar". Confirmar si los tokens `citeTitulo (mm:ss)` desaparecen y aparecen markdown links clicables. **Cambio de contrato:** `wiki_pages[].related_concepts/authors/works` ya no existen — usar `relations[]` o `relation_targets[]`
- [ ] **Si tokens persisten:** Plan B documentado — subir modelo de `gpt-5.4-mini` a `gpt-5.4` full en Mattermost (System Console → Agents → Ariadna → AI Service)

### Mejoras al modo híbrido (decidir tras observar uso real)

- [ ] **Tunear threshold `WIKI_DOMINANT_SCORE` (actualmente 0.65)** — observado en sesión: tras re-indexación con relations[], `sombra junguiana` cae a 0.624 (antes 0.698) porque el embed_text incluye más targets. Si en uso real se ven `balanced` cuando deberían ser `wiki_dominant`, bajar a 0.60. Vive en `ariadna/search.py:Searcher.WIKI_DOMINANT_SCORE`
- [ ] **`top_k_wiki` default = 1 en lugar de 2** — para queries focales, los wiki_pages 2 y 3 suelen ser ruido. Probar bajarlo en `mcp_server.py:search_corpus`
- [ ] **Threshold mínimo de wiki_score para incluir** — si `wiki_score < 0.50`, no devolver esa página. Filtrar antes de pasar al LLM
- [x] **`in_wiki_sources` en raw_chunks vía SQLite** — IMPLEMENTADO 2026-04-30. `Searcher` consulta `data/wiki.db:citations` por `(video_id, timestamp_seconds)` al servir cada raw_chunk. Validado en smoke test: query "sombra junguiana" → 3/5 chunks llevan `in_wiki_sources` poblado (Effy y Proxy, Peter Pan, etc.). Hizo además posible el siguiente, **mucho más potente**:
- [x] **Retrieval indirecto vía citations** — IMPLEMENTADO 2026-04-30. Para chunks raw con score≥0.55, JOIN inverso contra citations: si una wiki page los cita, traerla a `wiki_pages[]` aunque su focal no haya hecho match semántico. Página entra con `match_via="citation"` y `matched_via_chunks[]` listando los chunks citantes. Si la página YA estaba en la lane semántica, se enriquece con `match_via="both"`. **Sustituye a la línea descartada de section vectors** — soluciona el problema "sub-aspecto canónico sin match focal" sin duplicar índice semántico. Validado: query "Tarzan se conoce a si mismo a traves de Jane" → focal de jung-carl-gustav score 0.41 (no entraría), pero el chunk de Análisis arquetípico de Tarzán cita jung → entra a 0.6518
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

# Smoke test end-to-end (server vivo + wiki indexada). Exit 0 = todo verde.
python scripts/test_hybrid.py
python scripts/test_hybrid.py --json   # output máquina-legible

# Índice SQLite derivado (no requiere server). Reconstruible en ~1s.
python scripts/build_wiki_db.py                                # rebuild full
python scripts/build_wiki_db.py --check                        # rebuild + asserts
python scripts/build_wiki_db.py --no-rebuild --query stats     # ranking pages, types, videos
python scripts/build_wiki_db.py --no-rebuild --query backlinks jung-carl-gustav
python scripts/build_wiki_db.py --no-rebuild --query broken    # relations.to no compiladas (= candidatos a próximo batch)
python scripts/build_wiki_db.py --no-rebuild --query drift     # mismatch body↔relations
python scripts/build_wiki_db.py --no-rebuild --query citations svG7uT3Z8Rk

# Test modo híbrido manual (server vivo)
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
3. **Lock Qdrant embedded**: indexar wiki requiere parar el server. Sólo un proceso puede abrir `data/qdrant/` a la vez (ver `.lock`); pkill el server antes de `index_wiki_to_qdrant.py` o `build_index`. Si un crash deja el lock huérfano, `rm data/qdrant/.lock`.
4. **Server arranca en 8080 sin --port**: config.py default es 8080; run_server.sh override a 8765. Si lanzas con `nohup python -m ariadna.mcp_server`, **siempre añade `--port 8765`**.
5. **`in_wiki_sources` ya no es null**: tras la sesión 2026-04-30 noche se popula desde `data/wiki.db:citations`. Lista de page_ids que citan ese chunk; vacía si ninguna. Ver RESPONSE_FLOW.md §10.

## Si encuentras algo confuso

- Memoria persistente: `~/.claude/projects/-home-dae-PycharmProjects-ariadna/memory/`
- Diseño arquitectónico completo upstream: `../ProxySummaries/docs/knowledge-architecture-research.md`
- Repo público: https://github.com/sangaroth-ux/ariadna
