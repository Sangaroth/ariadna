---
version: 0.2.0
schema_version: 1.0.0
last_updated: 2026-05-02
review_status: draft_v0_pending_human_review
purpose: |
  Documento que define el alcance editorial del wiki Ariadna.
  El extractor por-summary lo recibe en el prefijo cached de cada call
  y lo usa para decidir promover / descartar / actualizar páginas.
  Es la "3ª capa de Karpathy": el contrato entre el corpus crudo y la wiki.
---

# Alcance editorial del wiki Ariadna

> **Misión**: documentar **lo que el canal Proxy trata sustantivamente**, no resumir lo que el canal repite. Una entidad/concepto/obra/autor merece página si el canal la **trabaja** (analiza, articula, aplica como marco), no si simplemente la nombra.

---

## 1. Dominios académicos en alcance

Whitelist de dominios OpenAlex (multi-valor permitido por página):

- `social.psychology` y subraíces (especialmente `social.psychology.jungian`, `social.psychology.psychoanalytic`)
- `social.sociology` (cuando aborda crítica cultural, no actualidad coyuntural)
- `humanities.philosophy` (filosofía moral, fenomenología, estructuralismo, ontología)
- `humanities.religion` (mitología comparada, simbolismo religioso, gnosticismo)
- `humanities.literature` (análisis literario, crítica textual)
- `arts.cinema` (películas analizadas como mitos modernos)
- `arts.literature` (autores literarios — Lovecraft, Tolkien, Borges, etc.)
- `interdisciplinary.cultural_studies`
- `interdisciplinary.semiotics`

**Política**: si el extractor estima un domain fuera de esta lista para una entidad candidata, NO descarte automático — flag `domain_out_of_scope: true` para revisión humana en el log.

---

## 2. Tipos de página y criterios de promoción

### 2.1 `concept` (concepto teórico, arquetipo, dinámica psíquica)

Promover si CUALQUIERA de:

- **Recurrencia**: aparece desarrollado (no solo nombrado) en ≥3 vídeos distintos
- **Monográfico**: ≥1 vídeo dedica ≥10 min sostenidos al concepto como tesis central
- **Framing-mark**: el speaker lo presenta como marco analítico que aplica (`"esto lo aplico siempre"`, `"el modelo que uso"`, `"siguiendo a"`)
- **Assumed-prior**: el speaker lo da por hecho sin presentarlo (señal de que es load-bearing aunque no se desarrolle aquí)
- **Connectivity**: ≥3 páginas existentes lo wikilinkan como `[[X]]` (demanda emergente del grafo)
- **Channel-canonical**: aparece en la lista de "channel-specific concepts" (§5)

Ejemplos en wiki actual: `shadow-archetype`, `individuation`, `collective-unconscious`, `hieros-gamos`, `consumismo-critica`, `mito-polar`.

### 2.2 `author` (figura cuyo pensamiento o obra el canal cita o analiza)

Promover si CUALQUIERA de:

- **Whitelist canónica**: figura en `canonical_whitelist.json:authors` (ver §4)
- **Substantive treatment**: ≥10 min de exposición de su pensamiento en ≥1 vídeo
- **Recurrent reference**: nombrado como referencia teórica en ≥3 vídeos
- **Channel-ingested**: el canal ha leído íntegros sus textos en directo (`as_author_of_sources > 0`) → **promoción automática**
- **Foundational citation**: el canal declara su trabajo como influencia directa en el marco propio

Distinción crítica entre dos roles del autor en el corpus:

- `as_subject_of_sources`: el autor es objeto de análisis (ej. Jung — el canal lo expone)
- `as_author_of_sources`: el canal ingiere su obra como input (ej. Lovecraft — cuentos leídos íntegros)

Una misma página captura ambos. La página de Jung tiene `as_author=0` hoy (sus libros no están ingeridos); ese campo se actualiza si Fase D ingiere su obra.

### 2.3 `entity_work` (obra concreta — película, libro, juego, álbum, serie)

Promover si CUALQUIERA de:

- **Análisis dedicado**: ≥1 vídeo monográfico (≥30 min) sobre la obra
- **Caso canónico**: la obra es ejemplo central recurrente de un concepto promovido (ej. Fight Club → shadow-archetype)
- **Connectivity**: ≥3 páginas existentes la wikilinkan
- **Cross-thematic**: análisis fragmentario en ≥4 vídeos donde la obra ilustra distintos arquetipos

NO promover (mantener en `mentions_index.md`):

- Películas/libros mencionados de pasada como ejemplo único
- Recomendaciones culturales sin análisis
- Referencias culturales contextuales sin desarrollo arquetípico

### 2.4 `synthesis` (análisis temático cross-conceptos largo)

Subdivido en dos sub-tipos con políticas distintas. El extractor debe etiquetar cada candidato `synthesis` con `synthesis_subtype: author_thesis | curatorial`.

#### 2.4.1 `author_thesis` — tesis articulada por el canal en un único vídeo

El speaker (Proxy) expone **su propia teoría coherente** sobre algo: teoría de la mente, modelo de cognición arquetípica, clasificación propia de psicosis/neurosis, tipología de mitos, modelo de fenómenos psíquicos. NO es análisis de una obra ni exposición de un concepto académico ya establecido — es articulación original del canal.

**Promueve auto-suggest si CUALQUIERA de**:

- Detectado **marcador de autoría de tesis**: `"mi tesis"`, `"propongo"`, `"yo digo que"`, `"el modelo que elaboro"`, `"mi clasificación de"`, `"como yo lo articulo"`, `"la teoría que defiendo"`, `"vengo elaborando"`
- **Registro pedagógico-expositivo sostenido** ≥20 min sobre un marco teórico (no análisis de obra). Verbos dominantes: clasificar / definir / proponer / distinguir / sistematizar
- **Estructura interna articulada**: numeración explícita de piezas (`"hay tres tipos de"`, `"se divide en cinco"`), sub-conceptos que dependen entre sí
- **Auto-referencia genealógica**: el speaker remite a otros vídeos suyos como construcción acumulativa de un sistema (`"como ya expliqué"`, `"recapitulando lo que vengo elaborando"`)

Cada candidato `author_thesis` lleva en el extracto:

- `quote_evidence[]`: citas literales del summary que justifican cada señal
- `signal_marks_detected[]`: lista de qué señales matched
- `framework_internal_structure`: array de sub-piezas si aplica (`["pieza 1", "pieza 2", ...]`)
- `requires_human_validation: true` (siempre — pase auto a `discard_log:thesis_candidates[]` para revisión, NO se aplica al wiki sin firma humana)

**Distinción frente a `concept`**:

| Caso | Tipo correcto |
|---|---|
| El canal expone qué es la sombra (concepto canon junguiano) | `concept` |
| El canal expone SU clasificación propia de cómo se manifiesta la sombra en cinco patrones | `synthesis_subtype: author_thesis` |
| El canal explica el monomito de Campbell | `concept` o referencia a `viaje-heroe` |
| El canal expone su modelo de cognición arquetípica donde el monomito es una pieza | `synthesis_subtype: author_thesis` |
| El canal habla de mito polar (concepto canal-específico ya nombrado) | `concept` (mito-polar) |
| El canal expone su tesis general sobre los mitos primarios y cómo se relacionan | `synthesis_subtype: author_thesis` |

Regla operativa: si el speaker está **expandiendo / articulando / sistematizando** un marco original, `author_thesis`. Si está **explicando / aplicando** un concepto ya existente (suyo o académico), `concept`.

#### 2.4.2 `curatorial` — síntesis cross-fuentes hilada por humano

Un editor humano integra ≥3 fuentes dispares en un ensayo coherente. Ejemplo: `mito-moderno-en-proxy.md` en su parte que teje Lovecraft + Matrix + Superman.

**No se proponen automáticamente.** El extractor NO sugiere crear páginas `synthesis_subtype: curatorial`. Sí puede sugerir actualizar las existentes con material nuevo del summary que se está procesando.

#### 2.4.3 Páginas synthesis híbridas

Una página existente puede ser híbrida: parte `author_thesis` (la tesis original del canal sobre algo) + parte `curatorial` (cómo el editor la conecta con otras piezas). Cuando el extractor procesa un summary que toca esa página, sólo enriquece la parte `author_thesis` con material nuevo del speaker; la parte curatorial se preserva intacta.

### 2.5 `entity.institution` (escuelas, corrientes, instituciones)

Reservado para futuro. Por ahora cualquier candidato `institution` queda en `review_priority: high`.

---

## 3. Out-of-scope explícito

Lo siguiente NO genera página, NO entra a `mentions_index`, se descarta directo (con log de descarte como cualquier otra entidad — auditable):

| Categoría | Ejemplos | Razón |
|---|---|---|
| Política española coyuntural | PSOE, PP, Vox, Sánchez, Feijóo, Ayuso, elecciones, leyes específicas | Comentario contingente sin valor enciclopédico. Cubierto en `topic_filters.json` |
| Fiscalidad / actualidad económica concreta | Impuestos hosteleros, factura luz, subidas de IVA | Coyuntural. Si hay crítica estructural, va a `consumismo-critica` |
| Meta-canal | "Suscríbete", saludos, moderación del chat, comentarios sobre los directos | Metadata del stream, no contenido |
| Promoción / patrocinio | Patrocinadores, merchandising, promociones | No enciclopédico |
| Anécdotas personales del presentador | Familia, viajes, comidas, gustos privados | Salvo que ilustren un concepto promovido |
| Recomendaciones culturales sin análisis | "Leed esto", "ved esta peli" sin desarrollo | Sin contenido extractable |

---

## 4. Foundational singletons (canonical whitelist)

**Problema que resuelve**: el filtro de frecuencia descarta justo el caso más valioso — figuras fundacionales nombradas pocas veces porque, una vez establecidas, se asumen. Ejemplo: Chomsky mencionado una vez como marco aplicado a lo largo del canal pero invisible para criterios cuantitativos.

**Mecanismo**: lista curada en `wiki/_meta/canonical_whitelist.json`. Toda entidad que matche un entry de la whitelist se promueve automáticamente al primer "substantive mention" (≥3 min discutida) sin necesidad de cumplir umbrales de recurrencia ni connectivity.

**Política de adición a la whitelist**:

- Solo se añade por commit explícito del propietario del repo (no auto-extensión por LLM)
- El extractor puede SUGERIR adiciones marcando `canonical_external_candidate: true` con justificación; quedan en `discard_log.json:promote_to_whitelist_candidates[]` para revisión humana
- Una vez en whitelist, nunca se quita silenciosamente (deprecación explícita con `deprecated_at` + razón)

Ver §6 de este documento para criterios de "qué entra en la whitelist".

---

## 5. Terminología canal-específica (concepts proxy.contemporary)

El canal Proxy mantiene un vocabulario propio que **no coincide siempre con la teoría académica de referencia**. El extractor debe respetar el lenguaje del canal cuando difiere del académico:

| Término del canal | Cómo lo usa el canal | NO confundir con |
|---|---|---|
| **Mitología propia / impropia** | Mito construido sabiéndose mito (propia, ej. Lovecraft) vs mito que no se reconoce como tal (impropia, ej. democracia) | Mito en sentido coloquial |
| **Mito polar** | Estructura mítica masculino/femenino como dipolo cosmogónico — "tercer camino" transformador | Polar = norte/sur geográfico |
| **Mito solar / lunar** | Mito del dios masculino cíclico vs mito de la diosa femenina cíclica — los dos polos cuya conjunción genera el polar | Solar/lunar como adjetivos |
| **Self / sí-mismo** | El canal NO usa "self" como término técnico junguiano explícito; lo articula vía "viaje del héroe + cambio alquímico" | Self junguiano clásico |
| **Ánima sola** | Concepto canal-específico, no en Jung clásico — ánima desconectada de su contraparte | Anima clásica de Jung |
| **Consumismo (crítica del canal)** | Crítica cultural-psicológica desde sustrato moral-tradicional. **NO marxista, NO anti-capitalista clásica** | Crítica al capitalismo de izquierda |
| **Capitalismo como categoría mitológica** | Capitalismo leído como mito moderno, no como sistema económico | Análisis económico |
| **Autotipo** | Categoría del canal: prototipo vaciado de sentido moral (degradación de mito a franquicia) | Autotipo en sentido genérico |
| **Égersis** (NO éxesis) | Despertar/elevación en el mito lunar — terminología precisa del canal (corregida en hieros-gamos) | Éxegesis |

El extractor NO debe "corregir" estos términos al canon académico. Si detecta uso del canal divergente del académico, lo registra como evidencia, no como error.

---

## 6. Criterios para añadir figuras a la whitelist canónica

Una figura entra en `canonical_whitelist.json:authors` si CUALQUIERA de:

- **Pilar disciplinar**: figura central en uno de los dominios en alcance (§1) cuya ausencia en el wiki sería editorialmente extraña
  - Ej. Jung en psicología junguiana (✓ ya en wiki)
  - Ej. Lévi-Strauss en estructuralismo
  - Ej. Eliade en mitología comparada
- **Marco aplicado**: el canal declara explícitamente seguir/aplicar su pensamiento (`"siguiendo a X"`, `"el marco de Y que uso"`)
- **Influencia genealógica**: la figura es referencia obligada para entender otras figuras ya promovidas
  - Ej. Freud como referencia para Jung (Jung está, Freud debería estar si aparece)
- **Lectura íntegra en directo**: el canal ha leído su obra en directo → `as_author_of_sources > 0` (promoción automática vía §2.2)

Una figura NO entra solo por:

- Ser canónica en su disciplina si su disciplina no está en alcance (ej. Newton en física)
- Aparecer una vez como ejemplo ilustrativo sin tratamiento sustantivo
- Ser nombrada como referencia cultural genérica

---

## 7. Convenciones de calidad de página

### 7.1 Lagunas honestas pero acotadas

> **Regla central**: las lagunas hablan de **sub-dimensiones del concepto que el corpus no aborda**, NO de obras/autores que el corpus sí aborda pero el extractor no encontró en su top-K.

Antes de declarar una laguna, el extractor debe verificarla con una query inversa al corpus. Si el corpus tiene material que refutaría la laguna, NO se declara.

| Tipo de laguna | Formato correcto |
|---|---|
| Sub-dimensión no tematizada | "el canal aborda el concepto X en su forma exitosa, no en su forma fallida/disolutiva" |
| Tradición no presente | "ausentes el polar dao, mesoamericano, hindú; el material recuperado se basa en Occidente" |
| Pregunta abierta | "el canal afirma X pero no desarrolla la base evolutiva/empírica" |
| **PROHIBIDO** | "Matrix no aparece" cuando Matrix sí aparece — eso es laguna del extractor, no del corpus |

### 7.2 Citas verificables literales

Cada afirmación de la página rastrea a ≥1 chunk raw del corpus con `cite_markdown` literal. Sin cita → no se incluye, va a la sección "lagunas".

### 7.3 Wikilinks tipados en `relations[]`

Set canónico en `wiki/_meta/relation_types.json` v2.0.0. El cuerpo declara wikilinks `[[X]]` solo cuando hay relación contextual real; el frontmatter `relations[]` es índice del grafo, debe coincidir con el cuerpo.

### 7.4 Vocabulario PROHIBIDO en el cuerpo

Heredado de NEXT_SESSION.md "Convenciones de escritura wiki":

- `"este batch"`, `"de este batch"`, `"del batch"`, `"top-15"`, `"top-N"`
- `"discovery via Qdrant"`, `"cold path"`, `"summary.md"`, `"chunks recuperados"`
- `"Sprint 1/2"`, `"piloto"`, `"sucesivas iteraciones"`
- Cualquier auto-referencia al sistema RAG, al pipeline o al proceso de compilación

El cuerpo es enciclopedia, no diario del proceso.

---

## 8. Ámbito temporal

- El canal sigue produciendo contenido. La wiki se reabre cada vez que llegan summaries nuevos. El extractor debe asumir que TODA página existente puede recibir actualizaciones, nunca que está cerrada
- Las actualizaciones propuestas durante un barrido NO se aplican en vivo — van a `wiki/_meta/pending_updates.json` y se aplican en batch al final de la sesión, tras revisión humana

---

## 9. Modificaciones a este documento

- Cambios al alcance editorial requieren commit explícito con razón en el mensaje
- `version` de frontmatter se sube en cada cambio sustantivo (semver)
- El extractor lee la versión que existe en `main` al inicio del barrido — si cambia mid-barrido, las llamadas posteriores ven la versión nueva (la caché ephemeral se invalida automáticamente al cambiar el byte-prefix)
