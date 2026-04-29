# Propuesta abierta: taxonomía, metadatos, tags y categorías

> Documento vivo. La calidad del corpus de hoy y la viabilidad de cualquier solución técnica futura (RAG, KAG, LLM Wiki, grafo semántico, agentes especializados) dependen de qué tan exhaustiva y consistente sea esta capa. Mejor sobre-especificar ahora que tener que migrar 6036 chunks dentro de 6 meses.

---

## 1. Por qué este documento existe (y por qué ahora)

Las decisiones que se toman aquí son **las menos reversibles** del proyecto. Como se argumenta en [ARCHITECTURE.md](ARCHITECTURE.md#4-importancia-ahora-de-la-taxonomía-y-el-léxico):

- Cambiar el modelo de embeddings cuesta 30 segundos (re-embedding)
- Cambiar la base vectorial cuesta horas (export/import)
- Cambiar las **categorías** cuesta semanas (re-clasificar el corpus a mano)
- Cambiar el **schema de chunk** rompe el parser y obliga a re-procesar todo

Por eso esta capa merece más rigor que la elección de tecnología.

---

## 2. La realidad multi-fuente (lo que el corpus va a ser)

Hoy el corpus es **288 vídeos de YouTube** del canal Proxy. Eso es la **fuente semilla**, no la fuente final.

El corpus que Ariadna va a tener que servir incluye en cuanto entre Fase D:

| Tipo de fuente | Ejemplos | Volumen estimado | Metadata clave |
|---|---|---|---|
| `youtube_video` | Canal Proxy, otros canales académicos | hoy 288, futuro abierto | video_id, channel, upload_date, duration, transcript_lang |
| `paper` | arXiv, Springer, Nature, JSTOR, preprints | crecimiento abierto | DOI, ORCID(s), journal, año, citations, abstract |
| `book_chapter` | Capítulos sueltos de libros académicos | medio | ISBN, autor, editor, páginas, edición |
| `book` | Libros completos (cuando aplique) | alto por chunk count | ISBN, autor, año, edición |
| `web_article` | Blogs, ensayos, columnas de opinión | alto | URL canónica, autor, fecha, dominio |
| `video_url` | Vídeos no-YouTube (Vimeo, web propio, lectures) | bajo | url, duration, autor/instructor |
| `podcast_episode` | Episodios de podcasts (con transcripción) | medio | podcast, episode_number, host(s), guest(s) |
| `lecture` | Conferencias, charlas grabadas (no podcasts seriados) | bajo | event, speaker, institution, date |
| `thread` | Hilos de Twitter/X, Bluesky, Mastodon | bajo | url, autor, fecha |
| `note` | Anotaciones del propietario, glosas, comentarios curados | bajo | autor (siempre el propietario), fecha |

**Implicación de diseño:** un schema "video-céntrico" como el actual de Fase A NO sirve para esto. El schema tiene que tener:

1. **Una capa común** (todo chunk tiene la misma forma para que el RAG pueda buscarlos juntos)
2. **Una capa específica por tipo de fuente** (cada paper tiene DOI; cada vídeo tiene timestamp; un libro no tiene ninguno de los dos)
3. **Una tabla de fuentes separada** referenciada por `source_id` para evitar duplicar metadata en cada chunk

---

## 3. Schema propuesto — separación chunk / source

### 3.1 Tabla / colección `sources` (una entrada por documento, no por chunk)

Aquí vive todo lo que es **propiedad del documento entero**: autores, fecha, URL, abstract, etc. Un paper de 50 páginas tendrá 1 entrada en `sources` y N entradas en `chunks` apuntando a ella.

#### Campos comunes (todos los source_type)

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `source_id` | str canónico | sí | Formato: `<scheme>:<id>`. Ej: `arxiv:2401.12345`, `doi:10.1038/s41586-024-...`, `youtube:dQw4w9WgXcQ`, `isbn:9788412345678`, `url:sha256(canonical_url)` |
| `source_type` | enum | sí | youtube_video, paper, book_chapter, book, web_article, video_url, podcast_episode, lecture, thread, note |
| `title` | str | sí | Título de la obra |
| `authors` | list[Author] | sí (al menos 1, puede ser "Anónimo" o "Desconocido") | Ver §3.2 |
| `language` | str (BCP 47) | sí | "es", "en", "es-MX", "en-US" |
| `publication_date` | str (ISO 8601, parcial OK) | sí cuando aplique | "2024-03-15" o "2024" si no se sabe el día |
| `canonical_url` | str | recomendable | URL estable. DOI > arXiv > publisher > web |
| `accessed_at` | str (ISO 8601) | sí | Cuándo se ingirió por primera vez en Ariadna |
| `domain` | list[str] (1-N de la taxonomía canónica) | sí | Categorías. Multi-valor permitido |
| `tags` | list[str] | opcional | Etiquetas libres |
| `abstract` | str | opcional pero recomendable | Resumen que el LLM puede usar como contexto rápido |
| `confidence_source` | enum | sí | `peer_reviewed`, `preprint`, `published`, `self_published`, `transcript`, `commentary`. Crucial para el LLM en hot path: "el paper de Nature dice X" pesa diferente a "un blog dice X" |
| `license` | str (SPDX o "unknown") | opcional | "CC-BY-4.0", "all-rights-reserved", "unknown" |
| `ingest_method` | str | sí | `manual_curation`, `markitdown`, `claude_summarizer`, `gemini_extract`, `youtube_transcript_api`, etc. |
| `schema_version` | str (semver) | sí | "1.0.0". Permite migrar gradualmente |

#### Campos específicos por tipo

**Para `paper`:**
| Campo | Tipo | Notas |
|---|---|---|
| `doi` | str | Identificador canónico cuando existe |
| `arxiv_id` | str | "2401.12345" |
| `pmid` | str | PubMed ID |
| `journal` | str | "Nature", "Cell", "PLoS ONE" |
| `volume`, `issue`, `pages` | str | Citation info |
| `references_doi[]` | list[str] | DOIs citados en el paper. Permite construir grafo de citas |
| `cited_by_doi[]` | list[str] | DOIs que citan este paper (vía Semantic Scholar / OpenAlex) |
| `peer_reviewed` | bool | true / false / unknown |
| `keywords[]` | list[str] | Keywords del paper |

**Para `youtube_video`:**
| Campo | Tipo | Notas |
|---|---|---|
| `youtube_id` | str | El ID estable (`dQw4w9WgXcQ`) |
| `channel` | str | "Proxy" |
| `channel_id` | str | ID estable del canal |
| `playlist` | str | Slug de playlist |
| `duration_seconds` | int | Duración total |
| `view_count` | int | Snapshot al ingerir |
| `transcript_source` | enum | `auto_youtube`, `manual`, `whisper`, `proxysummaries` |

**Para `book` / `book_chapter`:**
| Campo | Tipo | Notas |
|---|---|---|
| `isbn` | str | ISBN-13 preferido |
| `publisher` | str | Editorial |
| `edition` | str | "1st", "2nd revised" |
| `chapter_number` | int | Solo si chunk_type = book_chapter |
| `chapter_title` | str | |
| `total_pages` | int | |
| `original_language` | str | Idioma del original si es traducción |
| `translator[]` | list[Author] | |

**Para `web_article`:**
| Campo | Tipo | Notas |
|---|---|---|
| `domain` | str | "elpais.com", "nautil.us" |
| `archived_url` | str | Wayback Machine snapshot (defensa contra link rot) |
| `paywall` | bool | Para saber si la fuente es accesible |

**Para `podcast_episode`:**
| Campo | Tipo | Notas |
|---|---|---|
| `podcast_name` | str | "Lex Fridman Podcast" |
| `episode_number` | int | |
| `hosts[]` | list[Author] | |
| `guests[]` | list[Author] | |
| `duration_seconds` | int | |

### 3.2 Schema de `Author` (entidad reusable, vive en vocabulary)

Los autores no son strings sueltos — son entidades canónicas que pueden aparecer en muchas fuentes. "Carl Jung" es autor de libros, citado en papers, mencionado en vídeos.

```json
{
  "author_id": "jung-carl-gustav",
  "canonical_name": "Carl Gustav Jung",
  "aliases": ["Jung", "C.G. Jung", "Carl Jung"],
  "given_names": "Carl Gustav",
  "family_name": "Jung",
  "orcid": null,
  "wikidata_id": "Q41532",
  "birth_year": 1875,
  "death_year": 1961,
  "primary_domains": ["psicología", "filosofía"],
  "affiliations": ["University of Zurich"],
  "occurrence_count": 47,
  "as_author_of_sources": ["isbn:...", "doi:..."],
  "as_subject_of_sources": ["youtube:...", "doi:..."]
}
```

**Notas:**
- Distinción crítica: `as_author_of` (escribió el doc) vs `as_subject_of` (el doc habla sobre él/ella). El mismo Jung es ambos.
- ORCID (Open Researcher and Contributor ID) es la identidad canónica de autores académicos vivos. Para Jung histórico no aplica; para investigadores actuales, sí.
- Wikidata ID conecta a un grafo abierto, multilingüe.

### 3.3 Tabla / colección `chunks` (varias por source)

Aquí va lo que va al vector DB. **Forma común para todos los tipos** de fuente, lo que permite que el RAG haga search sobre todo el corpus en un solo query.

| Campo | Tipo | Obligatorio | Notas |
|---|---|---|---|
| `chunk_id` | str | sí | Estable. Formato: `<source_id>#<position_id>` |
| `source_id` | str | sí | FK a `sources` |
| `source_type` | enum | sí | Duplicado para filtrar sin join (Qdrant payload) |
| `position` | dict | sí | Localizador específico del tipo (ver §3.4) |
| `position_url` | str | sí | URL clicable que lleva al lugar exacto. Ver §3.4 |
| `title_breadcrumb` | str | sí | "Source title > Section/Chapter > Subsection" para mostrar al usuario |
| `content` | str | sí | El texto del chunk |
| `theme` | str | opcional | Heading o tema del chunk |
| `chunk_type` | enum | sí | `definition`, `analysis`, `example`, `critique`, `cite`, `meta`, `figure_caption`, `equation`, `table` |
| `tags` | list[str] | opcional | Etiquetas libres |
| `entities` | list[entity_ref] | recomendable | `[{"id": "jung-carl-gustav", "role": "subject"}, ...]` |
| `concepts` | list[str] | recomendable | IDs de concepto canónico de vocabulary |
| `confidence` | float [0, 1] | opcional | Certeza del autor (1.0 afirmación, 0.5 hipótesis, 0.0 cita irónica) |
| `language` | str | sí | A nivel chunk porque un paper puede tener fragmentos en otro idioma |
| `embedding_model` | str | sí | "BAAI/bge-m3:1024:dense:v1" — versionado para reembedding selectivo |
| `ingested_at` | str (ISO 8601) | sí | Cuándo este chunk concreto se procesó |
| `chunk_version` | int | sí | Empieza en 1, sube si se re-cura |
| `supersedes` | str (chunk_id) | opcional | Si reemplaza a un chunk antiguo |

### 3.4 Localizador de posición (`position` + `position_url`) por tipo

El gran problema de un corpus heterogéneo: cada tipo tiene su propio "dónde" — vídeos tienen segundos, papers páginas, libros también páginas pero con paginación distinta. Solución: campo `position` con shape específico + `position_url` derivada para clicar.

| source_type | `position` shape | `position_url` ejemplo |
|---|---|---|
| youtube_video | `{"timestamp_seconds": 323, "timestamp_str": "05:23"}` | `https://youtu.be/dQw4w9WgXcQ?t=323` |
| paper | `{"page": 7, "section": "3.2 Methods", "paragraph": 4}` | `https://doi.org/...#page=7` |
| book_chapter | `{"page": 142, "chapter": 5}` | `library://isbn/9788412345678#page=142` (interno, no clicable a internet) |
| web_article | `{"paragraph": 12, "anchor": "section-2"}` | `https://example.com/article#section-2` |
| video_url | `{"timestamp_seconds": 587}` | URL con `?t=587` o anchor según plataforma |
| podcast_episode | `{"timestamp_seconds": 1842}` | depende de plataforma (Spotify, Apple, RSS feed audio) |
| lecture | `{"timestamp_seconds": 2400, "slide": 12}` | URL del vídeo + anchor de slide si hay slides |
| thread | `{"post_index": 3, "post_id": "1234567"}` | URL del post concreto del hilo |
| note | `{"created_at": "2026-04-15T10:30:00"}` | enlace interno a la nota original |

**El RAG no procesa `position` directamente** — el `embedding` de cada chunk va sobre `content` + `theme`. Pero `position_url` es lo que se devuelve al LLM para que cite con enlace clicable, **independiente del tipo de fuente**.

---

## 4. Categorías canónicas (revisitadas para multi-fuente)

Las 5 actuales (`análisis de obra`, `cultura y actualidad`, `filosofía y teoría`, `mitología y religión`, `psicología`) están sesgadas hacia el corpus inicial (vídeos de divulgación). Cuando entren papers serán insuficientes.

**Propuesta:** dos niveles de clasificación, no excluyentes.

### 4.1 Dominios académicos (categoría primaria)

Vocabulario controlado, tomado prestado de taxonomías abiertas como [arXiv categories](https://arxiv.org/category_taxonomy) o [OpenAlex Concepts](https://docs.openalex.org/api-entities/concepts):

- `humanities.philosophy`
- `humanities.literature`
- `humanities.history`
- `humanities.religion`
- `humanities.classics`
- `social.psychology`
- `social.sociology`
- `social.anthropology`
- `social.political_science`
- `social.economics`
- `arts.cinema`
- `arts.literature`
- `arts.music`
- `interdisciplinary.cultural_studies`
- `interdisciplinary.media_studies`
- `interdisciplinary.popular_culture`
- ...

Multi-valor: un chunk puede tener `["social.psychology", "humanities.philosophy"]`.

### 4.2 Las 5 categorías legacy se descartan

Las 5 categorías originales (`análisis de obra`, `cultura y actualidad`, `filosofía y teoría`, `mitología y religión`, `psicología`) eran un **placeholder inicial sobre data de ejemplo** (los summaries del canal Proxy). **No se preservan** como retrocompatibilidad — se reemplazan limpiamente por la taxonomía OpenAlex en la próxima reindexación.

Razón: el corpus de Fase A es data semilla, no compromiso. Mantener un campo legacy `proxy_category` en chunks futuros añadiría ruido permanente al schema sin ningún consumidor real.

### 4.3 Política de multi-categoría

- `domain` es **list[str], multi-valor**, mínimo 1, máximo razonable 3-4
- `domain_primary` es un **str** que apunta al dominio dominante (para UX que muestre "1 categoría principal")
- Sin campo legacy — un chunk se reclasifica con OpenAlex o no es válido

### 4.4 Profundidad y namespace

- **Profundidad máxima 3 niveles**: `group.discipline.school` (ej. `social.psychology.jungian`). Más profundo introduce ramificación caótica que el LLM extractor no respeta consistentemente; para detalle fino usar `concepts[]` (entidad), no la taxonomía
- **Namespace `proxy.contemporary.*`** para conceptos culturales contemporáneos sin entrada en OpenAlex (ej. `proxy.contemporary.wokismo`, `proxy.contemporary.cancelacion`). Claramente separado del académico, así un consumidor sabe distinguir "concepto académico canónico" de "etiqueta cultural curada"

### 4.5 Bootstrap desde OpenAlex Topics

OpenAlex publica gratis su taxonomía completa (~4500 topics jerarquizados, IDs estables, multilingüe) vía API. Es la **fuente de verdad** para `domain` en este proyecto.

- Script: [`scripts/bootstrap_taxonomy.py`](../scripts/bootstrap_taxonomy.py) descarga `data/vocabulary/domains_full.json` con todos los topics
- Curación manual: filtrar a las ~80-100 topics que aplican al corpus → `data/vocabulary/domains.json` (la lista activa)
- Añadir manualmente los `proxy.contemporary.*` que el corpus requiera
- Cuando lleguen papers en Fase D, llegan ya con `domain` de OpenAlex desde Crossref/arXiv → enriquecimiento automático sin trabajo extra

---

## 5. Léxico controlado: vocabulary.json

Hoy no existe. Propuesta de estructura unificada para entidades + conceptos + autores:

```json
{
  "version": "1.0.0",
  "schema_version": "1.0.0",
  "authors": {
    "jung-carl-gustav": { /* ver §3.2 */ }
  },
  "entities_works": {
    "fight-club-novel": {
      "canonical_name": "Fight Club",
      "subtype": "novel",
      "year": 1996,
      "authors": ["palahniuk-chuck"],
      "isbn": "9780393355949",
      "occurrence_count": 23,
      "as_subject_of_sources": ["youtube:abc", "doi:..."]
    },
    "fight-club-1999-film": {
      "canonical_name": "Fight Club",
      "subtype": "film",
      "year": 1999,
      "directors": ["fincher-david"],
      "based_on": "fight-club-novel",
      "imdb_id": "tt0137523",
      "occurrence_count": 35
    }
  },
  "concepts": {
    "shadow-archetype": {
      "canonical_name": "La sombra (arquetipo junguiano)",
      "aliases": ["sombra", "shadow", "sombra junguiana", "lo reprimido"],
      "domain": ["social.psychology", "humanities.philosophy"],
      "related": ["individuation", "collective-unconscious", "anima-archetype"],
      "definition_chunks": ["youtube:abc#287", "doi:...#142"],
      "wikidata_id": "Q1334834"
    }
  },
  "categories_taxonomy": {
    "social.psychology": {
      "label_es": "Psicología",
      "label_en": "Psychology",
      "subcategories": ["jungian", "cognitive", "psychoanalytic", "evolutionary"],
      "parent": "social"
    }
  }
}
```

**Por qué unificar autores + entidades + conceptos:** porque en un paper el autor cita a Jung que escribió un libro que habla de la sombra. Las tres entradas se referencian entre sí. Tenerlas en un mismo namespace evita duplicaciones y permite cross-walks.

---

## 6. Ingesta multi-formato — markitdown

Para Fase D (cold path con voluntarios) la fuente de chunks no será solo summary.md de YouTube. Habrá:

- PDFs de papers académicos (arXiv, Springer, etc.)
- Libros (EPUB, capítulos en PDF)
- Artículos web (con paywall o sin)
- Podcasts (transcripciones, ya sea oficiales o vía Whisper)
- Vídeos no-YouTube (lectures grabadas, etc.)
- Documentos Office (Word, PowerPoint cuando hay slides de conferencia)

**[microsoft/markitdown](https://github.com/microsoft/markitdown)** resuelve la primera milla de esto: **convierte cualquier documento a markdown limpio** con metadata preservada. Soporta:

- PDF (incluyendo OCR para escaneados)
- Office (DOCX, PPTX, XLSX)
- HTML (con lectura limpia de artículos)
- Audio (con Whisper integrado)
- Imágenes (OCR + descripción LLM)
- ZIP, EPUB, otros

### Pipeline cold path con markitdown

```
[doc fuente: paper.pdf]
    ↓ markitdown
[markdown crudo + metadata extraída automáticamente]
    │   - Si es arXiv/DOI: arXiv API + Crossref API → metadata canónica
    │   - Si es scrape web: extraer <meta> tags
    │   - Si es OCR: limpieza de artefactos
    ↓
[LLM con prompt de structuring (Claude / Gemini / GPT)]
    │   - Identifica secciones, headers, autores, citas
    │   - Genera chunks con schema canónico de Ariadna
    │   - Extrae entidades / conceptos contra vocabulary.json
    │   - Asigna domain (categorización canónica)
    ↓
[chunks + source record propuestos]
    ↓ validación
    │   - Si entidades NO están en vocabulary → flag para revisión humana
    │   - Si domain no encaja en taxonomía → flag
    │   - Si DOI / ISBN inválido → flag
    ↓
[POST /ingest al servidor]
    ↓
[corpus enriquecido]
```

### Roles complementarios

| Componente | Hace | No hace |
|---|---|---|
| **markitdown** | doc → markdown limpio | NO crea schema de chunk, NO categoriza, NO genera metadata semántica |
| **APIs externas** (Crossref, arXiv, OpenAlex, Semantic Scholar) | metadata bibliográfica autoritativa por DOI/arXiv | NO chunkea, NO embebe |
| **Cold path worker (LLM)** | markdown → chunks con schema + categorización + extracción de entidades | NO extrae texto de PDFs/Office (lo hace markitdown) |
| **Vocabulary curator (humano + LLM)** | mantiene léxico canónico de autores/conceptos/entidades | NO procesa documentos, NO indexa |

Cada uno hace una cosa, ortogonales.

### Fuentes de metadata bibliográfica autoritativa (gratis)

Antes de pedir al LLM que infiera autores/fecha/journal de un PDF, se debe consultar:

| API | Para | Coste |
|---|---|---|
| [Crossref](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) | DOI → metadata completa (autores con ORCID, journal, fecha, abstract, references) | gratis |
| [arXiv API](https://info.arxiv.org/help/api/index.html) | arXiv ID → metadata + abstract | gratis |
| [OpenAlex](https://docs.openalex.org/) | DOI / título → metadata + grafo de citas + concepts | gratis |
| [Semantic Scholar](https://api.semanticscholar.org/) | DOI / título → metadata + tldr + citas | gratis con rate limit |
| [Open Library](https://openlibrary.org/developers/api) | ISBN → metadata de libro | gratis |
| [OpenLibrary / Wikidata](https://www.wikidata.org/wiki/Wikidata:Data_access) | autor → ORCID, biografía, obras | gratis |

**Esto es importantísimo** porque la metadata extraída por LLM de un PDF es propensa a errores (typos, fechas mal, autores incompletos). La metadata de Crossref es la **fuente de verdad** cuando existe DOI. Solo si no existe DOI, se cae al LLM.

---

## 7. Versioning del schema y migraciones

Cada chunk lleva `schema_version`. Cada source también. Estrategia:

- **Cambios MINOR** (añadir campo opcional, ampliar enum): los chunks viejos siguen valiendo, solo se rellenan campos nuevos al re-procesarlos. No requiere migración masiva.
- **Cambios MAJOR** (renombrar campo, cambiar tipo, romper formato): bump de major, migración explícita, posiblemente re-embedding selectivo.

Cada PR que toque el schema:
1. Bump del semver en `schema_version` constante
2. Migration script que reprocese chunks afectados
3. Update de `vocabulary.json` si afecta a entidades/conceptos
4. Update de este documento con la justificación

---

## 8. Cómo evolucionar este documento

Este doc es un punto de partida, no una especificación cerrada. Se actualiza cuando:

- Se descubre un caso que el schema actual no cubre (chunk no clasificable, entidad ambigua, source_type nuevo)
- Se añade un tipo de fuente no contemplado
- El uso real revela que un campo sobra o falta
- Se decide formalmente saltar a Layer 2 / 3 y se necesita schema más rico

---

## 9. Próximos pasos sugeridos (orden de prioridad)

1. **Decidir si el split sources / chunks ya en Sprint 2** — sin él, ingerir papers se vuelve un parche. Con él, está listo para crecer
2. **Empezar `vocabulary.json` v0.1** con autores + entidades + conceptos del corpus actual (las 30-50 más recurrentes)
3. **Documentar la migración del schema actual** al nuevo: qué campos pasan a `sources`, qué se queda en `chunks`, cómo se rellenan los nuevos para los 6036 chunks existentes
4. **Definir taxonomía de dominios canónicos** (importarla de OpenAlex / arXiv en vez de inventar) — política multi-valor confirmada
5. **Prototipar pipeline cold path con markitdown + Crossref** sobre 1 paper real para validar end-to-end antes de Fase D real
6. **Política de identidad de autores**: ORCID cuando exista; si no, slug del nombre con desambiguación manual

Discusión abierta — este doc se modifica en PRs, no se cierra.
