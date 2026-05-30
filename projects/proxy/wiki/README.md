# Wiki estructurada de Ariadna

> Base de conocimiento navegable. Cada página es una unidad atómica (entidad, concepto, autor u obra) generada por LLM a partir de los chunks raw del corpus, validada por humano, versionada en git.

---

## Cómo navegar

- **VSCode**: `Ctrl+P` → escribir nombre de página
- **Obsidian**: abre la carpeta `wiki/` como vault. Activa el grafo (`Ctrl+G`) para ver las relaciones emergentes
- **GitHub**: navegar como cualquier markdown

## Estructura

| Carpeta | Qué contiene |
|---|---|
| [`authors/`](authors/) | Páginas de autores citados o sujetos del corpus (Jung, Lovecraft, ...) |
| [`entities/works/`](entities/works/) | Obras analizadas (películas, libros, juegos, ...) |
| [`entities/institutions/`](entities/institutions/) | Instituciones, escuelas, corrientes (cuando aplique) |
| [`concepts/`](concepts/) | Conceptos canónicos (la sombra, hieros gamos, individuación, ...) |
| [`synthesis/`](synthesis/) | Análisis temáticos largos cross-conceptos |
| [`_meta/`](_meta/) | Metadatos del proceso de compilación (logs, tipos de relación, pendientes de revisión) |

## Cómo se generan las páginas

Pipeline completo en [../docs/WIKI_GENERATION.md](../docs/WIKI_GENERATION.md). Resumen:

```
[chunks raw del corpus]
    ↓ LLM extractor (cold path overnight, Claude Max / Gemini)
[JSON estructurado: entities + relations + claims + lagunas]
    ↓ generador de markdown (script Python plantillado)
[página .md borrador con frontmatter + cuerpo + wikilinks]
    ↓ validación automática
    ↓ commit a esta carpeta con review_status: auto_generated
    ↓ revisión humana asíncrona
    ↓ promote a review_status: human_reviewed
```

## Convenciones

### Identificadores (`page_id`)

- Slug en kebab-case
- Sufijo desambiguador cuando hace falta:
  - `jung-carl-gustav` (no `jung` solo)
  - `fight-club-1999-film` (distingue de la novela `fight-club-novel`)
  - `shadow-archetype` (no `sombra`, evita ambigüedad lingüística)

### Wikilinks

- `[[page_id]]` siempre con el page_id canónico, no con el nombre humano
- `[[page_id|Texto bonito]]` si quieres mostrar otro texto
- Toda mención de una entidad/concepto que tenga página propia debe ir como wikilink, no como texto plano

### Citas a chunks raw

Formato estándar:

```markdown
→ [Título del vídeo (timestamp)](https://youtu.be/VIDEO_ID?t=SECONDS)
```

Cada afirmación de la página debe rastrear a uno o más chunks raw. Las afirmaciones sin cita son inválidas y deben eliminarse.

### Lagunas

Cada página tiene sección `## Lagunas detectadas en el corpus` (puede estar vacía). Si el LLM no encuentra cobertura en los chunks raw para algún aspecto del concepto, lo declara aquí. Honestidad epistémica heredada del hot path.

### Estados de revisión (frontmatter)

- `auto_generated`: borrador generado por LLM, sin revisión humana
- `human_reviewed`: leído y aprobado por humano, posibles ediciones menores
- `human_curated`: editado significativamente por humano, fuente de verdad
- `needs_recompile`: el humano marca que la página debe regenerarse en próximo cold path

## Estado actual

Wiki vacía. Pendiente de:

1. Run [`scripts/bootstrap_taxonomy.py`](../scripts/bootstrap_taxonomy.py) → curar `data/vocabulary/domains.json`
2. Definir set canónico de relation types en `_meta/relation_types.json`
3. Piloto con 5 páginas (uno por categoría) — ver [docs/WIKI_GENERATION.md §8](../docs/WIKI_GENERATION.md)

## Documentación de referencia

- [docs/WIKI_GENERATION.md](../docs/WIKI_GENERATION.md) — pipeline completo
- [docs/TAXONOMY_PROPOSAL.md](../docs/TAXONOMY_PROPOSAL.md) — schema de chunk/source y vocabulary
- [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) — argumentación wiki-first / KG-emergente
- [docs/PHASES.md](../docs/PHASES.md#fase-b--wiki-estructurada-con-kg-emergente-layers-23-fusionadas) — Fase B
