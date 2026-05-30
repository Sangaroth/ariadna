# Prompt de continuidad — Ariadna

> **Cómo usar este archivo:** copia la sección "Prompt para pegar al iniciar nueva sesión" tal cual al asistente al abrir nueva conversación de Claude Code en este repo. El asistente leerá los docs referenciados y arrancará alineado con el estado actual.
>
> **Última actualización:** 2026-05-30 noche (REFACTOR UNIVERSAL — Fases 0–8 COMPLETAS; cross-search proxy+atlas verde. Ver bloque abajo).

---

## 🚧 REFACTOR EN MARCHA: modelo de referencias universal + multi-tenancy (2026-05-30)

**Branch:** `feat/multi-project-universal-model`. **Plan maestro:** `~/.claude/plans/ok-ha-llegado-de-virtual-sifakis.md` (leerlo primero). Specs: `docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md` + `docs/TAXONOMY_PROPOSAL.md` §3.

**Objetivo:** generalizar Ariadna a sistema multi-proyecto con modelo de referencias universal (youtube/paper/pdf/web/blog…) y pipeline centralizado (cola → worker → sumarios → wiki → RAG). Primer proyecto nuevo de prueba: **atlas-teleosemantico** (papers vía DOI con MCP paper-search).

**Decisiones fijadas:** TAXONOMY completo (sources/chunks split + position/position_url + Author entities + dominios OpenAlex); aislamiento TOTAL por proyecto (wiki/chunks/citations/authors con project_id; solo el archivo de fuentes es global); summarizer = módulo nuevo en ariadna; `project` polimórfico `str|list[str]|None` (cross-search a N proyectos, coste cero).

**HECHO y verificado (Fases 0–3, commits b83b8cb→63908bf):**
- **F0** `scripts/capture_baseline.py` + `data/baseline_pre_migration.json` (10 queries vía MCP HTTP) + `verify_phase{1,2}.py` (stubs).
- **F1** `data/ariadna.db` (15 tablas, WAL) poblado: `scripts/{init_ariadna_db,populate_sources_from_proxysummaries,migrate_wiki_db_to_global,populate_authors_from_wiki}.py`. 329 sources, 222 pages, 4570 citations generalizadas (source_id+position JSON), 634 page_domains, 15 authors. Idempotente, reconstruible.
- **F2** `scripts/migrate_raw_chunks_to_universal.py`: payload universal en Qdrant (6259 raw + 222 wiki) vía set_payload SIN re-embed. **Equivalencia funcional preservada (Δscore=0.00000)**. Reclasificación OpenAlex determinista (2049 chunks heredan dominio fino de wiki, cero LLM).
- **F3** Filesystem → `projects/proxy/{wiki,_meta}`; `wiki/_meta/` = global (relation_types_core.json + *_default.* plantillas). `ariadna/project_config.py` (ProjectConfig). 12 ficheros repuntados. test_hybrid 8/8.

**F4 HECHO y verificado (Fase 4 — adaptadores + search generalizado):**
- **`ariadna/sources/{base,registry,youtube,paper}.py`** — `SourceAdapter` Protocol + `Position`/`SourceRecord`/`GenericChunk`/`CitationRef`; `YoutubeAdapter` envuelve parsers.py verbatim; `PaperAdapter` (localización DOI/página completa, adquisición→NotImplementedError F6); `registry.get_adapter(type|scheme|source_id)` + `detect_source_type(url)`.
- **`scripts/verify_adapter_parity.py`**: diff chunk-a-chunk YoutubeAdapter ↔ parsers = **vacío** (304 vídeos, 6483 chunks) + round-trip de citas.
- **`search.py` migrado a ariadna.db**: citation lookup por `(source_id, position_key)` project-scoped (ya NO lee wiki.db); filtro `project_id` polimórfico **str|list|None** (None=todos, valida slugs → `PROJECT_NOT_FOUND`); cada hit (raw+wiki) expone `project_id`; `cite_markdown` universal del payload. `storage.search` soporta filtros lista (MatchAny/OR). Tool MCP `search_corpus` acepta `project`.
- **`build_wiki_db.py --project`**: reconstruye las 9 tablas wiki PER-PROJECT de ariadna.db vía adaptadores (citas universales, JSON compacto idéntico a SQLite) + puebla page_domains/authors desde frontmatter. **Parity: regenerar Proxy = diff vacío** vs migración (pages/aliases/relations/body_wikilinks/page_domains/citations/authors/author_aliases/author_sources, todas idénticas).
- **`index_wiki_to_qdrant.py --project`**: payload universal (`project_id`), id namespaced por proyecto, delete project-scoped. Reindexado en vivo (222 wiki, total 6481).
- **`verify_phase1.py` relleno (16 checks, server PARADO)**: **16/16 ✓** (1 SKIP: extract_themes→F6). functional_equivalence 10 queries ±0.01, qdrant_all_tagged 6481, domains_assigned 6259, citations_generalized 4570 sin huérfanas, cross-project isolation, build_wiki_db parity, validator exit 0.
- **`validate_wiki_relations.py --project`**. Arreglado el único stub con `relations: []` (inside-out-2-2024-film → compared_with inside-out-2015-film). test_hybrid 8/8.

**F5 HECHO y verificado (Fase 5 — tools MCP multi-proyecto):**
- **`ariadna/projects.py`** (create_project con SLUG_RE/seed_from_templates/inherit_from/.gitkeep + list_projects con n_chunks vía `CorpusStore.count_by_project`) y **`ariadna/research_queue.py`** (add_request idempotente + detect_source_type enum corto + cancel_request FSM pending|failed→cancelled + list_research_queue). Lógica aislada del server (reutilizable por el worker F7).
- **mcp_server.py**: 5 tools nuevas (create_project, add_to_research_queue, cancel_request, list_projects, list_research_queue); `get_wiki_page(page_id, project=None)` cross-all (desempata por indexed_at, expone `projects_with_this_id`); `search_corpus` ya con `project`; **retiradas get_video_summary y list_videos**. `retrieval_metadata.projects_seen`.
- **Fix**: `Searcher.resolve_projects` refresca `_known_projects` en miss (proyecto creado en caliente sin reiniciar).
- **`verify_phase2.py` relleno (24 checks, server vivo, auto-limpieza vp2-*)**: **24/24 ✓** (slugs inválidos, INCOMPATIBLE_OPTIONS, seed/inherit idénticos, detección youtube/paper/pdf/web/unknown, idempotencia, cancel FSM, INVALID_STATUS, obsolete tools removed, cross-project). test_hybrid 8/8 (7 tools). `data/ariadna.db.projects` tiene fila `proxy`.

**F6 HECHO y verificado (Fase 6 — source archive + summarizer nativo + extractor paper lean):**
- **`ariadna/source_archive.py`**: content-addressable `data/sources/<hash[:2]>/<hash>.<ext>` + tabla `source_files`. `store()` idempotente por sha256.
- **`ariadna/summarize/`**: summarizer nativo (patrón ProxySummaries portado). `run_claude.py` (`claude -p` agnóstico), `prompts.py` (`SUMMARY_PROMPT_PAPER_ES` markers [p.NN] + `validate_summary` generalizada), `pdf_extract.py` (pymupdf → [p.NN]), `generate.py` (PDF→summary.md). Dep nueva **pymupdf**.
- **`ariadna/sources/paper.py`**: `parse_summary_to_chunks` (- p.NN 🎭 → GenericChunk) + `summarize()` nativo; fix `citation_link_re` (DOI corta en `#`). `YoutubeAdapter.summarize` = seam diferido (proxy va por bypass).
- **DECISIÓN F6.4 (acordada)**: NO unificar el motor de YouTube (3991 líneas, riesgo parity). `extract_video_themes.py` queda **intacto**. Papers usan un extractor **LEAN nuevo**: `ariadna/extract/paper.py` (1 llamada LLM/paper → páginas JSON → materialización determinista a .md con citas `[title, p.N](doi#page=N)`). Ambos viven tras la interfaz del adapter.
- **ARQUITECTURA (acordada con el usuario)**: Ariadna es **universal con summarizer nativo por fuente**; el paso `summarize` del worker es **SALTABLE** vía bypass *bring-your-own-summary* (ProxySummaries como gestor del canal encola vídeos ya sumarizados con `summary` inline → skip). YouTube-nativo = seam diferido (sin consumidor inmediato).
- **Verificación**: `scripts/test_summarize.py` 4/4 + `scripts/test_extract_paper.py` 4/4 (deterministas, sin red/LLM). La llamada LLM real (summarize + extract) se ejercita en F8.

**Estado runtime:** search.py lee ariadna.db; **7 tools MCP**. Server vivo en :8080. `data/wiki.db` fuera del runtime. **OJO Mattermost**: cambió el set de tools (Refresh Tools necesario).

**F7 HECHO y verificado (Fase 7 — worker FSM + acquirer):**
- **`ariadna/research_queue.py`**: FSM con lock optimista `claim_next` (`UPDATE…WHERE id=(SELECT…LIMIT 1) RETURNING *`, sin doble-claim), `mark_done`, `mark_failed` (retry backoff 60/300/900s vía `metadata.next_attempt_at`, max_retries=3 → failed permanente). `add_request` con `summary`/`source_metadata` (bypass).
- **`ariadna/acquire.py`**: `PaperAcquirer` Protocol + `ClaudePaperAcquirer` (lanza `claude -p` con MCP paper-search: `download_paper`/`get_paper_by_doi`, parsea JSON) + `MockPaperAcquirer` (tests).
- **`scripts/worker.py`**: `process_item` (núcleo testeable, inyectable acquirer/summarize/extract): bypass o acquire→`source_archive.store`→`summarize`→`register_source` (sources+source_projects)→`extract_paper_to_pages`+`materialize`→`build_wiki_db --project` (ariadna.db inline; **Qdrant NO** inline). `run_loop` (claim→process→done/failed). `--index <project>` = ventana batch Qdrant (server parado).
- **mcp_server**: `add_to_research_queue` con `summary`/`source_metadata` (bypass).
- **Verificación**: `scripts/test_worker.py` 3/3 (FSM/lock/retry, bypass, process_item E2E con mocks: fuente registrada, página wiki materializada, 0 citas huérfanas). La adquisición real (claude -p paper-search) + LLM se ejercitan en F8.

**F8 HECHO y verificado (Fase 8 — E2E atlas, cross-search proxy+atlas):**
- **Proyecto `atlas-teleosemantico`** creado (seed_from_templates) + `scope.md` propio: **teoría de la mente bajo paradigma teleosemántico** (el lenguaje es UN pilar, no el centro; pilares: teleosemántica/contenido, ToM/metarrepresentación, sustrato neural, jerarquía transdominio, evolución, afecto/percepción).
- **Pipeline real ejecutado**: `claude -p` (summarize + extract) sobre un paper **full-text real** ("How to measure metacognition", Fleming & Lau 2014, Frontiers, 9 pp / 60K chars, open-access bajado directo de Frontiers) vía el **worker** con **bypass seguro por content-hash** → **17 páginas atlas** (concepts: meta-d′, AUROC2, Brier, SDT tipo-2, sensibilidad/sesgo/eficiencia metacognitiva; authors: Lau/Nelson/Brier; synthesis: "metacognición como índice de conciencia"). 32 citas paper, 43 relaciones.
- **Cross-search verde**: `search_corpus(project=["proxy","atlas-teleosemantico"])` devuelve hits de **ambos** corpus intercalados con `project_id` de procedencia (`projects_seen=['atlas-teleosemantico','proxy']`); `project="proxy"` **aísla** (cero fuga de atlas).

**Quirks de adquisición (F8)**: descarga de PDF real inestable — `download_paper` scihub no resuelve estos DOIs de revista (scraper), `semantic` 403, `wiley` exige `WILEY_TDM_TOKEN`. **Funcionó**: bajar open-access directo (Frontiers/PLOS/eLife/PNAS) con `curl` y archivar por hash → `add_request(source_file_hash=...)` (bypass seguro). El `ClaudePaperAcquirer` autónomo (claude -p + paper-search MCP) queda sin validar end-to-end (run_claude no pasa `--allowedTools`).

**REFACTOR COMPLETO (F4–F8). Backlog / siguientes (no del refactor):**

- **⭐ PRÓXIMA TAREA — IdeaBlock first-class (persistir sumario + indexar chunks Layer 0).** Diseño ACORDADO con el usuario (empezar aquí en sesión nueva):
  - **Concepto**: un IdeaBlock = un tema de sumario (theme + afirmaciones sintetizadas), NO un chunk crudo. El sumario es el paso CARO/no-determinista (LLM). **Persistirlo permite re-ejecutar la lógica downstream (extract/index) sin re-sumarizar** — esa es la motivación del usuario. Q&A contextualizada **DESCARTADA** (Q genérica homogeneiza embeddings; revisitar solo tras un eval).
  - **Estado HOY**: youtube → IdeaBlocks en `ProxySummaries/.../summary.md` + Qdrant (~6259 pts `source_type=youtube_video`). Papers → el worker genera el sumario en memoria y lo **descarta**; los chunks de paper **NO** se indexan (solo los 17 focales de wiki). `ariadna.db` no tiene tabla de chunks (viven en Qdrant).
  - **Persistir** (`ariadna/project_config.py`): añadir `self.summaries_dir = self.root / "summaries"`. Guardar `projects/<slug>/summaries/<sanitize(source_id)>.md` con frontmatter (`source_id, source_type, title, generated_at`) + cuerpo (el índice de IdeaBlocks).
  - **Reusar** (`scripts/worker.py:process_item`): si existe el summary persistido → reusarlo y **saltar acquire+summarize** (cero LLM, cero descarga); si no → bypass/generar → persistir. Helper nuevo `ariadna/ideablocks.py`: `summary_path/write_summary/read_summary`.
  - **Indexar Layer 0** (`ariadna/ideablocks.py:index_project_chunks(project)`): lee `summaries/*.md` → `adapter.parse_summary_to_chunks(body, source_id, title)` → embed (DenseEmbedder) → Qdrant upsert con payload universal + `embedding_role="chunk"`; idempotencia `delete_by_filter({project_id, embedding_role:"chunk"})`. Llamar desde `worker.index_batch` (ventana batch, server parado). ID entero = `sha256("chunk:"+chunk_id)`.
  - **search.py**: `SearchResult.from_payload` debe ser **TOLERANTE** — los chunks de paper no tienen `video_id/video_title/timestamp/youtube_url/category/playlist`; usar `.get()` con fallback a `source_id/title/position_url`. (Mejor a futuro: universalizar `SearchResult`.)
  - **Verificar**: tras `--index atlas-teleosemantico`, `search_corpus(project=["atlas-teleosemantico"], query="meta-d prime")` devuelve **raw_chunks** del paper (no solo el focal de wiki).
- **page_domains de papers**: `extract/paper.py` emite `domain_primary` escalar pero no lista `domain[]` → `page_domains` vacío para atlas (añadir `domain[]` al output del extractor + al render).
- **page_domains de papers**: el extractor lean emite `domain_primary` escalar pero no lista `domain[]` → `page_domains` vacío para atlas (añadir `domain[]` al output del extractor).
- **ClaudePaperAcquirer**: ampliar `run_claude` con `--allowedTools`/`--permission-mode` para adquisición autónoma; o integrar librería directa.
- **Bypass ProxySummaries (youtube)**: el canal de entrada legacy (summary inline) está implementado en cola+worker; falta el hook en ProxySummaries que llame a `add_to_research_queue`.
- **F4 pendiente menor**: generalización profunda de `extract_video_themes` (diferida; papers usan extractor lean).
- **F6** `ariadna/source_archive.py` (data/sources/<hash>) + `ariadna/summarize/` (PDF→summary.md p.NN, porta patrón ProxySummaries) + PaperAdapter.
- **F7** `scripts/worker.py` (FSM research_queue, paper-search MCP vía `claude -p`, ventana batch Qdrant).
- **F8** E2E atlas: create_project + descargar DOIs de `atlas_teleosemantico/data/bibliografia.csv` + encolar + worker + cross-search.

**Quirks:** parar el server con `kill <PID-exacto>` (NO `pkill -f mcp_server` → auto-mata el comando; tampoco `pgrep | head` a ciegas — puede matar un PID transitorio equivocado). Reiniciar: `nohup .venv/bin/python -m ariadna.mcp_server --warm > /tmp/ariadna.log 2>&1 &` (puerto 8080; `--warm` precarga el searcher). Reindex Qdrant y `verify_phase1.py` requieren server PARADO (lock embedded). `build_wiki_db.py --project` SÍ puede correr con el server vivo (ariadna.db en WAL, lectores+1 escritor). `verify_adapter_parity.py` no toca Qdrant. Comandos F4: `python scripts/{verify_adapter_parity,verify_phase1}.py` · `python scripts/build_wiki_db.py --project proxy [--check|--query ...]` · `python scripts/index_wiki_to_qdrant.py --project proxy` · `python scripts/validate_wiki_relations.py --project proxy`.

---

## Prompt para pegar al iniciar nueva sesión

```
Soy el mismo usuario. Continuamos el proyecto Ariadna (servidor MCP de RAG
sobre corpus YouTube del canal Proxy, integrado con Mattermost via plugin
Agents v2.0.0-rc1+ + ngrok).

Estado al 2026-05-16 tarde (segunda mitad de la sesión maratón cerrada):

ÚLTIMO TRABAJO HECHO HOY (continuación de la sesión madrugada→tarde):

1. Semantic recovery v2 — refactor profundo:
   - LLM judge ahora extrae alias_candidate como SUBCADENA LITERAL del
     surface_form (corpus = fuente, no normaliza morfología).
   - Prompt endurecido con ejemplos negativos (rechaza aplicaciones tipo
     "victimismo como estrategia política", "X vs Y", "X aplicado a Y").
   - ALIAS_MAX_WORDS reducido 7→4, ALIAS_MAX_CHARS 60→50.
   - JudgeDecision.from_dict tolera keys desconocidos (forward-compat).
   - Validación word-boundary anti-hallucination: alias_candidate debe
     aparecer literalmente en surface_form (re.escape + \b).

2. _add_alias_to_page bug fix CRÍTICO:
   - El regex ALIASES_BLOCK_RE de scan_mentions_ledger solo matcheaba
     flow YAML inline `aliases: [...]`. Las wikis usan block syntax
     `aliases:\n- A\n- B`. Mi código no encontraba el bloque existente
     y creaba bloques duplicados cada iteración.
   - Fix: regex propios _ALIASES_FLOW_RE + _ALIASES_BLOCK_RE_LOCAL,
     _parse_aliases_block detecta style ('flow'|'block') y posición,
     _render_aliases preserva el estilo original.
   - Caso original: alien-saga.md tenía 3 bloques aliases consecutivos.
   - Tests inline: 7/7 pasan, incluido caso de 3 iteraciones = 1 bloque.

3. applied_at flag para idempotencia del cache:
   - JudgeDecision añade applied_at + apply_outcome.
   - Cuando set, la entry NO se re-procesa en próximos runs.
   - La idempotencia NO depende del estado del wiki (que puede haber
     cambiado por edición humana) sino del flag.
   - Reset = borrar cache → todas vuelven a None → re-procesa todo.
   - Patch retroactivo aplicado a las 74 high entries del commit 76ff4e6.

4. MCP trim citations en get_wiki_page:
   - Sección "## Citations" se trima por defecto (puede ser 5-7 KB
     por wiki hub). Resuelve memo project_mcp_citations_trimming.md.
   - Flag opt-in include_citations=True para casos raros.
   - 222/223 wikis tienen sección Citations; 220KB trimables totales.

5. Corpus 100% procesado:
   - Run pilot_sonnet_20260509 completado: 170/178 done + 8 orphans
     (JSONs sin run_id pero contenido válido).
   - Aggregate post-run + recovery automático ejecutados con código
     fixed → 21 citations + 6 aliases adicionales aplicados.

COMMITS DE LA SESIÓN HOY (orden cronológico):
- 19c7fae refactor(semantic_recovery): LLM extrae alias_candidate como subcadena
- 46aef87 chore(embeddings): silenciar progress bars + deprecation
- 8a64ef4 fix(semantic_recovery): usar v.title (no v.video_title)
- fcedd81 fix(semantic_recovery): _enrich_findings_with_timestamps muta in-place
- 1d46143 fix(semantic_recovery): _add_alias_to_page soporta block syntax YAML
- 119b426 refactor(semantic_recovery): prompt LLM estricto + ALIAS_MAX_WORDS=4
- 76ff4e6 feat(wiki): semantic recovery apply v2 — 41 citations + 18 aliases
- 0c9b907 feat(semantic_recovery): applied_at flag para idempotencia del cache
- bda45b8 feat(mcp): trim sección Citations en get_wiki_page (flag opt-in)
- (+ commits del aggregate auto post-run: 1947379, 0d39b4d, f20c41e)

WIKI ACTUAL:
- 223 páginas (concepts 78, authors 15, entities/works 73, synthesis 56)
- 236 entries en wiki/_meta/semantic_recovery_cache.json (119 high applied)
- 100% del corpus procesado (296/296 vídeos)

PROCESOS VIVOS:
- MCP server: ariadna.mcp_server escuchando en :8080
- ngrok tunnel: https://8099-79-116-62-241.ngrok-free.app → :8080
  (Mattermost ya vio las 14 tools, falta activar Enable Server + tools
   individuales en plugin AI)

ROADMAP MULTI-TENANT (sin cambios desde la madrugada):
- Spec aprobada: docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md
- Plan completo 9 chunks: docs/superpowers/plans/2026-05-16-multi-project-and-research-queue.md
- Handoff: docs/AGENT_HANDOFF_2026-05-16.md (issues retrospectivos a fixear)
- Próximo paso: ejecutar plan con subagent-driven-development o executing-plans

DOCS CLAVE A LEER:
1. README.md — actualizado hoy con estado real + roadmap multi-tenant + prototipo
2. docs/PHASES.md — estado fases + Fase Multi-Tenant añadida
3. docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md
4. docs/superpowers/plans/2026-05-16-multi-project-and-research-queue.md
5. docs/AGENT_HANDOFF_2026-05-16.md
6. wiki/_meta/scope.md — alcance editorial
7. wiki/_meta/canonical_whitelist.json

VERIFICACIONES AL ARRANCAR:
- Procesos: ps -ef | grep -E "mcp_server|ngrok|extract_video"
- Wiki size: find wiki -name "*.md" -not -path "*_meta*" | wc -l
- Cache state: python -c "import json; c=json.load(open('wiki/_meta/semantic_recovery_cache.json')); print(f'total={len(c)}, applied={sum(1 for v in c.values() if v.get(\"applied_at\"))}')"
- Git history: git log --oneline -20

LÍNEAS DE TRABAJO POSIBLES (pregúntame cuál antes de proponer):
A) Prueba de control de Mattermost con el MCP vivo: cruzar conceptos
   dispares (3-4 saltos) — ver final de docs/NEXT_SESSION.md para opciones
   de queries. Requiere que el usuario active toggles en plugin AI.
B) Ejecutar plan multi-tenant (Chunks 1-9) con subagent-driven-development.
   Antes leer handoff para issues retrospectivos de spec.
C) Diseñar Fase B wiki_enrichment (módulo nuevo, agrupado por page_id,
   reusa applied_at flag): para reason_code "promotion_threshold_not_met"
   y similares, generar pending_updates editoriales en bloque (1 LLM call
   por página, no por entry). Spec abierta.
D) Generar nuevos summaries en ProxySummaries (26 pendientes) para
   ampliar corpus → próximo extractor con --limit los procesaría.
E) Otra cosa: pregúntame.

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
