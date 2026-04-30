# Generación de la Wiki estructurada — pipeline completo

> Cómo se construye, mantiene y consulta la wiki de conocimiento. La wiki vive en [`wiki/`](../wiki/) en este mismo repo, en markdown, versionada en git, navegable en Obsidian.

---

## 1. Modelo conceptual

```
Layer 0 — Raw chunks (Qdrant, BGE-M3)
   Fuente de verdad. Inmutable salvo re-curación. Cualquier afirmación
   en Layer 1 cita hacia aquí.

Layer 1 — Wiki estructurada (markdown en wiki/)
   Páginas por entidad / concepto / autor / obra.
   Cada página: frontmatter (metadata estructurada) + prosa (sintetizada
   por LLM, editable por humano) + wikilinks (relaciones explícitas).

Layer 2 — Grafo emergente (gratis, no se construye)
   El conjunto de wikilinks ES el grafo. Obsidian lo visualiza
   automáticamente. Si más adelante hace falta export a Neo4j / RDF /
   JSON-LD: parser trivial sobre los .md.
```

**Principio clave:** Layer 1 y Layer 2 viven en el mismo archivo. No hay sincronización entre wiki y grafo, no hay duplicación, no hay drift. El wiki **es** el grafo.

---

## 2. Estructura del repo wiki

```
wiki/
├── README.md                    ← índice + cómo navegar
├── _meta/
│   ├── compilation_log.json     ← log de compilaciones (qué página, cuándo, qué modelo)
│   ├── pending_review.json      ← páginas auto-generadas pendientes de validación humana
│   └── relation_types.json      ← set canónico de relation types permitidos
├── authors/
│   ├── jung-carl-gustav.md
│   ├── lovecraft-howard.md
│   └── ...
├── entities/
│   ├── works/
│   │   ├── fight-club-1999-film.md
│   │   ├── peter-pan-1953-film.md
│   │   └── ...
│   └── institutions/            ← cuando aplique (universidades, escuelas, corrientes)
├── concepts/
│   ├── shadow-archetype.md
│   ├── hieros-gamos.md
│   ├── individuation.md
│   └── ...
└── synthesis/                   ← análisis temáticos largos cross-conceptos
    ├── mito-moderno-en-proxy.md
    ├── violencia-en-el-corpus.md
    └── critica-consumista.md
```

Cada `.md` es:
- **Legible por humanos** (Obsidian, GitHub, VSCode)
- **Indexable por el RAG** (es markdown, mismo parser que el corpus)
- **Versionado en git** (cada edición es un commit, audit trail completo)
- **Wikilinkable** (`[[shadow-archetype]]` es enlace interno)

---

## 3. Anatomía de una página

### 3.1 Frontmatter (metadata estructurada)

Campos comunes a todas las páginas wiki:

```yaml
---
# Identidad
page_id: shadow-archetype
page_type: concept              # concept | entity_work | author | synthesis
canonical_name: La sombra (arquetipo junguiano)
aliases: [sombra, shadow, sombra junguiana, lo reprimido]

# Taxonomía (OpenAlex Topics + extensiones proxy.contemporary.*)
domain:
  - social.psychology.jungian
  - humanities.philosophy
domain_primary: social.psychology.jungian

# Relaciones tipadas (sustituyen a related_concepts/related_authors/related_works
# que se eliminaron en migración 2026-04-30). Cada relación: {type, to, [citations],
# [note], [weight]}. Set canónico de types en wiki/_meta/relation_types.json.
relations:
  - {type: developed_by,    to: jung-carl-gustav,        note: "dentro de la psicología analítica"}
  - {type: contained_in,    to: collective-unconscious,  note: "uno de sus contenidos centrales"}
  - {type: compared_with,   to: anima-archetype,         note: "complementario en la pareja arquetípica"}
  - {type: exemplified_by,  to: fight-club-1999-film,    weight: canonical, note: "Tyler Durden como prototipo"}

# Trazabilidad
sources_count: 37                    # número de chunks raw que sustentan esta página
last_compiled: 2026-04-29T22:00:00
compiler: claude-opus-4-7
schema_version: 1.0.0
review_status: auto_generated        # auto_generated | human_reviewed | human_curated
last_human_edit: null                # timestamp de la última edición manual
---
```

**Principio sobre el grafo:** la prosa del cuerpo (con `[[wikilinks]]` contextuales) es **fuente de verdad enciclopédica**. `relations[]` en frontmatter es **índice del grafo** derivado de esa prosa — permite consulta estructurada sin perder la fluidez del texto. El validador `scripts/validate_wiki_relations.py` verifica coherencia: cada `to:` resuelve a página existente o candidato conocido, cada `type:` está en `relation_types.json`, y cada `[[wikilink]]` del cuerpo aparece declarado en `relations[]`.

Campos específicos por `page_type`:

| page_type | Campos extra |
|---|---|
| `concept` | `definition_chunks[]` (chunks que mejor definen el concepto) |
| `entity.work` | `subtype`, `year`, `creators[]`, `imdb_id`/`isbn`/`doi` según corresponda |
| `author` | `orcid`, `wikidata_id`, `birth_year`, `death_year`, `as_author_of_sources[]`, `as_subject_of_sources[]` |
| `synthesis` | `concepts_synthesized[]`, `thesis_summary` |

### 3.2 Cuerpo (prosa con wikilinks)

Estructura recomendada para `concept`:

```markdown
# La sombra (arquetipo junguiano)

## Definición
Prosa sintetizada por el LLM a partir de los chunks raw. Marca la
definición canónica con citas a chunks raw concretos.

→ [Análisis arquetípico de Fight Club, 04:47](https://youtu.be/L4zXftKhU6M?t=287)

## Manifestaciones según el corpus

### En análisis de obra
- **[[fight-club-1999-film]]**: Tyler Durden encarna...
  → [Fight Club, 23:05](https://youtu.be/L4zXftKhU6M?t=1385)

### En psicología clínica
- ...

### En cultura/sociedad
- ...

## Relaciones con otros conceptos
- Opuesto complementario de [[anima-archetype]] en la pareja arquetípica
- Su integración es paso clave hacia la [[individuation]]
- Relacionado con [[collective-unconscious]] en tanto contenido transpersonal

## Lagunas detectadas en el corpus
Sección obligatoria. El LLM debe declarar qué aspectos del concepto
NO encuentra cubiertos en los chunks raw recibidos. Honestidad
epistémica que se mantiene del hot path al wiki.

## Fuentes
Lista bibliográfica de los 37 chunks usados, con link clicable.
```

### 3.3 Reglas de wikilinks

- `[[page_id]]` siempre con el `page_id` canónico, no con el `canonical_name`
- Si necesitas display name distinto: `[[page_id|texto a mostrar]]`
- Wikilinks son **relaciones direccionales** (la página origen apunta a la destino)
- Cualquier mención de una entidad/concepto que tenga página propia **debe** ir como wikilink, no como texto plano. El LLM extractor debe forzar esto

---

## 4. Pipeline de generación (cold path)

```
[summary.md de un vídeo] o [chunks de un paper / libro / etc.]
    ↓ recolección
[chunks asociados a un concepto candidato] (top-N por search vectorial sobre vocabulary)
    ↓ extracción
[LLM (Claude Max overnight) con prompt estructurado]
    ↓ JSON intermedio
[entidades + relaciones + claims + lagunas]
    ↓ generador de markdown
[página .md borrador con frontmatter + cuerpo + wikilinks]
    ↓ validación automática
[checks: wikilinks resuelven, dominios válidos, schema OK]
    ↓ persistencia
[wiki/<page_type>/<page_id>.md commiteada]
    ↓ indexación
[embedding + push a Qdrant con source_type=wiki_page]
    ↓ revisión humana (asíncrona)
[edits del propietario en VSCode/Obsidian, marcar review_status]
    ↓ ciclo
[próxima compilación VE las correcciones del humano y NO duplica]
```

### 4.1 Prompt extractor (esquema)

Prompt template para el cold path worker:

```
ROL: Eres un extractor de conocimiento estructurado del corpus Proxy.
Recibes N chunks de markdown que mencionan o desarrollan el concepto/entidad
"<TARGET>". Tu tarea es producir una página wiki en formato JSON
estructurado que luego se convertirá a markdown.

CONTEXTO QUE TE DAMOS:
- TARGET: el concepto/entidad sobre el que escribir
- VOCABULARY: lista de entidades y conceptos canónicos ya existentes
  en wiki/, con sus page_ids. NO inventes nuevos page_ids para algo
  que ya está en VOCABULARY — usa el page_id existente
- DOMAIN_TAXONOMY: lista de dominios canónicos (OpenAlex + proxy.contemporary)
  permitidos. NO inventes dominios fuera de esta lista
- RELATION_TYPES: set canónico de tipos de relación permitidos
- CHUNKS: array de chunks raw, cada uno con su chunk_id y URL

REGLAS ESTRICTAS:
1. Cada afirmación debe rastrear a uno o más chunk_ids concretos
2. Si una afirmación no se sustenta en los chunks recibidos, NO la
   incluyas. Mejor sección "lagunas" que invento
3. Wikilinks: usa page_ids del VOCABULARY. Si encuentras un concepto
   nuevo que NO está en VOCABULARY, anótalo en "new_entities_to_curate"
   pero NO crees página por tu cuenta
4. Domain: solo de DOMAIN_TAXONOMY. Si no hay match, anota
   "domain_gap" para revisión humana
5. Lagunas: sección obligatoria, vacía si no las hay

OUTPUT JSON SCHEMA:
{
  "page_id": str,
  "page_type": enum,
  "canonical_name": str,
  "aliases": [str],
  "domain": [str],
  "domain_primary": str,
  "definition": { "text": str, "citations": [chunk_id] },
  "sections": [
    {
      "heading": str,
      "subsections": [...],
      "claims": [
        { "text": str, "citations": [chunk_id], "wikilinks": [page_id] }
      ]
    }
  ],
  "relations": [
    { "type": relation_type, "to_page_id": str, "citations": [chunk_id] }
  ],
  "lagunas": [str],
  "new_entities_to_curate": [
    { "candidate_name": str, "context": str, "suggested_type": page_type }
  ],
  "domain_gaps": [str],
  "sources_used": [chunk_id]
}
```

### 4.2 Generador de markdown

Script Python que toma el JSON y produce el `.md` con frontmatter + cuerpo. No hay LLM aquí, es plantillado puro. Garantiza:
- Schema consistente del frontmatter
- Sintaxis correcta de wikilinks
- Citas con format estándar `[título (timestamp)](URL)`
- Sección "Fuentes" auto-generada de `sources_used`

### 4.3 Validación automática (gate de calidad)

Antes de commitear a `wiki/`, el script valida:

| Check | Si falla |
|---|---|
| Frontmatter respeta schema | rechazo, log a `_meta/extraction_errors.json` |
| Todos los wikilinks `[[X]]` resuelven a páginas existentes (o están en `new_entities_to_curate`) | rechazo |
| Todos los `domain` están en `data/vocabulary/domains.json` | rechazo |
| Todos los `chunk_id` citados existen en Qdrant | rechazo |
| Sección "Lagunas" presente (puede ser vacía) | rechazo |
| `relation` usa types de `_meta/relation_types.json` | rechazo |

Lo que pasa la validación se commitea con `review_status: auto_generated`. El humano lo promueve a `human_reviewed` cuando lo lee.

### 4.4 Loop iterativo con humano

```
Auto-generación → revisión humana → corrección → próxima auto-generación informada
```

Concretamente:
1. Cold path genera página borrador, va a `_meta/pending_review.json`
2. Humano abre Obsidian / VSCode, lee la página
3. Detecta: "este concepto debería fusionarse con éste" / "esta relación está mal" / "falta esta cita"
4. Edita el `.md` directamente, o renombra el archivo para fusionar entidades
5. Marca en frontmatter `review_status: human_reviewed` y actualiza `last_human_edit`
6. Git commit
7. Próxima compilación recibe en `VOCABULARY` el page_id ya canonizado y NO duplica

**El humano no es cuello de botella, es validador.** Las páginas mal-generadas siguen siendo útiles como borrador; solo bloquean la promoción al estado "human_reviewed" hasta que se revisan.

---

## 5. Set canónico de relation types

Vive en `wiki/_meta/relation_types.json` (v2.0.0 desde 2026-04-30). Cada entry tiene `description`, `from`, `to`, `inverse`. Los `from`/`to` son guía orientativa (qué `page_type` suele aparecer como source/target) — el validador solo emite warning si una relación los viola.

**Tipos canónicos vigentes:**

| Type | Inverso | Uso típico |
|---|---|---|
| `developed_by` | `developed` | Concepto/obra fue formulado por autor |
| `criticizes` | `criticized_by` | Objeción explícita |
| `extends` | `extended_by` | Continuidad/refinamiento |
| `contradicts` | `contradicts` | Conflicto estructural simétrico |
| `inverts` | `inverted_by` | Inversión especular sin contradicción (Lovecraft invierte el animismo arquetípico) |
| `synthesizes` | `synthesized_in` | Integración de múltiples elementos en nueva articulación |
| `exemplifies` | `exemplified_by` | Caso concreto de un arquetipo |
| `manifestation_of` | `manifested_in` | Encarnación cultural de un arquetipo (más estructural que `exemplifies`) |
| `interprets` | `interpreted_by` | Autor lee obra desde marco teórico |
| `based_on` | `basis_of` | Adaptación/derivación |
| `cites` | `cited_by` | Cita explícita |
| `references` | `referenced_by` | Mención sin desarrollo |
| `compared_with` | `compared_with` | Relación simétrica de contraste |
| `contains` | `contained_in` | Parte-todo (el inconsciente colectivo contiene la sombra) |
| `process_of` | `has_process` | X es proceso/dinámica de Y (la individuación es proceso del inconsciente colectivo) |
| `domain_of` | — | Pertenencia a dominio académico |
| `see_also` | `see_also` | Relación no tipificable — usar conservadoramente |

**Campos de cada relación en el frontmatter:**

- `type` (obligatorio): uno de los listados arriba
- `to` (obligatorio): page_id del target. Puede ser página existente o wikilink roto (candidato a futuro batch — el validador lo reporta como warning, no error)
- `citations` (opcional pero recomendado): lista de chunk_ids del corpus que justifican la relación. Formato `youtube:VIDEOID#TIMESTAMP_SECONDS`
- `note` (opcional): matización breve en castellano que captura nuance que el type canónico no captura. Ej: `"inversión del animismo arquetípico"`
- `weight` (opcional): `canonical` | `strong` | `tangential`. Calibra fuerza de la relación

**Política para tipos nuevos:** si el extractor LLM (Fase D) propone un type que no está, lo anota en `_meta/relation_types_proposed.json` para revisión humana. Solo se promueve a `relation_types.json` por commit explícito del propietario. El JSON canónico tiene `policy_notes` con la regla completa.

**Validación:** `python scripts/validate_wiki_relations.py` chequea coherencia. Errores (exit 1): type desconocido, `to` mal formado, falta de `relations[]` en página, presencia de campos legacy (`related_concepts/related_authors/related_works`). Warnings (no bloquean): wikilink roto, combinación from/to inesperada, `[[wikilink]]` del cuerpo no declarado en `relations[]` (drift de coherencia).

---

## 6. Indexación de la wiki en Qdrant

**Decidido (2026-04-30): Modo A focal — un vector por página.** El texto que se embebe es:

```
canonical_name
aliases: ...
dominio: ...
{primer párrafo de la primera sección H2}
conceptos relacionados: ...
```

Razones (evolucionado del descarte de section vectors):

- Embedding del cuerpo entero produce vectores difusos (manifestaciones, lagunas y fuentes diluyen la identidad del concepto)
- Embedding focal captura "qué es X" sin ruido. Un solo vector basta para validar el modo híbrido en queries reales antes de invertir en mayor granularidad
- El "problema del sub-aspecto canónico sin match focal" (que motivaba section vectors) lo resuelve la **lane indirecta vía citations** — sin duplicar índice semántico. Ver §7 y [`ariadna/search.py`](../ariadna/search.py).

Cada wiki_page en Qdrant lleva:

```json
{
  "source_type": "wiki_page",
  "page_id": "shadow-archetype",
  "page_type": "concept",
  "domain_primary": "social.psychology.jungian",
  "review_status": "human_reviewed",
  "relations": [{"type": "developed_by", "to": "jung-carl-gustav"}],
  "relation_targets": ["jung-carl-gustav", "..."],
  "relation_types_present": ["developed_by", "..."],
  "body": "..."
}
```

Esto permite filtrar:
- "solo wiki, solo conceptos" → `source_type=wiki_page AND page_type=concept`
- "solo lo revisado por humano" → `review_status=human_reviewed`
- "solo dominio X" → `domain_primary == "..."`

---

## 7. Hot path híbrido (cómo se consume)

`search_corpus` ejecuta **tres lanes de retrieval** sobre la misma fuente de verdad y las funde en una respuesta única. Implementación: [`ariadna/search.py:Searcher.search_hybrid`](../ariadna/search.py).

```python
def search_hybrid(query, top_k_raw=5, top_k_wiki=3, ...):
    q_vec = embedder.embed_query(query)

    # Lane 1 — semántica raw (chunks por similitud focal)
    raw_results = qdrant.search(
        q_vec, must_not={"source_type": "wiki_page"}, top_k=top_k_raw
    )

    # Lane 2 — semántica wiki (vector focal por página)
    wiki_results = qdrant.search(
        q_vec, must={"source_type": "wiki_page"}, top_k=top_k_wiki
    )

    # Lane 3 — indirecta vía citations
    # Para cada raw_chunk con score >= 0.55, JOIN contra
    # data/wiki.db:citations: si una wiki page lo cita literalmente,
    # entra a wiki_pages[] aunque su focal NO haya hecho match.
    # Lane category-blind por diseño (la wiki no respeta el filtro de categoría).
    citation_hits = lookup_wiki_via_citations(raw_results)

    wiki_pages = merge_wiki_lanes(
        semantic=wiki_results,
        citation_hits=citation_hits,  # match_via ∈ {semantic, citation, both}
    )

    return {
        "wiki_pages": wiki_pages,
        "raw_chunks": raw_results,        # con in_wiki_sources poblado
        "retrieval_metadata": {
            "mode_recommended": "...",    # wiki_dominant, balanced, raw_with_warning, ...
            "wiki_top_score": ...,
            "raw_top_score": ...,
            "wiki_via_citation_count": ...,
        },
    }
```

Schema autoritativo del output: [RESPONSE_FLOW.md §10](RESPONSE_FLOW.md#10-schema-autoritativo-vigente-desde-2026-04-30).

El LLM hot recibe ambos. Su prompt sabe distinguir:
- `raw_chunks` → fuentes primarias, citables vía `cite_markdown` literal
- `wiki_pages[match_via=semantic|both]` → síntesis pre-cocinada que adapta + cita
- `wiki_pages[match_via=citation]` → la página NO matched semánticamente pero cita los chunks que sí; útil cuando la query es sub-aspecto del concepto que el focal no captura

Ventajas sobre RAG puro:
- Para query factual ("qué vídeos hablan de X"): dominan los chunks raw (`mode_recommended: raw_only` o `raw_with_warning`)
- Para query conceptual ("explícame X"): la wiki provee la tesis ya construida (`wiki_dominant` o `balanced`), el LLM solo adapta + cita
- Para sub-aspectos canónicos sin match focal: la lane indirecta los rescata (`raw_with_wiki_via_citation`)
- Si la wiki no tiene cobertura del tema: degrada elegantemente a RAG puro

---

## 8. Bootstrap: por dónde empezar el piloto

Antes de escalar, validar el pipeline con 5 páginas:

1. **Run** [`scripts/bootstrap_taxonomy.py`](../scripts/bootstrap_taxonomy.py) → descarga OpenAlex Topics, deja `data/vocabulary/domains_full.json`
2. **Curar manualmente** las ~80-100 topics que aplican al corpus → `data/vocabulary/domains.json`
3. **Elegir 5 conceptos piloto** representativos (uno por categoría legacy):
   - `shadow-archetype` (psicología junguiana)
   - `mito-moderno` (mitología)
   - `consumismo-critica` (filosofía/crítica cultural)
   - `lovecraft-howard` (autor)
   - `fight-club-1999-film` (obra)
4. **Para cada uno**, recolectar chunks vía `search_corpus` (top-30) + filtros por entity mention
5. **Pasar al LLM extractor** (Claude vía cuota Max)
6. **Validar** automática + revisar manualmente las 5 páginas
7. **Iterar el prompt** hasta que la calidad sea aceptable
8. **Escalar** a los siguientes 20-50 conceptos

**Criterio de éxito del piloto:** al menos 3 de 5 páginas pasan validación automática y revisión humana sin reescritura mayor. Si <3, el prompt necesita refinamiento antes de escalar.

---

## 9. Mantenimiento

### Re-compilación selectiva

Una página debe re-compilarse cuando:
- Aparecen chunks raw nuevos que la mencionan (no estaban en `sources_used`)
- El humano edita y marca `review_status: needs_recompile` (raro)
- El schema_version del extractor sube
- Han pasado >6 meses sin recompilación (sanity check)

Script: `scripts/wiki_recompile_stale.py` corre overnight, decide qué recompilar.

### Detección de drift

Si una query devuelve top-5 chunks raw donde 4 NO están en `sources_used` de la wiki page que también devuelve la query → la wiki está stale para ese concepto. Marcado automático para recompilación.

### Versionado

Cada compilación es un commit. El log en `_meta/compilation_log.json` permite rollback granular si una versión sale mal:

```json
{
  "shadow-archetype": [
    { "compiled_at": "2026-04-29T22:00:00", "compiler": "claude-opus-4-7", "git_sha": "abc123", "sources_count": 37, "review_status": "auto_generated" },
    { "compiled_at": "2026-04-30T10:15:00", "compiler": "human", "git_sha": "def456", "review_status": "human_reviewed", "human_edits": "fusionado con shadow-individual, añadidas citas faltantes" }
  ]
}
```

---

## 10. Relación con otros docs

- [TAXONOMY_PROPOSAL.md](TAXONOMY_PROPOSAL.md) — schema de chunk y de source que la wiki referencia
- [PHASES.md](PHASES.md) — roadmap completo, dónde encaja la wiki
- [ARCHITECTURE.md](ARCHITECTURE.md) — argumentación de por qué wiki-first / KG-emergent
- [scripts/bootstrap_taxonomy.py](../scripts/bootstrap_taxonomy.py) — descarga OpenAlex Topics

---

## 11. Decisiones

### 11.1 Cerradas

- **Profundidad máxima de namespace OpenAlex** → 3 (`group.discipline.school`, ej. `social.psychology.jungian`). Más profundo introduce ramificación caótica. Detalle en [TAXONOMY_PROPOSAL.md §4.4](TAXONOMY_PROPOSAL.md#44-profundidad-y-namespace).
- **¿Wiki en markdown o también en Qdrant?** → Ambas. Markdown en `wiki/` es la fuente de verdad; Qdrant tiene 1 vector focal por página (`source_type=wiki_page`); `data/wiki.db` es índice SQLite derivado. Reconstruibles desde el filesystem.
- **Modo de embedding de la wiki** → Modo A focal (ver §6). Section vectors descartado en favor de la lane indirecta vía citations.
- **Wikilinks en `synthesis/`** → pueden referenciar entidades atómicas y otras síntesis, sin restricción. La validación solo exige que el target resuelva o esté declarado como candidato.

### 11.2 Abiertas

- **Política para detectar y fusionar entidades duplicadas** auto-generadas (ej. `jung-carl` y `jung-carl-gustav`). Provisional: emparejar por similitud + revisión humana en checkpoint. Por implementar cuando se active el cold path masivo.
- **Modelo LLM por defecto para el extractor**: Claude vía cuota Max (calidad) vs Gemini cuota gratis (volumen). A/B testing recomendado con primeros 10 videos del pipeline de cobertura sistemática.

Doc vivo. Cada decisión cerrada se documenta como tal en lugar de tirarse.
