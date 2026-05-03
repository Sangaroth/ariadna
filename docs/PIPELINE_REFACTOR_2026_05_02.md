# Refactor del pipeline de extracción — sesión 2026-05-02 (tarde)

> Sucede a [`POSTMORTEM_2026-05-02.md`](POSTMORTEM_2026-05-02.md) (mañana) y al
> rediseño documentado en [`EXTRACTION_PIPELINE.md`](EXTRACTION_PIPELINE.md).
> Este documento captura las decisiones tomadas en la sesión vespertina
> tras detectar que el rediseño "compile-as-rewrite" introducía nuevos
> problemas y aplicar correcciones más profundas.

---

## 1. Contexto y problema raíz

El rediseño matutino había sustituido el bucle apply-diff (que produjo
"golem") por **compile-as-primary** (LLM reescribe la página entera por
batch). Tras varios pilots empezamos a detectar:

1. **Drift de calidad**: cada vez que reforzábamos las HARD_RULES para
   arreglar un caso (ej. forzar `stub_proposed` rico para evitar stubs
   minimales), otro caso se degradaba (ej. el LLM empezaba a sobre-promover
   entidades out_of_scope).
2. **Acoplamiento de tareas cognitivas**: el main agent decidía simultáneamente
   scope (qué entra), extracción de updates (qué prosa nueva añadir) y
   construcción de stubs (frontmatter + body completos para promote_new).
   Una sola llamada al LLM tenía que balancear tres axiomas en conflicto.
3. **Schema prompt creciendo**: cada iteración añadía rules. System prompt
   pasó de 10K → 14K → 18K chars. La calidad se degradaba en lugar de mejorar.

**El bucle vicioso**: añadir reglas para arreglar un problema introduce
efectos colaterales en el LLM, requiere otra regla, etc.

**Decisión arquitectónica adoptada**: separar concerns. Cada llamada al LLM
debe tener UNA sola responsabilidad cognitiva.

---

## 2. Sub-agente in-loop para construcción de stubs

### Diseño

```
Main session (cached, --resume entre vídeos del batch):
  Por cada vídeo:
    1. Main emite { pending_updates[], promote_candidates[], discarded[] }
       NO emite cuerpo de páginas nuevas
    2. Apply pending_updates al shadow
    3. Por cada promote_candidate:
         spawn sub-agent (claude -p separado, sin --resume)
            input mínimo: scope.md + canonical_whitelist + relation_types
                          + lista page_ids existentes + 1 ejemplo seed
                          + candidato + summary excerpt
            output: stub_proposed { frontmatter rico + body markdown }
         materializa stub en shadow
    4. Continúa main con vid N+1 — VE stubs nuevos en shadow

Cierre del batch: sync shadow → wiki + commit auditable
```

### Por qué preserva Karpathy

El shadow sigue siendo el "compounding artifact". El sub-agente es un
**sub-proceso** del paso 1→3 dentro del loop, no una fase posterior.
Vid 2 ve el stub creado por vid 1 igual que antes, porque el shadow ya
contiene la página rica antes de que el main emita el contexto a vid 2.

### Por qué resuelve el bucle vicioso

- Cada llamada tiene UNA responsabilidad:
  - Main: decidir scope + emitir updates a páginas existentes
  - Sub-agente: construir UNA página específica con criterio editorial
- El system prompt del main bajó a 14.6K (de 18.2K), ya estable
- El sub-agente tiene un prompt focalizado de ~500 tokens
- Sin conflictos entre rules

### Implementación

`scripts/extract_video_themes.py`:
- `SUBAGENT_SYSTEM_PROMPT`: rol focalizado "construye UNA página"
- `build_subagent_user_msg(candidate, video, shadow)`: ~13K tokens con
  scope + whitelist + relation_types + page_ids existentes + seed example
  + candidato + summary excerpt
- `invoke_subagent_for_stub`: claude -p sin --resume, retry 1× si JSON parse falla
- `apply_video_output_to_shadow`: invoca sub-agente per promote_new

### Criterio: NO threshold de profundidad

Decisión confirmada con usuario: **todo promote_new dispara sub-agente**.
"Las wiki no se han de postergar". Aceptamos el coste de tokens por
priorizar quality y disponibilidad inmediata para vídeos posteriores.

### Coste estimado

- Sub-agente per candidato: ~13K input + ~5K output ≈ 18K tokens
- Estimación 296 vídeos × ~0.5-1 candidato medio = 150-300 sub-agentes
- Total adicional: ~3-5M tokens. Aceptable para Max plan.

---

## 3. Simplificación del schema del main

### Eliminado del OUTPUT_SCHEMA del main

- `proposed_initial_body` (string flat) → ya no se emite
- `stub_proposed` (objeto rico con frontmatter + body_markdown) → ya no se emite

### Eliminado de HARD_RULES

- Regla 16 estricta ("stub_proposed obligatorio con relations≥2") →
  reemplazada por una nota descriptiva: "NO construyes la página tú; un
  sub-agente lo hará".

### Mantenido

- Regla 9 reforzada (scope discipline, neuroanatomía out_of_scope etc.)
- Regla 17 (cita-only redundancia) — aunque el LLM raramente la dispara
- Regla anchor literal único (insertions seguras)
- Regla 1 quote_evidence literal (validación)

---

## 4. Delta injection: visibilidad de stubs nuevos al main

### Problema

El `heavy_context` (índice slim del wiki) se construye una vez al inicio
de la sesión y queda cacheado. Vídeos posteriores del batch ven el mismo
índice — sin las páginas creadas por vídeos previos del batch. El main
podría descubrirlas vía Glob/Grep tools, pero no las propondrá
proactivamente como referencias.

### Solución

`build_delta_block(shadow, baseline_page_ids)` construye un bloque
markdown con las pages creadas DESDE el inicio de la sesión:

```
## Nuevas wikis creadas en este batch (no estaban al inicio de la sesión)

- `[[mitologia-propia-impropia]]` (concept, humanities.religion) — Mitología propia vs impropia: ...
- `[[tarzan-1999-film]]` (entity_work, arts.cinema) — Tarzán (Disney, 1999): ...
```

Se prepende al `user_msg` del vídeo N+1 (NO al `heavy_context` cached) →
el cached prefix sigue válido, el delta es bytes adicionales solo del
turno actual.

### Coste

~50-150 tokens por stub × N nuevos = irrelevante.

---

## 5. Per-video JSONs trackeados en git

### Filosofía

> "no tendríamos necesidad de procesar de nuevo, justamente la idea de
> logear todo es poder reconstruir descartes, citas, etc. La filosofía es
> procesar 1 vez dejando todo en JSON para luego cambios de criterios"

### Cambio en `.gitignore`

Antes: `wiki/_meta/extraction_runs/*/*.json` ignored excepto aggregator outputs.
Después: per-video `<video_id>.json` también trackeados. Solo `state.json`,
`shadow_wiki/`, `applied_backup/` y los snapshots de prompts siguen ignored.

### Beneficio

- Cualquier cambio de criterio futuro (nuevo scope, nuevo schema, fix de
  parser) puede re-aplicarse vía `--reapply` sobre los JSONs commiteados
  sin re-llamada al LLM.
- Audit trail completo: surface_form, decision, quote_evidence, etc., de
  cada vídeo procesado en cada run, accesible meses después desde
  cualquier checkout.

### Coste

~15KB/vídeo × 296 ≈ 4-5MB para overnight completo. Trivial.

---

## 6. Auto-aggregate al cierre del run

### Cambio

`run()` invoca automáticamente `aggregate(run_id)` al cerrar el último
batch (excepto en pilots cortos para no contaminar logs). Esto produce
`discard_log.json`, `promote_queue.json`, `pending_updates.json`,
`thesis_candidates.json`, `aggregation_stats.json` — todos commiteables.

### Beneficio

Garantiza que cada overnight deje un audit trail consolidado en git.
El humano puede revisar tras un overnight largo sin tener que recordar
ejecutar `--aggregate` manualmente.

---

## 7. Auto-citation determinista con timestamps

### Problema

El LLM hace corte binario: prosa nueva → update_existing con prosa, o
descarte total. Raramente emite "cita-only update". Resultado: cada vez
que un vídeo cita un concepto sin novedad textual, el timestamp se pierde
para retrieval indirecto vía citations table.

Para retrieval indirecto: el lookup hace match EXACTO de
`(video_id, timestamp_seconds)`. Sin la cita en wiki.db, el chunk queda
huérfano (no resuelve a página vía indirect lane).

### Solución

`auto_generate_citations` opera AL FINAL de `apply_video_output_to_shadow`,
sobre el shadow ya enriquecido (incluye stubs nuevos del sub-agente):

1. **Construye alias_index** del shadow: para cada page, sus aliases +
   canonical_name + page_id + variantes (sin diacríticos, sin paréntesis
   trailing). Aliases <4 chars y blacklist (`el yo`, `ello`, etc.) excluidos.
2. **Escanea summary** con regex word-boundary case-insensitive por cada
   alias. Para cada match: busca el marker `- HH:MM` más cercano hacia
   atrás (idéntico al regex usado por `ariadna/parsers.py`). Esto da el
   timestamp del chunk en Qdrant.
3. **Si no hay marker** (summary atípico): skip silencioso, contador en
   stats. NO emitimos `t=0` (sería ruido en la PK del citations table).
4. **Dedup por (page, video, timestamp)**: cada chunk único = 1 cita.

### Formato compacto

Una línea por (page, video) con N timestamps en lugar de N líneas:

```markdown
## Citations

- **Análisis arquetípico de Tarzán** — chunks: [0:30](https://youtu.be/Tviv4PT0dv8?t=30) · [6:42](https://youtu.be/Tviv4PT0dv8?t=402) · [11:32](https://youtu.be/Tviv4PT0dv8?t=692) · ...
```

Cada `[mm:ss](URL?t=N)` matchea el `YT_CITATION_RE` de `build_wiki_db.py`
→ N entradas separadas en `data/wiki.db:citations` con la misma
`(page_id, video_id)` y distintos `timestamp_seconds`.

### Idempotencia y merge

`_upsert_video_citation_block(page_path, video_id, video_title, new_ts)`:
- Detecta líneas existentes que referencian este `video_id` (formato
  compacto, formato per-line legacy con `?t=N`, formato minimal del
  sub-agente con `video_id: \`XXX\``)
- Extrae timestamps existentes
- Une con `new_ts`, dedup, ordena
- Reemplaza las líneas legacy con UNA línea compacta
- Si la sección `## Citations` no existe, la crea al final del archivo

### Variantes de aliases (resolución robusta)

`_alias_variants(s)` genera:
- Original (`Tarzán (Disney, 1999)`)
- Sin diacríticos (`Tarzan (Disney, 1999)`)
- Sin paréntesis trailing (`Tarzán`, `Tarzan`)

Sin esto, vídeos del corpus que dicen "Tarzán" alone NO matchean la page
con canonical_name "Tarzán (Disney, 1999)". Bug detectado y arreglado en
sesión.

### Resultado validado

Tras `--reapply` de 3 runs piloto sobre 11 vídeos: 341 citas indexadas
en `data/wiki.db`, 99% con timestamp matchable. Top page (tarzan-1999-film)
con 24 citas distintas → 24 chunks recuperables vía indirect lane.

---

## 8. Dedup pre-sub-agente para overnight eficiente

### Problema

El main emite `canonical_guess: "Tarzán (Disney, 1999)"` (forma humana).
La page existente es `tarzan-1999-film` (kebab-case). El check
`_shadow_path_for_page_id` no encontraba la page existente porque
comparaba el page_id raw del main (no kebab) con el frontmatter (kebab).
→ Disparaba sub-agente innecesariamente. En 296 vídeos overnight =
decenas de invocaciones desperdiciadas.

### Solución

Pre-cargar `alias_map` y resolver el candidate page_id antes del check:

```python
canonical_pid = alias_map.get(page_id.lower())
if canonical_pid:
    page_id = canonical_pid  # "Tarzán (Disney, 1999)" → "tarzan-1999-film"
target = _shadow_path_for_page_id(shadow, page_id, page_type)
if target.exists():
    stats["stubs_skipped_existing"] += 1
    continue  # skip sub-agente
```

Validado: en `--reapply` post-fix se observan 0 sub-agente invocations
para JSONs cuyas pages ya existen.

---

## 9. Fallback chunk → video en retrieval indirecto

### Problema

Even after auto-citation, un vídeo de 2h con 80 chunks no tendrá cita
exacta en TODOS los chunks. Si el alias canonical_name no aparece literal
en un chunk concreto (aunque temáticamente sea relevante), el chunk no
matchea ninguna page vía exact lookup `(video_id, timestamp_seconds)`.

### Diseño confirmado con usuario

Two-pass lookup en `_lookup_wiki_via_citations`:

1. **Pass 1 (exact)**: lookup directo `(video_id, ts)`. Match → score
   completo, `match_strength='exact'`.
2. **Pass 2 (fallback)**: para chunks que no hallaron exact match Y con
   `dense_score >= CITATION_LOOKUP_VIDEO_FALLBACK_MIN_SCORE` (0.60), busca
   pages citadas POR EL MISMO VÍDEO (cualquier timestamp).
   - Score efectivo = `chunk_score * CITATION_VIDEO_FALLBACK_SCORE_MULTIPLIER` (0.3)
   - `match_strength='video_only'`
   - Skip si la page ya entró por exact match para el mismo vídeo

### Decisiones de calibración

- **Threshold pass 2 más estricto** (0.60 vs 0.55): pass 2 amplifica
  matches débiles → exigimos que el chunk en sí sea genuinamente
  relevante antes de heredar wikis del vídeo entero.
- **Penalty multiplicativo 0.3**: garantiza que un video-only match con
  chunk_score 0.7 (→ 0.21) no rebase un exact match con chunk_score 0.6
  (→ 0.6) en el ranking.
- **No duplicación**: si una page tiene exact match para el vídeo, los
  chunks vecinos del mismo vídeo no añaden la page con score reducido.
  Filtra ruido sin perder señal.

### match_via expuesto al cliente

En el output MCP cada wiki page lleva uno de:
- `semantic` — solo entró por similitud focal
- `citation` — solo entró por exact citation lookup (con o sin chunks
  video-only adicionales)
- `citation_video` — solo entró por fallback (sin exact match en ningún
  chunk citante) — señal débil pero útil
- `both` — entró tanto semánticamente como por citation

El LLM/UI puede usar este field para juzgar la fuerza del vínculo.

### Telemetría

Nuevos campos en `retrieval_metadata`:
- `wiki_via_citation_count` (total: exact + video_only + both)
- `wiki_via_citation_exact_count` (subset)
- `wiki_via_citation_video_only_count` (subset)

### Implementación

`ariadna/search.py`:
- Constantes `CITATION_LOOKUP_VIDEO_FALLBACK_MIN_SCORE` y
  `CITATION_VIDEO_FALLBACK_SCORE_MULTIPLIER`
- `_lookup_wiki_via_citations` con dos passes
- `_merge_wiki_lanes` distingue `citation` vs `citation_video`
- Test funcional con mock SQLite verifica:
  - exact match → match_strength=exact, effective_score=chunk_score
  - chunk vecino sin cita exacta → match_strength=video_only, effective_score=0.21
  - page con exact match no se duplica con video_only

---

## 9.5 Procesado incremental por defecto

### Problema

Cada `--run-id` arrancaba un state.json fresco. Si lanzabas un overnight
tras pilots, los vídeos ya extraídos se re-procesaban. Para 11 vídeos del
piloto en 296 totales = ~3.7% de tokens duplicados, pero contraviene la
filosofía "procesar 1 vez".

### Solución

`run()` invoca `_collect_processed_video_ids_global()` que escanea TODOS
los `wiki/_meta/extraction_runs/*/` buscando per-video JSONs. Cada vid_id
encontrado en cualquier run previo se skipea automáticamente del run
actual.

Aplica tanto a runs nuevos como a `--resume`. La lista local del state.json
sigue funcionando como segunda capa de control.

### Override: `--reprocess-all`

Para casos donde queremos re-extraer (ej. cambio importante de schema
que invalida los JSONs viejos), añadimos flag explícito que desactiva
el skip global. Default: incremental.

### Resultado

```
$ python scripts/extract_video_themes.py --run-id overnight_<TS>
Incremental: skipped 11 videos already extracted in prior runs (11 JSONs totales en extraction_runs/)
  → para re-procesar todo desde cero: --reprocess-all
Starting run overnight_<TS>: 285 videos
```

285 = 296 - 11 ya procesados. Cero re-trabajo.

---

## 10. Limpieza de deuda técnica

### `wiki/_meta/legacy/`

Movidos: `wiki_control.json`, `coverage_state.json`, `next_batch_ranking.json`.

Razón: pertenecen al pipeline pull-based original (pre-Karpathy).
**No se envían al LLM** y no participan en el flow actual. Se conservan
para histórico auditable y compatibilidad con `scripts/rank_wiki_candidates.py`
(que ahora también escribe en `legacy/`).

`wiki/_meta/legacy/README.md` documenta política y futura eliminación.

### Schema-tolerant aliases

`_alias_get` y `_quote_to_str` en `extract_video_themes.py` aceptan los
nombres alternativos que el LLM emite naturalmente:
- `action` ↔ `decision`
- `target_page_id` ↔ `page_id`
- `new_content_markdown` ↔ `content_proposed`
- `quote_evidence` como string o list[str]

Adopta el output del LLM en vez de pelearse con él. No requiere re-prompt.

### Parser tolerante a preámbulo

`_extract_json_object`: si el LLM emite prosa antes del JSON ("He leído...
{...}"), extraemos el primer `{...}` balanceado. Recupera ~20K tokens de
extracción por vídeo en lugar de tirar el output al fail bin.

### Validación soft por entrada

`parse_and_validate_output` ya no rechaza el vídeo entero si UNA
quote_evidence en discards no matchea literal. En su lugar:
- Drop entry concreta con bad quote → conservar resto
- Solo se rechaza si TODO queda vacío tras filtro (alucinación masiva)

---

## 11. Validación end-to-end (3 pilots)

| Métrica | Valor |
|---|---|
| Pages en wiki | 26 (11 seed + 15 nuevas) |
| Citations indexadas en wiki.db | 341 |
| % citations con timestamp matchable | 99.0% |
| Sub-agentes con éxito | 17/17 (0 failures) |
| Dedup pre-sub-agente trabajando | sí (0 invocaciones redundantes en --reapply) |
| Cross-batch enrichment | sí (tolkien-jrr enriquecido por 3 vídeos distintos) |
| Auto-cita determinista | sí (top page con 24 timestamps en línea compacta) |

---

## 12. Comandos de operación

### Procesar un overnight completo

```bash
python scripts/extract_video_themes.py --run-id overnight_$(date +%Y%m%d_%H%M%S) 2>&1 | tee /tmp/overnight.log
```

Auto-aggregate corre al final. Per-video JSONs commiteables en git.

### Re-aplicar un run sin re-llamar al LLM (cambios de schema, mejora de auto-cite, etc.)

```bash
python scripts/extract_video_themes.py --reapply <run_id>
```

Reconstruye un shadow fresco desde el estado actual del wiki, aplica los
JSONs ya logados, sync + commit. Coste 0 tokens.

### Refrescar `data/wiki.db` tras cambios en wiki/

```bash
python scripts/build_wiki_db.py
```

Lee el wiki actual y reconstruye `pages`, `aliases`, `relations`,
`body_wikilinks`, `citations`. Idempotente.

### Lanzar pilot

```bash
python scripts/extract_video_themes.py --pilot --run-id pilot_<TS>          # 5 vídeos hand-picked v1
python scripts/extract_video_themes.py --pilot-2 --run-id pilot_audit_<TS>  # 5 vídeos audit
```

---

## 13. Checklist post-overnight

1. Verificar `aggregation_stats.json` del run: `flagged_for_review_high`,
   counts de discards por reason_code, `thesis_auto_promoted`,
   `recommended_references`.
2. `python scripts/build_wiki_db.py` → refresh.
3. Inspeccionar pages canónicas (mito-polar, jung-carl-gustav,
   collective-unconscious): citations counts elevados (>50 esperado para
   conceptos centrales).
4. Inspeccionar synthesis pages auto-promovidas (`auto_promoted_synthesis: true`
   en frontmatter) — son las tesis monográficas del canal que el gate §2.4.1
   detectó. Auditar 1-2 manualmente para validar que la calidad del sub-agente
   synthesis es correcta.
5. Inspeccionar `recommended_references.json` del run — bibliografía recomendada
   por el speaker, agrupada por `book_title`. Decidir si renderizar como
   `wiki/_meta/bibliografia-recomendada.md` (post-process aparte).
6. Validar lane indirecta:
   ```python
   sqlite3 data/wiki.db "SELECT page_id, COUNT(*) FROM citations GROUP BY page_id ORDER BY 2 DESC LIMIT 20"
   ```
7. Smoke test del MCP server con queries golden (ver `scripts/test_hybrid.py`).
8. Considerar implementar `scripts/scan_mentions_ledger.py` para
   identificar entidades cumulativamente recurrentes que aún no son
   canonical (foundational singletons retroactivos).

---

## 14. Re-alineación de scope (v0.3) — corrección del sesgo arquetipal-estricto

**Fecha**: 2026-05-02 (noche, post-arranque overnight)

**Diagnóstico del primer arranque overnight** (`overnight_20260502_222302`):
los 5 primeros vídeos producían señal pobre (`applied=0 stubs+=0` en 4 de 5).
Inspección de los JSONs reveló que el problema NO era de pipeline sino de
**scope mal alineado con el canal real**.

### 14.1 Self-statement del canal (referencia editorial)

> "Inside Proxy es un proyecto de divulgación creado desde España, centrado
> en la batalla cultural a través del **liberalismo, la filosofía, la
> psicología cognitiva, la mitología y la neurociencia**."

El scope.md v0.2 cubría sólo psicología junguiana/arquetipal + mitología +
filosofía moral + estudios culturales. Excluía explícitamente psicología
cognitiva y neurociencia (regla 9.b) — **dos pilares declarados del canal**.
Tampoco contemplaba `humanities.philosophy.political` (liberalismo como
tradición intelectual). Resultado: vídeos foundational descartados o
relegados a thesis_candidates esperando firma humana indefinidamente.

### 14.2 Tres fallos estructurales evidenciados

**Caso `e3Aj775Rlw4` (golem-de-cobre, 81 min monográfico sobre cognición vs IA)**:
JSON declara textualmente "Cumple TODOS los criterios §2.4.1 author_thesis...
NO se aplica al wiki sin firma humana". 11 piezas de la tríada cognitiva
(memoria episódica/procedural/semántica/afectiva, hipocampo como índice,
trauma como afectividad fijada, IA como golem) → discard_log. Algunas
explícitas como `out_of_scope_domain` (Von Neumann, Turing, neurogénesis).
**Resultado: vídeo monográfico de tesis original del canal aporta cero al wiki.**

**Caso `wxcSuqipA6s` (diagrama-izq-der, 72 min, vídeo foundational del canal)**:
JSON: "Vídeo foundational del canal: articulación del 'Diagrama de Proxy' —
marco propio para clasificar orientación moral-política según dos ejes
(jerarquía / fundamentalismo moral) con correlato neuropsicológico... NO se
aplica al wiki sin firma humana". `promote_new: []`. BOLD/amígdala/ATV/
orbitofrontal → `out_of_scope_domain`. Rallo/Bastos → `out_of_scope_figure`.
Pablo Iglesias → `passing_mention` (debería ser caso ilustrativo del marco).

**Caso `s0MkondMt1o` (cuento-de-navidad, 119 min)**: `applied=1 stubs+=0`
pese a `promote_new: [{"page_id": "cuento-de-navidad-dickens"...}]` claro.
Bug del flow: el sub-agente no se invocaba porque el código solo iteraba
`entities[]` (`for ent in video_data["entities"]: if decision == "promote_new"`),
pero el LLM emite `promote_new[]` como array top-level frecuentemente.

### 14.3 Cambios en `wiki/_meta/scope.md` (v0.2 → v0.3)

**§1 dividido en incondicionales / condicionados**:
- 1.1 incondicionales: + `humanities.philosophy.political` (liberalismo,
  conservadurismo, anarquismo, marxismo como **tradiciones intelectuales** —
  NO actualidad partidista)
- 1.2 condicionados: `social.psychology.cognitive`,
  `interdisciplinary.cognitive_science`, `natural.neuroscience` — IN solo
  cuando el speaker los articula como marco propio aplicado o sustento
  empírico de tesis psicológico-arquetípica-cultural; OUT cuando aparecen
  como exposición técnica neutra. Tabla operacional con 4 casos de
  decisión.

**§2.4.1 con gate de auto-promoción**:

```
Auto-promote thesis_candidate a synthesis page (sin firma humana) si:
  minutes_sustained >= 30
  AND speaker_authorship_marks.length >= 3
  AND framework_internal_structure.length >= 4

Marca de auditoría: auto_promoted_synthesis: true en frontmatter
```

**§3 reescrita — politiqueo vs análisis político-ideológico**:
sustituye blacklist gruesa ("política española → out") por test
discriminante de 7 reglas operacionales aplicadas en orden + tabla de 12
ejemplos discriminantes + test de la cápsula del tiempo. Distinción central:
mecanismo psicológico/marco aplicado/tradición intelectual → IN; comentario
sobre actualidad partidista (≤12 meses) → OUT.

**§3.4 nueva — recommended_reference**: lane bibliográfica para manuales/
libros que el speaker recomienda como base de estudio del canal (Panksepp,
Redolar, Hamilton, DSM-5). Antes caían como `out_of_scope_domain` y se
enterraban; ahora se capturan en lane separada con campos estructurados
(book_title, authors, domain, why_recommended, timestamp).

**§5 + 2 entradas**: "Diagrama de Proxy", "Mitología propia/impropia
(re-articulación)".

### 14.4 Cambios en `scripts/extract_video_themes.py`

**Regla 9 reescrita**: criterio funcional vs blacklist rígida. 5 sub-reglas
(scope §3.3 incondicionales | politiqueo vs análisis | dominios condicionados
| recomendaciones bibliográficas | mención sin lente del canal) con
ejemplos. Regla de oro: "calidad = relevancia + densidad de marco aplicado,
no exhaustividad ni purismo arquetípico".

**Schema OUTPUT_SCHEMA**:

- `discarded[].reason_code`: ampliado con `partisan_commentary`,
  `recommended_reference`, `established_concept_used_as_example`,
  `established_taxonomy`, `in_work_character`, `already_captured`,
  `already_captured_extends_existing`, `captured_in_thesis_candidate`,
  `captured_in_promote_new`, `promotion_threshold_not_met`,
  `internal_framework_reference`, `out_of_scope_figure` (formaliza códigos
  ya en uso ad-hoc).
- `discarded[].enriches_concept`: nuevo, page_id existente al que esta
  mención debe sumar como cita (caso típico: figura política como ejemplo
  del diagrama de Proxy).
- `discarded[].recommended_reference_payload`: nuevo, sub-objeto con
  `book_title`, `authors[]`, `domain`, `why_recommended`,
  `timestamp_seconds`.
- `thesis_candidates[].proposed_page_id`: nuevo, kebab-case sugerido.
- `thesis_candidates[].requires_human_validation`: ahora boolean dinámico
  (false solo si gate cumplido), no literal true.

**Funciones nuevas**:

- `SUBAGENT_SYNTHESIS_SYSTEM_PROMPT`: system prompt del sub-agente
  encargado de construir páginas synthesis a partir de thesis_candidates
  auto-promovidos. Instrucciones específicas: H2 obligatorios "Tesis
  nuclear", "Estructura del marco" (con cada pieza de
  framework_internal_structure), "Citas del vídeo", "Páginas conectadas",
  "Lagunas", "Status auto-promoción".
- `build_subagent_synthesis_user_msg(thesis, video, shadow)`: arma user
  message con scope.md + relation_types.json + page_ids existentes + seed
  example + thesis_candidate completo + speaker_authorship_marks +
  framework_internal_structure + summary_excerpt extenso (~2500 chars).
- `invoke_subagent_for_thesis_synthesis(thesis, video, shadow)`: claude -p
  clean session, max_retries=1, devuelve `{frontmatter, body_markdown}` o
  None.
- `_thesis_meets_auto_promote_gate(thesis)`: verificación mecánica del
  gate (minutes>=30 AND marks>=3 AND structure>=4).

**Cambios en `apply_video_output_to_shadow`**:

```
1)   apply pending_updates (igual)
1.5) procesar discarded[].enriches_concept (telemetría — el flow real es
     auto_generate_citations escaneando aliases en summary)
2)   materialize promote_new stubs (sub-agente per candidato)
     SCHEMA-TOLERANT NUEVO: recolecta candidatos de entities[decision=promote_new]
     Y de promote_new[] top-level (era el bug del cuento-navidad)
2.5) AUTO-PROMOTE THESIS NUEVO: para cada thesis_candidate con
     requires_human_validation=false Y gate verificado mecánicamente,
     invoca sub-agente synthesis. Marca auto_promoted_synthesis=true en
     frontmatter para auditoría posterior.
2.6) RECOLECTAR recommended_references[]: extrae discarded[reason_code=
     recommended_reference] al video_data[_collected_recommended_references]
     para el aggregator.
3)   auto_generate_citations (igual)
```

**Aggregator**:

- Nuevo output `recommended_references.json` con estructura agrupada por
  `book_title`, mergeando occurrences de todos los vídeos. Cada bucket:
  `{book_title, authors[], domain, occurrences[{video_id, video_title,
  surface_form, why_recommended, quote_evidence, timestamp_seconds}]}`.
- Stats: `thesis_auto_promoted`, `thesis_pending_human_review`,
  `recommended_references`.
- Schema-tolerant promote_new (mismo fix que en runtime).

**Log per-vídeo en run_session**: añadidos `thesis-auto=N/human-review=M` y
`rec-refs=N` cuando >0.

### 14.5 Bug fix: `promote_new[]` top-level

Pre-fix: `for ent in video_data.get("entities", []): if decision == "promote_new"`.
El LLM frecuentemente emite `promote_new[]` como array top-level (más natural
que poner `decision="promote_new"` dentro de `entities[]`). Resultado: 0
candidatos detectados → 0 sub-agentes invocados → `stubs+=0` pese a tener
promote_new explícito.

Post-fix: schema-tolerant en runtime y aggregator. Recolecta candidatos de
ambas formas (`entities[decision=promote_new]` ∪ `promote_new[]`) en una sola
lista antes del bucle de sub-agente. Aplicado también en `aggregate()` para
que `promote_queue.json` y discard_log tampoco pierdan candidatos.

### 14.6 Validación esperada

Sanity check sobre 4 vídeos test antes de relanzar overnight:

| Vídeo | Lo esperado |
|---|---|
| `e3Aj775Rlw4` (golem-de-cobre 81min) | `thesis-auto=1` + `stubs+=1` (synthesis `cognicion-humana-vs-ia` o similar). Conceptos cognitivos en `captured_in_thesis_candidate`, no `out_of_scope_domain`. |
| `wxcSuqipA6s` (diagrama-izq-der 72min) | `thesis-auto=1` + `stubs+=1` (synthesis `diagrama-de-proxy`). Hitler/Iglesias con `enriches_concept`. BOLD/amígdala como `captured_in_thesis_candidate`. |
| `s0MkondMt1o` (cuento-navidad 119min) | `stubs+=1` (entity_work cuento-de-navidad-dickens) — valida bug fix promote_new top-level. Posible `thesis-auto=1` para marco luterano-católico. |
| `IytpR6sGWXg` (biblioteca-de-babel-ii) | `rec-refs>=2`. Manuales recomendados capturados en lane separada en lugar de enterrados como `out_of_scope_domain`. |

### 14.7 Comandos de operación (run aislado)

```bash
RUN_ID=sanity_v0_3_$(date +%Y%m%d_%H%M%S)

python scripts/extract_video_themes.py --run-id $RUN_ID \
    --video-id e3Aj775Rlw4 --reprocess-all 2>&1 | tee /tmp/sanity.log

python scripts/extract_video_themes.py --resume $RUN_ID \
    --video-id wxcSuqipA6s --reprocess-all 2>&1 | tee -a /tmp/sanity.log

python scripts/extract_video_themes.py --resume $RUN_ID \
    --video-id s0MkondMt1o --reprocess-all 2>&1 | tee -a /tmp/sanity.log

python scripts/extract_video_themes.py --resume $RUN_ID \
    --video-id IytpR6sGWXg --reprocess-all 2>&1 | tee -a /tmp/sanity.log

python scripts/extract_video_themes.py --aggregate $RUN_ID
```

Tras validación, borrar los 4 JSONs viejos del overnight original y relanzar:

```bash
rm wiki/_meta/extraction_runs/overnight_20260502_222302/{e3Aj775Rlw4,wxcSuqipA6s,IytpR6sGWXg,s0MkondMt1o}.json
python scripts/extract_video_themes.py --resume overnight_20260502_222302 \
    2>&1 | tee -a /tmp/overnight.log
```

### 14.8 Trabajo deferred

- Renderizado de `wiki/_meta/bibliografia-recomendada.md` desde
  `recommended_references.json` (post-process script aparte).
- Auditoría manual de las primeras synthesis pages auto-promovidas tras
  overnight.
- Re-procesar vídeos del overnight original con scope viejo si auditoría
  muestra que perdimos señal valiosa (los JSONs ya están commiteados, son
  recuperables sin re-LLM si solo cambia el flow de aplicación).

---

## 15. Protocolo de propagación de cambios — sin patches casuísticos

**Motivación**: durante esta sesión se detectaron varios cambios cuya
propagación a JSONs históricos requería decisiones caso por caso (cuántos
JSONs viejos tienen entradas que con scope nuevo serían `recommended_reference`,
cuántos tienen cuentos leídos en directo descartados con reason_code inventado,
etc.). El usuario flaggó esto como anti-patrón: "si arreglamos algo ha de
propagarse a TODO lo realizado y no casos concretos que yo te comente".

**Solución**: tres comandos del extractor que automatizan la propagación
con criterios uniformes, sin necesidad de auditar manualmente cada run.

### 15.1 `--rebuild-aggregates` (gratis, sin LLM)

```bash
python scripts/extract_video_themes.py --rebuild-aggregates
```

Itera todos los `wiki/_meta/extraction_runs/<run_id>/` y re-corre
`aggregate(run_id)` sobre cada uno. Capta cualquier cambio de:

- Aggregator (nuevo output `recommended_references.json`, schema-tolerant
  `promote_new[]` top-level, stats nuevos como `thesis_auto_promoted`)
- `compute_review_priority()` (criterios de §6 que cambien)
- Cualquier flow que opere sobre JSONs ya escritos

**Cuándo usar**: tras bug fix de aggregator, adición de nuevas lanes que
agreguen desde `discarded[]`, o cambio en cómputo de review priority.

**Coste**: ~1-3 segundos por run. Sin LLM, sin tokens.

### 15.2 `--audit-stale-vs-scope` (gratis, sin LLM)

```bash
python scripts/extract_video_themes.py --audit-stale-vs-scope [--audit-min-stale N]
```

Escanea TODOS los JSONs históricos y aplica heurística para detectar
entradas inconsistentes con `scope.md` actual. Heurística canónica:

- `out_of_scope_domain` con quote/detail matcheando keywords de manual
  recomendado → `recommended_reference`
- `out_of_scope_domain` con quote/detail matcheando neurociencia/
  cognición → `captured_in_thesis_candidate`
- `out_of_scope_domain` o `out_of_scope_figure` con tradición política
  intelectual → `captured_in_thesis_candidate`
- Reason codes inventados por LLM con scope viejo (`story_read_*`,
  `single_video_no_recurrence`, `below_recurrence_threshold`,
  `absorbed_in_promoted_page`, etc.) → flag con motivo
- `passing_mention` con keywords "diagrama"/"cuadrante"/"polariz" →
  candidato a `enriches_concept: diagrama-de-proxy`

**Filtro v0.3-aware**: JSONs que ya fueron procesados con scope v0.3
(detectados por presencia de campos schema v0.3 como
`recommended_reference_payload`, `enriches_concept`, `proposed_page_id`,
o reason_codes formalizados en v0.3) se SKIP — no son stale.

Genera reporte en `wiki/_meta/extraction_runs/_audit_stale_vs_scope.json`
con lista de JSONs flagged, sus stale entries, y new_reason_codes
sugeridos.

**Cuándo usar**: tras cambio de scope.md (versión, dominios, reglas
discriminantes).

**Coste**: ~5 segundos para 25 JSONs. Sin LLM, sin tokens.

### 15.3 `--reprocess-stale` (consume LLM tokens)

```bash
python scripts/extract_video_themes.py --reprocess-stale [--yes] [--audit-min-stale N]
```

Lee el reporte de `--audit-stale-vs-scope` y re-procesa los JSONs flagged
con LLM en un run aislado `reprocess_stale_<TS>`. Pide confirmación
interactiva (a menos que se pase `--yes` para uso scriptado). Borra los
JSONs viejos y crea entradas nuevas con scope actual.

**Cuándo usar**: tras `--audit-stale-vs-scope` cuando el reporte muestra
JSONs cuya re-extracción con scope nuevo aporta señal recuperable.

**Coste**: ~5-10 minutos por vídeo × tokens. Equivalente a una mini-overnight
para los flagged.

### 15.4 Workflow estándar tras cambio de scope

```bash
# 1. Editar scope.md / extract_video_themes.py con cambios deseados
# 2. Subir version: del frontmatter de scope.md (semver)
# 3. Propagar cambios:
python scripts/extract_video_themes.py --rebuild-aggregates    # gratis
python scripts/extract_video_themes.py --audit-stale-vs-scope  # gratis, genera reporte
# 4. Inspeccionar reporte y decidir
python scripts/extract_video_themes.py --reprocess-stale --yes # consume LLM
python scripts/extract_video_themes.py --rebuild-aggregates    # post-reprocess
```

Tras esto, todos los JSONs reflejan el scope actual sin necesidad de
auditar manualmente cada run o cada caso.

### 15.5 Aplicación práctica — propagación scope v0.2 → v0.3

Tras escribir scope v0.3:

- `--rebuild-aggregates` → 5 runs re-aggregated, 0 skipped. `recommended_references` capturado en sanity_v0_3 (18 books) sin re-LLM.
- `--audit-stale-vs-scope` → 25 JSONs escaneados, 7 ya v0.3 (skip), 5 stale flagged:
  - `A2RpbhypYLk` (Biblioteca de Babel I): 11 recommended_reference + 4 cognitive thesis
  - `gB5NoYbdZWk` (Sistema limbicocortical): 18 cognitive thesis
  - `SwEqFdvBI9M` (Otoño de cuentos Lovecraft): 3 entity_work read_in_session
  - `O-kzVFngjAQ` (Tolkien dragones): 4 reason_codes inventados
  - `Tviv4PT0dv8` (Tarzán arquetípico): 3 reason_codes inventados
- `--reprocess-stale --yes` → run aislado `reprocess_stale_<TS>`, 5 vídeos re-procesados con scope v0.3.

### 15.6 Reforma §2.3 — lectura íntegra en directo (v0.3)

Añadido a `wiki/_meta/scope.md` §2.3 nuevo criterio de promoción `entity_work`:

> **Lectura íntegra en directo**: el speaker lee la obra completa o
> sustancialmente completa en sesión directo. La lectura íntegra ES
> contenido del corpus (transcripción del texto del autor en el video),
> no mera mención. La página entity_work se promueve con flag
> `read_in_session: true` en frontmatter, además de la promoción
> automática del autor por §2.2.

Casos típicos: cuentos de Lovecraft leídos completos ("La extraña casa
elevada entre la niebla", "El descendiente", "Aire frío", "El modelo de
Pickman"), capítulos de Borges, textos de Eliade.

Reason_code prohibido: `story_read_no_dedicated_analysis_page` (inventado
por LLM con scope viejo). Si el cuento se lee íntegro → promote_new como
entity_work. Si solo se cita o resume → `passing_mention`.

### 15.7 Detección automática de stale JSONs — heurística

La función `_was_processed_with_scope_v03(data)` detecta si un JSON ya fue
procesado con scope v0.3+ basándose en marcadores del schema:

```python
- discarded[].recommended_reference_payload (objeto)
- discarded[].enriches_concept (campo presente)
- discarded[].reason_code en {recommended_reference, partisan_commentary,
  established_concept_used_as_example, captured_in_thesis_candidate,
  internal_framework_reference}
- thesis_candidates[].requires_human_validation == false
- thesis_candidates[].proposed_page_id (campo presente)
```

Cualquiera de estos marcadores → JSON es v0.3 → skip en audit. Esto
asegura que `--audit-stale-vs-scope` no flaggea como stale los JSONs ya
re-procesados (evita ciclos infinitos de re-procesado).

### 15.8 Limitaciones del protocolo

- La heurística de `_classify_stale_entry` opera sobre patrones regex
  en `surface_form` + `quote_evidence` + `reason_detail`. Puede tener
  falsos positivos (ej. flaggea vídeo monográfico de neuroanatomía técnica
  sin marco propio del canal — al re-procesar con scope v0.3 §1.2
  condicionado, el LLM debería seguir descartando). Esto es OK: el
  re-procesado no garantiza promoción, solo da al LLM la oportunidad de
  decidir bajo scope nuevo.
- La heurística NO detecta **falsos negativos** (entradas que con scope
  nuevo deberían cambiar pero la heurística no las identifica). Para
  cobertura completa habría que extender los patrones regex con cada
  cambio de scope. Workflow: tras reforma de scope, añadir patrones a
  `_STALE_*_PATTERNS` y `_INVENTED_REASON_CODES`.

---

## 16. Recovery de referencias débiles previas — `scan_mentions_ledger.py`

**Motivación**: cuando el sub-agente crea una page nueva (`bueno-gustavo`,
`gisbertocracia`, `cognicion-humana-vs-ia`), solo ve el contexto del vídeo
actual. Pero esa entidad pudo haber aparecido en vídeos anteriores como
`passing_mention`, `out_of_scope_figure`, `promotion_threshold_not_met`,
etc. Esas menciones quedan en `discarded[]` de los JSONs históricos pero
NO migran automáticamente a la page nueva. Resultado: la page recién
creada arranca con menos citas de las que el corpus históricamente la
respaldaría.

**Solución**: script `scripts/scan_mentions_ledger.py` que escanea todos
los JSONs históricos buscando menciones de aliases de pages existentes, y
materializa la "memoria operativa del LLM" como citations recuperables
sin re-llamar al LLM.

### 16.1 Tres modos

```bash
# Modo 1: una page específica (post sub-agente promote_new)
python scripts/scan_mentions_ledger.py --page-id bueno-gustavo

# Modo 2: audit completo de TODAS las pages (qué señal previa hay sin recoger)
python scripts/scan_mentions_ledger.py --audit-all [--min-findings N]

# Modo 3: aplicar (idempotente — _upsert_video_citation_block)
python scripts/scan_mentions_ledger.py --page-id <id> --apply
python scripts/scan_mentions_ledger.py --audit-all --apply
```

### 16.2 Heurística de match

Para cada page:
- Construye `page_terms = {canonical_name, aliases[], page_id_kebab→spaces}` normalizados (lowercase + sin diacríticos + collapse whitespace)
- Aliases con length <4 chars se filtran (evita stop-words tipo "el yo")

Para cada `discarded[]` entry de cada JSON histórico:
- Solo `reason_code in RECOVERABLE_REASON_CODES` (passing_mention, out_of_scope_figure, promotion_threshold_not_met, captured_in_thesis_candidate, in_work_character, established_concept_used_as_example, story_read_no_dedicated_analysis_page, etc.)
- Solo `quote_evidence` con length ≥30 chars (filtra trivia)
- Match: `surface_form` normalizado contiene cualquier `page_term` normalizado

Findings se enriquecen con `timestamp_seconds` cargando el summary del
vídeo y aplicando `_find_chunk_timestamp_for_text` (mismo flow que
auto_generate_citations).

### 16.3 Aplicación idempotente

Reusa `_upsert_video_citation_block` del extractor: si el bloque
`(video_id, video_title, timestamps)` ya existe en la sección Citations
de la page, NO duplica — solo añade timestamps faltantes.

### 16.4 Filtro shadow-aware (fix v0.3.1)

Al `rglob` de `wiki/`, excluye paths bajo `_meta/extraction_runs/` para
no incluir copias del shadow_wiki ni pages de runs en curso. Solo opera
sobre `wiki/{concepts,authors,entities,synthesis}/` real.

### 16.5 Workflow recomendado

```bash
# Tras cualquier overnight con pages nuevas:
python scripts/extract_video_themes.py --rebuild-aggregates
python scripts/scan_mentions_ledger.py --audit-all --apply
python scripts/build_wiki_db.py
```

El audit típicamente detecta pocos findings (~3 pages con señal
recuperable de 45 totales) porque el flow normal del extractor ya promueve
`update_existing` para pages existentes — solo hay gap genuino cuando una
page se crea **después** de menciones débiles previas.

### 16.6 Resultado real del primer overnight v0.3 (2026-05-03 madrugada)

Tras parar Session 9 por quota:

- **Wiki**: 37 → **104 pages** (+67 nuevas)
  - +28 concepts (heroe-truncado, kabbalah, pensamiento-poetico, sindrome-nino-masculino, sofisma-estetico, etc.)
  - +6 authors (bueno-gustavo, frazer, etc.)
  - +20 entity_works (cuentos Lovecraft + el-gran-lebowski + ediciones leídas en directo)
  - +11 synthesis (gisbertocracia, teoria-del-simbolo-en-proxy, golem-de-cobre, diagrama-de-proxy, etc. — la mayoría auto-promovidas)
- **JSONs procesados**: 103 / 296 vídeos del corpus = **35% completado**
- **Pages auto-promovidas como synthesis sin firma humana** (gate §2.4.1 cumplido): >5
- **scan_mentions_ledger audit-all post-overnight**: 1 page con señal débil recuperable (frazer-james-george, ya idempotentemente cubierta)
- **recommended_references agregados**: bibliografía cubriendo los 5 pilares declarados del canal

### 16.7 Optimización SESSION_MAX_VIDEOS (v0.3.2)

Bajado de 22 → **20 vids** + SESSION_MAX_SECONDS subido de 50 → 55min
(margen sobre 20 × ~165s = ~55min). Razón: con 22 vídeos a ~159s/vid
promedio, la mayoría de sessions cortaban por tiempo a las 50min en mid-vid.
Con 20 + 55min, sessions terminan limpiamente por número de vídeos.
