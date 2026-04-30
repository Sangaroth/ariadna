# Flujo de respuesta MCP — bondades y 4 ejemplos estructurados

> Documento de validación de la arquitectura híbrida wiki + raw chunks. Antes de implementar, ver con datos concretos cómo funcionaría una respuesta de Ariadna en distintos escenarios. Si la lógica resiste estos 4 casos, la implementación está justificada.

---

## 1. Bondades de la idea (lo que demostramos con los ejemplos)

| # | Bondad | Cómo se manifiesta en los ejemplos |
|---|---|---|
| **B1** | **Trazabilidad total** | Toda afirmación al usuario rastrea hacia un `chunk_id` raw con timestamp clicable. Sin excepciones. La wiki es síntesis, no fuente — la fuente es siempre el raw |
| **B2** | **Decoupling MCP / LLM** | Los JSON de tool result son agnósticos al cliente. GPT-mini, Claude, Gemini o un modelo local consumen exactamente la misma estructura. El cliente decide cómo razonar sobre ella |
| **B3** | **Coste hot path bajo** | Cada query enseña cuántos tokens consume el LLM hot. Cuando hay wiki page que ya hizo la síntesis, el coste cae a la mitad. Cuando no, fallback elegante |
| **B4** | **Lateral recall preservado** | El RAG raw sigue activo en paralelo. Aunque la wiki page no haya incluido un chunk relevante, los chunks raw lo recuperan |
| **B5** | **Cross-reference vía wikilinks tipados** | Las páginas wiki tienen relaciones explícitas (`[[shadow-archetype]]`, `[[consumismo-critica]]`). El LLM puede navegar el grafo en una segunda llamada cuando la query lo requiere |
| **B6** | **Detección de drift automática** | Si los top raw chunks NO están en `sources_used` de la wiki page, el LLM detecta que la wiki está stale. Marca la página para recompilación sin intervención manual |
| **B7** | **Honestidad epistémica heredada** | La wiki tiene sección "Lagunas". Cuando se devuelve, el LLM hereda la declaración honesta de qué NO cubre el corpus |
| **B8** | **Degradación elegante** | Sin wiki page → fallback a raw clásico. Sin raw chunks → admite no saber. El sistema nunca colapsa en modo "no sé qué hacer" |
| **B9** | **Cero síntesis duplicada** | Si la wiki ya respondió la pregunta de fondo, el LLM hot no la re-sintetiza. Solo adapta tono y formato |
| **B10** | **Auditable end-to-end** | Cada respuesta del LLM hot puede verificarse contra: chunks raw citados, wiki pages usadas, scores, tokens consumidos |

### Argumentación de fondo

La idea del modo híbrido no es "consultamos los dos a ver qué sale". Es:

> **Wiki = síntesis pre-cocinada, organizada por concepto canónico.**
> **Raw = fuente de verdad atomizada, organizada por chunk temático.**
>
> Al servir ambos al LLM hot, **cubres dos modos de pregunta a la vez**:
> - Preguntas conceptuales ("explícame X") → la wiki domina
> - Preguntas factuales ("qué vídeos hablan de Y") → el raw domina
>
> El LLM hot decide en cada caso qué pesa más, **pero nunca pierde la opción**.

Esto contrasta con dos extremos:
- **Solo raw**: el LLM hot re-sintetiza desde cero cada vez. Caro, lento, frágil al ruido del retrieval, sin capacidad de cross-reference profunda.
- **Solo wiki**: el LLM hot está limitado a lo que se sintetizó offline. Pierde lateral recall, no detecta drift, falla si la wiki no cubre el tema.

El híbrido **no es un compromiso**, es la combinación de las dos modalidades trabajando cada una en su mejor terreno.

---

## 2. Ejemplo 1 — Query conceptual con cobertura wiki

**Caso típico cuando la wiki está madura para el concepto preguntado.**

### 2.1 Query del usuario en Mattermost

```
sangaroth: Explícame el arquetipo de la sombra según el canal Proxy
```

### 2.2 Decisión del LLM hot (GPT-mini con Reasoning)

> *Razonamiento interno*: pregunta conceptual sobre término técnico junguiano. Debo invocar `search_corpus` para apoyarme en el corpus, no responder con conocimiento general.

### 2.3 Tool call

```json
{
  "tool": "search_corpus",
  "arguments": {
    "query": "arquetipo de la sombra según Jung en Proxy",
    "top_k": 5,
    "domain": "social.psychology.jungian"
  }
}
```

### 2.4 Respuesta MCP (modo híbrido)

> ⚠️ **Schema desactualizado en este ejemplo.** El JSON de abajo refleja la _intención de diseño_ original de 2026-04-29 (campos `frontmatter`, `related_concepts/authors/works`, `raw_chunks_referenced`, `drift_detected`, `all_top_raw_in_wiki_sources`). El **schema real implementado** evolucionó en 2026-04-30: ver **§10 Schema autoritativo (vigente)** al final del documento. Los §2.4, §3.4, §4.4 y §4.7 se conservan por su valor narrativo de tipos de respuesta esperados, pero NO consultar como referencia de campos.


```json
{
  "wiki_pages": [
    {
      "page_id": "shadow-archetype",
      "page_type": "concept",
      "score": 0.78,
      "domain": ["social.psychology.jungian", "humanities.philosophy"],
      "review_status": "human_reviewed",
      "last_compiled": "2026-04-29T22:00:00",
      "sources_used_count": 37,
      "frontmatter": {
        "canonical_name": "La sombra (arquetipo junguiano)",
        "aliases": ["sombra", "shadow", "lo reprimido"],
        "related_concepts": ["[[anima-archetype]]", "[[individuation]]", "[[collective-unconscious]]"],
        "related_authors": ["[[jung-carl-gustav]]"]
      },
      "content": "# La sombra (arquetipo junguiano)\n\n## Definición\nLa sombra es el arquetipo que contiene los aspectos del psiquismo individual que el yo consciente reprime o no reconoce como propios. Desarrollado por [[jung-carl-gustav]], constituye junto con [[anima-archetype]] una de las estructuras fundamentales del [[collective-unconscious]].\n→ [Análisis arquetípico de Fight Club, 04:47](https://youtu.be/L4zXftKhU6M?t=287)\n\n## Manifestaciones según el corpus\n\n### En análisis de obra\n- **[[fight-club-1999-film]]**: Tyler Durden encarna el contenido reprimido del Jack consumista; la violencia como erupción del inconsciente\n  → [Fight Club, 23:05](https://youtu.be/L4zXftKhU6M?t=1385)\n- **[[peter-pan-1953-film]]**: la sombra que se separa del cuerpo es interpretada como manifestación literal del arquetipo escapando al control del yo infantil\n  → [Peter Pan, 12:47](https://youtu.be/...)\n\n### En psicología clínica\n... [contenido omitido por brevedad]\n\n## Lagunas detectadas\n- No hay tratamiento explícito de la sombra colectiva (sombras de grupos sociales o naciones)\n",
      "raw_chunks_referenced": [
        "youtube:L4zXftKhU6M#287",
        "youtube:L4zXftKhU6M#1385",
        "youtube:abc123#762"
      ]
    }
  ],
  "raw_chunks": [
    {
      "chunk_id": "youtube:L4zXftKhU6M#1385",
      "score": 0.65,
      "video_title": "Análisis arquetípico de el club de la lucha",
      "timestamp": "23:05",
      "theme": "🛋️ El vacío existencial y la sociedad de consumo como anestesia",
      "content": "- Jack está completamente vacío porque se ha socializado en un mundo sin objetivos reales\n- El consumismo es una adicción que activa circuitos de dopamina a corto plazo sustituyendo la realización personal",
      "youtube_url": "https://youtu.be/L4zXftKhU6M?t=1385",
      "in_wiki_sources": true
    },
    {
      "chunk_id": "youtube:L4zXftKhU6M#287",
      "score": 0.62,
      "video_title": "Análisis arquetípico de el club de la lucha",
      "timestamp": "04:47",
      "theme": "🜂 La sombra junguiana en Fight Club",
      "content": "- Tyler Durden representa el contenido reprimido del Jack consumista\n- La violencia como erupción del inconsciente\n- Paralelo con el concepto de enantiodromía",
      "youtube_url": "https://youtu.be/L4zXftKhU6M?t=287",
      "in_wiki_sources": true
    },
    {
      "chunk_id": "youtube:peterpan#762",
      "score": 0.58,
      "video_title": "Peter Pan: análisis junguiano",
      "timestamp": "12:47",
      "theme": "🌑 La sombra que escapa",
      "content": "- En Peter Pan la sombra se desprende literalmente del cuerpo\n- Wendy la cose de vuelta: integración del arquetipo\n- Lectura junguiana: paso hacia la individuación",
      "youtube_url": "https://youtu.be/peterpan?t=762",
      "in_wiki_sources": true
    }
  ],
  "retrieval_metadata": {
    "wiki_top_score": 0.78,
    "raw_top_score": 0.65,
    "mode_recommended": "wiki_dominant",
    "drift_detected": false,
    "all_top_raw_in_wiki_sources": true
  }
}
```

### 2.5 Procesamiento del LLM hot

> *Razonamiento*:
> - `wiki_pages[0].score = 0.78` → wiki page muy relevante. Voy a apoyarme principalmente en su síntesis.
> - `retrieval_metadata.drift_detected = false` y `all_top_raw_in_wiki_sources = true` → la wiki está al día, los chunks raw que tengo coinciden con sus fuentes. Confianza alta.
> - La wiki incluye `## Lagunas detectadas` — debo trasladar esa honestidad al usuario.
> - Las URLs raw clicables ya están dentro del `content` de la wiki page. No necesito construirlas yo.

### 2.6 Respuesta final al usuario

```
La sombra es el arquetipo que contiene los aspectos del psiquismo
individual que el yo consciente reprime o no reconoce como propios.
Desarrollado por Carl Jung, constituye junto con el ánima una de las
estructuras fundamentales del inconsciente colectivo.
→ [Fight Club, 04:47](https://youtu.be/L4zXftKhU6M?t=287)

En el corpus Proxy se manifiesta principalmente en:

- **Fight Club**: Tyler Durden encarna el contenido reprimido del Jack
  consumista; la violencia funciona como erupción del inconsciente.
  → [Fight Club, 23:05](https://youtu.be/L4zXftKhU6M?t=1385)

- **Peter Pan**: la sombra se separa literalmente del cuerpo; Wendy
  la cose de vuelta como gesto de individuación.
  → [Peter Pan, 12:47](https://youtu.be/peterpan?t=762)

[NOTA del corpus] El canal no aborda la sombra colectiva (de grupos
sociales o naciones) explícitamente, aunque material adyacente sobre
polarización podría completarse en el futuro.
```

### 2.7 Costes

| Métrica | Valor |
|---|---|
| Tool calls realizados | 1 |
| Tokens enviados al LLM hot | ~1800 (wiki page + 3 raw chunks de verificación) |
| Tokens generados por el LLM hot | ~280 |
| Latencia retrieval | ~45ms (Qdrant + serialize) |
| Latencia total end-to-end | ~2.1s |
| Coste estimado en gpt-5.4-mini | $0.0008 |

### 2.8 Bondades demostradas

- **B1** Trazabilidad: cada afirmación tiene URL clicable a chunk raw
- **B3** Coste bajo: la síntesis ya estaba hecha, el LLM solo adapta (~280 tokens output, no ~700)
- **B6** Sin drift: el sistema lo verifica automáticamente
- **B7** Lagunas heredadas explícitamente
- **B9** Cero síntesis duplicada: la página dice lo que diría el LLM hot pero ya está escrita

---

## 3. Ejemplo 2 — Query factual de listado (la wiki no es la herramienta)

**Caso donde el LLM debe usar otra tool, no `search_corpus`.**

### 3.1 Query del usuario

```
sangaroth: ¿qué vídeos hay del canal sobre Tolkien?
```

### 3.2 Decisión del LLM hot

> *Razonamiento*: pregunta de listado, no conceptual. No tiene sentido buscar páginas wiki (no hay "wiki page de listados"). Debo usar `list_videos` o `search_corpus` con un filtro de palabra clave en título.

### 3.3 Tool call

```json
{
  "tool": "search_corpus",
  "arguments": {
    "query": "Tolkien Señor de los Anillos Hobbit",
    "top_k": 8
  }
}
```

(El LLM elige `search_corpus` y no `list_videos` porque "Tolkien" no es ni `category` ni `playlist` — es búsqueda semántica.)

### 3.4 Respuesta MCP

```json
{
  "wiki_pages": [],
  "raw_chunks": [
    {
      "chunk_id": "youtube:xyz1#0",
      "score": 0.71,
      "video_id": "xyz1",
      "video_title": "Tolkien y el mito moderno: análisis del Señor de los Anillos",
      "timestamp": "00:00",
      "theme": "📚 Introducción: Tolkien como mitógrafo",
      "content": "- ...",
      "youtube_url": "https://youtu.be/xyz1",
      "in_wiki_sources": false
    },
    {
      "chunk_id": "youtube:xyz2#0",
      "score": 0.68,
      "video_id": "xyz2",
      "video_title": "El Hobbit: lectura junguiana",
      "timestamp": "00:00",
      "theme": "🌲 Bilbo y el llamado del héroe",
      "content": "- ...",
      "youtube_url": "https://youtu.be/xyz2",
      "in_wiki_sources": false
    },
    {
      "chunk_id": "youtube:xyz3#125",
      "score": 0.59,
      "video_id": "xyz3",
      "video_title": "Mitología comparada: Tolkien, Lovecraft, Howard",
      "timestamp": "02:05",
      "theme": "🗡️ Tolkien y la creación de mitos modernos",
      "content": "- ...",
      "youtube_url": "https://youtu.be/xyz3?t=125",
      "in_wiki_sources": false
    }
  ],
  "retrieval_metadata": {
    "wiki_top_score": null,
    "raw_top_score": 0.71,
    "mode_recommended": "raw_only",
    "note": "No wiki page about Tolkien yet. Author entity 'tolkien-jrr' is candidate for next compilation cycle."
  }
}
```

### 3.5 Procesamiento del LLM hot

> *Razonamiento*:
> - No hay wiki page para Tolkien. `mode_recommended: raw_only`.
> - Tres vídeos distintos. Los agrupo por video_id para no duplicar.
> - Es pregunta de listado: no tiene sentido razonar conceptualmente. Solo enumero.

### 3.6 Respuesta final al usuario

```
En el corpus Proxy hay tres vídeos que tratan a Tolkien explícitamente:

1. **[Tolkien y el mito moderno: análisis del Señor de los Anillos](https://youtu.be/xyz1)**
   — análisis principal
2. **[El Hobbit: lectura junguiana](https://youtu.be/xyz2)**
   — Bilbo como arquetipo del héroe
3. **[Mitología comparada: Tolkien, Lovecraft, Howard](https://youtu.be/xyz3?t=125)**
   — Tolkien en contexto del mito moderno

[NOTA] No hay todavía una página wiki sintetizada sobre Tolkien como
autor; el corpus está disponible al detalle en los vídeos. Si quieres
profundizar en algún concepto concreto (eucatástrofe, sub-creación,
mitopoeia, ...) puedo buscar en los chunks específicos.
```

### 3.7 Costes

| Métrica | Valor |
|---|---|
| Tokens enviados al LLM hot | ~600 (sin wiki page, solo 3 chunks compactos) |
| Tokens generados | ~150 |
| Latencia | ~1.8s |
| Coste | $0.0004 |

### 3.8 Bondades demostradas

- **B3** Coste mínimo: query factual no carga wiki innecesariamente
- **B8** Degradación elegante: sin wiki page → modo raw clásico, sin error
- **B7** Honestidad: el LLM declara que no hay síntesis estructurada todavía y ofrece alternativa

---

## 4. Ejemplo 3 — Cross-reference: el LLM navega wikilinks

**Caso donde la primera página wiki recuperada apunta a otras páginas, y el LLM hace una segunda llamada para profundizar.**

### 4.1 Query del usuario

```
sangaroth: ¿cómo conecta el canal Proxy la sombra junguiana con la
crítica al consumismo? Necesito una explicación con citas.
```

### 4.2 Decisión inicial del LLM hot

> *Razonamiento*: la query toca dos conceptos (sombra + consumismo) y pide su intersección. Empiezo con search_corpus sobre el concepto principal.

### 4.3 Primera tool call

```json
{
  "tool": "search_corpus",
  "arguments": {
    "query": "sombra junguiana crítica consumismo",
    "top_k": 5
  }
}
```

### 4.4 Primera respuesta MCP

```json
{
  "wiki_pages": [
    {
      "page_id": "shadow-archetype",
      "score": 0.71,
      "frontmatter": {
        "canonical_name": "La sombra (arquetipo junguiano)",
        "related_concepts": ["[[anima-archetype]]", "[[individuation]]", "[[consumismo-critica]]"]
      },
      "content": "[ ...la página de la sombra... ]\n\n### En crítica cultural\nEl canal traza un paralelo entre la sombra individual y la [[consumismo-critica]]: el consumismo funciona como mecanismo social de represión del vacío existencial. Detalle en [[consumismo-critica]].\n→ [Fight Club, 23:05](https://youtu.be/L4zXftKhU6M?t=1385)",
      "raw_chunks_referenced": ["youtube:L4zXftKhU6M#1385", "youtube:L4zXftKhU6M#287"]
    }
  ],
  "raw_chunks": [
    {
      "chunk_id": "youtube:L4zXftKhU6M#1385",
      "score": 0.62,
      "theme": "🛋️ El vacío existencial y la sociedad de consumo como anestesia",
      "...": "..."
    }
  ],
  "retrieval_metadata": {
    "wiki_top_score": 0.71,
    "wikilinks_in_top_page": ["anima-archetype", "individuation", "consumismo-critica"]
  }
}
```

### 4.5 Decisión del LLM hot tras ver la respuesta

> *Razonamiento*:
> - La página de `shadow-archetype` menciona `[[consumismo-critica]]` como concepto relacionado.
> - El usuario pidió específicamente la intersección de ambos. La página de la sombra tiene **una sección** sobre consumismo, pero la página del consumismo probablemente tiene más detalle.
> - Hago una segunda llamada para traer la página de `consumismo-critica`.

### 4.6 Segunda tool call

```json
{
  "tool": "get_wiki_page",
  "arguments": {
    "page_id": "consumismo-critica"
  }
}
```

### 4.7 Segunda respuesta MCP

```json
{
  "page_id": "consumismo-critica",
  "page_type": "concept",
  "domain": ["social.sociology", "interdisciplinary.cultural_studies", "humanities.philosophy"],
  "frontmatter": {
    "canonical_name": "Crítica al consumismo (lectura del canal)",
    "related_concepts": ["[[shadow-archetype]]", "[[posindustrial-castracion]]"],
    "related_works": ["[[fight-club-1999-film]]", "[[el-amor-en-realidad]]"]
  },
  "content": "# Crítica al consumismo\n\n## Tesis del canal\nEl consumismo, según Proxy, opera como mecanismo cultural de represión del vacío existencial. Se conecta con la [[shadow-archetype]] en tanto el sujeto consumista rechaza confrontar lo reprimido y lo sustituye por bucles dopamínicos.\n→ [Fight Club, 23:05](https://youtu.be/L4zXftKhU6M?t=1385)\n→ [T5x09 El amor en realidad, 25:07](https://youtu.be/1ldYmBO4N4I?t=1507)\n\n## Manifestaciones\n- Marketing omnipresente: ya no se venden productos, se vende felicidad/identidad\n- Apps de citas: las personas se vuelven productos eligibles\n- Consumo cultural homogeneizado por plataformas\n  → [El Gólem de Cobre, 1:15:20](https://youtu.be/e3Aj775Rlw4?t=4520)\n\n## Conexión con [[shadow-archetype]]\nEl canal articula que el consumismo es una manifestación social del rechazo a la sombra: en lugar de individuar (integrar lo reprimido), el sujeto consumista huye hacia adelante en una espiral de gratificaciones que no llenan.\n→ [Fight Club, 23:05](https://youtu.be/L4zXftKhU6M?t=1385)\n",
  "raw_chunks_referenced": [
    "youtube:L4zXftKhU6M#1385",
    "youtube:1ldYmBO4N4I#1507",
    "youtube:e3Aj775Rlw4#4520"
  ]
}
```

### 4.8 Procesamiento del LLM hot

> *Razonamiento*:
> - Ahora tengo la perspectiva desde ambos extremos del puente.
> - La conexión está articulada explícitamente en la página `consumismo-critica` con citas raw.
> - Construyo respuesta apoyándome en la **sección "Conexión"** de la segunda página, complementada con la sección "En crítica cultural" de la primera.
> - 3 citas raw distintas (Fight Club + T5x09 + El Gólem de Cobre) → respuesta rica.

### 4.9 Respuesta final al usuario

```
El canal Proxy articula la conexión entre **la sombra junguiana** y
**la crítica al consumismo** en estos términos:

El consumismo opera como mecanismo cultural de **represión del vacío
existencial**. En lugar de individuar — integrar la sombra, lo
reprimido — el sujeto consumista huye hacia adelante en una espiral
de gratificaciones dopamínicas que sustituyen la realización personal.

→ [Fight Club, 23:05](https://youtu.be/L4zXftKhU6M?t=1385)

Manifestaciones que el canal documenta:

- **Marketing como venta de identidad**: ya no se venden productos,
  se vende felicidad y estatus
  → [T5x09 El amor en realidad, 25:07](https://youtu.be/1ldYmBO4N4I?t=1507)

- **Apps de citas**: las personas se convierten en productos elegibles,
  reforzando el ciclo
  → mismo vídeo

- **Consumo cultural homogeneizado por plataformas**: la diversidad de
  oferta colapsa, la identidad se diluye
  → [El Gólem de Cobre, 1:15:20](https://youtu.be/e3Aj775Rlw4?t=4520)

En síntesis: para el canal, el consumismo NO es solo un fenómeno
económico; es una **manifestación social del rechazo arquetípico a
confrontar la sombra**. Donde el junguiano clínico recomienda
individuación, el sujeto contemporáneo elige consumo.
```

### 4.10 Costes

| Métrica | Valor |
|---|---|
| Tool calls realizados | 2 (search_corpus + get_wiki_page) |
| Tokens al LLM hot (acumulado) | ~3500 |
| Tokens generados | ~320 |
| Latencia total | ~3.8s (incluye 2 round-trips MCP) |
| Coste | $0.0014 |

### 4.11 Bondades demostradas

- **B5** Cross-reference vía wikilinks: el LLM ve `[[consumismo-critica]]` y decide profundizar
- **B1** Trazabilidad: 3 citas raw distintas con timestamp, todas verificables
- **B9** Cero síntesis duplicada: la conexión sombra↔consumismo ya estaba sintetizada en la wiki, el LLM solo la presenta
- **B2** Decoupling: cualquier LLM con buenas capacidades de tool-use haría exactamente la misma secuencia

---

## 5. Ejemplo 4 — Sin cobertura wiki, fallback honesto

**Caso donde el wiki no tiene página relevante. El sistema NO falla — responde con raw + admite el hueco.**

### 5.1 Query del usuario

```
sangaroth: ¿qué dice el canal Proxy sobre el animismo?
```

### 5.2 Decisión del LLM hot

> *Razonamiento*: pregunta sobre concepto religioso/antropológico. Probablemente hay material adyacente. Busco.

### 5.3 Tool call

```json
{
  "tool": "search_corpus",
  "arguments": {
    "query": "animismo religiones primitivas espíritus naturaleza",
    "top_k": 5
  }
}
```

### 5.4 Respuesta MCP

```json
{
  "wiki_pages": [
    {
      "page_id": "religion-comparada",
      "score": 0.51,
      "page_type": "concept",
      "frontmatter": {
        "canonical_name": "Religión comparada (lecturas del canal)"
      },
      "content": "[ ...página general sobre religión... brevemente menciona animismo en contexto de mito... ]"
    }
  ],
  "raw_chunks": [
    {
      "chunk_id": "youtube:abc#562",
      "score": 0.49,
      "video_title": "Mitos y conciencia: lectura jungiana de la religión",
      "timestamp": "09:22",
      "theme": "🌳 La fase animista de la psique colectiva",
      "content": "- Para el junguiano, el animismo es la fase en que el inconsciente proyecta vida en la naturaleza\n- No es 'error primitivo' sino estructura psicológica universal",
      "youtube_url": "https://youtu.be/abc?t=562",
      "in_wiki_sources": false
    },
    {
      "chunk_id": "youtube:def#1820",
      "score": 0.46,
      "video_title": "Lovecraft: el horror cósmico como religión moderna",
      "timestamp": "30:20",
      "theme": "👁️ Animismo invertido: la naturaleza como amenaza",
      "content": "- Lovecraft retoma la estructura animista pero invertida: la naturaleza no protege, persigue\n- El animismo lovecraftiano es la sombra del animismo arcaico",
      "youtube_url": "https://youtu.be/def?t=1820",
      "in_wiki_sources": false
    },
    {
      "chunk_id": "youtube:ghi#445",
      "score": 0.44,
      "video_title": "Religión y mito: del sentido a la institución",
      "timestamp": "07:25",
      "theme": "🕯️ Tipologías religiosas",
      "content": "- Animismo como categoría taxonómica clásica (Tylor)\n- Críticas modernas: ¿realmente existió como sistema o es proyección eurocéntrica?",
      "youtube_url": "https://youtu.be/ghi?t=445",
      "in_wiki_sources": false
    }
  ],
  "retrieval_metadata": {
    "wiki_top_score": 0.51,
    "raw_top_score": 0.49,
    "mode_recommended": "raw_with_warning",
    "warning": "Wiki coverage thin (max score 0.51). Best wiki page is general; no dedicated page for 'animismo'. Consider candidate for next compilation cycle."
  }
}
```

### 5.5 Procesamiento del LLM hot

> *Razonamiento*:
> - Wiki top score 0.51 (bajo). La página `religion-comparada` solo lo menciona de pasada.
> - Raw top score 0.49 (también bajo absoluto). El corpus toca animismo pero no lo dedica como tema.
> - Tres chunks raw distintos con perspectivas variadas (junguiana, lovecraftiana, taxonómica).
> - Debo:
>   1. Construir respuesta con los chunks raw (no hay síntesis pre-cocinada útil)
>   2. **Declarar honestamente** que el corpus no dedica un análisis sistemático al animismo
>   3. Sugerir profundización si el usuario quiere

### 5.6 Respuesta final al usuario

```
El canal Proxy no dedica un análisis sistemático al animismo, pero
lo menciona en tres contextos distintos:

1. **Lectura junguiana** (Mitos y conciencia, 09:22): el animismo
   sería la fase en que el inconsciente colectivo proyecta vida en
   la naturaleza. No es "error primitivo" sino estructura psicológica
   universal.
   → [vídeo](https://youtu.be/abc?t=562)

2. **Animismo invertido en Lovecraft** (Lovecraft: horror cósmico, 30:20):
   Lovecraft retoma la estructura animista pero la invierte — la
   naturaleza ya no protege, persigue. Animismo como sombra del animismo.
   → [vídeo](https://youtu.be/def?t=1820)

3. **Crítica taxonómica** (Religión y mito, 07:25): el canal recoge
   las críticas modernas a Tylor — ¿el animismo realmente existió como
   sistema, o es proyección eurocéntrica?
   → [vídeo](https://youtu.be/ghi?t=445)

[NOTA explícita]: el corpus no tiene una pieza dedicada al animismo
como tema central. Los tres extractos lo abordan tangencialmente. Si
quieres una síntesis estructurada, esto es candidato a generarse en
el próximo ciclo de compilación de wiki.
```

### 5.7 Costes

| Métrica | Valor |
|---|---|
| Tokens al LLM hot | ~1100 (1 wiki page débil + 3 raw chunks) |
| Tokens generados | ~280 |
| Latencia | ~2.0s |
| Coste | $0.0006 |

### 5.8 Bondades demostradas

- **B8** Degradación elegante: sin wiki dedicada → raw + warning explícito al LLM
- **B7** Honestidad epistémica: el LLM declara que no hay tratamiento sistemático
- **B4** Lateral recall: los 3 chunks raw vienen de **3 videos completamente distintos** (Mitos y conciencia / Lovecraft / Religión y mito) — el RAG raw los encuentra aunque "animismo" no esté en ninguno como tema central
- **B10** Auditable: la respuesta incluye sugerencia de mejorar la wiki ("candidato a próximo ciclo de compilación") basada en `retrieval_metadata.warning`

---

## 6. Lo que los 4 ejemplos demuestran sobre el diseño

### 6.1 Cobertura completa del espacio de queries

| Eje | E1 (sombra) | E2 (Tolkien) | E3 (cross-ref) | E4 (animismo) |
|---|---|---|---|---|
| **Tipo de query** | conceptual | factual/listado | cross-reference | conceptual sin cobertura |
| **Wiki domina** | ✅ sí | ❌ no aplica | ✅ sí (con segunda llamada) | ❌ wiki débil |
| **Raw domina** | secundario | ✅ sí | secundario | ✅ fallback |
| **Tool calls** | 1 | 1 | 2 (cross-ref) | 1 |
| **Tokens output LLM** | 280 | 150 | 320 | 280 |
| **Latencia** | 2.1s | 1.8s | 3.8s | 2.0s |
| **Coste** | $0.0008 | $0.0004 | $0.0014 | $0.0006 |

Los 4 cubren el cuadrante completo: con wiki / sin wiki × pregunta simple / pregunta compleja. **El sistema responde bien en los 4 casos sin lógica condicional ad-hoc** — el modo correcto emerge del contenido del retrieval, no de un "router" que decida arriba.

### 6.2 Coste promedio realista

Promedio de los 4: **~$0.0008 por query, ~2.4s end-to-end**. Para un Mattermost con 50 queries diarias, eso son **~$1.20 al mes**. El coste no es preocupación.

### 6.3 La wiki amortiza solo en el caso E1

De los 4 ejemplos, solo **E1** se beneficia significativamente del trabajo de cold path (wiki). E2 y E4 funcionan igual con o sin wiki. E3 muestra el caso donde la wiki + wikilinks tipados aportan valor diferencial (cross-reference profunda con coste de 2 tool calls en lugar de 5+).

**Implicación práctica:** la prioridad para compilar páginas wiki son **conceptos preguntados repetidamente** (caso E1) y **conceptos que conectan con muchos otros** (caso E3). Compilar páginas para temas one-off (E2, E4) tiene baja amortización.

### 6.4 Riesgos no demostrados (a vigilar en producción)

- **Drift sigiloso**: si la wiki no se recompila y los nuevos chunks raw introducen contradicciones, el LLM podría reportar la wiki como "actual" cuando ya no lo es. La detección automática (`drift_detected`) ayuda pero no es perfecta.
- **Fragmentación del cross-reference**: si E3 hubiera requerido 4 wikilinks navegados, ¿el LLM hace 4 tool calls? ¿Hasta dónde llega? Hay que poner límites.
- **Threshold de fallback**: 0.55 es arbitrario. Necesita tuning con queries reales.
- **Coste explosivo en queries que devuelven multi-wiki + multi-raw**: si una query toca 5 conceptos, ¿devolvemos 5 wiki pages? Hay que tope explícito.

---

## 7. Decisiones que estos ejemplos cierran

A partir de validar este flujo:

1. ✅ **Modo híbrido por defecto** (no wiki-first)
2. ✅ **search_corpus devuelve siempre `wiki_pages` + `raw_chunks` + `retrieval_metadata`** (estructura unificada)
3. ✅ **`retrieval_metadata.mode_recommended`** orienta al LLM ("wiki_dominant" / "raw_only" / "raw_with_warning") sin imponer
4. ✅ **`get_wiki_page(page_id)` como tool aparte** para cross-reference (E3)
5. ✅ **Cada chunk raw lleva `in_wiki_sources: bool`** para detección de drift
6. ✅ **Warnings explícitos en metadata** cuando wiki es débil (E4)
7. ✅ **El LLM hereda lagunas y warnings** explícitamente al usuario (B7)

## 8. Decisiones aún abiertas (a tunear con datos reales)

1. **Threshold de wiki score** para considerar "wiki suficiente" (provisional 0.65)
2. **Threshold de raw score** para fallback honesto a "no encuentro" (provisional <0.45)
3. **Límite de tool calls** por query (provisional 3, evita loops infinitos en cross-ref)
4. **Top-K de wiki pages** vs raw chunks (provisional 2 wiki + 5 raw)
5. **Política de warnings**: ¿siempre traslad arlos al usuario o solo en casos críticos?

---

## 9. Conclusión

El modo híbrido **no es un compromiso entre dos extremos**. Es la forma natural de servir un corpus donde la síntesis pre-cocinada (wiki) y la fuente atomizada (raw) **responden a tipos distintos de pregunta**, ambos válidos.

Los 4 ejemplos muestran que el sistema:
- Responde bien sin lógica condicional ad-hoc (el modo correcto emerge del retrieval)
- Mantiene trazabilidad en todos los casos
- Degrada elegantemente cuando falta cobertura
- Tiene coste predecible y bajo
- Es auditable end-to-end

Si esta lógica se sostiene en producción, la implementación de Fase B está justificada. Si los datos de uso real revelan otros patrones, este documento se actualiza.

Doc vivo. Próxima revisión: tras 1-2 meses de uso de Fase B.

---

## 10. Schema autoritativo (vigente desde 2026-04-30)

Esta sección refleja el **schema real implementado** en `ariadna/search.py:Searcher.search_hybrid()`. Sustituye a los snippets ilustrativos de §2.4, §3.4, §4.4 y §4.7 a efectos de contrato MCP.

### 10.1 Output completo

```json
{
  "wiki_pages": [
    {
      "score": 0.6518,
      "page_id": "jung-carl-gustav",
      "page_type": "author",
      "canonical_name": "Carl Gustav Jung",
      "domain_primary": "social.psychology",
      "aliases": ["Jung", "C.G. Jung", "Carl Jung", "junguiano (adj.)"],
      "relations": [
        {"type": "developed", "to": "shadow-archetype", "note": "arquetipo central de la psicología analítica"},
        {"type": "developed", "to": "anima-archetype", "note": "pareja contrasexual interior"}
      ],
      "relation_targets": ["anima-archetype", "collective-unconscious", "individuation", "shadow-archetype"],
      "relation_types_present": ["developed"],
      "file_path": "wiki/authors/jung-carl-gustav.md",
      "body": "# Carl Gustav Jung\n\n## Perfil\n\nCarl Gustav Jung (1875-1961)...",
      "match_via": "citation",
      "matched_via_chunks": [
        {
          "video_id": "Tviv4PT0dv8",
          "timestamp_seconds": 4878,
          "video_title": "Análisis arquetípico de Tarzán",
          "chunk_score": 0.6518
        }
      ]
    }
  ],
  "raw_chunks": [
    {
      "score": 0.6518,
      "video_title": "Análisis arquetípico de Tarzán",
      "timestamp": "1:21:18",
      "theme": "Tarzán y el ánima como vehículo de individuación",
      "content": "...",
      "category": "analisis de obra",
      "playlist": "...",
      "youtube_url": "https://youtu.be/Tviv4PT0dv8?t=4878",
      "cite_markdown": "[Análisis arquetípico de Tarzán (1:21:18)](https://youtu.be/Tviv4PT0dv8?t=4878)",
      "in_wiki_sources": ["jung-carl-gustav"]
    }
  ],
  "retrieval_metadata": {
    "wiki_top_score": 0.4134,
    "raw_top_score": 0.6518,
    "mode_recommended": "raw_with_warning",
    "warning": null,
    "wiki_pages_count": 3,
    "wiki_via_citation_count": 1,
    "raw_chunks_count": 5
  }
}
```

### 10.2 Diferencias clave con los ejemplos antiguos

| Antes (§2.4 etc.) | Ahora (vigente) |
|---|---|
| `frontmatter.related_concepts/authors/works: ["[[X]]", ...]` (3 buckets, strings con corchetes) | `relations: [{type, to, note?, weight?}]` + `relation_targets: [...]` + `relation_types_present: [...]` |
| `raw_chunks_referenced: ["youtube:VID#SEC"]` en cada wiki page | NO existe — la dirección útil es la inversa: `raw_chunks[].in_wiki_sources` (qué wiki cita este chunk) |
| `content` (cuerpo de la página) | `body` (mismo contenido, nombre cambiado para diferenciar de get_wiki_page que SÍ usa `content`) |
| `frontmatter.canonical_name/aliases` anidados | Promovidos a top-level: `canonical_name`, `aliases`, `domain_primary`, `page_type`, `file_path` |
| `retrieval_metadata.drift_detected`, `all_top_raw_in_wiki_sources` | NO existen como campos — la info equivalente sale de inspeccionar `raw_chunks[].in_wiki_sources` directamente |
| `mode_recommended: wiki_dominant \| balanced \| raw_only \| no_results` | Mismos + `raw_with_warning` (wiki cobertura fina) + `raw_with_wiki_via_citation` (sin match semántico pero hay match indirecto vía citas) |
| Wiki encontrada solo por similitud focal | Wiki puede entrar por: (a) similitud del vector focal, (b) **lookup indirecto vía citations** — cualquier chunk raw con score≥0.55 dispara JOIN contra `data/wiki.db:citations`. Cada wiki entry lleva `match_via: "semantic" \| "citation" \| "both"` |
| `in_wiki_sources: true` (bool) en raw_chunks | `in_wiki_sources: ["page_id1", "page_id2", ...]` (lista de page_ids que citan ese chunk; lista vacía si ninguna cita) |

### 10.3 Cómo usa el LLM esta info

- **`match_via="semantic"`** → la página ganó por su propio mérito. Usar como respuesta canónica si `score` alto.
- **`match_via="citation"`** → la página NO matched semánticamente, pero cita los chunks que sí matched. Útil cuando la query es sobre un sub-aspecto del concepto que el focal no captura. **Score deriva del chunk citante** — no comparable directamente con scores semánticos. Usar como contexto sintetizado complementario al chunk raw.
- **`match_via="both"`** → match semántico + chunks citantes. Caso fuerte: la página es relevante Y hay material raw concreto que la respalda.
- **`raw_chunks[].in_wiki_sources`** → para cada chunk raw, qué wiki pages lo sintetizan. Si está vacío, el material no tiene página wiki (cobertura pendiente). Si está poblado, el LLM puede llamar `get_wiki_page(page_id)` para contexto extendido si la query lo justifica.

### 10.4 Implementación de referencia

`ariadna/search.py:Searcher.search_hybrid()` y los helpers `_lookup_wiki_via_citations()`, `_fetch_wiki_pages_from_db()`, `_merge_wiki_lanes()`. Smoke test del schema: `scripts/test_hybrid.py` (7 checks, 5/5 + 2 nuevos sobre la lane indirecta).

