# Propuesta abierta: taxonomía, metadatos, tags y categorías

> Documento vivo. La calidad del corpus de hoy y la viabilidad de cualquier solución técnica futura (RAG, KAG, LLM Wiki, grafo semántico, agentes especializados) dependen de qué tan exhaustiva y consistente sea esta capa. Mejor sobre-especificar ahora que tener que migrar 6036 chunks dentro de 6 meses.

---

## 1. Por qué este documento existe (y por qué ahora)

Las decisiones que se toman aquí son **las menos reversibles** del proyecto. Como se argumenta en [ARCHITECTURE.md](ARCHITECTURE.md#4-importancia-ahora-de-la-taxonomía-y-el-léxico):

- Cambiar el modelo de embeddings cuesta 30 segundos (re-embedding)
- Cambiar la base vectorial cuesta horas (export/import)
- Cambiar las **categorías** cuesta semanas (re-clasificar 288 vídeos a mano)
- Cambiar el **schema de chunk** rompe el parser y obliga a re-procesar todo el corpus

Por eso esta capa merece más rigor que la elección de tecnología.

---

## 2. Schema actual del chunk (Fase A)

Lo que hoy se persiste por chunk en Qdrant:

| Campo | Tipo | Obligatorio | Ejemplo | Estable? |
|---|---|---|---|---|
| `video_id` | str (YouTube ID) | sí | `"dQw4w9WgXcQ"` | ✅ inmutable |
| `video_title` | str | sí | `"Fight Club: La sombra en Tyler Durden"` | ⚠️ puede cambiar si renombran |
| `timestamp` | str (`MM:SS` o `H:MM:SS`) | sí | `"05:23"` | ✅ |
| `timestamp_seconds` | int | sí | `323` | ✅ |
| `theme` | str (emoji + título tema) | sí | `"🜂 La sombra junguiana en Fight Club"` | ⚠️ varía con curaduría |
| `content` | str (bullets) | sí | `"- Tyler Durden representa..."` | ⚠️ varía con curaduría |
| `category` | str (1 de 5 canónicas) | sí | `"psicología"` | ✅ canónico |
| `playlist` | str (slug) | sí | `"analisis-arquetipico"` | ⚠️ depende de curaduría upstream |
| `channel` | str | sí | `"Proxy"` | ✅ |
| `upload_date` | str (`YYYYMMDD`) | sí | `"20240315"` | ✅ inmutable |
| `duration` | int (segundos) | sí | `3847` | ✅ inmutable |
| `youtube_url` | str | sí | `https://youtu.be/dQw4w9WgXcQ?t=323` | ✅ derivable |

### Categorías canónicas actuales (5)

1. `análisis de obra` — análisis de películas, libros, series
2. `cultura y actualidad` — comentario de eventos, sociedad
3. `filosofía y teoría` — teoría política, ética, filosofía
4. `mitología y religión` — mitos, simbolismo, religión comparada
5. `psicología` — psicología cognitiva, psicoanálisis, junguiano

**Problema conocido:** las categorías son **mutuamente no-exclusivas en la realidad**. Un análisis de Fight Club desde Jung tendría que ser tanto "análisis de obra" como "psicología". Hoy se asigna una sola; perdemos información.

---

## 3. Propuesta abierta de extensión

Cambios sugeridos al schema, agrupados por urgencia. **No es un commit cerrado, es punto de partida para discusión.**

### 3.1 Cambios MÍNIMOS — añadir sin romper (compatible hacia atrás)

Campos nuevos opcionales (chunks viejos sin ellos siguen funcionando):

| Campo | Tipo | Por qué |
|---|---|---|
| `tags` | list[str] | múltiples etiquetas libres por chunk: `["jung", "sombra", "consumismo", "fight-club"]`. Permite cross-cutting sin romper categoría única |
| `entities` | list[dict] | entidades extraídas: `[{"name": "Carl Jung", "type": "person", "canonical_id": "jung-carl"}, ...]`. Base para Layer 2 |
| `concepts` | list[str] | conceptos canónicos: `["arquetipo de la sombra", "individuación", "consumismo crítico"]`. Diferente de tags (más curado) |
| `chunk_type` | enum | `definition`, `analysis`, `example`, `critique`, `cite`, `meta`. Permite filtrar "dame solo definiciones" |
| `confidence` | float (0-1) | nivel de certeza del autor: 1.0 si afirma, 0.5 si especula. Útil para cold path que distingue afirmación de hipótesis |
| `language` | str (BCP 47) | `"es"`, `"en"`, `"es-MX"`. Necesario si el corpus se extiende a otros idiomas |
| `source_type` | enum | `youtube_video`, `paper`, `book_chapter`, `podcast`, `article`. Crucial para Fase D (cold path ingiere PDFs, papers, etc.) |
| `ingested_at` | str (ISO 8601) | timestamp del momento de ingestión. Permite reindex selectivo |
| `ingest_method` | enum | `manual_curation`, `markitdown`, `claude_summarizer`, `gemini_extract`, etc. Trazabilidad de origen |

### 3.2 Cambios INTERMEDIOS — afinar lo que ya hay

| Campo | Cambio propuesto | Por qué |
|---|---|---|
| `category` | mantener canónica + añadir `subcategory` opcional | "análisis de obra > literatura", "psicología > junguiano" |
| `category` | aceptar **multi-categoría** (`primary` + `secondary[]`) | resuelve el problema de Fight Club junguiano |
| `theme` | separar `theme_emoji` y `theme_title` | el emoji es metadata, no contenido. Útil para filtrar |
| `content` | en lugar de string monolítico, list de `bullet_points[]` con metadata por bullet (afirmación, cita, ejemplo, contraste) | granularidad para reasoning fino |

### 3.3 Cambios MAYORES — replantear (riesgo alto, valor alto)

| Cambio | Justificación |
|---|---|
| **Versionado de chunks** (`chunk_version`, `supersedes`) | Permite curar el corpus iterativamente sin perder histórico. Si re-edito un summary, el chunk viejo queda como `superseded_by` el nuevo |
| **Relaciones entre chunks** (`see_also[]`, `contradicts[]`, `expands_on[]`) | Pre-cocina el cross-reference que hoy hace el RAG por similitud. Construye el grafo desde la curación |
| **Embeddings multi-modelo** (vector dense BGE-M3 + vector sparse + vector futuro) | Qdrant lo soporta nativo. Permite hybrid search sin migración |
| **Schema versioned** | Cada chunk lleva `schema_version`. Si en el futuro cambia el schema, los chunks viejos se pueden re-procesar selectivamente |

---

## 4. Léxico controlado: vocabulary.json

Hoy no existe. Propuesta de estructura mínima:

```json
{
  "version": "1.0.0",
  "entities": {
    "jung-carl": {
      "canonical_name": "Carl Gustav Jung",
      "aliases": ["Jung", "C.G. Jung", "Carl Jung", "junguiano (adj.)"],
      "type": "person",
      "wikipedia_url": "https://es.wikipedia.org/wiki/Carl_Gustav_Jung",
      "domain": ["psicología", "filosofía"],
      "occurrences_count": 47
    },
    "fight-club-1999": {
      "canonical_name": "Fight Club",
      "aliases": ["El Club de la Lucha", "Fight Club (1999)", "ECL"],
      "type": "work",
      "subtype": "film",
      "year": 1999,
      "director": ["David Fincher"],
      "based_on": "novel:fight-club-palahniuk-1996",
      "occurrences_count": 23
    }
  },
  "concepts": {
    "la-sombra": {
      "canonical_name": "La sombra (arquetipo)",
      "aliases": ["sombra", "shadow", "sombra junguiana", "lo reprimido"],
      "domain": ["psicología", "junguiano"],
      "related": ["individuación", "inconsciente-colectivo", "ánima"],
      "definition_chunk_id": "abc123_287"
    }
  },
  "categories_taxonomy": {
    "análisis de obra": {
      "subcategories": ["literatura", "cine", "videojuego", "serie"],
      "description": "..."
    }
  }
}
```

**Por qué ahora:** sin léxico controlado, el RAG dense matchea por similitud pero pierde precisión en nombres propios. Layer 2 (entity index) **requiere** esto. Layer 3 (Wiki) lo necesita para wikilinks.

**Mantenimiento:** combinación de:
- Curación humana del propietario
- Extracción automática (NER) del cold path
- Sugerencias del LLM cuando encuentra una entidad nueva en un chunk

---

## 5. Ingesta multi-formato — markitdown

Para Fase D (cold path con voluntarios) la fuente de chunks no será solo summary.md de YouTube. Habrá:

- PDFs de papers académicos
- Libros (EPUB, capítulos en PDF)
- Artículos web
- Podcasts (transcripciones)
- Documentos Office (Word, PowerPoint)

**[microsoft/markitdown](https://github.com/microsoft/markitdown)** resuelve la primera milla de esto: **convierte cualquier documento a markdown limpio** con metadata preservada. Soporta:

- PDF (incluyendo OCR)
- Office (DOCX, PPTX, XLSX)
- HTML
- Audio (con Whisper)
- Imágenes (con OCR + descripción LLM)
- ZIP, EPUB, otros

### Por qué encaja

- **Output canónico**: todo se reduce a markdown estructurado, **el mismo formato del corpus actual**. El parser de Ariadna ya sabe leer markdown
- **Mantenido por Microsoft**: serio, con tests, evolución activa
- **Pipeline cold path**:
  ```
  /queue_analysis paper.pdf
    → worker descarga el PDF
    → markitdown lo convierte a markdown estructurado
    → LLM (Claude / Gemini / GPT) reorganiza en chunks con schema canónico
    → POST al servidor → corpus enriquecido
  ```

### Roles complementarios

| Componente | Hace | No hace |
|---|---|---|
| **markitdown** | doc → markdown limpio | NO crea schema de chunk, NO categoriza, NO genera metadata |
| **Cold path worker (LLM)** | markdown → chunks con schema | NO extrae texto de PDFs/Office (lo hace markitdown) |
| **Vocabulary curator (humano + LLM)** | mantiene léxico canónico | NO procesa documentos, NO indexa |

Cada uno hace una cosa, ortogonales.

### Anotación a futuro

Cuando se implemente Fase D, el worker template debe usar markitdown como primera capa. La arquitectura final del cold path será:

```
[doc fuente]
    ↓ markitdown
[markdown crudo]
    ↓ LLM con prompt de structuring
[chunks con schema canónico]
    ↓ validación contra vocabulary.json
[chunks aprobados]
    ↓ POST /ingest
[corpus enriquecido]
```

---

## 6. Cómo evolucionar este documento

Este doc es un punto de partida, no una especificación cerrada. Se actualiza cuando:

- Se descubre un caso que el schema actual no cubre (chunk no clasificable, entidad ambigua)
- Se añade un tipo de fuente nuevo en cold path (papers, audio, etc.)
- El uso real revela que un campo sobra o falta
- Se decide formalmente saltar a Layer 2 / 3 y se necesita schema más rico

Cada cambio al schema debe ir acompañado de:
1. Migración de chunks existentes (con `schema_version` bump)
2. Update del parser
3. Update del vocabulary.json si afecta a entidades/conceptos
4. Actualización de este documento con la justificación

---

## 7. Próximos pasos sugeridos (orden de prioridad)

1. **Decidir si añadir `tags[]` y `entities[]` ya en Sprint 2** — son cambios mínimos compatibles, base para todo lo demás
2. **Empezar `vocabulary.json`** con las 20-30 entidades / conceptos más recurrentes en el corpus (Jung, Lovecraft, sombra, arquetipo, mito, ...)
3. **Documentar las playlists actuales** y su semántica (¿qué distingue `analisis-arquetipico` de otra playlist?)
4. **Definir política de multi-categoría**: ¿permitir, prohibir, primary+secondary?
5. **Prototipar pipeline cold path con markitdown** sobre 1 paper para validar end-to-end antes de Fase D real

Discusión abierta — este doc se modifica en PRs, no se cierra.
