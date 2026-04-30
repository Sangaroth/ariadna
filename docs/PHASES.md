# Fases de desarrollo de Ariadna

> Roadmap por capas. Cada fase añade valor independiente y se construye encima de la anterior sin romperla.

## Estado actual: **Fase B en curso** (2026-04-30)

- **Fase A Sprint 1**: cerrada 2026-04-23 (validación end-to-end en DM con Ariadna).
- **Fase B**: piloto + escalado parcial — 11 wiki pages compiladas, modo híbrido vivo (3 lanes: raw semántica, wiki semántica focal, wiki indirecta vía citations), índice SQLite derivado en `data/wiki.db`. Pendiente: pipeline de cobertura sistemática (`extract_video_themes.py`, `inventory_summaries.py`) y escalado a las ~280 páginas mínimas estimadas.

Estado vivo y próximos pasos en [NEXT_SESSION.md](NEXT_SESSION.md).

---

## Fase A — RAG mínimo viable

**Objetivo:** demostrar que el corpus se puede consultar semánticamente desde Mattermost via MCP, con cita de fuente y honestidad epistémica.

### Sprint 1 — Layer 0 RAG dense (✅ CERRADO 2026-04-23)

- [x] Parser de `summary.md` → chunks con metadata estructurada
- [x] Embedder BGE-M3 local en GPU
- [x] Qdrant embedded con 6036 chunks indexados
- [x] Servidor MCP HTTP exponiendo 3 tools iniciales (`search_corpus`, `get_video_summary`, `list_videos`)
- [x] Integración con Mattermost AI plugin v2.0.0-rc6 via ngrok
- [x] Per-tool policy en Auto Run (DM) — sin Accept/Reject manual
- [x] Validación de calidad con queries golden + control out-of-corpus

**Métricas alcanzadas:**
- Indexado completo: 86s para 288 vídeos / 6036 chunks
- Latencia query end-to-end: <200ms
- Scores BGE-M3 en queries relevantes: 0.55-0.67
- Recall correcto en cross-reference, lateral search funcional, citas verificadas no alucinadas

### Sprint 2 — backlog de mejoras sobre Layer 0

Cuando se ataque, decidir orden por métricas de uso real:

- [ ] **Reclasificación de chunks con taxonomía OpenAlex** (drop del legacy `proxy_category`) — reemplazar las 5 categorías ad-hoc por dominios canónicos multi-valor. Bootstrap ya disponible en [`scripts/bootstrap_taxonomy.py`](../scripts/bootstrap_taxonomy.py); falta curar a ~80-100 dominios relevantes en `data/vocabulary/domains.json` y reindexar.
- [ ] **Sparse retrieval BM25** (BGE-M3 lo soporta nativo) — ayuda con nombres propios raros, términos técnicos
- [ ] **Threshold de score** en search_corpus — filtrar resultados <0.50 antes de devolver al LLM
- [ ] **Reranking cross-encoder** sobre top-20 → top-5 — mejora precisión sin cambiar retrieval
- [ ] **Fix bug citation rendering** del plugin v2.0.0-rc6 (esperar v2.0.0 stable o reportar)

Sprint 2 NO bloquea Fase B: la wiki se está compilando sobre el corpus actual sin esperar a la migración de taxonomía.

---

## Fase B — Wiki estructurada con KG emergente (Layers 2+3 fusionadas)

**Objetivo:** construir una base de conocimiento navegable en markdown — páginas por entidad, concepto, autor y obra — donde la estructura del grafo emerge naturalmente de los wikilinks. Reemplaza el plan original de "entity index SQLite" + "LLM Wiki" como dos fases separadas: **es una sola cosa que escala**.

### Por qué wiki-first en lugar de KG-first

- **Markdown es a la vez prosa correctable y datos estructurados** — el humano lo edita en VSCode/Obsidian, el LLM lo ingiere como contexto, el grafo se extrae de los wikilinks
- **Los summaries de ProxySummaries ya son una primera síntesis** (vídeo crudo → bullets temáticos curados). Pasar de ahí a entidades + relaciones es **un paso, no dos**
- **Sin vendor lock-in**: no Neo4j, no triplestore, no JSON-LD obligatorio. El día que haga falta KAG formal, parser de wikilinks → triples es trivial
- **Visualización gratis** (Obsidian graph view, GitHub mermaid)
- **Versionable en git** (audit trail completo, rollback granular)

### Componentes

- **Cold path extractor** (Claude Max overnight) que lee chunks raw y produce JSON estructurado por concepto/entidad
- **Generador de markdown** (script Python plantillado) que convierte JSON → `.md` con frontmatter + cuerpo + wikilinks
- **Validación automática** antes de commitear a `wiki/`: schema, wikilinks resuelven, types canónicos, citas verificables ([`scripts/validate_wiki_relations.py`](../scripts/validate_wiki_relations.py))
- **Indexación de wiki en Qdrant** como `source_type=wiki_page` junto a los chunks raw — 1 vector focal por página ([`scripts/index_wiki_to_qdrant.py`](../scripts/index_wiki_to_qdrant.py))
- **Índice SQLite derivado** del filesystem en `data/wiki.db` — pages, aliases, relations, body_wikilinks, citations. Habilita la lane indirecta del modo híbrido sin necesidad de un segundo índice semántico ([`scripts/build_wiki_db.py`](../scripts/build_wiki_db.py))
- **Tool MCP `get_wiki_page(page_id)`** — devuelve la página completa con frontmatter + cuerpo
- **`search_corpus` híbrido** — devuelve `{wiki_pages, raw_chunks, retrieval_metadata}` con tres lanes de retrieval (raw semántica, wiki semántica focal, wiki indirecta vía citations) y `match_via` por entrada wiki

### Estructura del repo wiki

```
wiki/
├── README.md
├── _meta/
│   ├── relation_types.json     ← set canónico de relation types
│   ├── wiki_control.json       ← registro de páginas compiladas
│   ├── coverage_state.json     ← estado del pipeline de cobertura sistemática (latente)
│   ├── topic_filters.json      ← filtros declarativos pre-extracción
│   └── next_batch_ranking.json ← ranking determinista del próximo batch
├── authors/
├── entities/works/
├── concepts/
└── synthesis/
```

Detalle completo del pipeline: [WIKI_GENERATION.md](WIKI_GENERATION.md).

### Estrategia incremental dentro de Fase B

1. ✅ **Piloto** — 5 páginas generadas y validadas (batch 1, 2026-04).
2. ✅ **Refinamiento de prompt + schema** — ≥3/5 del piloto pasaron validación; schema migrado a `relations[]` tipadas (2026-04-30).
3. ✅ **Modo híbrido en hot path** — `search_corpus` devuelve wiki + raw + metadata; smoke test 8/8 verde.
4. ✅ **Índice SQLite derivado + retrieval indirecto vía citations** (2026-04-30).
5. 🟡 **Escalado** — 11 páginas compiladas; objetivo intermedio ~50 páginas hub. Siguiente palanca: pipeline de cobertura sistemática (ver [CORPUS_COVERAGE_STRATEGY.md](CORPUS_COVERAGE_STRATEGY.md)) que requiere `inventory_summaries.py` + `extract_video_themes.py` (pendientes).
6. ⏸️ **Loop iterativo continuo** — recompilación selectiva, drift detection. Por activar.

### Métrica de éxito

- Para una query conceptual repetida (ej. "explícame la sombra junguiana"), la wiki page recupera el 80% de las afirmaciones que el LLM hot generaría desde chunks raw, con citas verificables al raw
- Latencia total NO se degrada (mismo orden, <300ms con dos índices)
- Coste de tokens por respuesta del LLM hot baja >30% (síntesis ya pre-cocinada)

---

## Fase C — Despliegue producción (Hetzner)

**Objetivo:** quitar ngrok y la dependencia del PC del desarrollador. URL fija, autenticación, alta disponibilidad básica.

### Componentes

- Servidor ligero en Hetzner (2-4 GB RAM, sin GPU): Qdrant + servidor MCP
- Indexado sigue corriendo local (en la GPU del desarrollador), sync via rsync de la carpeta `data/qdrant/`
- BGE-M3 en CPU para query encoding (200-500ms, aceptable)
- URL fija en subdominio propio
- Auth: bearer token en header MCP
- TLS via Caddy / Let's Encrypt

### Migración

- Cero cambios en código del servidor MCP (es portable)
- Cambia el AI Service en Mattermost a la URL nueva
- ngrok desaparece, los compañeros pueden seguir consultando

---

## Fase D — Cold path con voluntarios

**Objetivo:** producción asíncrona de nuevos chunks aprovechando recursos ociosos distribuidos.

### Flujo

```
Usuario en chat:
  /queue_analysis <documento>

Servidor:
  → encola job en SQLite con metadata (qué documento, prioridad, tipo de análisis)

Worker voluntario (overnight):
  → toma job, procesa con su recurso (Claude Max, GPU local, API personal)
  → genera chunks con la misma estructura del corpus existente
  → POST al servidor → corpus enriquecido

Próxima query del usuario:
  → ya puede consultar lo nuevo
```

### Componentes

- Tool MCP `enqueue_deep_analysis(description, source_url_or_pdf, priority)`
- Cola SQLite simple (`tasks(id, status, payload, created_at, claimed_by, completed_at)`)
- API REST de workers para `claim_job` / `submit_result`
- Worker template (Python script ejecutable con `claude -p` headless o llamando a Gemini/GPT)
- **Capa de ingesta multi-formato con [microsoft/markitdown](https://github.com/microsoft/markitdown)** — convierte PDF, Office, HTML, audio, imágenes a markdown estructurado. Es la primera milla obligada del worker antes de pasar el contenido al LLM para chunking. Detalles en [TAXONOMY_PROPOSAL.md §5](TAXONOMY_PROPOSAL.md#5-ingesta-multi-formato--markitdown)
- Webhook de notificación cuando un job se completa

### Modelo de coste

- $0 marginal cuando el voluntario usa cuota Max ya pagada o API gratuita
- Los workers son "best effort" — si nadie procesa, el job espera
- El propietario del proyecto podría correr 1 worker permanente con su cuota Max para asegurar throughput mínimo

---

> **Nota:** la antigua "Fase E — LLM Wiki compilado" se ha **fusionado con Fase B** en una sola estrategia wiki-first / KG-emergente. Ya no es una fase separada al final del roadmap. Detalle en [WIKI_GENERATION.md](WIKI_GENERATION.md).

---

## Principios transversales (todas las fases)

1. **Cada fase añade tools MCP, no rompe las existentes** — el cliente Mattermost sigue funcionando aunque el servidor evolucione
2. **El corpus es el contrato estable** — schema de chunk no cambia entre fases (solo se añaden campos, no se quitan)
3. **Decoupling MCP/LLM intacto** — ninguna fase introduce dependencia con un LLM concreto
4. **Lo que se puede diferir, se difiere** — cada fase solo se construye cuando hay evidencia de que la anterior no basta
5. **Hot vs Cold separados** — ninguna fase mezcla los dos flujos en un solo path

Para argumentación detallada de las decisiones de diseño ver [ARCHITECTURE.md](ARCHITECTURE.md).
