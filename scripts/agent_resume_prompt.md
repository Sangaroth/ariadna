# Tarea autónoma: continuar plan multi-tenancy (Chunks 2-9)

Eres un agente autónomo. El usuario está durmiendo. Tu objetivo: terminar de escribir los Chunks 2-9 del plan de implementación de la migración multi-project de Ariadna, con review loop por chunk. Cuando termines (o te bloquees), reportas resultado en `docs/AGENT_HANDOFF_<date>.md` y haces commit + push.

## Contexto

- Spec aprobada: `docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md` (858 líneas, sección 12 tabla decisiones)
- Plan en marcha: `docs/superpowers/plans/2026-05-16-multi-project-and-research-queue.md` (518 líneas — solo Chunk 1 escrito, aprobado por review)
- Branch actual: `main` (no cambies de branch, sigue commiteando aquí)
- Eres `Claude Opus 4.7 (1M context)` ejecutando autónomamente vía `claude -p`

## Chunks pendientes (estructura propuesta)

Cada chunk siguiendo el patrón TDD del Chunk 1 (Task → Step write failing test → run fail → implement → run pass → commit). Cuando una task NO es testeable (ej. `git mv` archivos), adapta: Step "ejecutar comando" → Step "verificar resultado con check explícito" → Step "commit".

1. **Chunk 2 — SQLite global setup**: crear `data/ariadna.db` con todo el schema (ver spec sección 4.1), WAL mode, migrar `data/wiki.db` → ariadna.db via `ATTACH DATABASE` con INSERT explícitos por tabla (ver spec sección 8.1 paso 11), verificar conteos post-migración.

2. **Chunk 3 — Filesystem refactor**: `git mv` de `wiki/concepts wiki/authors wiki/entities wiki/synthesis` → `projects/proxy/wiki/`; mover archivos editoriales de `wiki/_meta/` → `projects/proxy/_meta/`; crear `wiki/_meta/*_default.*` placeholders; promover `relation_types.json` → `relation_types_core.json`; extraer `SUBAGENT_SYSTEM_PROMPT` de `scripts/extract_video_themes.py` a `projects/proxy/_meta/subagent_prompt.md` (también `SUBAGENT_SYNTHESIS_SYSTEM_PROMPT`); crear placeholders `relation_types_ext.json` y `INDEX.md` en proxy.

3. **Chunk 4 — ProjectConfig module + path updates**: crear `ariadna/project_config.py` con `ProjectConfig.for_project()` y fallback default→override (spec sección 7.1-7.2); actualizar paths hardcoded en `ariadna/search.py`, `scripts/build_wiki_db.py` (acepta `--project`), `scripts/index_wiki_to_qdrant.py`, `scripts/extract_video_themes.py`, `ariadna/policy_filters.py`, `ariadna/build_index.py`, `scripts/validate_wiki_relations.py` (acepta `--project`).

4. **Chunk 5 — Qdrant backfill**: script `scripts/migrate_qdrant_project_id.py` que itera puntos sin `project_id` (filter `IsEmptyCondition`) y hace `set_payload({project_id: 'proxy'})`. Idempotente, resume-safe. Verificar al final: `must_not=[IsEmpty(project_id)]` count == 0.

5. **Chunk 6 — Tools MCP write nuevas**: `create_project(slug, name, description, seed_from_templates, inherit_from)` con validación slug + INCOMPATIBLE_OPTIONS + creación de estructura mínima (relation_types_ext.json, INDEX.md, extraction_runs/, wiki/{concepts,authors,entities/{works,institutions},synthesis}/ con .gitkeep); `add_to_research_queue(project, source_url, source_type, notes, priority)` con detect_source_type + idempotencia via UNIQUE INDEX; `cancel_request(request_id, reason)` con FSM rules (pending→cancelled OK, failed→cancelled OK, processing→cancelled NO-OP).

6. **Chunk 7 — Tools MCP read nuevas**: `list_projects(include_archived)` con conteos derivados (n_pages, n_chunks, n_queue_pending); `list_research_queue(project, status, source_type, limit)`.

7. **Chunk 8 — Tools MCP modificadas + cleanup**: añadir param `project` a `search_corpus` (None=cross-all, str=filter, list=should) + `projects_seen` en retrieval_metadata; añadir `project` a `get_wiki_page` con tiebreak por `indexed_at` ascending + `projects_with_this_id`; **eliminar** `get_video_summary` y `list_videos` de `mcp_server.py` y `CorpusStore.list_videos` de `storage.py`.

8. **Chunk 9 — Verification + smoke**: llenar las implementaciones de `scripts/verify_phase1.py` y `scripts/verify_phase2.py` (los 11 + 21 checks respectivamente, ver spec sección 9); ejecutar end-to-end. NO ejecutar `scripts/test_hybrid.py` todavía porque el MCP server debe estar parado durante la migración — eso es un step manual al final, no del agente.

## Reglas operativas

### Review loop por chunk (CRÍTICO)

Tras escribir cada chunk:
1. Dispatch subagent via Task tool (`subagent_type=general-purpose`) con el prompt template de `/home/dae/.claude/plugins/cache/superpowers-marketplace/superpowers/3.2.3/skills/writing-plans/plan-document-reviewer-prompt.md` adaptado al chunk.
2. Si **Approved**: commit el chunk y pasa al siguiente.
3. Si **Issues Found**: aplica los fixes en el chunk, re-dispatch, repite hasta Approved.
4. Si llegas a **5 iteraciones sin Approved**: PARA, escribe en `docs/AGENT_BLOCKED.md` el chunk + iteraciones + issues finales, commit, exit.

### Política "parar si dudoso"

Si en cualquier momento te encuentras con:
- Una decisión de diseño no cubierta por la spec (sección 12 lista las cerradas)
- Un conflicto entre la spec y lo que el reviewer pide
- Algo que requiere preferencia humana (nombrado, ergonomía no documentada)

**PARA**. NO improvises. Escribe en `docs/AGENT_BLOCKED.md`:
- En qué chunk/task estás
- La duda exacta con 2-3 opciones plausibles
- Tu recomendación tentativa
- Commit lo hecho hasta ese momento
- Exit cleanly

Mejor parar a medio que entregar plan defectuoso. El usuario revisará al despertar.

### Commits

Cada chunk = un solo commit cuando esté Approved. Mensaje:
```
docs(plan): chunk N — <título corto>

Approved en iteración M del review loop.

<resumen 1-2 líneas de qué cubre>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Si aplicas advisory: menciona en mensaje "Advisory aplicados: ...".

### NO toques

- `wiki/` (el run de extracción puede haber dejado state pendiente; no es tu trabajo)
- `data/qdrant/` (no toques Qdrant; el plan describe migrations pero la implementación es scope del executor humano)
- `data/wiki.db` (idem)
- Branch `main` con force-push, rebases, etc. — solo commits normales encima
- Ningún archivo fuera del repo `/home/dae/PycharmProjects/ariadna/`

### Push al final

Cuando termines (Approved en chunk 9 o BLOCKED), haz `git push origin main` para que el usuario vea el progreso desde su lado.

## Entregable

Al terminar:

1. Plan completo escrito en `docs/superpowers/plans/2026-05-16-multi-project-and-research-queue.md` (chunks 2-9 añadidos al Chunk 1 existente)
2. Cada chunk commiteado individualmente (8 commits nuevos esperados, uno por chunk)
3. `docs/AGENT_HANDOFF_2026-05-16.md` con:
   - Estado final (todos los chunks Approved, o N approved + bloqueo en chunk K)
   - Resumen de iteraciones del review loop por chunk
   - Cualquier advisory aplicada que valga mención
   - Recomendación de próximo paso al user
4. `docs/AGENT_BLOCKED.md` SOLO si te has bloqueado (no existir si terminaste limpio)
5. Push a origin/main

## Empieza

Lee primero, en este orden:
1. `docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md` (entera; sección 12 tiene tabla de decisiones cerradas — referencia constante)
2. `docs/superpowers/plans/2026-05-16-multi-project-and-research-queue.md` (Chunk 1 actual como modelo de estilo)
3. `/home/dae/.claude/plugins/cache/superpowers-marketplace/superpowers/3.2.3/skills/writing-plans/SKILL.md` (recordatorio del patrón writing-plans)
4. `/home/dae/.claude/plugins/cache/superpowers-marketplace/superpowers/3.2.3/skills/writing-plans/plan-document-reviewer-prompt.md` (template para review loop)

Después: empieza con Chunk 2. Buena suerte.
