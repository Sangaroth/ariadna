# Estrategia de cobertura del corpus — wiki orientada a documentación, no a compendio

> ✅ **Estado al 2026-05-02: pipeline IMPLEMENTADO.** Este documento captura la **argumentación original** del cambio de enfoque (pull → push) tras el batch 3. La especificación operativa actual vive en [`docs/EXTRACTION_PIPELINE.md`](EXTRACTION_PIPELINE.md), que es **el documento autoritativo** sobre cómo funciona el pipeline real. Los scripts mencionados (`scripts/extract_video_themes.py` etc.) ya existen, fueron extendidos con patrón Karpathy "LLM Wiki" (index slim + Read on-demand) y sirven al barrido sistemático.
>
> Lee este doc para **entender la motivación**. Lee `EXTRACTION_PIPELINE.md` para **operar** el pipeline.

> Documento que captura el cambio de enfoque tras el batch 3 (2026-04-29). La wiki deja de generarse por demanda del grafo emergente (wikilinks rotos rankeados por recurrencia) y pasa a generarse por **cobertura sistemática del corpus** combinada con priorización inteligente.

---

## 1. Por qué cambiamos

### Lo que hicimos hasta el batch 3

- Batch 1 (piloto): 5 páginas elegidas a mano para validar schema
- Batch 2: 5 páginas elegidas a mano por demanda del grafo emergente
- Batch 3: 1 página por ranking determinista (`scripts/rank_wiki_candidates.py`) con criterio `recurrence + connectivity + domain_diversity`

### El sesgo que detectamos

El ranking determinista filtra por **recurrencia temática** (cuántos chunks distintos del corpus mencionan el candidato). Eso privilegia ejes transversales (sombra, individuación, mito polar) y descarta sistemáticamente:

- **Temas mono-fuente potentes**: un video monográfico sobre "reflejo de orientación", "teoría de la mente clínica" o "una técnica narrativa específica" tiene material denso pero solo 5-8 chunks porque solo lo trata un video. Nunca pasa el filtro `n_chunks ≥ 10`
- **Autores únicos**: un autor citado en un solo video pero con análisis sustancial nunca aparece como wikilink roto (no hay otra página que lo mencione todavía)
- **Obras concretas**: películas tratadas en un solo análisis arquetípico no llegan a tener wikilinks salientes desde otras páginas

Resultado neto: la wiki se sesgaba hacia **compendio de los conceptos más insistentes del canal**, no hacia **documentación del corpus**. Estos son objetivos distintos.

### Crítica del usuario que cierra la decisión

> "288 videos se tratan mil temas distintos, mil autores, películas y más. Priorizar por avg score temático es simplemente filtrar por temas centrales, no documentar corpus. Un video específico tratando cómo funciona el reflejo de orientación tiene mucho peso en el canal pero es poco referenciado."

La wiki tiene que documentar lo que el canal *trata*, no lo que el canal *repite*.

---

## 2. El nuevo enfoque: cobertura combinada

```
Universo de candidatos        =   entidades extraídas de los 288 summaries
                                + wikilinks rotos del grafo emergente

Filtros (declarativos)        →  topic_filters.json descarta bloques irrelevantes
                                  ANTES de entrar al universo

Priorización (no exclusión)   →  ranking_score = f(connectivity, recurrence,
                                  domain_diversity, singularity_bonus)
                                  Una página marginal NO se descarta — se
                                  encola con prioridad menor

Síntesis transversales        →  carpeta wiki/synthesis/ sigue siendo trabajo
                                  curatorial humano, no derivación mecánica
```

### Dos cosas que NO cambian

1. **Las páginas hub transversales** (sombra, individuación, etc.) se siguen formando; de hecho mejor, porque ahora se alimentan con material extraído de TODOS los videos relevantes, no solo los que ya las mencionan como wikilinks
2. **`wiki_control.json`** sigue siendo el registro de páginas compiladas con sus métricas. Lo nuevo (`coverage_state.json`) es complementario: trackea el universo total y el estado del pipeline

### Lo que SÍ cambia

| Antes | Después |
|---|---|
| Universo de candidatos = wikilinks rotos | Universo = entidades de cada summary + wikilinks rotos |
| Viability filter como exclusión (`n ≥ 10, avg ≥ 0.55`) | Viability como modulador de prioridad, no exclusión |
| Compilación a partir de top-N chunks (Qdrant discovery) | Compilación a partir del summary.md completo del video que introdujo el tema (Qdrant queda solo para discovery lateral) |
| 5-10 candidatos por iteración | Cientos de candidatos en cola, procesados por prioridad |

---

## 3. Componentes a implementar

### 3.1 `wiki/_meta/topic_filters.json` — filtro declarativo

Lista editable a mano de patrones que descartan bloques temáticos antes de que entren al universo de candidatos. Escala: bloque (no video entero), excepto en casos `video_overrides` explícitos.

```json
{
  "version": "1.0.0",
  "include_domains": ["social.psychology.*", "humanities.*", "arts.*", "interdisciplinary.*"],
  "exclude_patterns": [
    {
      "pattern": "actualidad política|elecciones|psoe|pp|vox|sumar",
      "reason": "comentario coyuntural sin valor enciclopédico",
      "scope": "block",
      "added_at": "2026-04-29",
      "added_by": "human"
    }
  ],
  "video_overrides": {
    "<video_id>": {"action": "skip_entirely", "reason": "..."}
  }
}
```

Política: cada entrada lleva `reason` y `added_at`. Editable en commits explícitos del propietario. Sin filtros automáticos por LLM (se equivocan silenciosamente).

### 3.2 `scripts/extract_video_themes.py` — pipeline summary → themes

Para cada `summary.md` no procesado:

1. Parsear estructura (timestamps + headings producen bloques temáticos)
2. Por cada bloque: LLM-extractor identifica entidades canónicas (concept / author / work) + dominio estimado
3. Aplicar `topic_filters.json` → bloques filtrados quedan registrados con su razón, no se silencia el descarte
4. Bloques que pasan emiten candidatos `{page_id, source_video_id, source_block_id, dominant_concept, domain_estimated}`
5. Candidatos se acumulan en `coverage_state.json`. Si una entidad ya estaba en el universo, se añade el video como `source_videos[]` y se incrementa cobertura para esa página

Implementación pragmática: el extractor LLM puede ser Claude vía cuota Max (cold path) o Gemini (cuota gratis grande). El script soporta ambos vía flag.

### 3.3 `scripts/rank_wiki_candidates.py` — refactor

Cambia de:
```
universo = wikilinks rotos
filter   = viability (n_chunks, avg_score)
output   = top-K viables
```

A:
```
universo = candidatos en coverage_state.json (NO compiled aún)
score    = 0.30 * connectivity (wikilinks rotos hacia el page_id)
         + 0.20 * recurrence_normalized
         + 0.20 * domain_diversity_bonus
         + 0.15 * singularity_bonus (peso si el video que lo introdujo NO tiene aún representación wiki)
         + 0.15 * source_density (cuánto material denso del summary alimenta esta entidad)
output   = lista completa ordenada (no filtrada). Marca de "viable_for_immediate_compile" si supera umbrales pero NO la usa para excluir
```

Este ranking sigue siendo determinista. Lo que ya no hace: descartar candidatos. Lo que sigue haciendo: poner orden.

### 3.4 `scripts/inventory_summaries.py` — inicialización del estado

One-shot:
1. Leer `<PROXYSUMMARIES_ROOT>/data/playlists/` y popular `coverage_state.inventory.videos[]`
2. Para cada video sin `summary.md` parseable, marcar `status: ingest_error`
3. Sin extracción todavía; solo inventario

Crea la base sobre la que opera `extract_video_themes.py`.

---

## 4. Sistema de control: `wiki/_meta/coverage_state.json`

Único archivo de estado del pipeline. Permite reanudar mecánicamente entre sesiones.

### Schema

```json
{
  "version": "1.0.0",
  "schema_version": "1.0.0",
  "last_updated": "2026-04-29T22:30:00",
  "summaries_root": "<PROXYSUMMARIES_ROOT>/data/playlists",

  "inventory": {
    "total_videos_detected": 0,
    "last_inventoried_at": null,
    "videos": {}
  },

  "candidates": {
    "total_proposed": 0,
    "total_filtered_out": 0,
    "total_compiled": 0,
    "by_page_id": {}
  },

  "pipeline_state": {
    "phase": "not_started",
    "next_action": "Run scripts/inventory_summaries.py",
    "last_resumable_checkpoint": null
  },

  "filtered_blocks_log": []
}
```

### `inventory.videos[<video_id>]` schema

```json
{
  "summary_path": "data/playlists/<playlist>/<video_id>/summary.md",
  "title": "...",
  "playlist": "...",
  "duration_estimated": null,
  "extraction": {
    "status": "pending|themes_extracted|skipped|error",
    "extracted_at": null,
    "blocks_count": 0,
    "themes_proposed": [],
    "themes_filtered_out": [],
    "themes_queued_to_candidates": [],
    "extractor_used": null,
    "extractor_version": null
  },
  "skip": null
}
```

### `candidates.by_page_id[<page_id>]` schema

```json
{
  "page_type": "concept|author|entity_work|synthesis",
  "domain_estimated": "...",
  "source_videos": [{"video_id": "...", "block_ref": "...", "weight": 1.0}],
  "ranking": {
    "score": null,
    "components": {"connectivity": 0, "recurrence": 0, "domain_diversity": 0, "singularity": 0, "source_density": 0},
    "computed_at": null
  },
  "status": "queued|compiling|compiled|merged_into|rejected",
  "compiled_path": null,
  "merged_into": null,
  "rejection_reason": null,
  "history": []
}
```

### `pipeline_state.phase` valores posibles

- `not_started` — inicio
- `inventoried` — todos los videos enumerados, sin extracción aún
- `extracting` — `extract_video_themes.py` en curso (último video procesado en `last_resumable_checkpoint`)
- `extraction_complete` — universo de candidatos completo
- `ranking` — `rank_wiki_candidates.py` ejecutándose
- `compiling_batch` — un batch en compilación; `last_resumable_checkpoint.batch_id` y `current_page_id` permiten reanudar
- `idle_awaiting_review` — esperando revisión humana de un batch antes de cerrar

---

## 5. Protocolo de reanudación entre sesiones

Al iniciar una nueva sesión:

1. Leer `wiki/_meta/coverage_state.json`
2. Mirar `pipeline_state.phase` y `pipeline_state.next_action`
3. Ejecutar la siguiente acción indicada
4. Cada herramienta (`inventory_summaries.py`, `extract_video_themes.py`, `rank_wiki_candidates.py`) actualiza `coverage_state.json` atómicamente con su progreso

### Reanudaciones típicas

| Estado al abrir sesión | Acción siguiente |
|---|---|
| `phase: not_started` | `python scripts/inventory_summaries.py` |
| `phase: inventoried` | `python scripts/extract_video_themes.py --limit 20` (procesar lote) |
| `phase: extracting`, checkpoint vivo | Mismo comando — el script salta videos ya procesados |
| `phase: extraction_complete` | `python scripts/rank_wiki_candidates.py --refresh` |
| `phase: compiling_batch`, checkpoint en página X | Continuar con página X manualmente o relanzar el orquestador del batch |

### Garantías que debe ofrecer cada script

- **Idempotencia**: re-ejecutar no duplica candidatos ni reescribe páginas ya compiladas
- **Atomicidad de escritura**: usar `<file>.tmp` + `os.replace()` para que un kill no deje estado corrupto
- **Logs de descartes**: cada bloque filtrado o candidato rechazado deja entrada en `filtered_blocks_log[]` con razón — auditabilidad total

---

## 6. Cómo se preserva la transversalidad (recordatorio)

La objeción legítima del usuario: "si vamos video-por-video ¿perdemos vista transversal?"

**No.** La transversalidad es **propiedad emergente del proceso de extracción**, no del orden de descubrimiento:

1. **Páginas hub transversales** (sombra, individuación) reciben aportaciones de muchos videos cuando la extracción identifica el concepto en cada uno. La página acumula material en cada nueva pasada del extractor sobre videos que la mencionan
2. **Páginas synthesis** (carpeta `wiki/synthesis/`) son **trabajo curatorial humano explícito** — no se generan mecánicamente. El compilador humano (o cold path con prompt específico) decide qué tema cross-conceptos merece síntesis
3. **El ranking** sigue dando peso fuerte a `connectivity` (cuántas páginas referencian el candidato). Una página altamente conectada se prioriza para compilación temprana, igual que antes — solo que ahora no es la única vía de entrada al universo

Lo que cambia es: **los videos mono-tema dejan de ser invisibles**. Un video sobre "reflejo de orientación" entra al universo en cuanto se extrae, aunque ningún otro lo referencie todavía.

---

## 7. Cuándo está "completa" la wiki

Definición pragmática:

- **Cobertura básica**: ≥1 página por video que pase filtros = ~280 páginas mínimas estimadas
- **Cobertura ampliada**: páginas hub transversales = ~50 conceptos / autores recurrentes
- **Cobertura curatorial**: páginas synthesis = ~10-30 ensayos cross-tema

Total estimado al cerrar: ~350 páginas. La wiki actual tiene 11. Espacio recorrido: ~3%.

Esta cifra confirma que el cold path (Fase D — cola SQLite + workers) deja de ser opcional. A mano no es viable. La estrategia documentada aquí solo es realista con extracción + compilación delegadas a workers asíncronos.

---

## 8. Documentos relacionados

- [WIKI_GENERATION.md](WIKI_GENERATION.md) — pipeline detallado de generación. Sección 4 actualizada para reflejar este enfoque
- [ARCHITECTURE.md](ARCHITECTURE.md) — argumentación de diseño general; el corpus como activo
- [TAXONOMY_PROPOSAL.md](TAXONOMY_PROPOSAL.md) — schema de chunk y source que la extracción usa
- [NEXT_SESSION.md](NEXT_SESSION.md) — estado vivo y próximos pasos; sección "Reanudación" apunta aquí

## 9. Decisiones aún abiertas

1. **Modelo LLM por defecto del extractor**: Claude vía cuota Max vs Gemini cuota gratis. A/B testing recomendado con primeros 10 videos.
2. **Granularidad de bloques**: ¿bloque por timestamp+heading o bloque por sección semántica detectada? Probablemente el primero suficiente para iniciar.
3. **Política de fusión de entidades duplicadas**: el extractor puede proponer `jung-carl` y `jung-carl-gustav` como entidades distintas. Requiere lógica de fusión en `coverage_state.candidates`. Provisional: emparejar por similitud + revisión humana en checkpoint.
4. **Threshold de "viable_for_immediate_compile"**: provisional `n_chunks ≥ 10 AND avg_score ≥ 0.55` (los del filtro actual) — pasan a marca informativa, no exclusión.
5. **Ritmo de pasadas extracción**: ¿procesar 288 videos de una vez (1-2 noches de cold path) o por lotes manuales de 20? La segunda da más control sobre filtros.
