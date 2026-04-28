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

### Sprint 2 — mejoras incrementales sobre Layer 1 (PRÓXIMO, opcional)

A decidir según métricas observadas en uso real:

- [ ] **Sparse retrieval BM25** (BGE-M3 lo soporta nativo) — ayuda con nombres propios raros, términos técnicos
- [ ] **Threshold de score** en search_corpus — filtrar resultados <0.50 antes de devolver al LLM
- [ ] **Reranking cross-encoder** sobre top-20 → top-5 — mejora precisión sin cambiar retrieval
- [ ] **System prompt reforzado** con instrucción explícita de búsqueda lateral antes de declarar huecos en el corpus
- [ ] **Fix bug citation rendering** del plugin v2.0.0-rc6 (esperar v2.0.0 stable o reportar)

**Criterio de salto a Fase B:** si las queries de cross-reference complejas siguen perdiendo conexiones cross-vídeo aún con sparse + reranker, justifica entity index.

---

## Fase B — Entity index (Layer 2)

**Objetivo:** búsqueda por entidad, no solo por similitud semántica. Mejorar cross-reference: "todas las menciones de Jung en el corpus", "co-ocurrencias entre arquetipo y consumismo".

### Componentes

- Extracción de entidades por chunk (NER + curación manual)
- `vocabulary.json` enriquecido: entidades canónicas + aliases
- Tabla SQLite de co-ocurrencias `(entidad, chunk_id, weight)`
- Nuevas tools MCP:
  - `list_concept_occurrences(concept, include_aliases)` — todos los chunks que mencionan X
  - `cross_reference(concept_a, concept_b)` — chunks donde aparecen ambos
  - `get_related_concepts(concept, top_n)` — entidades co-ocurrentes con peso

### Por qué no en Fase A

Layer 2 requiere que el corpus esté **saneado y categorizado** (Fase A). Construir entity index sobre datos sucios = doble trabajo. Por eso A primero.

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

## Fase E — LLM Wiki compilado (Layer 3)

**Objetivo:** páginas concepto pre-sintetizadas que se sirven directamente cuando aplica, sin re-sintetizar en cada query.

### Estructura

```
wiki/
├── entities/
│   ├── jung-carl.md           ← biografía + apariciones en el canal
│   ├── lovecraft.md
│   └── tyler-durden.md
├── concepts/
│   ├── la-sombra.md           ← síntesis cross-vídeo de la sombra junguiana
│   ├── hieros-gamos.md
│   └── arquetipo-solar.md
└── synthesis/
    ├── violencia-en-proxy.md  ← análisis temáticos largos
    └── mito-moderno.md
```

### Cómo se generan

- Cold path (Fase D) toma jobs de tipo "wiki_compile"
- Worker overnight invoca `claude -p` con prompt: "construye página concepto sobre X usando solo chunks del corpus que voy a darte"
- Resultado se versiona en Obsidian-friendly markdown con wikilinks
- Tool MCP `get_concept_wiki(concept)` devuelve la página completa o RAG sobre las páginas

### Hot path con wiki

- Search se hace contra **dos índices**: chunks crudos (Layer 1) + wiki pages (Layer 3)
- Para queries factuales/recuperativas → dominan chunks
- Para queries conceptuales/cross-reference → dominan wiki pages (síntesis ya hecha)
- LLM ve ambos: fuentes primarias citables + síntesis pre-cocinada

### Cuándo justifica

- Cuando se observa que las queries conceptuales repetidas malgastan tokens del LLM hot re-sintetizando lo mismo
- Cuando hay >100 conceptos que merecen tratamiento sistemático
- Cuando la base de usuarios crece y la economía de "cocinar una vez, servir mil" se vuelve relevante

---

## Principios transversales (todas las fases)

1. **Cada fase añade tools MCP, no rompe las existentes** — el cliente Mattermost sigue funcionando aunque el servidor evolucione
2. **El corpus es el contrato estable** — schema de chunk no cambia entre fases (solo se añaden campos, no se quitan)
3. **Decoupling MCP/LLM intacto** — ninguna fase introduce dependencia con un LLM concreto
4. **Lo que se puede diferir, se difiere** — cada fase solo se construye cuando hay evidencia de que la anterior no basta
5. **Hot vs Cold separados** — ninguna fase mezcla los dos flujos en un solo path

Para argumentación detallada de las decisiones de diseño ver [ARCHITECTURE.md](ARCHITECTURE.md).
