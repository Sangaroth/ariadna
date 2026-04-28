# Pipeline de Ariadna — cómo funciona de principio a fin

## 0. Vista general

```
ProxySummaries (markdown)  →  Ariadna (Python)  →  Qdrant (DB vectorial)  →  MCP (HTTP)  →  Mattermost AI
     summary.md                parser + BGE-M3        índice coseno          JSON-RPC       invoca tools
     meta.json                 (GPU)                  dim=1024               streamable-http LLM cita videos
```

Dos procesos separados:

- **Indexado (offline, una vez):** lee markdown → embeddings → Qdrant. ~86s para todo el corpus.
- **Consulta (online, realtime):** Mattermost llama MCP → embed de la query → búsqueda en Qdrant → JSON de vuelta. <200ms.

---

## 1. Corpus de entrada (formato)

Cada vídeo está en una carpeta de ProxySummaries con dos ficheros:

- `meta.json` — `video_id` (id YouTube), `title`, `category`, `upload_date`, `duration`, `channel`
- `summary.md` — notas con estructura de bullets temáticos, tipo:

```markdown
- 05:23 🜂 La sombra junguiana en Fight Club
  - Tyler Durden representa el contenido reprimido...
  - La violencia como erupción del inconsciente
  - Paralelo con el concepto de enantiodromía
- 12:47 🌑 Consumismo como síntoma
  - Crítica al capitalismo tardío...
```

**Total actual:** 288 vídeos, agrupados en 5 categorías canónicas (analisis de obra, cultura y actualidad, filosofía y teoría, mitología y religión, psicología).

---

## 2. Chunking — cómo se parte el texto

**No** es chunking de tamaño fijo (ej. "500 tokens con overlap de 50"). Es **chunking semántico por estructura del markdown**: cada cabecera `MM:SS emoji título` del summary es un chunk natural.

Ver [ariadna/parsers.py:17-24](../ariadna/parsers.py#L17-L24):

```python
_CHUNK_HEADER_RE = re.compile(
    r"^- (?P<ts>\d{1,2}(?::\d{2}){1,2})\s+(?P<theme>\S.*?)$",
    re.MULTILINE,
)
```

**Tamaño real de chunk:** variable. Un chunk es `theme + bullets` y suele estar entre ~50 y ~500 tokens. Ejemplo:

```
🜂 La sombra junguiana en Fight Club

- Tyler Durden representa el contenido reprimido...
- La violencia como erupción del inconsciente
- Paralelo con el concepto de enantiodromía
```

Cada chunk lleva adjunto como **payload** (metadata no vectorizada):

| Campo | Ejemplo |
|---|---|
| `video_id` | `"dQw4w9WgXcQ"` |
| `video_title` | `"Fight Club: La sombra en Tyler Durden"` |
| `timestamp` | `"05:23"` |
| `timestamp_seconds` | `323` |
| `theme` | `"🜂 La sombra junguiana..."` |
| `content` | `"- Tyler Durden...\n- La violencia..."` |
| `category` | `"psicología"` |
| `playlist` | `"analisis-arquetipico"` |
| `youtube_url` | `https://youtu.be/dQw4w9WgXcQ?t=323` |

**Total:** 288 vídeos → **6036 chunks** (~21 chunks/vídeo de media).

Ventaja vs chunking fijo: cada chunk es una **unidad semántica coherente** (un tema, no un corte arbitrario a mitad de frase), y ya trae timestamp clicable gratis.

---

## 3. Embedding — de texto a vector

**Modelo:** [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3), cargado via `sentence-transformers` ([ariadna/embeddings.py:29](../ariadna/embeddings.py#L29)).

| Propiedad | Valor |
|---|---|
| Dimensión | **1024** (vector de 1024 floats) |
| Tipo | dense (BGE-M3 también soporta sparse, **no lo usamos todavía**) |
| Device | CUDA (RTX 3080) |
| Batch size | 32 |
| Normalización | **sí** (`normalize_embeddings=True`), norma L2 = 1 |
| Velocidad | ~195 chunks/s → 31s para todo el corpus |

**Por qué BGE-M3:** multilingüe (español nativo, no traduce), SOTA en benchmarks MTEB para retrieval, 8192 tokens de contexto (nuestros chunks caben holgadamente), gratis y local.

**Qué pasa exactamente al embeber un chunk:**

```python
texto = "🜂 La sombra junguiana en Fight Club\n\n- Tyler Durden representa..."
vector = model.encode(texto, normalize_embeddings=True)
# vector.shape == (1024,), dtype=float32, ||vector|| == 1.0
```

El vector captura el **significado semántico**: dos chunks que hablan de "la sombra junguiana" tendrán vectores parecidos aunque usen palabras distintas.

---

## 4. Almacenamiento — Qdrant

**Qdrant embebido** (no hay servidor separado, vive en `data/qdrant/` como archivos locales). [ariadna/storage.py:75](../ariadna/storage.py#L75).

Configuración de la colección [storage.py:86-92](../ariadna/storage.py#L86-L92):

```python
VectorParams(
    size=1024,
    distance=Distance.COSINE,
)
```

**Sí, coseno** — exactamente lo que preguntabas.

Cada "punto" en Qdrant = 1 vector de 1024 dims + 1 payload con toda la metadata. **6036 puntos** en total, ~72 MB en disco.

**Por qué coseno y no euclídea:** como normalizamos los vectores (norma=1), coseno es equivalente a producto escalar, es rápido de calcular y da similitud en rango [-1, 1] (en práctica 0 a 1 con BGE-M3). Nuestros scores de queries golden van de **0.55 a 0.67** — rangos razonables para RAG.

**Filtros:** Qdrant puede filtrar por metadata **antes** de calcular similitud. Ejemplo:

```python
# "busca hieros gamos pero solo en vídeos de categoría mitología"
filter = Filter(must=[FieldCondition(key="category", match=MatchValue(value="mitología y religión"))])
```

Esto es lo que hace `search_corpus(query, category="mitología y religión")`.

---

## 5. Pipeline de consulta — de Mattermost al vector

Este es el flujo cuando un usuario escribe `"explícame el hieros gamos"` en Mattermost:

### 5.1 Mattermost → MCP (JSON-RPC por HTTP)

Mattermost AI plugin envía un POST a `https://…ngrok…/mcp` con:

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "method": "tools/call",
  "params": {
    "name": "search_corpus",
    "arguments": {"query": "hieros gamos", "top_k": 5}
  }
}
```

**Protocolo:** [MCP](https://modelcontextprotocol.io/) (estándar de Anthropic) sobre **streamable-http**. Es esencialmente JSON-RPC 2.0 con un par de convenciones para tool discovery (`tools/list`) y tool call (`tools/call`).

El servidor está en [ariadna/mcp_server.py](../ariadna/mcp_server.py), usa **FastMCP** (`mcp.server.fastmcp`), SDK oficial de Anthropic en Python.

### 5.2 MCP → embedder → Qdrant

```python
# mcp_server.py:78 — la tool decorada con @mcp.tool
def search_corpus(query: str, top_k: int = 5, category=None, playlist=None):
    # 1. Embed de la query — mismo modelo BGE-M3
    q_vec = embedder.embed_query("hieros gamos")  # (1024,)

    # 2. Búsqueda coseno en Qdrant, top-5
    results = store.search(q_vec, top_k=5, filters={...})

    # 3. Cada resultado trae score + payload completo
```

Coste aproximado:

- Embed de la query: **~30-50ms** en GPU (una sola vez por llamada)
- Query a Qdrant: **~5-20ms** para 6036 puntos
- Serialización JSON: <5ms
- **Total end-to-end: <200ms**

### 5.3 Respuesta JSON → Mattermost → LLM

MCP devuelve algo como:

```json
[
  {
    "score": 0.612,
    "video_title": "Mitos de unión sagrada",
    "timestamp": "08:15",
    "theme": "🜂 Hieros gamos y el matrimonio alquímico",
    "content": "- Unión de opuestos como símbolo...\n- Paralelos en...",
    "youtube_url": "https://youtu.be/abc123?t=495",
    "category": "mitología y religión"
  }
]
```

Mattermost mete ese JSON en el contexto del LLM (OpenAI gpt-5.4-mini vía `mattermost-matty-dev`), y el LLM **redacta la respuesta final** citando los vídeos con sus URLs.

---

## 6. Mapa de piezas y responsabilidades

| Capa | Tecnología | Qué hace | Archivo |
|---|---|---|---|
| Corpus source | markdown + json | ProxySummaries genera `summary.md` | upstream |
| Parser | Python + regex | `summary.md` → `Chunk` dataclass | [parsers.py](../ariadna/parsers.py) |
| Embedder | sentence-transformers + BGE-M3 + CUDA | texto → vector 1024-d normalizado | [embeddings.py](../ariadna/embeddings.py) |
| Vector DB | Qdrant embedded | guarda vectores + payload, busca por coseno | [storage.py](../ariadna/storage.py) |
| Search | Python wrapper | junta embed + qdrant.search + dataclasses de resultado | [search.py](../ariadna/search.py) |
| MCP server | FastMCP (`mcp` SDK) | expone 3 tools vía JSON-RPC/HTTP en `/mcp` | [mcp_server.py](../ariadna/mcp_server.py) |
| Transport | streamable-http | protocolo MCP sobre HTTP con SSE opcional | FastMCP |
| Exposición | ngrok | túnel `localhost:8765` → URL pública HTTPS | [scripts/run_tunnel.sh](../scripts/run_tunnel.sh) |
| LLM (hot) | OpenAI gpt-5.4-mini | orquesta tool calls + redacta respuesta | Mattermost AI plugin |
| UI | Mattermost 11.6 | chat donde el usuario habla con Ariadna | `<your-mattermost-instance>` |

---

## 7. Lo que **no** tenemos (todavía)

- **Sparse/BM25:** BGE-M3 lo soporta, está pospuesto. Ayudaría con nombres propios raros (ej. "Enheduanna") que dense a veces embarra.
- **Re-ranking:** en RAG serio se suele meter un cross-encoder sobre los top-20 para reordenar. Aquí cogemos directo el top-5 de Qdrant.
- **Chunk overlap / padres-hijos:** chunking plano, sin jerarquía.
- **Entity index (Layer 2):** buscar por "menciones de Jung" a nivel entidad, no solo semántica.
- **Wiki compilado (Layer 3):** páginas concepto pre-sintetizadas.

Esto es **Fase A Sprint 1**: lo mínimo útil. Si la calidad falla en las queries golden, la primera palanca es añadir sparse + reranker antes de ir a Layer 2/3.
