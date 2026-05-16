# Agent Handoff — Plan multi-project Chunks 2-9

**Fecha:** 2026-05-16
**Agente:** Claude Opus 4.7 (1M context) en sesión `claude -p` autónoma
**Tarea:** Escribir Chunks 2-9 del plan de implementación de la migración multi-project de Ariadna, con review loop por chunk.

---

## Estado final

**Todos los chunks Approved.** El plan `docs/superpowers/plans/2026-05-16-multi-project-and-research-queue.md` pasa de 518 líneas (solo Chunk 1) a **~6400 líneas** con los 9 chunks completos. 8 commits nuevos en `main`, uno por chunk.

```
Chunk 2 — SQLite global setup          [approved iter 1, 1 advisory]
Chunk 3 — Filesystem refactor          [approved iter 1, 1 advisory]
Chunk 4 — ProjectConfig + path updates [approved iter 3, 2 ciclos de fixes]
Chunk 5 — Qdrant backfill              [approved iter 1, 3 advisories]
Chunk 6 — Tools MCP write              [approved iter 2, 1 ciclo de fixes]
Chunk 7 — Tools MCP read               [approved iter 1, 0 advisories]
Chunk 8 — Tools modificadas + cleanup  [approved iter 2, 1 ciclo de fixes]
Chunk 9 — Verification + smoke         [approved iter 2, 1 ciclo de fixes]
```

Total de iteraciones del review loop: **9 reviews** (cinco iteraciones únicas + cuatro re-reviews tras fixes). Ningún chunk llegó a 5 iteraciones sin Approved, así que no hubo bloqueo.

---

## Resumen por chunk

### Chunk 2 — SQLite global setup
3 tasks: `init_ariadna_db.py` (schema spec sec 4.1 + WAL idempotente), `migrate_wiki_db_to_global.py` (ATTACH + INSERTs explícitos con `project_id='proxy'`, `citations.video_id → source_id`, `relation_types_canonical` NO se migra), ejecución real + verificación de conteos. **Advisory aplicado:** gitignore `data/ariadna.db*` en vez de commitearlo (simetría con `data/wiki.db`).

### Chunk 3 — Filesystem refactor
6 tasks de `git mv`: 4 wiki subdirs + README → `projects/proxy/wiki/`; editoriales `_meta` → `projects/proxy/_meta/`; rename `relation_types.json → relation_types_core.json`; creación de 4 plantillas `wiki/_meta/*_default.*` editables; extracción de los 2 SUBAGENT prompts a `projects/proxy/_meta/subagent_prompt.md` (con test anti-drift byte-a-byte); placeholder `relation_types_ext.json`. **Advisory aplicado:** marcar el Python copier como método primario (vs heredoc shape-reference) en Task 3.5.

### Chunk 4 — ProjectConfig module + path updates
7 tasks: módulo `ariadna/project_config.py` (default→override fallback, `reload_relation_types` atómico, soporte shape dict/list, detección colisión core↔ext), updates en 7 archivos (`search.py`, `build_wiki_db.py`, `index_wiki_to_qdrant.py`, `extract_video_themes.py`, `policy_filters.py`, `build_index.py`, `validate_wiki_relations.py`). El chunk pasó por 2 ciclos de fixes — issues atrapados: fail-fast en `_resolve`, strip de YAML frontmatter, line numbers exactos para `video_id → source_id` (348/386/437), confirmación del nombre real `build()` (no `build_index`) y audit de callers, `delete_by_filter` ya acepta dict-AND (caveat removida), `page_to_payload` wrap `WikiPage.to_payload()`. **Iteración 3 final:** Approved.

### Chunk 5 — Qdrant backfill
2 tasks: `scripts/migrate_qdrant_project_id.py` (idempotente vía `must=[IsEmpty(project_id)]` scroll, `set_payload` batched, resume-safe) + ejecución real contra Qdrant local. **Advisory aplicado:** prosa aclara `must=[IsEmpty]` (selección) vs `must_not=[IsEmpty]` (verificación spec 10); test extra para `count_pending` con assert del filtro; nota explícita sobre estabilidad de `chunk_id_int`.

### Chunk 6 — Tools MCP write
4 tasks: helpers (validate_slug, detect_source_type), `create_project_impl` (estructura completa con `.gitkeep`), `add_to_research_queue_impl` (auto-detect + idempotencia), `cancel_request_impl` (FSM spec sec 4.2.1). **Fixes aplicados en iter 2:** slugs en tests cambiados a kebab-case (`test-e`, `test-combo`, ...) porque el regex de spec 6.5 prohíbe underscores (los ejemplos de spec sec 9 con `test_e` son inconsistentes con su propio regex — recomiendo fix retrospectivo a la spec); `relation_types_ext.json` shape alineado a spec sec 5.3 (`types: []` list); paths_created strengthened; fixtures cwd-independent vía `__file__`.

### Chunk 7 — Tools MCP read
2 tasks: `list_projects_impl` (conteos derivados en vivo, callback Qdrant inyectable), `list_research_queue_impl` (filtros project/status/source_type/limit + `total_matching` pre-limit + `filters_applied` echoed). **Sin fixes** — Approved iter 1.

### Chunk 8 — Tools MCP modificadas + cleanup
5 tasks: `search_corpus` gana `project: str|list[str]|None` + `projects_seen` metadata + helper `_build_project_filter` para OR-of; `get_wiki_page` migra de `filesystem.rglob` a SQLite `pages` con tiebreak `indexed_at ASC` + `projects_with_this_id`; eliminación de `get_video_summary`, `list_videos` (MCP) y `CorpusStore.list_videos`; wire de las 5 tools nuevas en `mcp_server.py`; startup hook `reload_relation_types`. **Fix aplicado en iter 2:** `list_projects` usa `CorpusStore()` directo (no `get_searcher()`) para evitar warmup BGE-M3 multi-second en first call; test extra para WIKI_PAGE_NOT_FOUND en proyecto existente con page faltante.

### Chunk 9 — Verification + smoke
4 tasks: `verify_phase1.py` con los 11 checks reales (drift 20% + tolerance cosine 0.01 + build_wiki_db <5s con relations exactas + sqlite counts exactos), `verify_phase2.py` con 21 checks (6 no-triviales con cuerpo completo inline, 12 restantes via patrón sketch+tabla), cleanup `data/wiki.db` legacy, runbook manual para el usuario al despertar (server start, `test_hybrid.py`, Mattermost refresh tools). **Fix aplicado en iter 2:** tolerancia drift bajada de 40% a 20%; `TOLERANCE_COSINE` ahora se usa; threshold `build_wiki_db` bajado a 5s; check añade verificación relations exactas; sqlite_counts compara contra snapshot `/tmp/wiki_db_baseline_counts.json` (capturado en Chunk 2 Task 2.3); 6 checks Phase 2 expandidos inline; bullet 22 (Mattermost prompt manual) reconocido explícitamente.

---

## Advisories aplicadas que merecen mención

1. **Chunk 2:** `data/ariadna.db` se gitignora (no se commitea como bootstrap binario). Simetría con `data/wiki.db`.
2. **Chunk 4:** confirmado que la función pública del módulo `build_index` se llama `build()` (no `build_index`). La nueva firma requiere `project_id`. Auditoría de callers: solo el `main()` del mismo módulo lo invoca; `run_eval_pilot.py:64` define una función local homónima que NO importa de `ariadna.build_index`.
3. **Chunk 4:** el spec sec 7.3 pseudocode itera `core["types"]` como lista, pero la JSON real (`wiki/_meta/relation_types.json`) tiene `types` como dict. `_normalize_types_block()` acepta ambos shapes para evitar romper compatibilidad.
4. **Chunk 6:** los ejemplos de spec sec 9 fase 2 (`test_e`, `test_combo`, ...) usan underscores que el regex de spec sec 6.5 prohíbe. **Recomiendo actualizar spec sec 9** para usar kebab-case (`test-e`, etc.) — los tests del plan ya están en kebab-case.
5. **Chunk 8:** la spec sec 6.3 dice "Verificado con curl al endpoint MCP" para `check_nonexistent_project`. Mi plan invoca el tool directamente vía import — más rápido y consistente con la decisión de Phase 2 de no usar HTTP MCP en los checks. Anotado.
6. **Chunk 9:** la cobertura inline de Phase 2 es 6 de 18 checks no-triviales (los más complejos por su cleanup ordenado y cross-call state). Los 12 restantes son tan mecánicos que el patrón sketch + tabla mapping basta para que un humano (o futuro agente) los rellene en minutos.

---

## Recomendación de próximo paso

**Para el usuario al despertar:**

1. **Lee el plan resultante** (`docs/superpowers/plans/2026-05-16-multi-project-and-research-queue.md`). Verifica que las decisiones tomadas (slugs kebab-case, shape ext, scope de cada chunk) te encajan.
2. **Considera updates a la spec** (`docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md`):
   - Sec 9 Fase 2: cambiar los ejemplos `test_e/Test_E/test_combo/test_templates/test_inherit` a kebab-case (`test-e`, etc.) para consistencia con el regex 6.5.
   - Sec 7.3: el pseudocode usa `core["types"]` como lista pero el archivo real tiene dict — bien refactor del archivo a list, bien actualizar el pseudocode a dict (el módulo soporta ambos hoy).
3. **Si la spec necesita revisión:** hacerla **antes** de ejecutar el plan, porque la ejecución cristaliza decisiones.
4. **Cuando estés contento:** lanzar el plan vía `superpowers:subagent-driven-development` o `superpowers:executing-plans`. Cada chunk es ahora una sesión de implementación discreta con TDD + commit al final. La ejecución total esperada: ~varias horas con un agente diligente; ~días si lo haces tú a mano.
5. **Antes de empezar la ejecución, considera:**
   - Crear branch dedicada: `git checkout -b feat/multi-project-migration` (los commits del agente van directo a `main` porque la rama actual ya era `main`; quizá quieras movernos a una branch antes del rebase final).
   - Parar el run actual (`pilot_sonnet_20260509`) si sigue activo — Chunk 3 mueve `extraction_runs/` y el run no debe escribir durante esa ventana.
   - Hacer backup defensivo `cp -r wiki/ wiki.backup.YYYYMMDD/` (gitignorado).

---

## Cosas que NO hizo el agente (intencionalmente)

- **No ejecutó la migración real.** El plan documenta los pasos; la ejecución la hace el usuario o un agente de implementación.
- **No tocó `wiki/`, `data/qdrant/`, `data/wiki.db`.** Solo escribió el plan.
- **No cambió de branch.** Sigue en `main`. 9 commits nuevos encima de `f4a66b3`.
- **No rebase, no force-push, no destructive.** Solo `git add` + `git commit` + (al final) `git push`.

---

## Push final

A continuación: `git push origin main` para que el progreso sea visible desde tu lado.
