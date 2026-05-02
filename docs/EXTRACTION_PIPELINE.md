# Pipeline push-based de extracción — Karpathy "LLM Wiki" en Ariadna

> Estado al 2026-05-02. Este documento es la **fuente de verdad** sobre cómo se ingiere el corpus en la wiki, qué decide el extractor, cómo se aplica al filesystem, y cómo intervenir en cada punto del flujo.
>
> Doc autoritativo: cualquier referencia previa en `CORPUS_COVERAGE_STRATEGY.md`, `WIKI_GENERATION.md` o `NEXT_SESSION.md` que difiera de éste **queda superada por este**.

---

## 1. Filosofía: Karpathy "LLM Wiki" como compounding artifact

### 1.1 El problema que resuelve

El RAG clásico responde queries pulling fragmentos relevantes en tiempo real. Cada consulta paga el coste de re-recuperar y re-sintetizar lo mismo. La wiki estructurada de Ariadna sustituye eso por un **artefacto compuesto**: las síntesis ya están escritas, las cross-references ya están establecidas, el LLM consultor solo adapta y cita.

Pero **cómo se construye y mantiene** ese artefacto era hasta ahora pull-based: para compilar `mito-polar.md`, ejecutamos `search_corpus("mito polar")`, recuperamos top-K chunks por similitud, y sintetizamos. Eso introduce **selection bias del top-K**: lo que no entra en el top-K es invisible al extractor → lagunas falsas, casos canónicos perdidos.

Caso real detectado: la página `mito-polar.md` declaraba laguna *"Tradiciones no-occidentales"* y mencionaba a Tolkien como caso polar central. Pero el corpus tiene 6+ directos sobre Tolkien (Inside Proxy, Silmarillion, Tolkien y los dragones, etc.) cuyos chunks **no entraron en el top-K** de la query `"mito polar"` porque su similitud focal era 0.4-0.5. El extractor declaró ausencia de material que sí estaba en el corpus.

### 1.2 La inversión Karpathy

[Gist de referencia](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Tres ideas centrales:

1. **Tres capas**: raw sources (inmutables) / wiki (markdown editable) / scope (configuración del LLM)
2. **Operación canónica = ingest**: cuando llega un source nuevo, el LLM **lo lee y actualiza las páginas wiki que toca**. Las cross-references se construyen al ingerir, no al consultar
3. **Index-first, drill-down on-demand**: el extractor recibe un índice slim del wiki, decide qué páginas son relevantes para el source actual, y usa una tool para fetchear el cuerpo solo de esas

| Aspecto | Pull-based (anterior) | Push-based Karpathy (actual) |
|---|---|---|
| Trigger | Decido compilar página X → query top-K | Llega source nuevo → LLM lo lee → actualiza N páginas que toca |
| Dirección | Pull: una página ← top-K chunks | Push: un source → muchas páginas |
| Cobertura | Página ve solo top-K de UNA query | Cada source toca cada página relevante |
| Lagunas | "no entró en mi top-K" → falsa | "no aparece en ningún source ingerido" → verificable |
| Escalabilidad de cross-refs | Lineal con re-compilaciones | Lineal con sources nuevos (compounding) |

### 1.3 Por qué este pipeline es del tipo "compounding artifact"

Cada barrido enriquece la wiki. El siguiente barrido (cuando lleguen vídeos nuevos) ve la wiki ya enriquecida en su `heavy_context` → propone updates a páginas que en el barrido anterior no existían → la wiki gana cross-references emergentes. Sin re-trabajo: cada source se procesa **una vez** y deja huella permanente.

---

## 2. Las tres capas de Karpathy materializadas en Ariadna

### 2.1 Layer 0 — Raw sources (inmutable)

- **Corpus YouTube de Proxy**: 296 vídeos en `<PROXYSUMMARIES_ROOT>/data/playlists/<playlist>/<slug>/`
- Cada vídeo lleva `meta.json`, `summary.md` (curated bullets con timestamps), `transcript.txt`, `subtitles.es.json3`
- **El extractor lee SOLO `summary.md`** — la curaduría upstream (ProxySummaries) es ya una pre-síntesis. Procesar transcript sería 15× más coste y 0× mejor calidad
- Trade-off conocido: si un curador omitió matiz, el extractor no lo verá. Mitigación futura (no implementada): drilldown selectivo sobre transcript para entidades sospechosas — Sprint posterior

### 2.2 Layer 1 — Wiki (markdown editable + grafo emergente)

- Vive en `wiki/` del repo, versionado en git
- 11 páginas iniciales (compiladas a mano en batches 1-3 antes de adoptar este pipeline) — siguen siendo el seed
- Cada página: frontmatter YAML (page_id, page_type, domain_primary, relations[]) + cuerpo prosa con `[[wikilinks]]` + sección Lagunas
- `relations[]` tipadas con vocabulario canónico de [`wiki/_meta/relation_types.json`](../wiki/_meta/relation_types.json) (28 types)
- Indexada en Qdrant como `source_type=wiki_page` (1 vector focal por página) y en `data/wiki.db` (SQLite con citations + relations)

### 2.3 Layer 2 — Scope (configuración editorial del LLM extractor)

**La tercera capa de Karpathy es el documento que define qué entra al wiki y qué no**. En Ariadna esa capa es DOS archivos:

- [`wiki/_meta/scope.md`](../wiki/_meta/scope.md) — alcance editorial: dominios, page_types, criterios de promoción multi-path, out-of-scope explícito, terminología canal-específica, política de calidad
- [`wiki/_meta/canonical_whitelist.json`](../wiki/_meta/canonical_whitelist.json) — figuras, frameworks, channel-specific concepts y obras con `auto_promote: true/false`. Resuelve el caso "foundational singleton" (Chomsky mencionado una vez como marco aplicado a lo largo del canal — no detectable por frecuencia)

Adicionalmente, [`wiki/_meta/topic_filters.json`](../wiki/_meta/topic_filters.json) define exclusiones declarativas pre-LLM (política española coyuntural, meta-canal, promo).

**Cualquier modificación a estos tres archivos cambia el comportamiento del extractor en futuros barridos**. Editarlos es la palanca principal de calibración. Ver §6 "flujos operativos".

---

## 3. Pipeline end-to-end

### 3.1 Diagrama del flujo

```
PER-SOURCE (1 vídeo):
  summary.md
       ↓ extract_video_themes.py invoca claude -p (Opus 4.7 vía Max)
       ↓ heavy_context = scope.md + whitelist + relation_types +
       ↓                 topic_filters + INDEX SLIM del wiki
       ↓ tool Read on-demand sobre file_path de páginas relevantes
       ↓
  <video_id>.json — output JSON con:
    - entities[]              decisión + justificación + cita literal
    - pending_updates[]       updates propuestos a páginas existentes
    - thesis_candidates[]     tesis articulada del autor (synthesis_subtype: author_thesis)
    - discarded[]             entidades filtradas con razón
    - blocks_filtered_by_topic_filters[]
    - extraction_metadata

PER-RUN (N vídeos en sesión cacheada):
  N × <video_id>.json
       ↓ aggregator (--aggregate run_id)
       ↓
  6 colas de revisión:
    - discard_log.json         — toda entidad evaluada con review_priority
    - pending_updates.json     — agregadas, agrupables por page_id
    - promote_queue.json       — candidatos a página nueva
    - thesis_candidates.json   — tesis del canal
    - blocks_filtered.json
    - aggregation_stats.json   — resumen numérico

PER-BATCH (5 vídeos en overnight_run.py):
  extract_batch → aggregate → git commit (decisiones)
       ↓
  apply_pending_updates --apply --auto-commit
       ↓
  rebuild data/wiki.db (cheap, no lock)
       ↓
  update processed_videos.json
       ↓
  housekeeping_commit
       ↓
  next batch
```

### 3.2 Componentes y ficheros

| Archivo | Propósito |
|---|---|
| [`scripts/extract_video_themes.py`](../scripts/extract_video_themes.py) | Extractor. Itera vídeos, invoca claude -p en sesiones cacheadas. CLI: `--pilot`, `--video-id`, `--run-id`, `--aggregate`, `--dry-run`, `--discover` |
| [`scripts/extract_incremental.py`](../scripts/extract_incremental.py) | Wrapper para detectar vídeos no procesados (vs `processed_videos.json`) y procesarlos. CLI: `--bootstrap`, `--dry-run`, `--limit` |
| [`scripts/overnight_run.py`](../scripts/overnight_run.py) | Orquestador batch overnight. Lotes de 5 con extract+aggregate+apply+commit+rebuild. Auto-stop en errores críticos |
| [`scripts/apply_pending_updates.py`](../scripts/apply_pending_updates.py) | Aplica `pending_updates.json` al wiki con seguridad por capas (4 ops diff-style + uniqueness anchor + backup + auto-commit) |
| [`scripts/build_wiki_db.py`](../scripts/build_wiki_db.py) | Reconstruye índice SQLite `data/wiki.db` desde filesystem |
| [`scripts/index_wiki_to_qdrant.py`](../scripts/index_wiki_to_qdrant.py) | Reindexa wiki en Qdrant (requiere parar MCP server) |
| [`scripts/rank_wiki_candidates.py`](../scripts/rank_wiki_candidates.py) | Legacy del ranking pull-based (ya no es la palanca; útil para inventario) |
| [`scripts/validate_wiki_relations.py`](../scripts/validate_wiki_relations.py) | Validador estructural de páginas wiki (relations[], wikilinks, frontmatter) |
| `wiki/_meta/scope.md` | Alcance editorial — 3ª capa Karpathy |
| `wiki/_meta/canonical_whitelist.json` | Whitelist de foundational singletons |
| `wiki/_meta/topic_filters.json` | Exclusiones declarativas pre-LLM |
| `wiki/_meta/relation_types.json` | Vocabulario canónico de relations[] |
| `wiki/_meta/processed_videos.json` | Registro acumulado de vídeos ingeridos (gitignored: NO; commited) |
| `wiki/_meta/extraction_runs/<run_id>/` | Outputs por-run. **Gitignore opción B**: per-video JSONs y snapshots ignored, aggregator outputs + applied_log committed |

### 3.3 Decisiones de diseño y por qué

#### Caching cross-call con `--resume`

Cada sesión Claude Code procesa hasta **22 vídeos** con `claude -p --resume <session_id>`. El primer vídeo de la sesión envía `heavy_context` completo (~13K tokens vía stdin); los siguientes vídeos solo envían su summary y se benefician del **prompt cache** de Anthropic sobre el conversation prefix.

**Verificación empírica**: en piloto v2 (5 vídeos, 1 sesión), `tokens_cached: 495,877` confirma que el caching cross-vídeo funciona (~99K cached/vídeo en vídeos 2-5). Sin cache, el coste se multiplicaría por ~7×.

**Cuts de sesión**: 22 vídeos OR 50 minutos OR 500K tokens — cualquiera primero. El límite temporal (50 min) protege contra invalidación de cache TTL (1h ephemeral); el de 500K protege contra context window overrun (Opus 4.7 = 1M).

#### Heavy context vía stdin, system prompt vía argv

Linux limita argv a ~128KB-2MB (ARG_MAX). El heavy_context (~50K chars / 13K tokens) lo bursaba. Solución: `claude -p` lee el user message de stdin (`subprocess.run(input=...)`), el system prompt corto (~2-3K tokens) sí va por argv.

#### Karpathy index pattern (no full bodies)

`heavy_context` contiene el ÍNDICE SLIM del wiki (1 línea por página: page_id + canonical_name + domain + qué cubre + relations + lagunas + file_path), NO los cuerpos completos. El extractor usa la tool `Read` sobre `file_path` para drillar en páginas concretas que va a tocar.

Reduce heavy_context de 172K (full bodies) a 51K (index). Escalable lineal con páginas tocadas, no con páginas totales.

`--allowedTools "Read,Grep,Glob"` se pasa a `claude -p` para habilitar el drilldown.

#### Validación de quote_evidence con normalización cosmética

El LLM al "copiar" prosa elimina automáticamente formato cosmético (markdown italic `*texto*`, comillas curly, espacios redundantes, em-dashes). No es alucinación — es comportamiento esperado del LLM.

`_normalize_for_quote_match()` aplica la misma normalización a ambos lados antes de comparar:

- Markdown emphasis: `**bold**`, `*italic*`, `__bold__`, `_italic_` → contenido sin formatos
- Comillas curly → straight
- Em-dash/en-dash → hyphen
- Whitespace runs → un solo espacio
- Backticks de código inline → contenido sin backticks

Lo que SIGUE rechazando (real fail): paráfrasis con drift semántico (cambio de palabras de contenido), alucinación pura (cita inexistente), tipos inesperados.

#### Diff-style ops con anchor literal único

Para `pending_updates`, en lugar de "concat al final de sección" se usan operaciones diff-style con regla de oro: el `anchor_passage` debe aparecer **exactamente una vez** en la página existente. Si 0 ó ≥2 → skip seguro.

| `update_type` | Operación | Riesgo |
|---|---|---|
| `insert_after_passage` | inserta tras anchor único | Bajo |
| `insert_before_passage` | inserta antes de anchor único | Bajo |
| `extend_passage` | continúa frase tras anchor sin saltos | Bajo |
| `replace_passage` | reemplaza anchor por nuevo texto | Medio (cambia contenido) |
| `append_to_section` | concat al final (legacy/fallback) | Medio (degrada a cronología) |
| `mark_laguna_resolved` | marca con HTML comment, NO borra | Cero |

Filosofía: incremental editorial. El extractor es responsable de proveer anchors con suficiente contexto para uniqueness; si falla, el fallo es seguro (skip).

#### Autoridad git: orchestrator gestiona, no apply

Durante overnight, el orquestador es la AUTORIDAD git. `apply_pending_updates --no-git-check` para que el subscript no aborte por dirty tree (overnight ya lo gestiona con housekeeping_commit entre lotes).

Cada lote produce 1-2 commits semánticos:
1. `chore(extractor): aggregate decisions <run_id>` — outputs del aggregator
2. `extractor(<run_id>): apply N pending_updates → M pages` — cambios al wiki + applied_log.json
3. `chore(extractor): batch N housekeeping` — recoge `processed_videos.json` + huérfanos

#### Snapshot wiki frozen durante una sesión

Mientras una sesión está activa, las páginas wiki cambian (tras cada `--apply`). Pero el `heavy_context` cacheado en la sesión **no se actualiza** — es snapshot del momento del start. Esta es una decisión consciente: invalidar cache mid-sesión costaría 50K tokens × N vídeos restantes. Trade-off aceptado: el extractor del vídeo K+1 puede proponer un `update_existing` a la página X aunque ya hubiera sido tocada por el vídeo K en el mismo run.

Mitigación: el `apply` es per-batch (5 vídeos) en overnight; entre batches cada sesión arranca con wiki actualizado. Drift acotado a max 5 vídeos.

---

## 4. Salidas del pipeline (qué auditas tras un run)

### 4.1 Por vídeo (gitignored, audit local)

`<run_id>/<video_id>.json`: output JSON crudo del extractor con todos los campos (entities, pending_updates, discarded, etc.).

`<run_id>/<video_id>.failed.json`: si la validación rechazó (JSON malformado, paráfrasis genuina, alucinación). Contiene el output crudo del LLM + lista de errors.

### 4.2 Por run (committed)

| Archivo | Para qué sirve |
|---|---|
| `aggregation_stats.json` | Resumen numérico: videos_aggregated, entities_total, promoted_new, promoted_updates, discarded, thesis_candidates, flagged_for_review_high |
| `discard_log.json` | Cada entidad evaluada con sus occurrences cross-vídeos + decisions_seen + review_priority. **Es el índice fino del corpus filtrado por LLM** |
| `pending_updates.json` | Cambios propuestos a páginas existentes — entrada de `apply_pending_updates.py` |
| `promote_queue.json` | Candidatos a página nueva (compilación pendiente — script `compile_wiki_pages.py` aún no implementado) |
| `thesis_candidates.json` | Tesis articuladas por el autor del canal — siempre requieren firma humana |
| `blocks_filtered.json` | Bloques de summary que matched topic_filters.json |
| `applied_log.json` | Audit trail del `--apply`: qué updates se aplicaron, a qué páginas, con qué resultado |

### 4.3 Estado global (committed)

| Archivo | Contenido |
|---|---|
| `wiki/_meta/processed_videos.json` | Registro acumulado: para cada video_id, `{first_run, last_run}`. Permite incremental |

### 4.4 Estado del wiki (committed normalmente)

- `wiki/concepts/*.md`, `wiki/authors/*.md`, etc.: las páginas modificadas/creadas
- `data/wiki.db`: índice SQLite derivado (rebuilds en cada apply, gitignored)

---

## 5. Flujos operativos (cómo intervenir en cada punto)

### 5.1 Lanzar barrido completo overnight

```bash
# 1. Verificar tree limpio
git status

# 2. Si processed_videos.json está vacío, bootstrap (registra runs anteriores)
python scripts/extract_incremental.py --bootstrap

# 3. Verificar pendientes
python scripts/extract_incremental.py --dry-run | wc -l

# 4. Lanzar overnight (background)
nohup python scripts/overnight_run.py > /tmp/overnight.log 2>&1 &

# 5. Confirmar arranque
sleep 5 && tail -30 /tmp/overnight.log

# 6. Por la mañana
cat wiki/_meta/extraction_runs/overnight_*/STATUS.txt
git log --oneline -30
```

### 5.2 Procesar un vídeo concreto (debug o re-procesado)

```bash
# Por video_id (YouTube ID)
python scripts/extract_video_themes.py --video-id <video_id> --run-id debug_<TS>

# Por slug (carpeta del corpus)
python scripts/extract_video_themes.py --video-slug <slug> --run-id debug_<TS>

# Aggregate después
python scripts/extract_video_themes.py --aggregate debug_<TS>
```

### 5.3 Procesar incremental (vídeos nuevos en el corpus)

```bash
# Detectar nuevos
python scripts/extract_incremental.py --dry-run

# Procesar todos los nuevos
python scripts/extract_incremental.py

# Limitar (útil para muchos a la vez)
python scripts/extract_incremental.py --limit 20
```

### 5.4 Recuperar vídeos failed

```bash
# Listar fails
ls wiki/_meta/extraction_runs/*/*.failed.json 2>/dev/null

# Inspeccionar uno
cat wiki/_meta/extraction_runs/<run_id>/<video_id>.failed.json | python3 -m json.tool

# Re-procesar individual (con scope.md/whitelist actualizadas si fuera necesario)
python scripts/extract_video_themes.py --video-id <video_id> --run-id retry_<TS>
```

### 5.5 Aplicar pending_updates al wiki (manual o auditado)

```bash
# Dry-run (solo muestra diff, no aplica)
python scripts/apply_pending_updates.py --from-run <run_id>

# Filtrar por tipo de operación
python scripts/apply_pending_updates.py --from-run <run_id> --types insert_after_passage,extend_passage

# Filtrar por página
python scripts/apply_pending_updates.py --from-run <run_id> --page-id mito-polar

# Aplicar con commit semántico
python scripts/apply_pending_updates.py --from-run <run_id> --apply --auto-commit

# Aplicar pero parar si una página recibe demasiados updates (curaduría humana requerida)
python scripts/apply_pending_updates.py --from-run <run_id> --apply --max-updates-per-page 5
```

### 5.6 Ajustar `topic_filters.json` (quitar tema de excluidos / añadir nuevo)

`wiki/_meta/topic_filters.json` define exclusiones por regex case-insensitive. Edición manual + commit.

**Para QUITAR un tema de excluidos** (ej. quieres que la política sí entre):

```diff
   "exclude_patterns": [
-    {
-      "pattern": "(?i)\\b(actualidad pol[ií]tica|elecciones|psoe|pp\\b|...)\\b",
-      "reason": "comentario coyuntural sin valor enciclopédico",
-      "scope": "block",
-      "added_at": "2026-04-29",
-      "added_by": "human"
-    },
   ]
```

Tras editar, los próximos barridos **ya no descartarán esos bloques**. Vídeos ya procesados con el filtro anterior tendrán los descartes en su `blocks_filtered.json` (auditable). Para re-procesar:

```bash
# Identificar qué vídeos tuvieron bloques filtrados con ese pattern
grep -rl '"matched_pattern".*actualidad' wiki/_meta/extraction_runs/*/blocks_filtered.json

# Re-procesar esos vídeos
python scripts/extract_video_themes.py --video-id <vid_de_la_lista> --run-id retry_after_unfilter_<TS>
```

**Para AÑADIR un patrón nuevo** (ej. quieres excluir comentarios sobre criptomonedas):

```diff
   "exclude_patterns": [
+    {
+      "pattern": "(?i)\\b(bitcoin|criptomonedas|nft|tokens nft)\\b",
+      "reason": "tema fuera de alcance editorial junguiano/mitológico",
+      "scope": "block",
+      "added_at": "2026-MM-DD",
+      "added_by": "human"
+    },
   ]
```

### 5.7 Forzar promoción de un autor (canonical whitelist)

`wiki/_meta/canonical_whitelist.json` es la lista curada de figuras canónicas. Editar + commit.

**Para AÑADIR figura con auto_promote** (se promueve a página al primer substantive mention ≥3 min):

```diff
   "authors": [
+    {
+      "page_id_canonical": "baudrillard-jean",
+      "name": "Jean Baudrillard",
+      "auto_promote": true,
+      "domain_primary": "interdisciplinary.cultural_studies",
+      "reason": "Crítico de simulacro y consumismo — usuario decide forzar tras detectar que aparece en discard_log múltiples veces",
+      "added_by": "human",
+      "page_exists": false
+    },
   ]
```

Tras commit, los próximos barridos detectarán a Baudrillard y propondrán `promote_new`. Para revisitar vídeos ya procesados donde fue descartado:

```bash
# Buscar discards de Baudrillard
grep -rli "baudrillard" wiki/_meta/extraction_runs/*/discard_log.json

# Por cada vídeo afectado, re-procesar
python scripts/extract_video_themes.py --video-id <vid> --run-id force_baudrillard_<TS>
```

**Para BAJAR auto_promote a soft** (figura ya no se auto-promueve, requiere otros criterios del gate):

```diff
       "page_id_canonical": "lacan-jacques",
-      "auto_promote": false
+      "auto_promote": false,
+      "reason": "Re-evaluación 2026-MM-DD: no aparece como marco aplicado, baja a soft",
```

### 5.8 Ajustar criterios de promoción (`scope.md`)

`wiki/_meta/scope.md` define los criterios de promote_new / update_existing / discard. Editar prosa del documento + commit.

Cambios típicos:

- **Añadir dominio académico**: editar §1 añadiendo entry a la lista de dominios OpenAlex en alcance
- **Añadir señal de promoción**: editar §2.1/§2.2/§2.3 añadiendo bullet al gate ANY-OF
- **Añadir tipo de laguna prohibida**: editar §7.1 con regla y ejemplo
- **Añadir terminología canal-específica**: editar §5 con entry a la tabla

Cualquier cambio se aplica al **siguiente barrido**. Vídeos ya procesados conservan sus decisiones según el scope vigente al momento; para re-evaluar con scope nuevo, re-procesar vídeo a vídeo.

### 5.9 Revisar la lista de candidatos en cola (sin aplicar)

```bash
# Stats del último run
cat wiki/_meta/extraction_runs/<run_id>/aggregation_stats.json | python3 -m json.tool

# Candidatos a página nueva
cat wiki/_meta/extraction_runs/<run_id>/promote_queue.json | python3 -c "
import json,sys
d = json.load(sys.stdin)
for it in d['items']:
    e = it['entity']
    print(f\"{e['canonical_guess']:30} ({e['page_type']}) depth={e['depth_in_video']} from={it['from_video']}\")
"

# Updates propuestos
cat wiki/_meta/extraction_runs/<run_id>/pending_updates.json | python3 -c "
import json,sys
d = json.load(sys.stdin)
for it in d['items']:
    u = it['update']
    print(f\"{u['page_id']:25} {u['update_type']:25} from={it['from_video']}\")
"

# Tesis del canal pendientes de firma humana
cat wiki/_meta/extraction_runs/<run_id>/thesis_candidates.json | python3 -m json.tool

# Descartes flagged review_priority high (sospechosos)
cat wiki/_meta/extraction_runs/<run_id>/discard_log.json | python3 -c "
import json,sys
d = json.load(sys.stdin)
for canon, e in d['entities'].items():
    if e.get('review_priority') == 'high':
        print(f\"{canon:30} occ={e['occurrences_count']} reason={e['review_priority_reason']}\")
"
```

### 5.10 Reindexar Qdrant tras cambios al wiki

Reindexar requiere parar el MCP server (Qdrant embedded usa lock):

```bash
pkill -f "ariadna.mcp_server"
python scripts/index_wiki_to_qdrant.py
nohup python -m ariadna.mcp_server --port 8765 --warm > /tmp/ariadna.log 2>&1 &
sleep 5 && python scripts/test_hybrid.py
```

Cuándo hacerlo:
- Tras un barrido completo (al final de overnight o manual)
- Tras añadir/modificar páginas al wiki manualmente
- NO entre lotes del overnight (usa `--reindex-qdrant` flag opt-in si lo quieres así, default off)

---

## 6. Validación y auditoría

### 6.1 Validador de quote_evidence (extractor)

Ejecuta automáticamente en cada call a `parse_and_validate_output()`:

1. JSON parse — fail crítico (output rechazado, .failed.json)
2. Cada `quote_evidence` se busca en `summary.md + metadata header`, normalizando ambos lados (markdown italic, comillas curly, em-dash, whitespace)
3. Match no encontrado = error → output rechazado

Si un vídeo aparece en `.failed.json`:
- Inspeccionar el contenido del .failed.json para ver el quote y la razón
- Si es paráfrasis genuina: re-procesar puede o no resolver (LLM puede repetir el error)
- Si es alucinación: mejorar prompt o whitelist (raro)

### 6.2 Validador estructural del wiki

```bash
python scripts/validate_wiki_relations.py
```

Verifica coherencia: cada `to:` en relations[] resuelve a página existente o candidato conocido, cada `type:` está en `relation_types.json`, cada `[[wikilink]]` del cuerpo aparece declarado en `relations[]`. Errores rechazan, warnings reportan.

Se ejecuta automáticamente tras cada `apply_pending_updates --apply` (a menos que `--no-validator`).

### 6.3 Smoke test del MCP server

```bash
python scripts/test_hybrid.py
```

8 checks end-to-end: tools/list, wiki_primary, raw_with_warning, balanced, wiki_via_citation, citation_survives_category, in_wiki_sources, get_wiki_page. Útil tras reindexar Qdrant para validar que el modo híbrido sigue OK.

### 6.4 Cómo interpretar `discard_log.json` review_priority

Cada entidad descartada lleva `review_priority` computado por 5 disparadores:

| Disparador | Priority | Significado |
|---|---|---|
| `is_canonical_external + at_least_one_discard` | high | Figura del whitelist canónico no debería descartarse silenciosamente |
| `recurrent (n≥3) without promotion` | high | Aparece en 3+ vídeos pero el extractor nunca la promovió — patrón sistemático |
| `sustained discussion (≥20min, n≥2) without promotion` | high | Mucho tiempo invertido por el canal sin que se traduzca en página — sospechoso |
| `inconsistent decisions across occurrences` | high | El extractor decidió cosas distintas para la misma entidad en distintos vídeos |
| `whitelist_soft + at_least_one_discard` | medium | Vale la pena verificar |

Si una entidad tiene `review_priority: high`, conviene:
1. Leer sus occurrences (cita literal por vídeo)
2. Decidir si se añade a `canonical_whitelist.json` con `auto_promote: true`
3. Re-procesar vídeos donde fue descartada (§5.7)

---

## 7. Estado actual y próximos pasos (al 2026-05-02)

### 7.1 Implementado y operativo

- Scope editorial v0.2.0 + canonical whitelist v0.1.0 (3ª capa Karpathy)
- Extract pipeline con index pattern + Read on-demand
- Aggregator con 6 colas de revisión + review_priority
- Apply pipeline con 4 ops diff-style + uniqueness anchor + auto-commit
- Overnight orchestrator con stop crítico + housekeeping git
- Incremental wrapper para vídeos nuevos
- Validación con normalización cosmética
- Gitignore opción B (audit trail committed, intermedios gitignored)

### 7.2 Pendiente de implementar (Sprint posterior)

- **`scripts/compile_wiki_pages.py`**: vacía `promote_queue.json` compilando páginas nuevas a partir de los summaries fuente acumulados. Sin esto, los candidatos a página nueva quedan en cola indefinidamente
- **Drilldown sobre transcripts**: para entidades sospechosas (review_priority high) o `thesis_candidates`, leer el transcript completo del vídeo (no solo summary) en busca de matices perdidos en la curaduría upstream
- **Cross-run aggregator** (`scripts/cross_run_aggregate.py`): consolida discard_log de múltiples runs para detectar patrones cross-temporales (entidad descartada N veces → sugerir whitelist)
- **Auditor de drift**: detecta cuando una página wiki contiene afirmaciones que el corpus actual ya no soporta (chunks citados que ya no existen, lagunas refutadas que nadie marcó)
- **CI gate**: `validate_wiki_relations.py --strict` en pre-commit hook para impedir merges con campos legacy o types inválidos

### 7.3 Decisiones cerradas que NO se reabren

- Summary.md como single source de extracción (NO transcript) — coste 15× menor, calidad equivalente
- Karpathy index pattern en heavy_context (NO full bodies) — escala a 100s de páginas
- Strict reject en validador con normalización cosmética (NO modo "warnings tolerantes") — auditabilidad clara, pocos falsos positivos
- Diff-style ops con anchor único (NO append-at-end por defecto) — preserva flujo editorial
- Gitignore opción B (aggregator outputs commited, per-video JSONs ignored) — reproducibilidad desde seed sin inflar repo
- Apply auto-commit con mensaje semántico estándar — audit trail vía git log

---

## 8. Referencias cruzadas

- [`docs/WIKI_GENERATION.md`](WIKI_GENERATION.md) — anatomía de página, frontmatter, relations[], convenciones de wikilinks. **Sección 4 (Pipeline de generación) queda superada por este documento; el resto sigue vigente**
- [`docs/CORPUS_COVERAGE_STRATEGY.md`](CORPUS_COVERAGE_STRATEGY.md) — argumentación original del cambio pull → push. **Estado: implementado** (este documento)
- [`docs/PHASES.md`](PHASES.md) — roadmap completo. La Fase B incluye este pipeline como su mecanismo central
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — argumentación wiki-first / KG-emergent
- [`docs/RESPONSE_FLOW.md`](RESPONSE_FLOW.md) §10 — schema autoritativo del MCP (lo que consume el wiki)
- [`docs/NEXT_SESSION.md`](NEXT_SESSION.md) — estado vivo + próximos pasos por sesión

---

## 9. Glosario rápido

| Término | Significado en este pipeline |
|---|---|
| **3ª capa de Karpathy** | scope.md + canonical_whitelist.json — el contrato editorial entre raw y wiki |
| **anchor literal único** | substring del cuerpo de una página existente que aparece exactamente una vez. Protección de las ops diff-style |
| **author_thesis** | Subtipo de synthesis donde el speaker articula SU teoría (no academic standard). Detectable por marcadores lingüísticos |
| **batch** | Lote de vídeos en una sesión cacheada del extractor (default 22, overnight 5) |
| **compounding artifact** | Karpathy: la wiki crece monotónicamente con cada source ingerido, las cross-refs se acumulan |
| **discard_log** | Catálogo fino de entidades descartadas con cita literal — índice del corpus filtrado por LLM |
| **drilldown** | Read on-demand sobre el file_path de una página relevante para el summary actual |
| **foundational singleton** | Figura citada poco porque es load-bearing y se asume (Chomsky, estructuralismo) |
| **framing-mark** | Marcador lingüístico del speaker que invoca una entidad como marco (`"siguiendo a"`, `"el modelo que uso"`) |
| **heavy_context** | Documentos autoritativos enviados como primer user message de cada sesión cacheada |
| **housekeeping_commit** | Commit que recoge archivos huérfanos del pipeline para mantener tree limpio |
| **review_priority** | Etiqueta {low, medium, high} que el aggregator asigna a entidades sospechosas |
| **session cut** | Punto donde el extractor cierra la sesión y arranca otra (50min / 500K tok / 22 vídeos) |
| **TTL ephemeral** | Tiempo de vida del prompt cache de Anthropic (5 min default, 1h con `cache_control`) |
