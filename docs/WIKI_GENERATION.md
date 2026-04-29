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
page_type: concept              # concept | entity | author | work | synthesis
canonical_name: La sombra (arquetipo junguiano)
aliases: [sombra, shadow, sombra junguiana, lo reprimido]

# Taxonomía (OpenAlex Topics + extensiones proxy.contemporary.*)
domain:
  - social.psychology.jungian
  - humanities.philosophy
domain_primary: social.psychology.jungian

# Relaciones explícitas (los wikilinks en el cuerpo también cuentan)
related_concepts:
  - [[anima-archetype]]
  - [[individuation]]
  - [[collective-unconscious]]
related_authors:
  - [[jung-carl-gustav]]

# Trazabilidad
sources_count: 37                    # número de chunks raw que sustentan esta página
last_compiled: 2026-04-29T22:00:00
compiler: claude-opus-4-7
schema_version: 1.0.0
review_status: auto_generated        # auto_generated | human_reviewed | human_curated
last_human_edit: null                # timestamp de la última edición manual
---
```

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

Vive en `wiki/_meta/relation_types.json`. Inicialmente:

```json
{
  "version": "1.0.0",
  "types": {
    "developed_by": "El concepto fue desarrollado/formulado por la entidad X (autor)",
    "criticizes": "El autor o concepto X critica al concepto/autor Y",
    "extends": "El concepto X extiende, refina o profundiza Y",
    "contradicts": "X y Y se contradicen explícitamente",
    "synthesizes": "X integra/sintetiza Y y Z",
    "exemplifies": "X es ejemplo concreto del concepto/arquetipo Y",
    "interprets": "El analista/canal X interpreta la obra Y",
    "based_on": "La obra X está basada en la obra Y",
    "cites": "El paper/obra X cita a Y",
    "references": "El concepto X refiere/menciona a Y sin desarrollarlo",
    "compared_with": "X y Y se contrastan o ponen en relación",
    "manifestation_of": "X es manifestación cultural concreta del arquetipo Y",
    "domain_of": "X pertenece al dominio académico Y",
    "see_also": "X y Y son temas relacionados sin relación tipificada"
  }
}
```

**Política:** si el LLM propone un tipo nuevo que no encaja, lo anota en `_meta/relation_types_proposed.json` para revisión humana. Solo se promueve a `relation_types.json` por commit explícito del propietario.

---

## 6. Indexación de la wiki en Qdrant

Tres modos posibles de embedding (decisión de Sprint):

### Modo A — un vector por página (simple)
- Embed del título + `definition.text` + primera sección
- Pro: 1 vector por página, simple
- Con: páginas largas pierden recall sobre secciones específicas

### Modo B — chunking de páginas como cualquier otro markdown
- Mismo parser que para los summaries originales
- Pro: granular, permite hits en una sección concreta
- Con: pierde la "atomicidad" del concepto

### Modo C — jerárquico (recomendado para Sprint 2)
- 1 vector "concept-level" del título + definition (alto peso para queries conceptuales)
- N vectores por sección secundaria
- Tag `embedding_role: concept | section` permite priorizar concept-level en hot path

Cada chunk del wiki en Qdrant lleva:

```json
{
  "source_type": "wiki_page",
  "page_id": "shadow-archetype",
  "page_type": "concept",
  "embedding_role": "concept",
  "domain": ["social.psychology.jungian"],
  "review_status": "human_reviewed",
  "content": "..."
}
```

Esto permite filtrar:
- "solo wiki, solo conceptos" → `source_type=wiki_page AND page_type=concept`
- "solo lo revisado por humano" → `review_status=human_reviewed`
- "solo dominio X" → `domain CONTAINS "..."`

---

## 7. Hot path híbrido (cómo se consume)

`search_corpus` se extiende para devolver chunks de **dos índices** en paralelo:

```python
def search_corpus(query, top_k=5, ...):
    q_vec = embedder.embed_query(query)

    # Búsqueda en chunks raw (lo de siempre)
    raw_results = qdrant.search(
        q_vec, filter={"source_type": "raw_chunk"}, top_k=top_k
    )

    # Búsqueda en wiki pages (concept-level prioritario)
    wiki_results = qdrant.search(
        q_vec, filter={"source_type": "wiki_page", "embedding_role": "concept"}, top_k=2
    )

    return {
        "raw_chunks": raw_results,
        "wiki_pages": wiki_results,
    }
```

El LLM hot recibe ambos. Su prompt sabe distinguir:
- `raw_chunks` → fuentes primarias, citables al usuario
- `wiki_pages` → síntesis pre-cocinada que puede adaptar

Ventaja sobre RAG puro:
- Para query factual ("qué vídeos hablan de X"): dominan los chunks raw
- Para query conceptual ("explícame X"): la wiki provee la tesis ya construida, el LLM solo adapta + cita
- Si la wiki no tiene página para el tema: degrada elegantemente a RAG puro (chunks solo)

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

## 11. Decisiones aún abiertas

Lista para discusión:

1. **Profundidad máxima de namespace OpenAlex**: 2 (`group.discipline`) o 3 (`group.discipline.school`)?
2. **¿La wiki vive solo en `wiki/` markdown o también hay una colección Qdrant con embeddings desde el día 1?**
3. **Política para detectar y fusionar entidades duplicadas** auto-generadas (ej. `jung-carl` y `jung-carl-gustav`)
4. **Modelo LLM por defecto para el extractor**: Claude (calidad) vs Gemini (cuota gratis grande) vs ambos en A/B
5. **¿Wikilinks en `synthesis/` (síntesis largas) deben apuntar a entidades atómicas o pueden referenciar otras síntesis?**

Doc vivo. Cada decisión cerrada baja a "Política implementada" cuando aplique.
