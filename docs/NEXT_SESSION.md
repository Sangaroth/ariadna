# Prompt de continuidad — Ariadna

> **Cómo usar este archivo:** copia la sección "Prompt para pegar al iniciar nueva sesión" tal cual al asistente al abrir nueva conversación de Claude Code en este repo. El asistente leerá los docs referenciados y arrancará alineado con el estado actual.
>
> **Última actualización:** 2026-04-29 (tras primer batch piloto de wiki)

---

## Prompt para pegar al iniciar nueva sesión

```
Soy el mismo usuario. Continuamos el proyecto Ariadna (servidor MCP de RAG sobre
corpus YouTube del canal Proxy, integrado con Mattermost via plugin Agents
v2.0.0-rc6 + ngrok).

Estado al 2026-04-29:
- Fase A Sprint 1 CERRADA (RAG validado en DM con calidad notable)
- Fase B (Wiki estructurada con KG emergente) iniciada con primer batch piloto
  de 5 páginas markdown compiladas
- Repo público: github.com/sangaroth-ux/ariadna
- Último commit en main: d4327cd

ANTES DE HACER NADA, lee en este orden:
1. docs/SESSION_CONTEXT.md — estado vivo del proyecto, decisiones, quirks
2. docs/NEXT_SESSION.md — este archivo, resumen ejecutivo + opciones de avance
3. docs/ARCHITECTURE.md — argumentación de diseño (decoupling, hot/cold,
   por qué taxonomía importa más que tecnología)
4. docs/WIKI_GENERATION.md — pipeline cold path actualizado (cargar summaries
   completos del source original, NO chunks aislados de Qdrant)
5. docs/RESPONSE_FLOW.md — 4 ejemplos estructurados de respuesta híbrida wiki+raw
6. wiki/_meta/wiki_control.json — control del batch piloto, criterio ordenación,
   observaciones, recomendaciones para próximo batch

Verifica al inicio:
- Si servidor MCP local sigue vivo (ss -tlnp | grep 8765, pgrep ngrok)
- Si la URL ngrok actual coincide con la registrada en SESSION_CONTEXT
- Si he interrumpido alguna tarea a medias en el todo list previo

Pregúntame qué línea quiero retomar antes de proponer trabajo nuevo.
Las opciones razonables están en la sección "Próximas opciones" de
docs/NEXT_SESSION.md.
```

---

## Estado actual (resumen ejecutivo)

| Capa | Estado | Notas |
|---|---|---|
| **Layer 0** RAG dense BGE-M3 + Qdrant + MCP server + Mattermost | ✅ Producción | Tools en Auto Run (DM), validado |
| **Layer 1** Wiki estructurada en `wiki/` | 🟡 Piloto en marcha | 5 páginas compiladas en primer batch |
| **Layer 2** KG emergente de wikilinks | 🟡 Implícito | 30 wikilinks salientes ya generados, mini-grafo formado |
| **Sprint 2** mejoras Layer 1 (sparse, reranker, threshold) | ⏸️ Backlog | A decidir tras observar uso real |
| **Fase C** despliegue Hetzner (URL fija) | ⏸️ Pendiente | Independiente, en cualquier momento |
| **Fase D** cold path con voluntarios + ingesta multi-formato | ⏸️ Diseñado | Necesario para escalar wiki >50 páginas |

## Trabajo más reciente (sesión 2026-04-29)

1. Refactor del roadmap: fusión de antiguas Fase B (entity index) y Fase E (LLM Wiki) en una sola estrategia **wiki-first con KG emergente**
2. Decisión: modo **híbrido (wiki + raw paralelo)** confirmado sobre wiki-first puro
3. Decisión: las 5 categorías legacy del corpus se **descartan**, taxonomía oficial = OpenAlex Topics
4. Doc nuevo: `docs/RESPONSE_FLOW.md` con 4 ejemplos estructurados validando el modo híbrido
5. Doc nuevo: `docs/WIKI_GENERATION.md` con pipeline cold path completo
6. Doc revisado: `docs/TAXONOMY_PROPOSAL.md` con schema multi-fuente (papers, libros, podcasts, etc.) y `Author` como entidad canónica con ORCID/Wikidata
7. Script nuevo: `scripts/bootstrap_taxonomy.py` para descargar OpenAlex Topics
8. Aclaración importante: **el cold path lee summaries.md completos del source original**, NO chunks aislados. Qdrant es discovery, no compilation
9. **Primer batch piloto wiki** completado: 5 páginas compiladas con discovery via Qdrant + escritura markdown actuando como LLM extractor

## Las 5 páginas piloto compiladas

| Página | page_type | domain | Top score | Wikilinks out |
|---|---|---|---|---|
| `wiki/concepts/shadow-archetype.md` | concept | social.psychology.jungian | 0.628 | 5 |
| `wiki/authors/jung-carl-gustav.md` | author | social.psychology | 0.592 | 4 |
| `wiki/entities/works/fight-club-1999-film.md` | entity_work | arts.cinema | 0.599 | 4 |
| `wiki/concepts/hieros-gamos.md` | concept | humanities.religion | 0.601 | 6 |
| `wiki/synthesis/mito-moderno-en-proxy.md` | synthesis | interdisciplinary.cultural_studies | **0.710** | **11** |

Stats agregados:
- 105 chunks únicos recuperados (en discovery)
- 56 citas raw verificables (timestamps clicables a YouTube)
- 30 wikilinks salientes (mini-grafo entre las 5 + referencias a páginas futuras)
- 20 lagunas declaradas honestamente

## Decisiones tomadas (no obvias del código)

| Decisión | Razón | Doc |
|---|---|---|
| **Híbrido > wiki-first puro** | Lateral recall, drift detection, verificación cruzada | `docs/RESPONSE_FLOW.md` §1 |
| **OpenAlex Topics como taxonomía oficial** | 4500+ topics canónicos, IDs estables, gratis, prepara Fase D | `docs/TAXONOMY_PROPOSAL.md` §4.5 |
| **Wiki en markdown puro (no Neo4j)** | Editable por humano, ingestible por RAG, KG emerge gratis | `docs/ARCHITECTURE.md` §5 |
| **Cold path lee source original, no chunks** | Fidelidad pleno contexto. Qdrant solo descubre qué fuentes leer | `docs/WIKI_GENERATION.md` §1 |
| **Wiki vive en mismo repo (`wiki/`)** | Atomicidad de versionado, no separar contenido de código | esta sesión |
| **5 categorías legacy descartadas** | Eran placeholder de data semilla, no compromiso | `docs/TAXONOMY_PROPOSAL.md` §4.2 |

## Decisiones aún abiertas

1. **Threshold de wiki score** para considerar "wiki suficiente" (provisional 0.65) — tunear con datos reales
2. **Threshold de raw score** para fallback honesto a "no encuentro" (provisional <0.45)
3. **Profundidad máxima de namespace OpenAlex** (provisional 3 niveles `group.discipline.school`)
4. **Política de promoción manual de relation types nuevos** (lista canónica en `wiki/_meta/relation_types.json`)
5. **Modelo LLM por defecto del extractor cold path**: Claude (calidad) vs Gemini (cuota gratis grande) vs A/B
6. **Top-K de wiki vs raw chunks devueltos**: provisional 2 wiki + 5 raw

## Próximas opciones (elegir según ánimo)

### A — Continuar batch wiki (recomendado si queremos consolidar Layer 1)

⚠️ **REQUISITO ANTES DE EJECUTAR ESTE BATCH:** los candidatos del batch piloto fueron elegidos a mano para demostrar el concepto y validar el schema. **A partir del próximo batch el criterio debe ser determinista y reproducible** — no más selección por intuición.

**Pre-requisito obligatorio:** crear `scripts/rank_wiki_candidates.py` que:

1. Parsee todas las páginas en `wiki/` y extraiga wikilinks `[[page_id]]`
2. Filtre a wikilinks "rotos" (sin `.md` correspondiente) — ese es el universo de candidatos
3. Para cada candidato:
   - **Connectivity** = cuántas páginas existentes lo referencian (el campo más fuerte ahora; expresa demanda real del grafo)
   - **Recurrence** = nº chunks en corpus que lo mencionan (vía query MCP del page_id + sus aliases)
   - **Domain diversity** = bonus si su domain estimado no está aún cubierto en `pages_compiled`
4. Score = `0.5 * norm(recurrence) + 0.3 * norm(connectivity) + 0.2 * domain_diversity_bonus`
5. Tie-break alfabético por `page_id` (determinista)
6. Aplicar filtro de viabilidad (≥10 chunks, score promedio ≥0.55)
7. Output: lista ordenada en `wiki/_meta/next_batch_ranking.json` con score, métricas y reasoning

Sin script, NO se compila siguiente batch — la decisión queda fuera del control criterial documentado y reintroduce sesgo humano.

**Candidatos previsibles** (sólo orientación, esperar al script para orden definitivo):

- `anima-archetype` — referenciado desde 3+ páginas piloto
- `individuation` — referenciado desde 4+ páginas
- `collective-unconscious` — 3 referencias
- `consumismo-critica`, `lovecraft-howard`, `matrix-1999-film`, `man-of-steel-2013-film`
- `mito-solar`, `mito-lunar`, `mito-polar`

**Beneficio del batch (una vez ranking determinista):** resuelve wikilinks rotos y refuerza la mini-grafo emergente con orden auditable.

### B — Bootstrap taxonomía OpenAlex

Pasos:
1. `python scripts/bootstrap_taxonomy.py --mailto tu@email`
2. Curar `data/vocabulary/domains_full.json` → `data/vocabulary/domains.json` (las 80-100 que aplican al corpus)
3. Añadir extensiones `proxy.contemporary.*` para conceptos no académicos
4. Reclasificar chunks existentes con nuevo schema (drop legacy `category` field)

**Beneficio:** prerrequisito para próximos batches con taxonomía rigurosa, prepara Fase D.

### C — Sprint 2: mejoras incrementales Layer 1

- Sparse BM25 (BGE-M3 ya soporta) — ayuda con nombres propios raros
- Threshold de score en `search_corpus` — filtrar <0.50
- Reranker cross-encoder sobre top-20 → top-5
- Prompt reforzado con búsqueda lateral

**Beneficio:** mejora calidad de hot path sin tocar wiki.

### D — Despliegue Hetzner (Fase C)

Quitar ngrok, URL fija, auth, multi-cliente. Servidor ligero (sin GPU), Qdrant + MCP server + sync rsync de `data/qdrant/` desde local tras reindexado.

**Beneficio:** producción real, los compañeros pueden usar Ariadna sin depender del PC del desarrollador.

### E — Cold path infra (Fase D)

Cola SQLite, tool MCP `enqueue_deep_analysis`, worker template con markitdown + Crossref/arXiv API. Permite que el wiki escale a >50 páginas y empiece a ingerir papers, libros, podcasts.

**Beneficio:** desbloquea generación a escala de wiki + multi-fuente.

### F — Validación humana del piloto

Leer las 5 páginas wiki compiladas, marcar `review_status: human_reviewed` en frontmatter, corregir errores. Iterar si hay patrones de fallo del extractor.

**Beneficio:** valida que el pipeline produce calidad utilizable antes de escalar.

## Comandos clave

```bash
# Setup sesión
cd /home/dae/PycharmProjects/ariadna && source .venv/bin/activate

# Verificar infraestructura
ss -tlnp 2>/dev/null | grep 8765        # MCP server vivo?
pgrep -af ngrok                          # tunel vivo?

# Levantar (si no están vivos)
./scripts/run_server.sh                  # terminal 1
./scripts/run_tunnel.sh                  # terminal 2

# Búsqueda CLI (con server parado)
python -m ariadna.search "query" --top-k 5

# Búsqueda HTTP en paralelo (server corriendo)
# Definir función bash en ~/.bashrc primero (ver SESSION_CONTEXT.md)
ariadna-q "query" 5

# Test MCP directo
curl -s -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Re-indexar corpus si cambió ProxySummaries (servidor parado)
python -m ariadna.build_index --recreate

# Ver wiki control file
cat wiki/_meta/wiki_control.json | python3 -m json.tool

# Ver últimos commits remoto
gh repo view sangaroth-ux/ariadna --json url,pushedAt
gh api repos/sangaroth-ux/ariadna/commits --jq '.[0:3] | .[] | {sha: .sha[0:7], msg: .commit.message | split("\n")[0]}'
```

## Quirks vivos al 2026-04-29

1. **ngrok URL volátil** — cambia en cada restart. Actualizar en Mattermost MCP Server config + Refresh Tools.
2. **Plugin Mattermost Agents v2.0.0-rc6 citation rendering bug** — tokens `citeturnNsearchN` se filtran como texto. Workaround: prompt del agente fuerza markdown explícito `[título](url)`.
3. **Qdrant embedded lock** — solo un proceso. Si CLI da `RuntimeError: Storage folder already accessed`, parar server o usar `ariadna-q` (HTTP).
4. **ngrok snap no kill desde sandbox** — kill -9 desde Claude Code falla por confinement. Hace falta terminal del usuario o `sudo snap restart ngrok`.
5. **MCP client not connected (false positive)** tras cambios de config en Mattermost — Clear Cache + Refresh Tools en pestaña Tools soluciona.

## Si encuentras algo confuso

- Memoria persistente: `~/.claude/projects/-home-dae-PycharmProjects-ariadna/memory/`
- Diseño arquitectónico completo (RAG vs KAG vs Wiki) upstream: `../ProxySummaries/docs/knowledge-architecture-research.md` (~750 líneas)
- Repo público con todos los docs: https://github.com/sangaroth-ux/ariadna
