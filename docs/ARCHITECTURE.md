# Arquitectura de Ariadna — argumentación de diseño

> Por qué el sistema está hecho como está, qué decisiones son reversibles y cuáles no, y dónde poner el esfuerzo en este momento.

![Arquitectura: HOT path (consulta) y COLD path (generación de conocimiento)](images/architecture.png)

---

## 1. Premisa: el corpus es el activo, todo lo demás es reemplazable

Antes de hablar de tecnología hay un principio que ordena las decisiones siguientes:

**El valor a largo plazo de Ariadna no está en el modelo de embeddings, ni en la base vectorial, ni en el LLM que orquesta — está en el corpus saneado, su taxonomía y su léxico controlado.**

Esto importa porque:

- Los **modelos cambian cada 3-6 meses** — BGE-M3 hoy, BGE-M4 mañana, otro embedding abierto pasado mañana
- Las **bases vectoriales cambian cada 1-2 años** — Qdrant hoy, podría ser Milvus, Vespa, pgvector mañana
- Los **LLMs cambian cada semana** — gpt-5.4-mini hoy, Claude 4.7 mañana, modelo local pasado
- Los **protocolos también** — MCP es estándar emergente; podría haber otra capa encima en 2 años

Pero el **corpus**, una vez sistematizado con buenos chunks, metadata consistente y categorías canónicas, sobrevive a todos esos cambios. Re-indexar 6036 chunks bien parseados con un nuevo modelo de embeddings cuesta 30 segundos. Re-clasificar y re-categorizar 288 vídeos mal etiquetados cuesta semanas.

**Corolario práctico:** en el sprint actual, el esfuerzo más rentable no está en mejorar el RAG sino en asegurar que la fuente de datos esté **sistematizada y agnóstica**:

- Taxonomía estable (5 categorías canónicas, no 27 ad-hoc)
- Léxico controlado (términos canónicos para conceptos repetidos)
- Metadata consistente por chunk (timestamp, video_id, category, playlist obligatorios)
- Estructura de markdown predecible que el parser pueda procesar sin casos especiales

Una vez la fuente está saneada, **cualquier tecnología futura — RAG, KAG, LLM Wiki, grafo de conocimiento, búsqueda híbrida — se construye encima sin tocar el corpus**.

---

## 2. Decoupling: MCP como contrato, LLM como cliente intercambiable

```
┌──────────────────────────┐         ┌──────────────────────────┐
│  CUALQUIER LLM           │  MCP    │  Ariadna MCP Server      │
│  - GPT-5.4-mini  (hoy)   │ ◄────►  │  - search_corpus         │
│  - Claude 4.7            │  HTTP   │  - get_video_summary     │
│  - Gemini 2.5 Pro        │  JSON-  │  - list_videos           │
│  - Llama local           │  RPC    │                          │
│  - Modelo X de 2027      │         │  Implementación interna: │
└──────────────────────────┘         │  RAG → KAG → Wiki        │
                                      │  (libre de cambiar)      │
                                      └──────────────────────────┘
```

### Por qué desacoplamos

**El LLM es el componente más volátil del sistema.** Cambia precio, calidad y disponibilidad cada pocos meses. Acoplar el corpus a un LLM concreto sería atarse a su API, su tokenizer, su política de uso, y su precio.

**MCP (Model Context Protocol) actúa como contrato estable.** El servidor expone 3 tools con esquema JSON definido. Cualquier LLM que hable MCP puede consumirlas. Cualquier reorganización interna del servidor (cambiar de Qdrant a Vespa, añadir reranking, meter caching) es transparente al cliente.

### Beneficios concretos del desacople

| Beneficio | Implicación práctica |
|---|---|
| **Coste-eficiencia dinámica** | Hoy gpt-5.4-mini ($0.15/M tokens). Si mañana sale un modelo open-source decente, basta con cambiar AI Service en Mattermost. El servidor no se entera |
| **Privacidad opcional** | Para queries sensibles, swap a Llama 3.3 local. Sin tocar Ariadna |
| **A/B testing** | Configurar 2 agentes en Mattermost (Ariadna-GPT, Ariadna-Claude) apuntando al mismo MCP. Comparar calidad sin duplicar infraestructura |
| **Resistencia a deprecation** | Cuando OpenAI deprecate gpt-5.4-mini en 2027, no hay refactor — solo cambias el modelo configurado |
| **Multi-tenancy futuro** | El mismo servidor MCP puede servir a varios LLMs en paralelo (un equipo con Claude, otro con Gemini) |

### El riesgo de NO desacoplar (anti-patrón evitado)

Si hubiéramos integrado las llamadas a OpenAI **dentro del servidor de búsqueda** (server llama embed → search → LLM completion → respuesta), tendríamos:

- API key de OpenAI gestionada por Ariadna → secret a custodiar
- Lógica de prompt acoplada al modelo concreto → cambiar a Claude requiere reescribir
- Coste por query atribuido al servidor (no al chat) → modelo de billing rígido
- Retries / rate-limiting que reimplementar → cosas que el plugin de Mattermost ya hace bien

Decoupling vía MCP **delega esas responsabilidades al cliente** (Mattermost AI plugin), que ya las resuelve, las parametriza y las gestiona.

---

## 3. Hot path vs Cold path: dos flujos ortogonales

Ariadna distingue dos modos de operación que cohabitan en el mismo servidor pero responden a presiones distintas:

### HOT PATH — consulta en tiempo real (lee, no escribe)

```
Usuario en Mattermost
  → "¿hay videos sobre la sombra junguiana?"
  → LLM (GPT-mini) decide invocar search_corpus
  → MCP call al servidor (categoría + concepto)
  → embed query (~30ms en GPU local)
  → búsqueda Qdrant top-K (~10ms)
  → 5 chunks JSON de vuelta (<200ms total)
  → LLM redacta respuesta citando vídeos
```

**Características:**
- Latencia objetivo: **<500ms end-to-end**
- Coste por query: bajo (search local + tokens del LLM hot)
- Frecuencia: alta (todas las preguntas del usuario)
- Side-effects: ninguno (read-only sobre el corpus)

**Por qué baratea coste:** la operación cara (síntesis de respuesta) la hace el LLM hot que el usuario ya está pagando vía Mattermost AI. El servidor solo aporta los datos. **Sin RAG, el LLM tendría que recibir el corpus entero en cada query** (imposible: 6036 chunks ≈ millones de tokens). El RAG comprime el contexto a los 5 chunks relevantes — divide el coste de tokens por ~1000.

### COLD PATH — generación asíncrona de conocimiento (escribe corpus)

```
Usuario en Mattermost
  → "/queue_analysis paper_jung_2024.pdf"
  → comando se encola en SQLite del servidor
  → durante la noche:
     - voluntarios con GPU local procesan jobs
     - o cuotas Max de Claude consumen jobs vía claude -p
     - o APIs personales de Gemini, etc.
  → cada worker:
     - lee el PDF / documento
     - genera nuevos chunks con metadata sistematizada
     - los inserta en el corpus de Ariadna
  → al día siguiente, el HOT path ya puede consultar lo nuevo
```

**Características:**
- Latencia objetivo: **horas o noches**, no es tiempo real
- Coste por job: variable, **a menudo $0 marginal** (cuota Max ya pagada, GPU del voluntario, API personal)
- Frecuencia: baja (a demanda, días-semanas)
- Side-effects: **sí** (escribe en el corpus)

**Por qué baratea coste:** análisis profundos (resumir un paper de 50 páginas, extraer entidades de un libro entero) son operaciones que **no necesitan ser realtime** y que se pueden delegar a recursos infrautilizados:

- **Cuota Claude Max del propietario** que de noche está dormida
- **GPU del voluntario** que de noche no juega
- **API gratuita de Gemini** que el usuario tiene anyway

El cold path **convierte recursos ociosos distribuidos en producción de conocimiento** sin sumar coste a la operación realtime.

### Por qué la separación importa

Mezclar ambos en un solo flujo sería un error costoso:

- Si pides al LLM hot que analice un PDF de 100 páginas → se cuelga, se queja del context window, cuesta $$$
- Si quisieras hacer cold path con latencia realtime → necesitarías GPU dedicada 24/7 e infra mucho más cara
- Los dos tienen modelos de coste, latencia y permisos completamente diferentes

**Separarlos en dos flujos hace que cada uno se optimice por sus propias métricas.**

---

## 4. Importancia (ahora) de la taxonomía y el léxico

El sprint actual no es "subir el RAG al 90% de precisión". Es más estructural:

### Decisiones que cuesta caro revertir

| Decisión | Si la tomas mal | Coste de revertir |
|---|---|---|
| **Categorías canónicas** del corpus | Mezclas géneros (psicología vs filosofía sin criterio) | Re-categorizar 288 vídeos a mano |
| **Estructura del chunk** | Rompes el formato de markdown a mitad de proyecto | Re-parsear todo el corpus |
| **Léxico de conceptos** | "junguiano" / "jungian" / "Jung" como entidades distintas | Vocabulary cleanup + re-embedding selectivo |
| **Schema de metadata** | Olvidas un campo crítico (ej. `playlist`) y lo añades luego | Backfill complejo, posibles huecos |
| **Identificadores estables** | Usas slug del título (que cambia) en vez de video_id de YouTube | Romper enlaces, perder histórico |

### Decisiones que NO cuesta revertir

| Decisión | Por qué es reversible |
|---|---|
| Modelo de embeddings (BGE-M3 → otro) | Re-embedding es 30 segundos |
| Vector DB (Qdrant → pgvector → Vespa) | Schema de metadata es portable |
| LLM hot path (GPT → Claude → Gemini) | Cambias config en Mattermost, sin tocar servidor |
| Threshold de retrieval, top-K, filtros | Parámetros runtime |
| Reranker, sparse retrieval, hybrid | Capas que se añaden encima del corpus existente |

**La asimetría es brutal**: mejorar el RAG es trivial; reparar un corpus mal sistematizado es semanas de trabajo manual.

### Por eso, en este sprint:

- **Categorías canónicas** definidas y validadas (5: análisis de obra, cultura y actualidad, filosofía y teoría, mitología y religión, psicología). Cualquier vídeo nuevo encaja en una de las 5 o se rechaza
- **video_id de YouTube** como identificador estable. Nunca el slug del título
- **Metadata schema** explícito por chunk (`video_id`, `video_title`, `timestamp`, `timestamp_seconds`, `theme`, `content`, `category`, `playlist`, `upload_date`, `duration`, `youtube_url`) — todos obligatorios
- **Chunking semántico** por estructura de markdown, no por tokens fijos. Cada chunk es una unidad temática coherente con timestamp clicable
- **Normalización de categoría** en la búsqueda (acepta variantes con/sin acentos)

Cuando llegue Fase B (entity index) o Fase E (LLM Wiki), encontrarán datos limpios sobre los que construir. Cualquier inversión en RAG hoy se beneficia inmediatamente; cualquier inversión en KAG mañana también.

**Documento abierto:** la propuesta concreta de schema extendido (tags, entities, concepts, multi-categoría, vocabulary.json controlado, ingesta multi-formato) vive en [TAXONOMY_PROPOSAL.md](TAXONOMY_PROPOSAL.md) — se actualiza iterativamente, no se cierra.

---

## 5. Roadmap: qué viene encima de esta base

| Fase | Tecnología | Reutiliza | Aporta |
|---|---|---|---|
| **A** (hoy) | RAG dense BGE-M3 + Qdrant | corpus base | búsqueda semántica top-K |
| **A.1** | + sparse BM25 (BGE-M3 ya soporta) | mismos chunks, mismo Qdrant | precisión en nombres propios raros |
| **A.2** | + reranker cross-encoder | mismos resultados de retrieval | reordena top-20 → top-5 más preciso |
| **B** | Entity index | mismo corpus + extracción NER | "todas las menciones de Jung", co-ocurrencia |
| **C** | Despliegue Hetzner | mismo servidor, sin GPU | URL fija, multi-cliente, prod-ready |
| **D** | Cold path con voluntarios | nuevo: cola SQLite + workers | fuente de chunks autogenerada |
| **E** | LLM Wiki compilado | corpus + cold path | páginas concepto pre-sintetizadas |

**Cada fase es opcional.** Si Layer 1 ya da calidad suficiente, Layer 2 no se necesita. La arquitectura permite ir añadiendo capas sin desmontar las anteriores. Esto es consecuencia directa del decoupling MCP/LLM y de tener el corpus saneado: cada nueva tool MCP que añadamos (`cross_reference`, `get_concept_wiki`, `enqueue_deep_analysis`) es ortogonal a las existentes.

---

## 6. Resumen ejecutivo

- **El corpus es el activo**, modelo y DB son reemplazables → invertir en saneamiento de datos
- **MCP desacopla servidor de LLM** → cualquier modelo (GPT, Claude, Gemini, local) consume las mismas tools sin refactor
- **Dos flujos ortogonales**: hot path (realtime, lee) y cold path (overnight, escribe) optimizan por métricas distintas
- **Hot path baratea coste**: el LLM solo procesa los 5 chunks relevantes, no el corpus entero
- **Cold path baratea generación**: aprovecha recursos ociosos (cuotas Max, GPUs voluntarias, APIs personales)
- **Taxonomía y léxico ahora**, RAG/KAG/Wiki después — la asimetría de coste lo justifica

Para detalle de implementación ver:
- [run_pipeline.md](run_pipeline.md) — pipeline técnico paso a paso
- [SESSION_CONTEXT.md](SESSION_CONTEXT.md) — estado vivo del proyecto, decisiones, quirks
- [INTEGRACION_MATTERMOST.md](INTEGRACION_MATTERMOST.md) — guía de integración con el cliente
