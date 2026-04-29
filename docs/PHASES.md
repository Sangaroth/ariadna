# Fases de desarrollo de Ariadna

> Roadmap por capas. Cada fase añade valor independiente y se construye encima de la anterior sin romperla.

## Estado actual: **Fase A Sprint 1 — CERRADA** (2026-04-23)

Validación end-to-end completada con calidad notable en DM con Ariadna. Detalles en [SESSION_CONTEXT.md](SESSION_CONTEXT.md#validacion-calidad--resultados).

---

## Fase A — RAG mínimo viable

**Objetivo:** demostrar que el corpus se puede consultar semánticamente desde Mattermost via MCP, con cita de fuente y honestidad epistémica.

### Sprint 1 — Layer 1 RAG dense (✅ CERRADO)

- [x] Parser de `summary.md` → chunks con metadata estructurada
- [x] Embedder BGE-M3 local en GPU
- [x] Qdrant embedded con 6036 chunks indexados
- [x] Servidor MCP HTTP exponiendo 3 tools (`search_corpus`, `get_video_summary`, `list_videos`)
- [x] Integración con Mattermost AI plugin v2.0.0-rc6 via ngrok
- [x] Per-tool policy en Auto Run (DM) — sin Accept/Reject manual
- [x] Validación de calidad con queries golden + control out-of-corpus

**Métricas alcanzadas:**
- Indexado completo: 86s para 288 vídeos / 6036 chunks
- Latencia query end-to-end: <200ms
- Scores BGE-M3 en queries relevantes: 0.55-0.67
- Recall correcto en cross-reference, lateral search funcional, citas verificadas no alucinadas

### Sprint 2 — mejoras incrementales sobre Layer 1 + bootstrap de Fase B

A decidir según métricas observadas en uso real:

- [ ] **Reclasificación de chunks con taxonomía OpenAlex** (drop del legacy `proxy_category`) — reemplazar las 5 categorías ad-hoc por dominios canónicos multi-valor desde [`data/vocabulary/domains.json`](../data/vocabulary/domains.json)
- [ ] **Bootstrap de OpenAlex Topics** vía [`scripts/bootstrap_taxonomy.py`](../scripts/bootstrap_taxonomy.py) → curar a ~80-100 dominios relevantes
- [ ] **Sparse retrieval BM25** (BGE-M3 lo soporta nativo) — ayuda con nombres propios raros, términos técnicos
- [ ] **Threshold de score** en search_corpus — filtrar resultados <0.50 antes de devolver al LLM
- [ ] **Reranking cross-encoder** sobre top-20 → top-5 — mejora precisión sin cambiar retrieval
- [ ] **System prompt reforzado** con instrucción explícita de búsqueda lateral antes de declarar huecos en el corpus
- [ ] **Fix bug citation rendering** del plugin v2.0.0-rc6 (esperar v2.0.0 stable o reportar)

**Criterio de salto a Fase B:** una vez la taxonomía esté importada y los chunks reclasificados, el extractor de wiki puede arrancar con bases sanas.

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
- **Validación automática** antes de commitear a `wiki/`: schema, wikilinks resuelven, dominios válidos, citas verificables
- **Indexación de wiki en Qdrant** como `source_type=wiki_page` junto a los chunks raw
- **Nuevas tools MCP:**
  - `get_wiki_page(page_id)` — devuelve la página completa con frontmatter + cuerpo
  - `list_wiki_pages(page_type, domain, review_status)` — listado filtrado
  - `find_relations(page_id_a, page_id_b)` — explora paths de wikilinks entre dos entidades
  - `search_corpus` extendido para devolver chunks raw + wiki pages en paralelo (modo híbrido)

### Estructura del repo wiki

```
wiki/
├── README.md
├── _meta/
│   ├── compilation_log.json
│   ├── pending_review.json
│   └── relation_types.json
├── authors/
├── entities/works/
├── concepts/
└── synthesis/
```

Detalle completo del pipeline: [WIKI_GENERATION.md](WIKI_GENERATION.md).

### Estrategia incremental dentro de Fase B

1. **Piloto** — generar 5 páginas (uno por categoría) y validar end-to-end calidad humano + máquina
2. **Refinamiento de prompt** hasta que ≥3/5 pasen validación sin reescritura mayor
3. **Escalado** a las 50-100 entidades/conceptos más recurrentes del corpus actual
4. **Indexación híbrida** activa en hot path
5. **Loop iterativo continuo**: nuevos chunks → recompilación selectiva → validación humana

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
