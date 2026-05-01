# Reranker — segunda pasada con cross-encoder

> Por qué Ariadna usa un reranker después de la búsqueda dense, qué problema resuelve, qué decisiones lo cierran como capa estable y cómo lo validamos antes de meterlo en producción.

---

## 1. El problema que resuelve

La búsqueda dense con BGE-M3 que ya teníamos hace lo siguiente: convierte la pregunta del usuario en un vector de 1024 números, hace lo mismo con cada uno de los 6259 chunks del corpus, y devuelve los chunks cuyos vectores están más cerca por coseno.

Esto es rápido (decenas de milisegundos) y suficiente para encontrar los **20 chunks que probablemente contienen la respuesta**, pero tiene una limitación estructural:

- BGE-M3 (un **bi-encoder**) embebe pregunta y chunk **por separado**, en momentos distintos. Cada uno se comprime a 1024 floats sin "saber" del otro.
- Esa compresión pierde matices: dos chunks pueden quedar igual de cerca de la pregunta aunque uno responda exactamente y el otro solo comparta el tema.

El resultado típico: el chunk correcto está casi siempre en el **top-20** del dense, pero no siempre en el top-5 que se manda al LLM.

---

## 2. La solución: cross-encoder

Un **cross-encoder** (BGE-reranker-v2-m3 en nuestro caso) procesa pregunta y chunk **juntos** en una sola pasada del transformer:

```
[CLS] ¿qué es la sombra para Jung? [SEP] La sombra es el aspecto inconsciente... [SEP]
```

La atención del modelo puede comparar token a token entre los dos textos. Detecta interacciones que el bi-encoder no puede:

- Negaciones ("Jung NO dice X" vs "Jung dice X").
- Polisemia ("sombra" como concepto junguiano vs "sombra" en cinematografía).
- Match parcial vs match preciso (chunks que tocan el tema vs chunks que lo responden).

Es **mucho más caro** que el bi-encoder: una pasada por cada par (query, chunk). Imposible sobre 6259 chunks; razonable sobre 20.

**El truco**: combinar los dos.

```
Query
  └─► [bi-encoder dense]  6259 chunks → top-20    (~30ms, recall grueso)
        └─► [cross-encoder rerank]   20 chunks → top-5    (~80ms GPU, precisión fina)
              └─► al LLM
```

El bi-encoder garantiza que el chunk bueno esté entre los 20 candidatos. El cross-encoder los reordena con precisión y devuelve los 5 mejores al LLM.

---

## 3. Cómo se integra en Ariadna

### Archivos tocados

- **[ariadna/reranker.py](../ariadna/reranker.py)** (nuevo) — clase `Reranker` que envuelve `sentence_transformers.CrossEncoder` con BGE-reranker-v2-m3.
- **[ariadna/config.py](../ariadna/config.py)** — constantes `RERANKER_MODEL_NAME`, `RERANKER_PREFETCH_N` (=20), `RERANKER_MAX_LENGTH` (=512).
- **[ariadna/search.py](../ariadna/search.py)** — `Searcher.__init__` carga el reranker (lazy), `search()` y `search_hybrid()` hacen prefetch top-20 → rerank → top-K.

### Sin flags, siempre activo

Decisión de diseño explícita: el reranker está **siempre activo**, no hay parámetro para desactivarlo. Razones:

- Menos condicionales = menos paths de ejecución = menos sorpresas.
- En la fase actual de evaluación, queremos que sea evidente cuando opera (los `score` del output son rerank_scores, en escala sigmoide ~0-1, distintos visualmente de los cosine de antes).
- Si en algún momento queremos desactivarlo, basta con pasar `reranker=NoOpReranker()` desde el lado del caller. Es una decisión de inyección, no de runtime.

### Lo que se rerankea y lo que no

| Lane | ¿Rerank? | Por qué |
|---|---|---|
| **raw_chunks** (en `search()` y `search_hybrid()`) | ✅ sí | El uso principal del retrieval — ahí se ve la ganancia. |
| **wiki_pages** | ❌ no | Solo top-2, body es página completa (max 512 tokens trunca demasiado), score semantics distintas (focal vector). |
| **citation_seed** (lookup interno wiki vía citations) | ❌ no | Es un mecanismo de navegación, no se devuelve al LLM. Reranquearlo añadiría latencia sin ganancia visible. |

### Compatibilidad con `mode_recommended`

El sistema híbrido decide entre `wiki_dominant` / `raw_with_warning` / `balanced` etc. comparando el top score de la lane wiki con el top score de la lane raw. Esa comparación necesita scores **comparables** (ambos cosine).

Después del rerank, el `score` de raw_chunks es rerank_score (escala sigmoide), no comparable con el cosine de wiki. Para no romper la lógica:

- **Antes** de rerankear, guardamos `raw_top_cosine = raw_results_dense[0]["score"]`.
- **Después**, en cada chunk reranked guardamos `dense_score` con el cosine original y sustituimos `score` por `rerank_score`.
- `mode_recommended` se calcula con `raw_top_cosine` (cosine), no con rerank_score.
- El threshold de citation lookup (0.55, calibrado a coseno) usa `dense_score` con fallback a `score` para soportar tanto entrada reranked como sin rerankear.

Detalle en [search.py:155-186](../ariadna/search.py#L155-L186) y [search.py:280-302](../ariadna/search.py#L280-L302).

---

## 4. Cómo lo validamos

Antes de integrarlo, corrimos dos pilots aislados sobre una colección Qdrant separada (`data/qdrant_eval/`, no afecta producción) con los 6259 chunks indexados con BGE-M3 dense + sparse.

### Pilot v1: 10 queries sintéticas

10 queries generadas a partir de chunks reales del corpus, mezclando 4 naturales, 3 paráfrasis y 3 con nombres propios. Se compararon **dense top-5** vs **RRF top-5** (fusión dense+sparse).

**Resultado**: dense ya ponía el chunk fuente en top-3 al 100% y en top-1 al 80%. RRF no movía la aguja en ninguna de las 10. Sparse aportaba ruido en posiciones intermedias (cuela chunks irrelevantes que comparten palabras incidentales).

→ Decisión: **descartar RRF/sparse** para producción. No reindexamos. Detalle en [data/eval/results_v1.md](../data/eval/results_v1.md).

### Pilot v2: + 5 queries adversariales + reranker

Mantuvimos las 10 queries v1 y añadimos 5 queries adversariales (coloquial extremo, paráfrasis muy lejanas, sin nombres propios). Comparamos **dense top-5** vs **RRF top-5** vs **dense top-20 → reranker → top-5**.

**Resultado**: en queries limpias (v1) el reranker mejora marginalmente (q03 de #3 a #1, q04 de #2 a #1). En queries adversariales:

| Query | Dense puro | RRF | Reranker |
|---|---|---|---|
| q13 — "el rollo ese de Diddy y los raperos que palmaron de los 90" | chunk fuente en **#6** (fuera top-5) | #5 | **#2** |
| q14 — "diferencia entre soñar despierto sabiendo que no pasa y querer algo de verdad" | chunk fuente en **#18** (fuera top-5) | fuera | **#4** |

→ Decisión: **integrar reranker**. Es la única capa que rescata casos donde dense entierra el chunk correcto. Detalle en [data/eval/results_v2.md](../data/eval/results_v2.md).

### Caveat metodológico importante

Después de integrarlo en producción descubrimos que **el LLM cliente (gpt-mini en el plugin Mattermost) reformula las queries antes de llamar al MCP**. La query coloquial cruda nunca llega a Ariadna; llega ya en versión más formal.

Eso significa que los rescates dramáticos del v2 (#18 → #4) **no se replican tal cual** en producción, porque la reformulación del LLM ya hace parte del trabajo de "limpiar" la query. El valor real del reranker en producción es más modesto que sugería el v2.

Pero sigue habiendo ganancia: el reranker mete chunks más específicos al top-5 y discrimina mejor entre candidatos topicalmente similares. Ver §5.

---

## 5. Validación en producción real (Mattermost)

Test directo: misma pregunta del usuario al plugin de Mattermost, antes y después de activar el reranker en el MCP.

### Pregunta del usuario

> "diferencia entre soñar despierto sabiendo que no pasa y querer algo de verdad"

(El LLM la reformula a algo tipo "diferencia entre fantasía y deseo / anhelo en psicología" antes de llamar a `search_corpus`.)

### Antes (dense puro)

El LLM cita 4 chunks:

1. T5x05 *Síndrome Delirante* (51:37) — "todo lo que ocurre en el interior no orientado al exterior"
2. T5x05 *Síndrome Delirante* (37:39) — "representación recreativa"
3. *La enfermedad del aburrimiento* (58:01) — "el primer input debería proceder del exterior"
4. *Psicología Incel* (22:29) — superyo como fantasía

Respuesta correcta, prosa lineal.

### Después (con reranker)

El LLM cita 4 chunks **— uno cambia**:

1. T5x05 *Síndrome Delirante* (51:37) — igual
2. ⭐ **Lunes 100 tífiko: Therians (40:38)** — *"no tiene que ver con la imaginación sino con la voluntad de no estar en el aquí y el ahora"* ← **nuevo, sustituye al chunk de T5x05 37:39**
3. *La enfermedad del aburrimiento* (58:01) — igual
4. *Psicología Incel* (22:29) — igual

El reranker sustituye el chunk T5x05 (37:39) "representación recreativa" por **Therians (40:38)**, que aporta una formulación mucho más directa para la pregunta. El LLM construye sobre esa frase su síntesis y cierra con un aforismo más memorable: "la fantasía sustituye, el deseo real apunta".

### Lectura honesta

- El reranker no produce un cambio dramático en producción (no hay rescate desde top-18).
- Sí produce **diversidad útil** y **reemplazo cualitativo** de chunks marginales por chunks más específicos.
- La respuesta final del LLM es **medio escalón mejor**: más estructurada, mejor sintetizada, con cita más quotable.
- Atribuirlo todo al reranker sería exagerado (variabilidad del LLM entre ejecuciones), pero el chunk Therians es un input objetivamente superior que el dense puro no traía.

---

## 6. Coste

| Recurso | Coste |
|---|---|
| Latencia añadida al hot path | ~80ms en GPU local (top-20 cross-encoder en paralelo). ~200-400ms en CPU con cuantización ONNX int8 (no aplicado todavía). |
| Latencia hot path total | ~125ms (dense embed + Qdrant search + rerank) — bajo presupuesto de 500ms. |
| RAM | +~2 GB (modelo cargado en VRAM/RAM). |
| Disco | +~2 GB (modelo cacheado en `~/.cache/huggingface`). |
| Tiempo de arranque MCP | +~5s (carga del modelo en `Searcher.__init__`). |
| Reindexación | **cero** — el reranker es 100% query-time. |
| Cambios en storage / corpus | **cero**. |

---

## 7. Decisiones cerradas

- ✅ **Reranker SÍ** — aporta marginal pero consistente, cero coste de migración.
- ❌ **RRF (sparse fusion) NO** — sparse aporta ruido en corpus pre-distilled; el corpus de Proxy (theme + bullets ya sintéticos) no necesita matching exacto adicional.
- ❌ **Activación por flag NO** — siempre activo; menos condicionales, comportamiento más predecible.
- ❌ **Rerank de wiki lane NO** — top-2 de wiki, body largo, score semantics distintas.
- ❌ **Cuantización ONNX NO todavía** — no urgente mientras estemos en local con GPU. Necesario antes de despliegue Hetzner sin GPU (Fase C).

---

## 8. Reproducir los pilots

Si quieres re-correr la evaluación con queries propias:

```bash
# Instala FlagEmbedding (no es dep de producción, solo para los pilots)
uv pip install FlagEmbedding

# 1. Indexa los 6259 chunks con dense+sparse en colección aislada (data/qdrant_eval/)
python scripts/run_eval_pilot.py
# → produce data/eval/results_v1.md (dense vs RRF)

# 2. Añade reranker al comparativo, incluye 5 queries adversariales
python scripts/run_pilot_v2.py
# → produce data/eval/results_v2.md (dense vs RRF vs reranker)
```

Las queries vienen de [data/eval/queries_eval_v1.jsonl](../data/eval/queries_eval_v1.jsonl) (10 queries) y [data/eval/queries_eval_v2.jsonl](../data/eval/queries_eval_v2.jsonl) (5 queries adversariales). Edita esos JSONL para añadir las tuyas.

---

## 9. Lo que cambió respecto al backlog A.2

El backlog [PHASES.md](PHASES.md) y [ARCHITECTURE.md §5](ARCHITECTURE.md#5-roadmap-qué-viene-encima-de-esta-base) listaban A.2 como "Sparse BM25 + threshold + reranker". Después del eval:

- **Sparse / BM25**: descartado (RRF no aporta sobre dense BGE-M3 puro en este corpus).
- **Reranker**: integrado y activo.
- **Threshold**: el de citation lookup (0.55 cosine) se mantiene; sigue calibrado a `dense_score`.

A.2 queda **cerrada con menos piezas de las planeadas** y mejor entendimiento del corpus.
