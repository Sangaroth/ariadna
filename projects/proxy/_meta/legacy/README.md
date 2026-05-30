# wiki/_meta/legacy/

Archivos de pipelines previos del proyecto Ariadna que **NO** participan en el flujo actual (extract_video_themes.py + sub-agente + shadow flow, post-2026-05-02).

Se conservan como histórico auditable y para compatibilidad de scripts legacy
puntuales (`scripts/rank_wiki_candidates.py`).

## Contenido

- `wiki_control.json` — control file del pipeline pull-based original (ranking
  + viability_filter + coverage tracking). No leído por el extractor actual.
- `coverage_state.json` — estado de cobertura del pipeline pull-based
  (qué chunks raw cubren qué páginas). Reemplazado por shadow flow + commits
  auditables.
- `next_batch_ranking.json` — ranking determinista del próximo batch generado
  por `rank_wiki_candidates.py`. Output del workflow legacy.

## Política

- **NO se envía al LLM** — el extractor actual usa solo `scope.md`,
  `canonical_whitelist.json`, `relation_types.json`, `topic_filters.json` y el
  índice slim derivado del filesystem (.md con frontmatter `page_id`).
- Si volvemos a un workflow ranking-based, regenerar desde aquí o reubicar.
- Eliminar definitivamente cuando el workflow shadow + sub-agente esté
  consolidado y no haya rollback previsible.
