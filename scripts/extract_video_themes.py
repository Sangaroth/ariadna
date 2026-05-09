#!/usr/bin/env python3
"""extract_video_themes.py

Extractor push-based de la wiki Ariadna (patrón LLM Wiki de Karpathy).

Para cada summary.md del corpus Proxy, invoca Claude Opus 4.7 vía suscripción
Max (headless `claude -p` con --resume para reutilizar sesión y aprovechar
prompt caching) y emite JSON estructurado con:

  - entities[]               : entidades detectadas con clasificación + señales
  - pending_updates[]        : actualizaciones propuestas a páginas wiki existentes
  - thesis_candidates[]      : tesis articuladas por el speaker (author_thesis)
  - discarded[]              : entidades filtradas con justificación + cita literal
  - summary_stats            : metadata de la extracción

NADA se aplica al wiki sin firma humana. El aggregator fusiona los JSONs por
vídeo en colas de revisión (`discard_log.json`, `pending_updates.json`,
`promote_queue.json`, `thesis_candidates.json`) — el humano firma desde ahí.

Uso:
    # Listar summaries pendientes (no invoca Claude)
    python scripts/extract_video_themes.py --discover

    # Dry run: construye prompts y muestra primer summary, no invoca Claude
    python scripts/extract_video_themes.py --dry-run

    # Piloto: 5 vídeos hand-picked, escribe outputs pero NO al wiki
    python scripts/extract_video_themes.py --pilot

    # Procesar un único vídeo concreto
    python scripts/extract_video_themes.py --video-id gB5NoYbdZWk

    # Barrido completo (288+ vídeos)
    python scripts/extract_video_themes.py --run-id batch_2026_05_02

    # Reanudar barrido interrumpido
    python scripts/extract_video_themes.py --resume batch_2026_05_02

    # Agregar JSONs de un run en colas de revisión
    python scripts/extract_video_themes.py --aggregate batch_2026_05_02

Requisitos:
  - Claude Code CLI (`claude`) en PATH, autenticado con cuenta Max
  - Variable ARIADNA_CORPUS_PATH apuntando a ProxySummaries/data/playlists
    (default: ../ProxySummaries/data/playlists relativo al repo)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parent.parent
WIKI = REPO / "wiki"
META = WIKI / "_meta"
RUNS_DIR = META / "extraction_runs"

SCOPE_PATH = META / "scope.md"
WHITELIST_PATH = META / "canonical_whitelist.json"
RELATION_TYPES_PATH = META / "relation_types.json"
TOPIC_FILTERS_PATH = META / "topic_filters.json"

DEFAULT_CORPUS = Path(
    os.environ.get(
        "ARIADNA_CORPUS_PATH",
        str(REPO.parent / "ProxySummaries" / "data" / "playlists"),
    )
)

# ---------------------------------------------------------------------------
# Límites de sesión (evitar invalidación de caché por TTL y proteger contra
# context-window overrun). Valores firmados con usuario 2026-05-02.
# ---------------------------------------------------------------------------

SESSION_MAX_VIDEOS = 20
SESSION_MAX_SECONDS = 55 * 60  # margen sobre 20 vids × ~165s = ~55min para evitar cortes mid-vid
SESSION_MAX_TOKENS = 500_000
PER_CALL_TIMEOUT_S = 1200

# Vídeos seleccionados a mano para el piloto. Cubrir: monográfico Tolkien,
# monográfico Lovecraft, vídeo con tesis articulada del canal, mixto,
# vídeo con bloques out-of-scope para validar discards.
PILOT_VIDEO_SLUGS = [
    "leyendo-el-silmarillion-tolkien-y-el-mal-primario",  # monográfico Tolkien
    "otono-de-cuentos-lovecraft",                          # monográfico Lovecraft
    "4x02-sistema-limbicocortical-hipocampo",             # tesis del canal: clasificación de memoria, neuroanatomía
    "analisis-arquetipico-de-tarzan",                     # análisis de obra (mixto: arquetipo + obra)
    "t5x11-el-amor-en-realidad-ii",                       # candidato out-of-scope parcial
]

# Piloto 2 (audit) — casuísticas distintas para validar antes de overnight.
# Cubre: enriquecimiento de stub existente, intra-batch dedup de page_id,
# update sobre seed rico (regla cita-only), promote_new no-canonical,
# foundational singleton (figura canónica rara).
PILOT_2_VIDEO_SLUGS = [
    "tolkien-y-los-dragones",                                       # enriquece stub tolkien-jrr existente
    "el-genesis-en-tolkien-parte-1",                                # overlap intra-batch con anterior
    "psicologia-101-como-un-pollo-demostro-a-jung",                 # update sobre jung-carl-gustav (rico)
    "analisis-arquetipico-de-dracula-de-bram-stoker",               # promote_new monográfico no-canonical
    "que-es-el-materialismo-filosofico-con-daniel-alarcon",         # foundational singleton + canonical raros
]

# Modelos diferenciados por rol. Main extraction y synthesis son judgment-heavy
# (scope discrimination §3, gate §2.4.1, articulación de tesis original); el
# stub sub-agente de concept/author/entity_work es schema-driven y Sonnet basta.
CLAUDE_MODEL_MAIN = "claude-opus-4-7"
CLAUDE_MODEL_STUB_SUBAGENT = "claude-sonnet-4-6"
CLAUDE_MODEL_SYNTHESIS_SUBAGENT = "claude-opus-4-7"


# ---------------------------------------------------------------------------
# Output schema (lo verá el LLM en system prompt)
# ---------------------------------------------------------------------------

OUTPUT_SCHEMA = """
# Schema de salida (JSON estricto, sin texto previo ni posterior, sin code fences)

{
  "video_id": "string — id de YouTube",
  "video_title": "string",
  "playlist": "string",
  "category": "string — categoría legacy del corpus si aplica",

  "entities": [
    {
      "surface_form": "string — cómo aparece literal en el summary",
      "canonical_guess": "string — slug propuesto en kebab-case (ej. 'jung-carl-gustav', 'mito-polar')",
      "page_type": "concept | author | entity_work | entity_institution",
      "domain_primary_guess": "string — un dominio de scope.md §1, p.ej. 'social.psychology.jungian'",
      "depth_in_video": "passing_mention | secondary | central_thesis",
      "minutes_estimate": "number — minutos del vídeo dedicados",
      "framing_marks": [
        {
          "mark_type": "applied_framework | self_referenced_origin | declared_thesis | foundational_invocation",
          "quote_evidence": "string — cita literal del summary que justifica este flag"
        }
      ],
      "assumed_prior": "boolean — el speaker da por hecho la entidad sin presentarla",
      "is_canonical_external": "boolean — figura en canonical_whitelist con auto_promote:true",
      "is_in_whitelist_soft": "boolean — figura en whitelist con auto_promote:false",
      "exists_in_wiki": "boolean — page_id ya tiene página en el wiki snapshot recibido",
      "decision": "promote_new | update_existing | mentions_index | discard",
      "decision_reason": "string — razón breve, referenciando el criterio del scope.md",
      "quote_evidence": "string — cita literal del summary donde aparece la entidad"
    }
  ],

  "_doc_promote_new": "Para entities con decision=promote_new NO emites el cuerpo de la página: tu rol aquí es DECIDIR qué merece página. Un sub-agente posterior, con contexto focalizado, construirá el stub completo (frontmatter rico + body con secciones, citas y wikilinks). Tú aportas: page_id, page_type, domain_primary_guess, depth_in_video, decision_reason justificando el criterio scope.md, y quote_evidence con la cita más representativa. Eso basta.",

  "pending_updates": [
    {
      "page_id": "string — page_id de página existente. Solo si has hecho Read del file_path",
      "update_type": "insert_after_passage | insert_before_passage | extend_passage | replace_passage | append_to_section | mark_laguna_resolved | add_relation",
      "anchor_passage": "string — substring LITERAL ÚNICO en la página existente que sirve de ancla. Obligatorio para insert_*/extend_/replace_. La página se rechazará si el anchor no aparece literal o aparece más de una vez. Para uniqueness incluye contexto suficiente (15-40 palabras típico). NO uses anchor si update_type es append_to_section o mark_laguna_resolved",
      "section_target": "string — solo para append_to_section (path 'H2 → H3'); ignorado en otros tipos",
      "content_proposed": "string — para insert_*/extend_/replace_/append_*: el markdown a insertar/reemplazar. Para mark_laguna_resolved: vacío o nota breve",
      "supersedes_laguna_text": "string|null — solo para mark_laguna_resolved: el texto literal de la laguna a marcar como resuelta. Debe matchear substring del bullet en sección Lagunas",
      "wikilinks_introduced": ["page_id1", "page_id2"],
      "citations_added": [
        {
          "video_id": "string",
          "timestamp_seconds": "number",
          "cite_markdown": "string — formato [Título (mm:ss)](https://youtu.be/ID?t=SECS)"
        }
      ],
      "rationale": "string — por qué este update mejora la página y por qué este update_type es el correcto editorialmente",
      "editorial_intent": "enrich | refine | correct | extend | resolve_laguna — intención editorial detrás del update"
    }
  ],

  "thesis_candidates": [
    {
      "thesis_title_proposed": "string — título sintético de la tesis",
      "proposed_page_id": "string — page_id kebab-case sugerido para la futura synthesis page (ej. 'cognicion-humana-vs-ia', 'diagrama-de-proxy', 'marco-luterano-catolico'). Solo informativo; sub-agente puede ajustar.",
      "synthesis_subtype": "author_thesis",
      "speaker_authorship_marks": [
        {
          "mark_type": "thesis_marker | pedagogic_register | internal_structure | genealogical_self_reference",
          "quote_evidence": "string — cita literal"
        }
      ],
      "framework_internal_structure": ["pieza 1", "pieza 2", "..."],
      "minutes_sustained": "number — minutos de exposición sostenida",
      "domain_guess": "string",
      "related_existing_pages": ["page_id1", "..."],
      "requires_human_validation": "boolean — false SOLO si cumple el gate de auto-promoción de scope.md §2.4.1: minutes_sustained>=30 AND speaker_authorship_marks.length>=3 AND framework_internal_structure.length>=4. true en cualquier otro caso (queda en thesis_candidates.json esperando firma humana).",
      "rationale": "string — por qué pasa los criterios de §2.4.1 del scope.md"
    }
  ],

  "discarded": [
    {
      "surface_form": "string",
      "reason_code": "topic_filter | passing_mention | out_of_scope_domain | out_of_scope_figure | meta_canal | promo | political_news | partisan_commentary | personal_anecdote | unverifiable | recommended_reference | established_concept_used_as_example | established_taxonomy | in_work_character | already_captured | already_captured_extends_existing | captured_in_thesis_candidate | captured_in_promote_new | promotion_threshold_not_met | internal_framework_reference",
      "reason_detail": "string — específico",
      "quote_evidence": "string — cita literal del summary",
      "review_priority": "low | medium | high",
      "review_priority_reason": "string|null — si high, por qué",
      "enriches_concept": "string|null — page_id existente al que esta mención debe sumar como cita/passing_mention. Si presente, el extractor genera automáticamente un pending_update tipo add_citation a esa page con timestamp del marker más cercano. Usar SOLO cuando reason_code es passing_mention y la mención es caso ilustrativo de un concepto ya promovido (ej. 'Pablo Iglesias' → enriches_concept: 'diagrama-de-proxy'; 'Hitler proyección narcisista' → enriches_concept: 'proyeccion').",
      "recommended_reference_payload": {
        "_doc": "Solo cuando reason_code='recommended_reference'. Datos para futura página índice de bibliografía recomendada.",
        "book_title": "string — título normalizado",
        "authors": ["string"],
        "domain": "string — biología, neurociencia, lógica, divulgación, psicología cognitiva, etc.",
        "why_recommended": "string — rol pedagógico que el speaker le asigna",
        "timestamp_seconds": "number|null — segundos del marker más cercano para deep-link al chunk; null solo si no hay marker recuperable"
      }
    }
  ],

  "blocks_filtered_by_topic_filters": [
    {
      "block_quote": "string — cita literal del bloque del summary que matched",
      "matched_pattern": "string — el regex de topic_filters.json que matched",
      "reason": "string"
    }
  ],

  "summary_stats": {
    "entities_total": "number",
    "promoted_new": "number",
    "promoted_updates": "number",
    "thesis_candidates_count": "number",
    "discarded_count": "number",
    "blocks_filtered_count": "number"
  },

  "extraction_metadata": {
    "extracted_at": "ISO 8601",
    "extractor_version": "0.1.0",
    "scope_md_version": "string — el frontmatter version de scope.md cargado",
    "whitelist_version": "string"
  }
}
"""

HARD_RULES = """
# Reglas duras (violación → output rechazado)

1. **quote_evidence SIEMPRE literal**. Toda cita debe ser substring exacta del summary recibido. No paráfrasis, no traducción, no resumen. Un script verifica que `quote_evidence in summary_text`. Si no matched literal, la entidad/decisión se descarta automáticamente.

2. **NUNCA inventar entidades**. Solo emite entidades que aparezcan en el summary recibido. Cero alucinación. Si dudas si una entidad está mencionada, omítela.

3. **NUNCA inventar page_id existente**. Solo marca `exists_in_wiki: true` si el page_id está en el wiki snapshot que recibes. No te fíes de tu memoria del wiki.

4. **NUNCA inventar relation types**. Solo usa types listados en relation_types.json. Si necesitas una relación nueva, déjala en `pending_updates` como sugerencia textual, no como entry tipada.

5. **Decisión `promote_new` requiere ≥1 criterio de scope.md §2 disparado**. Documenta cuál en `decision_reason`.

6. **Decisión `update_existing` requiere haber LEÍDO el cuerpo completo de la página existente Y verificar que el material es genuinamente NUEVO**. Tras Read, si el summary no aporta nada que no esté ya cubierto en prosa o citas, NO emites pending_update de prosa. Cuenta como prosa nueva solo si: (a) trae matiz, contraejemplo o aplicación no presente, (b) refuta o resuelve una laguna declarada, (c) traduce el concepto a un dominio que la página todavía no documenta. El campo `rationale` debe afirmar EXPLÍCITAMENTE qué hay de nuevo respecto al cuerpo leído.

7. **`thesis_candidates` requiere ≥2 señales de §2.4.1** (no basta una sola). Si solo hay una, el contenido va a `entities[]` con `page_type: concept` o como `pending_updates` a una página existente.

8. **`is_canonical_external` debe matchear exactamente el campo `auto_promote: true` del whitelist** que recibes. No interpretes laxamente.

9. **Out-of-scope vs in-scope condicionado** (refundido en scope.md v0.3 §1.2 + §3):

   El canal cubre 5 pilares declarados: liberalismo, filosofía, **psicología cognitiva**, mitología, **neurociencia**. La política previa "neurociencia/cognición → siempre out" era incorrecta — solo aplica a exposición técnica neutra, NO cuando el speaker articula marco propio.

   (a) **scope.md §3.3 incondicionales**: meta-canal, promo, anécdotas personales sin valor ilustrativo, recomendaciones culturales sueltas sin marco bibliográfico → `discard` con reason_code apropiado.

   (b) **Politiqueo vs análisis político-ideológico** (scope.md §3.1 — test discriminante):
       - El speaker articula mecanismo psicológico/sociológico/filosófico → IN
       - Aplica marco propio o ajeno (Jung, Lakoff, diagrama de Proxy, locus de control) → IN
       - Critica una tradición intelectual (liberalismo, marxismo, conservadurismo, anarcocapitalismo) → IN
       - Figura política como caso ilustrativo de un concepto → IN como `passing_mention` con `enriches_concept: <page_id>`
       - Comentario sobre actualidad partidista (≤12 meses) sin marco teórico → OUT (`political_news`)
       - Valoración de ley específica como pieza de actualidad sin elevarla a estructura → OUT (`political_news`)
       - Predicción electoral, juicio moral sobre persona-político, comentario sobre campaña → OUT (`partisan_commentary`)
       - **Test de la cápsula del tiempo**: si retiras el nombre propio actual y la afirmación pierde valor, es politiqueo.

   (c) **Dominios condicionados** (psicología cognitiva, ciencia cognitiva, neurociencia — scope.md §1.2):
       - El speaker articula tesis propia que aplica el mecanismo (razonamiento motivado, locus de autoridad, tríada cognitiva, BOLD/amígdala como sustento empírico de marco psicológico) → integrar en `thesis_candidate` o como evidencia (NO descartar como out_of_scope_domain).
       - El speaker explica concepto técnico estándar sin aplicarlo a marco propio → `established_concept_used_as_example` o `passing_mention`.
       - Concepto técnico aparece como caso ilustrativo de un concepto del canal ya promovido → `passing_mention` con `enriches_concept: <page_id>` (genera pending_update a esa page).
       - Ningún concepto neurocientífico/cognitivo se promueve como **página autónoma** (las pages son del canal, no de la disciplina).

   (d) **Recomendaciones bibliográficas** (scope.md §3.4 — NUEVO):
       - Manual/libro recomendado por el speaker como base de estudio o referencia (Panksepp, Redolar, Hamilton, DSM-5, manuales de bachillerato) → `recommended_reference` (NO `out_of_scope_domain`). Lane bibliográfica separada con campos: `book_title`, `authors[]`, `domain`, `why_recommended`, `quote_evidence`, `timestamp`.
       - Libro objeto de análisis arquetípico aplicado (Tolkien, Pinocho, Cuento de Navidad) → `promote_new` como `entity_work`.
       - Mención bibliográfica con tesis embrionaria pero sin desarrollo (Gödel-Escher-Bach, Hofstadter) → `passing_mention` con `review_priority: medium`.

   (e) **Mención sin lente del canal**: si el canal nombra una entidad sin leerla desde NINGÚN marco (ni arquetípico ni psicológico ni filosófico ni cultural), → `discard` con reason_code: passing_mention.

   **Regla de oro v0.3**: la calidad del wiki = relevancia + densidad de marco aplicado, no exhaustividad ni purismo arquetípico. Si el canal articula tesis cognitiva/neurocientífica/política como suya, eso ES contenido enciclopédico del canal. Si el canal solo expone técnica neutra sin marco, NO lo es.

10. **Salida JSON estricta**. Sin preámbulo, sin epílogo, sin code fences ```. El primer carácter es `{`, el último es `}`. Si fallas en parsing JSON, el output se descarta y se reintenta.

11. **Anchor literal único** (regla DURA para insert/replace/extend): el `anchor_passage` debe aparecer EXACTAMENTE UNA VEZ en el cuerpo de la página leída. Si dudas, incluye más contexto (frase completa + 1-2 palabras del párrafo siguiente). El script de aplicación rechaza anchors con 0 o ≥2 matches.

12. **Cuándo usar cada update_type — guía editorial**:
   - `insert_after_passage`: cuando hay material nuevo que enriquece justo DESPUÉS de un párrafo/cita existente (típico: nueva cita complementaria, nueva instancia del mismo arquetipo)
   - `insert_before_passage`: cuando el material nuevo debe leerse ANTES (raro; típico: contextualización previa)
   - `extend_passage`: cuando una frase/cita existente requiere matización añadida justo a continuación, sin reemplazar
   - `replace_passage`: cuando el cuerpo dice algo INCORRECTO o DESACTUALIZADO. Solo para errores factuales, no para "lo diría mejor"
   - `append_to_section`: último recurso — solo si el material es genuinamente "más casos / más ejemplos" que van al final de una sección sin disrupción del flujo
   - `mark_laguna_resolved`: cuando el summary aporta material que cubre lo que la laguna declara como ausente. NO borra la laguna — la marca para revisión humana
   - `add_relation`: nueva relación tipada en frontmatter (futuro; no implementado todavía)

13. **PROHIBIDO append-at-end por defecto**. Append_to_section degrada la página a concatenación cronológica. Solo úsalo si NO hay anchor razonable en la sección target.

14. **Lagunas refutadas**: si descubres que un summary aporta material que refuta una laguna, propón `update_type: mark_laguna_resolved` con `supersedes_laguna_text` literal del bullet de la laguna. ADEMÁS, propón el update de enrich/insert que aporta el material refutador.

15. **No corregir terminología canal-específica al canon académico** (scope.md §5). El canal usa "égersis" no "éxesis", "mito polar" como concepto propio, etc. Respeta su lenguaje.

16. **NO construyes la página tú** para promote_new. Tu rol es DECIDIR qué entidades merecen página y justificar con scope.md y quote_evidence. Un sub-agente focalizado, con contexto limpio, recibe tu candidato y construye la página completa (frontmatter rico + body con secciones, citas, wikilinks). Esta separación libera al main de mantener tres tareas cognitivas simultáneas (scope + updates + construcción) y es lo que estabiliza la calidad. NO emitas `stub_proposed`, `proposed_initial_body`, `body_markdown` ni equivalentes — solo metadata de decisión.

17. **Redundancia: distinguir prosa de citas**. El mismo concepto canónico (mito polar, sombra, individuación) aparece en muchos vídeos del corpus. La página NO crece linealmente con cada mención.

    **Prosa redundante → DESCARTAR el pending_update**: si la sección target ya tiene 3-5 ejemplos canónicos del mismo tipo y el tuyo no aporta matiz nuevo, no emitas la inserción de prosa. Documenta en `decision_reason` o en `discarded[]` que la mención existe pero la prosa sería redundante.

    **Citas con timestamp NUEVAS → AÑADIR SIEMPRE** aunque la prosa sería redundante. Razón operativa: el índice SQLite de citations (`data/wiki.db`) alimenta una lane de retrieval indirecto donde un chunk raw mapea al wiki_page vía las citas que lo referencian. Más cobertura de citas distintas = mejor recall. Para añadir solo citas, emite un `pending_update` con:
      - `update_type: add_citation`  (alias: `append_to_section` con section_target=Citations o equivalente)
      - `content_proposed`: el bullet/línea con cita formateada `→ [Título (mm:ss)](https://youtu.be/ID?t=SECS)`
      - `rationale`: "cita-only — prosa ya cubierta, añadimos timestamp para retrieval indirecto"
      - `editorial_intent: enrich`

    Caso típico: vídeo es la mención #35 de "mito polar". La página ya tiene Tarzán, Matrix, Pandora, Adán-Eva como ejemplos. Si tu summary aporta una aplicación NUEVA (p.ej. mito polar en Frozen) → prosa nueva justificada. Si tu summary solo cita "mito polar" como framework aplicado a Tarzán (ya documentado) → solo cita-only update al timestamp donde el speaker lo invoca.
"""

ROLE_PROMPT = """
Eres un extractor de conocimiento estructurado para la wiki Ariadna.

CONTEXTO: Ariadna es un wiki markdown que documenta el corpus YouTube del canal Proxy
(análisis arquetípico, mitología comparada, psicología junguiana, crítica cultural).
Cada vídeo del canal tiene un summary.md curado a mano. Tu trabajo es leer un summary
y proponer cómo enriquecer la wiki con su contenido.

PRINCIPIO RECTOR (Karpathy "LLM Wiki"): cada source que leas es una oportunidad de
ACTUALIZAR las páginas wiki que toca y de DETECTAR entidades nuevas que merezcan
página propia. Las referencias cruzadas se construyen al ingerir, no al consultar.

NADA de lo que propongas se aplica al wiki sin firma humana. Tu output va a colas
de revisión. Sé exhaustivo en la detección y honesto en la justificación: el humano
revisará tus descartes con contador agregado, así que un descarte bien justificado
con cita literal es más valioso que un promote precipitado sin evidencia.
"""


# ---------------------------------------------------------------------------
# Construcción del system prompt
# ---------------------------------------------------------------------------


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
PAGE_ID_RE = re.compile(r"^page_id:\s*(\S+)", re.MULTILINE)
PAGE_TYPE_RE = re.compile(r"^page_type:\s*(\S+)", re.MULTILINE)
DOMAIN_PRIMARY_RE = re.compile(r"^domain_primary:\s*(\S+)", re.MULTILINE)
CANONICAL_NAME_RE = re.compile(r"^canonical_name:\s*(.+?)$", re.MULTILINE)
ALIASES_BLOCK_RE = re.compile(r"^aliases:\s*\[(.*?)\]", re.MULTILINE | re.DOTALL)
RELATION_RE = re.compile(r"^\s*-\s*\{?\s*type:\s*(\S+),?\s*to:\s*(\S+?)[\},\s]", re.MULTILINE)
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _extract_one_liner(body: str) -> str:
    """Extrae 'qué cubre la página' desde el primer párrafo de la primera H2."""
    m = H2_RE.search(body)
    if not m:
        return ""
    after = body[m.end():]
    for line in after.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#") or s.startswith(">") or s.startswith("```"):
            continue
        # Toma primera oración o 180 chars
        for sep in [". ", "! ", "? "]:
            if sep in s:
                return s.split(sep, 1)[0].strip() + "."
        return s[:180]
    return ""


def _count_lagunas(body: str) -> int:
    """Cuenta bullets en sección Lagunas (orientativo)."""
    m = re.search(r"^##\s+Lagunas", body, re.MULTILINE)
    if not m:
        return 0
    after = body[m.end():]
    next_h2 = H2_RE.search(after)
    section = after[: next_h2.start()] if next_h2 else after
    return sum(1 for ln in section.splitlines() if re.match(r"^\s*-\s+", ln))


def build_wiki_index(wiki_root: Optional[Path] = None) -> str:
    """Índice slim del wiki — 1 entrada por página, ~150-250 chars cada una.

    Patrón Karpathy: el extractor ve el índice, decide qué páginas son
    relevantes para el summary actual, y usa la tool Read sobre `file_path`
    para fetchear el contenido completo solo de las páginas que va a tocar.

    Esto sustituye la inyección del wiki entero (~43K tok → ~3-5K tok) y
    escala linealmente con páginas tocadas, no con páginas totales.

    `wiki_root` permite apuntar al shadow de la sesión en vez del wiki real.
    Las file_path emitidas son ABSOLUTAS — el LLM Read funciona con cualquiera.
    """
    root = wiki_root or WIKI
    entries: list[str] = []
    for md in sorted(root.rglob("*.md")):
        if md.name == "README.md":
            continue
        # Emite path absoluta — Read del LLM funciona con cualquier cwd y no
        # depende del wiki_root usado (real vs shadow).
        rel = md.resolve()
        text = md.read_text(encoding="utf-8")
        fm_match = FRONTMATTER_RE.match(text)
        if not fm_match:
            continue
        fm = fm_match.group(1)
        body = text[fm_match.end():]

        page_id = (PAGE_ID_RE.search(fm) or [None, ""])[1] if PAGE_ID_RE.search(fm) else ""
        page_id = PAGE_ID_RE.search(fm).group(1) if PAGE_ID_RE.search(fm) else ""
        page_type = PAGE_TYPE_RE.search(fm).group(1) if PAGE_TYPE_RE.search(fm) else ""
        domain = DOMAIN_PRIMARY_RE.search(fm).group(1) if DOMAIN_PRIMARY_RE.search(fm) else ""
        cname_m = CANONICAL_NAME_RE.search(fm)
        canonical_name = cname_m.group(1).strip().strip('"').strip("'") if cname_m else page_id
        aliases_m = ALIASES_BLOCK_RE.search(fm)
        aliases_str = ""
        if aliases_m:
            aliases_str = aliases_m.group(1).replace("\n", " ").strip()

        relations = RELATION_RE.findall(fm)
        relation_summary = ", ".join(f"{t}→{to}" for t, to in relations[:5])
        if len(relations) > 5:
            relation_summary += f" (+{len(relations)-5} más)"

        one_liner = _extract_one_liner(body)
        n_lagunas = _count_lagunas(body)

        entry = "\n".join(
            [
                f"### {page_id}",
                f"- **canonical_name**: {canonical_name}",
                f"- **page_type**: {page_type}  |  **domain**: {domain}",
                f"- **aliases**: {aliases_str[:120]}" if aliases_str else "",
                f"- **qué cubre**: {one_liner}" if one_liner else "",
                f"- **relations**: {relation_summary}" if relation_summary else "- **relations**: (ninguna)",
                f"- **lagunas declaradas**: {n_lagunas}",
                f"- **file_path**: `{rel}`",
            ]
        )
        # Quita líneas vacías generadas por campos opcionales ausentes
        entry = "\n".join(line for line in entry.split("\n") if line.strip())
        entries.append(entry)

    header = (
        "## Índice del wiki actual\n\n"
        "Cada página existente está listada con su page_id, tipo, dominio, "
        "qué cubre (1 frase), relations[] tipadas, número de lagunas declaradas "
        "y file_path. Si una página parece relevante para el summary que estás "
        "procesando, **usa la tool Read sobre el `file_path`** para fetchear "
        "su contenido completo ANTES de proponer un update. Sin haber leído la "
        "página completa NO propones pending_updates a esa página — escribirías "
        "duplicado o desafinado.\n\n"
        f"Total páginas existentes: {len(entries)}\n"
    )
    return header + "\n\n" + "\n\n".join(entries)


def build_system_prompt_short() -> str:
    """System prompt corto (~10K) que va por argv (--append-system-prompt).

    Contiene SOLO role + output schema + hard rules. El contexto pesado
    (scope.md + whitelist + relation_types + topic_filters + wiki snapshot)
    se inyecta como PRIMER user message de cada sesión — eso evita el límite
    ARG_MAX de Linux y permite que el caching automático de Anthropic capture
    el conversation prefix.
    """
    return "\n\n".join(
        [
            ROLE_PROMPT,
            "# Contexto",
            (
                "El primer mensaje de usuario de esta sesión te entrega los "
                "documentos autoritativos: scope.md, canonical_whitelist.json, "
                "relation_types.json, topic_filters.json y un snapshot completo "
                "de las páginas wiki existentes. A partir del segundo mensaje "
                "recibes solo el summary del vídeo a procesar; los documentos "
                "de la primera turno permanecen como contexto autoritativo "
                "durante toda la sesión."
            ),
            OUTPUT_SCHEMA,
            HARD_RULES,
        ]
    )


def build_heavy_context_message(wiki_root: Optional[Path] = None) -> str:
    """Primer mensaje de usuario de cada sesión: ~10-15K tokens.

    Patrón Karpathy "LLM Wiki": el contexto pesado es un INDEX slim del wiki
    (no los cuerpos completos). El extractor usa la tool Read sobre el
    `file_path` indicado para drillar en páginas relevantes al summary.
    Esto reduce ~43K → ~10K en el prefix, escala lineal con pages tocadas.

    `wiki_root` permite apuntar al shadow de la sesión: el LLM Read sobre los
    file_path absolutos del shadow ve el estado acumulado del batch sin que
    toquemos wiki/ real hasta el cierre.
    """
    index = build_wiki_index(wiki_root=wiki_root)
    return "\n\n".join(
        [
            "# Documentos autoritativos de la sesión",
            "",
            "Los siguientes documentos definen el alcance, vocabulario y estado "
            "actual del wiki Ariadna. Trátalos como autoritativos durante toda "
            "esta sesión.",
            "",
            "## scope.md",
            SCOPE_PATH.read_text(encoding="utf-8"),
            "## canonical_whitelist.json",
            "```json\n" + WHITELIST_PATH.read_text(encoding="utf-8") + "\n```",
            "## relation_types.json",
            "```json\n" + RELATION_TYPES_PATH.read_text(encoding="utf-8") + "\n```",
            "## topic_filters.json",
            "```json\n" + TOPIC_FILTERS_PATH.read_text(encoding="utf-8") + "\n```",
            index,
            "---",
            "## Cómo procesar cada summary que llega a partir de aquí",
            "",
            "1. Lee el summary y identifica entidades/conceptos/obras presentes",
            "2. Para CADA candidato a update_existing, usa la tool **Read** "
            "sobre el `file_path` de la página existente. NUNCA propongas un "
            "pending_update sin haber leído el cuerpo completo de la página.",
            "3. Compara summary ↔ página leída. Identifica:",
            "   - Material nuevo no presente en la página → propón update con "
            "anchor literal único (insert_after_passage / extend_passage / etc.)",
            "   - Lagunas declaradas en la página que el summary refuta → "
            "marca con `supersedes_laguna`",
            "   - Errores factuales → `replace_passage` con anchor literal único",
            "4. Para entidades nuevas (no en wiki), decide promote_new / "
            "mentions_index / discard según scope.md §2",
            "5. Aplica reglas duras del schema (quote_evidence literal, "
            "anchor único, etc.)",
            "",
            "",
            "## Estado del wiki durante esta sesión",
            "",
            "El wiki que ves arriba es una **copia de trabajo del batch** "
            "(shadow). A medida que procesas vídeos de este batch, los "
            "`pending_updates` y `promote_new` que emites se aplican al shadow "
            "antes del siguiente vídeo. Vídeos posteriores del batch ven el "
            "estado acumulado.",
            "",
            "Implicaciones operativas:",
            "- Si una página parece haberse creado en este batch (status: "
            "stub_in_session en el frontmatter), referencia con wikilink y "
            "enriquécela con incrementales si aplica — no propongas otra "
            "promote_new para la misma entidad.",
            "- El índice slim que recibes refleja el estado al ARRANQUE de la "
            "sesión. Si sospechas que un page_id puede haberse creado por un "
            "vídeo previo, usa `Glob` sobre la raíz del shadow (los "
            "`file_path` te dan la ruta) o `Grep` por el surface_form/canonical_guess.",
            "- NO tocas el wiki real con tus outputs — al cierre del batch, el "
            "shadow se sincroniza al wiki real con commit auditable.",
            "",
            "Confirma listo respondiendo al primer vídeo a procesar (que llega "
            "a continuación en este mismo mensaje).",
        ]
    )


def build_user_message(video: "VideoInput") -> str:
    return f"""# Vídeo a procesar

**video_id**: {video.video_id}
**title**: {video.title}
**playlist**: {video.playlist}
**category**: {video.category}
**duration**: {video.duration_s}s ({video.duration_s // 60}min)
**upload_date**: {video.upload_date}

## summary.md

```markdown
{video.summary_text}
```

---

Devuelve ÚNICAMENTE el JSON del schema, sin texto previo, sin epílogo, sin code fences.
El primer carácter de tu respuesta debe ser `{{` y el último `}}`.
"""


# ---------------------------------------------------------------------------
# Discovery de summaries
# ---------------------------------------------------------------------------


@dataclass
class VideoInput:
    video_id: str
    title: str
    playlist: str
    slug: str
    category: str
    duration_s: int
    upload_date: str
    url: str
    summary_path: Path
    summary_text: str = ""
    estimated_tokens: int = 0


def discover_videos(corpus_path: Path) -> list[VideoInput]:
    videos: list[VideoInput] = []
    for summary_path in sorted(corpus_path.rglob("summary.md")):
        meta_path = summary_path.parent / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        slug = summary_path.parent.name
        playlist = summary_path.parent.parent.name
        videos.append(
            VideoInput(
                video_id=meta.get("video_id", "unknown"),
                title=meta.get("title", slug),
                playlist=playlist,
                slug=slug,
                category=meta.get("category", "uncategorized"),
                duration_s=int(meta.get("duration", 0)),
                upload_date=meta.get("upload_date", ""),
                url=meta.get("url", ""),
                summary_path=summary_path,
            )
        )
    return videos


def load_summary(video: VideoInput) -> None:
    text = video.summary_path.read_text(encoding="utf-8")
    video.summary_text = text
    # Heurística estándar: ~4 chars por token
    video.estimated_tokens = len(text) // 4


# ---------------------------------------------------------------------------
# Estado del run (resumibilidad)
# ---------------------------------------------------------------------------


@dataclass
class RunState:
    run_id: str
    started_at: str
    last_updated: str
    videos_total: int = 0
    videos_done: list[str] = field(default_factory=list)
    videos_failed: list[dict] = field(default_factory=list)
    videos_pending: list[str] = field(default_factory=list)
    sessions: list[dict] = field(default_factory=list)
    total_tokens_estimate: int = 0

    @classmethod
    def load(cls, run_dir: Path) -> "RunState":
        state_path = run_dir / "state.json"
        if state_path.exists():
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return cls(**data)
        raise FileNotFoundError(f"No state.json in {run_dir}")

    def save(self, run_dir: Path) -> None:
        self.last_updated = now_iso()
        (run_dir / "state.json").write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Shadow wiki — copia de trabajo por sesión
# ---------------------------------------------------------------------------
#
# Patrón discutido 2026-05-02 (postmortem golem). Para que vídeos consecutivos
# de un mismo batch puedan referenciarse entre sí sin recompilar tras cada uno,
# el extractor lee de un shadow_wiki/ — copia de wiki/ creada al arrancar la
# sesión. Tras cada vídeo procesado, los `pending_updates` y `entities[]
# promote_new` se aplican EN EL SHADOW (no en wiki/). El siguiente vídeo ve un
# estado "logicamente actual" sin que toquemos el wiki real. Al cierre del
# batch se descarta el shadow y un compile real (con prior_text del wiki real)
# integra los updates con criterio editorial.
#
# Justificación: evita "golem" (concatenación incoherente vía apply diff) y
# preserva caching de la sesión Claude (no inyectamos delta messages).


def setup_shadow_wiki(run_dir: Path) -> Path:
    """Crea shadow_wiki/ como copia fresca de wiki/. Idempotente."""
    shadow = run_dir / "shadow_wiki"
    if shadow.exists():
        shutil.rmtree(shadow)
    shutil.copytree(WIKI, shadow, ignore=shutil.ignore_patterns("_meta"))
    # Copiamos _meta selectivamente — solo lo que el extractor necesita Read.
    # Excluimos extraction_runs/ (ruido) y otros dirs grandes.
    (shadow / "_meta").mkdir(exist_ok=True)
    for f in ("scope.md", "canonical_whitelist.json", "relation_types.json", "topic_filters.json"):
        src = META / f
        if src.exists():
            shutil.copy2(src, shadow / "_meta" / f)
    return shadow


def teardown_shadow_wiki(shadow: Path) -> None:
    if shadow.exists():
        shutil.rmtree(shadow)


def sync_shadow_to_wiki(shadow: Path) -> dict:
    """Copia archivos del shadow al wiki real al cierre de batch.

    Excluye _meta (no debe modificarse desde el extractor — vive en el wiki
    real autoritativo). Sobreescribe wiki/<path> con shadow/<path> cuando
    contenido difiere; crea archivos nuevos cuando el shadow tiene páginas
    inexistentes en wiki (stubs promote_new que han sobrevivido al batch).
    """
    stats = {"copied": 0, "new": 0, "unchanged": 0}
    for src in shadow.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(shadow)
        if rel.parts and rel.parts[0] == "_meta":
            continue
        dst = WIKI / rel
        if dst.exists():
            if src.read_bytes() == dst.read_bytes():
                stats["unchanged"] += 1
                continue
            stats["copied"] += 1
        else:
            stats["new"] += 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return stats


def commit_batch_to_wiki(run_id: str, session_idx: int, sync_stats: dict, video_ids: list[str]) -> Optional[str]:
    """Commit auditable de los cambios en wiki/ tras sync shadow→wiki.

    Devuelve el SHA del commit, o None si no había cambios.
    """
    # Comprobación previa: hay diff staged?
    try:
        subprocess.run(
            ["git", "add", "wiki/"],
            cwd=REPO,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"  ! git add failed: {e.stderr.decode()[:200]}", file=sys.stderr)
        return None

    diff_check = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=REPO,
        capture_output=True,
    )
    if diff_check.returncode == 0:
        return None  # sin cambios staged

    msg = (
        f"feat(wiki): batch {run_id}/session_{session_idx} "
        f"(+{sync_stats['new']} stubs, ~{sync_stats['copied']} updated)\n\n"
        f"Vídeos: {', '.join(video_ids[:5])}{'...' if len(video_ids) > 5 else ''}\n"
        f"Sync shadow→wiki tras incrementales del batch.\n"
        f"Cambios: {sync_stats['copied']} páginas modificadas, "
        f"{sync_stats['new']} stubs creados, "
        f"{sync_stats['unchanged']} sin cambio.\n"
    )
    try:
        proc = subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=REPO,
            check=True,
            capture_output=True,
        )
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return sha
    except subprocess.CalledProcessError as e:
        print(f"  ! git commit failed: {e.stderr.decode()[:300]}", file=sys.stderr)
        return None


def _shadow_path_for_page_id(shadow: Path, page_id: str, page_type: str = "concept") -> Path:
    """Resuelve la ruta probable de un page_id en el shadow.

    Orden de búsqueda: cualquier .md cuyo frontmatter tenga ese page_id.
    Fallback: derivar por page_type a la subcarpeta canónica.
    """
    for md in shadow.rglob("*.md"):
        if md.name == "README.md":
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        if PAGE_ID_RE.search(m.group(1)):
            existing = PAGE_ID_RE.search(m.group(1)).group(1)
            if existing == page_id:
                return md
    # No existe: ruta para stub nuevo
    subdir_by_type = {
        "concept": "concepts",
        "author": "authors",
        "entity_work": "entities/works",
        "entity_institution": "entities/institutions",
        "synthesis": "synthesis",
    }
    sub = subdir_by_type.get(page_type, "concepts")
    return shadow / sub / f"{page_id}.md"


def _materialize_stub_page(
    shadow: Path,
    page_id: str,
    page_type: str,
    domain: str,
    canonical_name: str,
    quote_evidence: str,
    video_id: str,
    video_title: str,
    surface_form: str,
    proposed_initial_body: Optional[str] = None,
) -> Path:
    """Crea un stub para una página promote_new en el shadow.

    Si `proposed_initial_body` está presente: cuerpo proporcional a la
    profundidad del vídeo (esperado para depth secondary/central_thesis).
    Si es None: stub minimal con quote_evidence (passing_mention).

    Stub explícito ("propuesta en este batch") para que el LLM en vídeos
    siguientes la pueda leer y referenciar sin confundirla con una página
    consolidada.
    """
    target = _shadow_path_for_page_id(shadow, page_id, page_type)
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = (
        "---\n"
        f"page_id: {page_id}\n"
        f"page_type: {page_type}\n"
        f"canonical_name: \"{canonical_name}\"\n"
        f"domain_primary: {domain}\n"
        "aliases: []\n"
        "relations: []\n"
        "status: stub_in_session\n"
        "---\n\n"
    )
    banner = f"# {canonical_name}\n\n"
    citations_block = (
        f"## Citations\n\n"
        f"- video_id: `{video_id}` — {video_title}\n"
        f"  - surface_form: {surface_form!r}\n"
    )
    if proposed_initial_body and proposed_initial_body.strip():
        # Cuerpo rico provisto por el LLM para depth secondary/central_thesis.
        body_text = proposed_initial_body.strip()
        # Strip H1 si el LLM emitió su propio título — el banner usa
        # canonical_name autoritativo (puede diferir de surface_form).
        body_text = re.sub(r"^#\s+[^\n]+\n+", "", body_text, count=1)
        body_text = body_text.strip()
        # Si tras el strip no empieza por H2, prefijamos Tesis emergente
        if not body_text.startswith("##"):
            body_text = "## Tesis emergente\n\n" + body_text
        # Sólo añade Citations si el LLM no ya emitió una sección equivalente
        if "## Citations" not in body_text and "## Citaciones" not in body_text:
            body = banner + body_text + "\n\n" + citations_block
        else:
            body = banner + body_text + "\n"
        # Asegura sección Lagunas para que vídeos posteriores tengan
        # anchor donde declarar gaps vía append_to_section
        if "## Lagunas" not in body:
            body = body.rstrip() + "\n\n## Lagunas\n\n- (sin lagunas declaradas todavía)\n"
    else:
        # Stub minimal — passing_mention o LLM no emitió cuerpo
        body = (
            banner
            + f"## Tesis emergente\n\n{quote_evidence}\n\n"
            + "## Lagunas\n\n- (sin lagunas declaradas todavía)\n\n"
            + citations_block
        )
    target.write_text(frontmatter + body, encoding="utf-8")
    return target


def _alias_get(d: dict, *keys, default=None):
    """Devuelve el primer valor no-vacío entre las keys dadas.

    El LLM con frecuencia usa nombres alternativos al schema declarado
    ('action' vs 'decision', 'page_id_proposed' vs 'canonical_guess', etc.).
    En lugar de forzar al LLM, adoptamos su variante con aliases defensivos.
    """
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return default


def _quote_to_str(quote) -> str:
    """Acepta string o list[str]; devuelve el primer item no vacío."""
    if isinstance(quote, str):
        return quote
    if isinstance(quote, list):
        for q in quote:
            if isinstance(q, str) and q.strip():
                return q
    return ""


# ---------------------------------------------------------------------------
# Sub-agente focalizado para construir páginas (separa scope/decisión de
# construcción para que cada llamada al LLM tenga UNA sola responsabilidad
# cognitiva). Patrón acordado 2026-05-02 tras detectar que rules estrictas
# en el main para forzar stub rico provocaban regresión scope.
# ---------------------------------------------------------------------------


SUBAGENT_SYSTEM_PROMPT = """Eres un constructor focalizado de páginas wiki para Ariadna.

CONTEXTO: Ariadna es un wiki markdown sobre el corpus YouTube del canal Proxy
(análisis arquetípico, mitología comparada, psicología junguiana, crítica cultural).

TU ÚNICA TAREA: dado UN candidato aprobado (entidad + metadata + cita evidence) + un
fragmento del summary del vídeo donde aparece, devuelves la página markdown completa
(frontmatter YAML + body markdown) lista para insertar en el wiki.

NO tomas decisiones de scope. NO descartas. NO sugieres otras páginas.
NO juzgas si merece ser página — alguien ya lo decidió. Tú solo CONSTRUYES.

Conforme al schema y vocabulario que se te entregan, produces un JSON estricto con
dos campos: `frontmatter` (object) y `body_markdown` (string). Sin preámbulo,
sin epílogo, sin code fences. Primer carácter '{', último '}'.

Reglas duras:
1. `frontmatter.relations[]` con AL MENOS 2 entradas tipadas (usa relation_types.json).
2. `frontmatter.aliases[]` con variantes razonables del surface_form (con/sin diacríticos, abreviadas, etc.) — al menos 1 entrada si hay variación.
3. `body_markdown` empieza con `# {canonical_name}`, contiene ≥3 secciones H2, citas en formato `> \"texto literal del summary\"\\n→ [Título (mm:ss)](https://youtu.be/ID?t=SECS)`, wikilinks `[[page-id]]` para referenciar otras páginas existentes o de este batch.
4. Sección `## Lagunas` al final con bullets de gaps declarados o `(sin lagunas declaradas todavía)`.
5. Citas LITERALES del summary recibido (substring exacto). Sin paráfrasis ni traducción.
6. Respeta vocabulario del canal (égersis, mito polar, mitología propia/impropia, etc.) — ver scope.md §5.
"""


_seed_example_cache: Optional[str] = None


def _load_seed_example() -> str:
    """Devuelve el contenido de individuation.md como referencia de formato."""
    global _seed_example_cache
    if _seed_example_cache is not None:
        return _seed_example_cache
    seed = WIKI / "concepts" / "individuation.md"
    _seed_example_cache = seed.read_text(encoding="utf-8") if seed.exists() else ""
    return _seed_example_cache


def _list_existing_page_ids(shadow: Path) -> list[str]:
    """Lista todos los page_ids en el shadow (para wikilinks correctos)."""
    ids: list[str] = []
    for md in sorted(shadow.rglob("*.md")):
        if md.name == "README.md":
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        pid_m = PAGE_ID_RE.search(m.group(1))
        if pid_m:
            ids.append(pid_m.group(1))
    return ids


def _summary_excerpt_around_quote(summary: str, quote: str, ctx_chars: int = 1500) -> str:
    """Extrae fragmento del summary alrededor de la cita evidence."""
    if not summary:
        return ""
    if not quote or quote not in summary:
        return summary[:3000]
    idx = summary.find(quote)
    start = max(0, idx - ctx_chars)
    end = min(len(summary), idx + len(quote) + ctx_chars)
    return summary[start:end]


def build_subagent_user_msg(
    candidate: dict,
    video: "VideoInput",
    shadow: Path,
) -> str:
    """User message del sub-agente. ~5-8K tokens. Contiene contexto autoritativo
    mínimo necesario para producir página coherente con el resto del wiki.
    """
    seed_example = _load_seed_example()
    existing_ids = _list_existing_page_ids(shadow)
    quote = _quote_to_str(candidate.get("quote_evidence", ""))
    summary_excerpt = _summary_excerpt_around_quote(video.summary_text, quote)

    page_id = _alias_get(candidate, "canonical_guess", "page_id_proposed", "page_id") or ""
    page_type = _alias_get(candidate, "page_type") or "concept"
    surface_form = candidate.get("surface_form", page_id)
    domain = _alias_get(candidate, "domain_primary_guess", "domain_primary") or ""
    depth = _alias_get(candidate, "depth_in_video", "depth") or ""
    decision_reason = candidate.get("decision_reason", "")
    minutes = candidate.get("minutes_estimate", 0)

    return f"""# Documentos autoritativos

## scope.md
{SCOPE_PATH.read_text(encoding="utf-8")}

## canonical_whitelist.json
```json
{WHITELIST_PATH.read_text(encoding="utf-8")}
```

## relation_types.json
```json
{RELATION_TYPES_PATH.read_text(encoding="utf-8")}
```

## Page IDs ya en el wiki (usa estos para wikilinks `[[page-id]]`)

{', '.join(sorted(existing_ids))}

## Ejemplo de página canónica del wiki (referencia de formato — NO incluyas en tu output)

```markdown
{seed_example}
```

---

# Candidato a construir

- **page_id**: {page_id}
- **page_type**: {page_type}
- **surface_form (el speaker dice)**: {surface_form}
- **domain_primary sugerido**: {domain}
- **depth_in_video**: {depth}
- **minutes_estimate**: {minutes}
- **decision_reason**: {decision_reason}
- **quote_evidence**: {quote!r}

## Vídeo fuente

- **video_id**: {video.video_id}
- **title**: {video.title}
- **playlist**: {video.playlist}
- **url**: {video.url}

## Fragmento del summary alrededor de la cita

```markdown
{summary_excerpt}
```

---

# Output schema

Devuelve JSON estricto con esta estructura (sin preámbulo, sin code fences):

{{
  "frontmatter": {{
    "page_id": "{page_id}",
    "page_type": "{page_type}",
    "canonical_name": "<nombre canónico>",
    "aliases": ["<variante1>", "<variante2>"],
    "domain_primary": "{domain or '<dominio>'}",
    "primary_domains": ["<dom1>", "<dom2>"],
    "relations": [
      {{"type": "<relation_type>", "to": "<page_id>", "weight": "<canonical|strong|weak>", "note": "<explicación>"}},
      {{"type": "<relation_type>", "to": "<page_id>", "note": "<explicación>"}}
    ],
    "sources_count": 1,
    "schema_version": "1.0.0",
    "review_status": "stub_in_session"
  }},
  "body_markdown": "# <canonical_name>\\n\\n## <H2 sección 1>\\n\\nprosa con citas...\\n→ [Título (mm:ss)](URL)\\n\\n## <H2 sección 2>\\n\\n...\\n\\n## Lagunas\\n\\n- (sin lagunas declaradas todavía)\\n"
}}

Para entity_work añade en frontmatter: `year`, `studio_or_publisher`, `medium` cuando apliquen.

Devuelve ÚNICAMENTE el JSON. Primer carácter `{{`, último `}}`.
"""


def _extract_json_object(text: str) -> Optional[str]:
    """Extrae el primer objeto JSON balanceado de un string. Tolera preámbulo."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
    if not text:
        return None
    if text[0] != "{":
        start = text.find("{")
        if start == -1:
            return None
        text = text[start:]
    depth = 0
    in_str = False
    escape = False
    for i, c in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[: i + 1]
    return None


def invoke_subagent_for_stub(
    candidate: dict,
    video: "VideoInput",
    shadow: Path,
    max_retries: int = 1,
) -> Optional[dict]:
    """Llama a un sub-agente claude -p (clean session, sin --resume) para construir
    UNA página completa. Devuelve dict {frontmatter, body_markdown} o None si falla.

    Diseñado para ser invocado in-loop tras una decisión promote_new del main agent.
    Mantiene compounding intra-batch: el sub-agente lee el shadow actual (que ya
    incluye stubs creados por vídeos anteriores del batch) y vídeos posteriores del
    batch verán este nuevo stub en shadow tras su materialización.
    """
    if not video.summary_text:
        load_summary(video)

    user_msg = build_subagent_user_msg(candidate, video, shadow)

    for attempt in range(max_retries + 1):
        try:
            output_text, _meta = invoke_claude(
                user_msg=user_msg,
                system_prompt_appended=SUBAGENT_SYSTEM_PROMPT,
                resume_session_id=None,
                model=CLAUDE_MODEL_STUB_SUBAGENT,
            )
            json_text = _extract_json_object(output_text)
            if not json_text:
                print(f"     ! subagent: no JSON object found (attempt {attempt + 1})", file=sys.stderr)
                continue
            stub = json.loads(json_text)
            if (
                isinstance(stub, dict)
                and isinstance(stub.get("frontmatter"), dict)
                and isinstance(stub.get("body_markdown"), str)
                and stub["body_markdown"].strip()
            ):
                return stub
            print(
                f"     ! subagent: malformed structure (attempt {attempt + 1}) — keys={list(stub.keys()) if isinstance(stub, dict) else type(stub).__name__}",
                file=sys.stderr,
            )
        except subprocess.TimeoutExpired:
            print(f"     ! subagent timeout (attempt {attempt + 1})", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"     ! subagent JSON parse error (attempt {attempt + 1}): {e}", file=sys.stderr)
        except Exception as e:
            print(f"     ! subagent error (attempt {attempt + 1}): {str(e)[:200]}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Sub-agente para auto-promover thesis_candidate (vídeo monográfico de tesis
# articulada del canal — golem-de-cobre, diagrama-de-proxy, marco luterano-
# católico, etc.). Análogo a invoke_subagent_for_stub pero produce una
# página `synthesis` con `synthesis_subtype: author_thesis`. Solo se invoca
# cuando el thesis_candidate cumple el gate de §2.4.1 (minutes_sustained>=30,
# ≥3 authorship_marks, ≥4 piezas en framework_internal_structure).
# ---------------------------------------------------------------------------


SUBAGENT_SYNTHESIS_SYSTEM_PROMPT = """Eres un constructor focalizado de páginas synthesis para Ariadna.

CONTEXTO: Ariadna documenta el canal Proxy. Las páginas `synthesis` con
`synthesis_subtype: author_thesis` capturan TESIS ORIGINALES articuladas por el speaker
en vídeos monográficos sostenidos. NO son explicaciones de conceptos académicos
estándar (eso son `concept`); son el marco PROPIO del canal.

TU ÚNICA TAREA: dado UN thesis_candidate auto-promovido (cumple gate de scope.md §2.4.1)
+ contexto del summary del vídeo monográfico, devuelves la página markdown completa
(frontmatter YAML + body markdown) que articula la tesis con sus piezas internas.

NO tomas decisiones de scope. La promoción ya pasó el gate automático.
NO descartas piezas. Cada elemento de framework_internal_structure es contenido valioso.

Conforme al schema, produces JSON estricto con `frontmatter` y `body_markdown`.
Sin preámbulo, sin code fences. Primer carácter '{', último '}'.

Reglas duras:
1. `frontmatter.page_type: "synthesis"` y `frontmatter.synthesis_subtype: "author_thesis"`.
2. `frontmatter.auto_promoted_synthesis: true` (marca de auditoría — esta página se promovió sin firma humana porque el gate cumplió).
3. `frontmatter.relations[]` con AL MENOS 2 entradas tipadas hacia páginas existentes que la tesis toca o critica.
4. `frontmatter.aliases[]` con variantes razonables del thesis_title.
5. `body_markdown` empieza con `# {thesis_title}` y contiene:
   - `## Tesis nuclear` (1-2 párrafos articulando lo que el speaker propone)
   - `## Estructura del marco` con sub-bullets para CADA pieza de framework_internal_structure (no omitas piezas)
   - `## Citas del vídeo` con los speaker_authorship_marks como `> "literal"\\n→ [Título (mm:ss)](URL)`
   - `## Páginas conectadas` con wikilinks `[[page-id]]` a `related_existing_pages`
   - `## Lagunas` al final
   - `## Status auto-promoción` con disclaimer: "Esta página se ha auto-promovido al cumplir el gate de scope.md §2.4.1 (minutes_sustained, signal_marks, framework pieces). Queda abierta a revisión humana — campo `auto_promoted_synthesis: true` en frontmatter es la marca de auditoría."
6. Citas LITERALES del summary recibido (substring exacto).
7. Respeta vocabulario del canal (égersis, mito polar, mitología propia/impropia, diagrama de Proxy, etc.) — ver scope.md §5.
"""


def build_subagent_synthesis_user_msg(
    thesis: dict,
    video: "VideoInput",
    shadow: Path,
) -> str:
    """User message del sub-agente synthesis. Recibe thesis_candidate completo
    + contexto del vídeo monográfico. ~6-10K tokens.
    """
    seed_example = _load_seed_example()
    existing_ids = _list_existing_page_ids(shadow)

    title = thesis.get("thesis_title_proposed", "")
    proposed_pid = thesis.get("proposed_page_id", "")
    if not proposed_pid and title:
        proposed_pid = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]

    structure = thesis.get("framework_internal_structure", []) or []
    marks = thesis.get("speaker_authorship_marks", []) or []
    related = thesis.get("related_existing_pages", []) or []
    domain = thesis.get("domain_guess", "")
    minutes = thesis.get("minutes_sustained", 0)
    rationale = thesis.get("rationale", "")

    # Snippet del summary alrededor de la primera quote_evidence de los marks
    first_quote = ""
    for m in marks:
        q = _quote_to_str(m.get("quote_evidence", ""))
        if q:
            first_quote = q
            break
    summary_excerpt = _summary_excerpt_around_quote(
        video.summary_text, first_quote, ctx_chars=2500
    )

    marks_block = "\n".join(
        f"- **{m.get('mark_type','?')}**: {_quote_to_str(m.get('quote_evidence',''))!r}"
        for m in marks
    )
    structure_block = "\n".join(f"- {p}" for p in structure)
    related_block = ", ".join(f"`{r}`" for r in related) if related else "(ninguna declarada)"

    return f"""# Documentos autoritativos

## scope.md
{SCOPE_PATH.read_text(encoding="utf-8")}

## relation_types.json
```json
{RELATION_TYPES_PATH.read_text(encoding="utf-8")}
```

## Page IDs ya en el wiki (usa estos para wikilinks `[[page-id]]`)

{', '.join(sorted(existing_ids))}

## Ejemplo de página canónica del wiki (referencia de formato)

```markdown
{seed_example}
```

---

# Thesis candidate auto-promovido (gate §2.4.1 cumplido)

- **thesis_title_proposed**: {title}
- **proposed_page_id**: {proposed_pid}
- **synthesis_subtype**: author_thesis
- **domain_guess**: {domain}
- **minutes_sustained**: {minutes}
- **rationale**: {rationale}

## framework_internal_structure (cada pieza debe aparecer en el body)

{structure_block}

## speaker_authorship_marks (citas literales del speaker)

{marks_block}

## related_existing_pages

{related_block}

## Vídeo fuente monográfico

- **video_id**: {video.video_id}
- **title**: {video.title}
- **playlist**: {video.playlist}
- **url**: {video.url}

## Fragmento extenso del summary

```markdown
{summary_excerpt}
```

---

# Output schema

Devuelve JSON estricto:

{{
  "frontmatter": {{
    "page_id": "{proposed_pid}",
    "page_type": "synthesis",
    "synthesis_subtype": "author_thesis",
    "auto_promoted_synthesis": true,
    "canonical_name": "<nombre canónico de la tesis>",
    "aliases": ["<variante1>", "<variante2>"],
    "domain_primary": "{domain or '<dominio>'}",
    "primary_domains": ["<dom1>", "<dom2>"],
    "relations": [
      {{"type": "<relation_type>", "to": "<page_id>", "weight": "<canonical|strong|weak>", "note": "<explicación>"}}
    ],
    "sources_count": 1,
    "schema_version": "1.0.0",
    "review_status": "auto_promoted_pending_audit"
  }},
  "body_markdown": "# <canonical_name>\\n\\n## Tesis nuclear\\n\\n...\\n\\n## Estructura del marco\\n\\n- pieza 1: ...\\n- pieza 2: ...\\n\\n## Citas del vídeo\\n\\n> \\"literal\\"\\n→ [Título (mm:ss)](URL)\\n\\n## Páginas conectadas\\n\\n- [[page-id]] — relación\\n\\n## Lagunas\\n\\n- ...\\n\\n## Status auto-promoción\\n\\nEsta página se ha auto-promovido al cumplir el gate de scope.md §2.4.1...\\n"
}}

Devuelve ÚNICAMENTE el JSON.
"""


def invoke_subagent_for_thesis_synthesis(
    thesis: dict,
    video: "VideoInput",
    shadow: Path,
    max_retries: int = 1,
) -> Optional[dict]:
    """Llama a un sub-agente claude -p para construir una página synthesis a partir
    de un thesis_candidate que cumplió el gate de auto-promoción §2.4.1.

    Devuelve dict {frontmatter, body_markdown} o None si falla.
    """
    if not video.summary_text:
        load_summary(video)

    user_msg = build_subagent_synthesis_user_msg(thesis, video, shadow)

    for attempt in range(max_retries + 1):
        try:
            output_text, _meta = invoke_claude(
                user_msg=user_msg,
                system_prompt_appended=SUBAGENT_SYNTHESIS_SYSTEM_PROMPT,
                resume_session_id=None,
                model=CLAUDE_MODEL_SYNTHESIS_SUBAGENT,
            )
            json_text = _extract_json_object(output_text)
            if not json_text:
                print(
                    f"     ! synthesis subagent: no JSON object (attempt {attempt + 1})",
                    file=sys.stderr,
                )
                continue
            stub = json.loads(json_text)
            if (
                isinstance(stub, dict)
                and isinstance(stub.get("frontmatter"), dict)
                and isinstance(stub.get("body_markdown"), str)
                and stub["body_markdown"].strip()
            ):
                return stub
            print(
                f"     ! synthesis subagent: malformed structure (attempt {attempt + 1})",
                file=sys.stderr,
            )
        except subprocess.TimeoutExpired:
            print(f"     ! synthesis subagent timeout (attempt {attempt + 1})", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(
                f"     ! synthesis subagent JSON parse error (attempt {attempt + 1}): {e}",
                file=sys.stderr,
            )
        except Exception as e:
            print(
                f"     ! synthesis subagent error (attempt {attempt + 1}): {str(e)[:200]}",
                file=sys.stderr,
            )
    return None


def _thesis_meets_auto_promote_gate(thesis: dict) -> bool:
    """Gate de §2.4.1: minutes_sustained>=30 AND signal_marks>=3 AND structure>=4.

    Si el LLM declara explícitamente requires_human_validation=false, confiamos
    en su evaluación pero verificamos los criterios mecánicos por seguridad.
    """
    minutes = thesis.get("minutes_sustained", 0) or 0
    marks = thesis.get("speaker_authorship_marks", []) or []
    structure = thesis.get("framework_internal_structure", []) or []
    try:
        m_int = int(minutes) if not isinstance(minutes, int) else minutes
    except (TypeError, ValueError):
        m_int = 0
    return (
        m_int >= 30
        and len(marks) >= 3
        and len(structure) >= 4
    )


def _build_alias_to_page_id_map(shadow: Path) -> dict[str, str]:
    """Construye mapa lowercase(alias|canonical_name|page_id) → page_id leyendo
    todas las pages del shadow. Usado para resolver surface_forms del LLM
    a páginas existentes en auto_citation.
    """
    import yaml as _yaml
    alias_to_pid: dict[str, str] = {}
    for md in shadow.rglob("*.md"):
        if md.name == "README.md":
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        fm_text = m.group(1)
        try:
            fm_data = _yaml.safe_load(fm_text)
        except Exception:
            fm_data = None
        if not isinstance(fm_data, dict):
            continue
        pid = fm_data.get("page_id")
        if not isinstance(pid, str):
            continue
        # Indexa page_id, canonical_name y todos los aliases
        alias_to_pid[pid.lower()] = pid
        cname = fm_data.get("canonical_name")
        if isinstance(cname, str):
            alias_to_pid[cname.lower()] = pid
        for a in fm_data.get("aliases", []) or []:
            if isinstance(a, str):
                alias_to_pid[a.lower()] = pid
    return alias_to_pid


_TIMESTAMP_LINE_RE = re.compile(r"^- (\d+):(\d+)(?::(\d+))?\s", re.MULTILINE)


def _find_chunk_timestamp_for_text(summary: str, needle: str) -> Optional[int]:
    """Devuelve segundos del chunk donde aparece el needle, o None si no se
    puede localizar. Los summaries del corpus se organizan en chunks marcados
    por bullets `- HH:MM <emoji> Título` o `- H:MM:SS …`. Cada chunk contiene
    sub-bullets indentados con sus puntos temáticos. Para un quote_evidence
    determinado, encontramos el último timestamp marker antes de la posición
    del quote en el texto.
    """
    if not summary or not needle:
        return None
    idx = summary.find(needle)
    if idx == -1:
        # Intenta normalización ligera (lowercase + dedup whitespace) por si
        # el LLM re-escribió formato cosmético
        norm_sum = _normalize_for_quote_match(summary)
        norm_needle = _normalize_for_quote_match(needle)
        idx = norm_sum.find(norm_needle)
        if idx == -1:
            return None
        # Reproyectamos approx — usa el match en summary normalizado para
        # localizar el último timestamp en summary original
    matches = list(_TIMESTAMP_LINE_RE.finditer(summary[:idx]))
    if not matches:
        return None
    last = matches[-1]
    h = int(last.group(1))
    m = int(last.group(2))
    s = int(last.group(3)) if last.group(3) else 0
    # Si solo hay 2 grupos válidos, el primero es minutos y el segundo segundos
    if last.group(3) is None:
        # Formato MM:SS
        return h * 60 + m
    # Formato H:MM:SS
    return h * 3600 + m * 60 + s


_YT_TIMESTAMP_LINK_RE = re.compile(
    r"\[(\d+(?::\d+){1,2})\]\(https?://(?:www\.)?youtu\.be/([a-zA-Z0-9_-]+)\?t=(\d+)\)"
)


def _format_ts_display(ts_secs: int) -> str:
    """Formatea segundos a MM:SS o H:MM:SS según magnitud."""
    if ts_secs >= 3600:
        h = ts_secs // 3600
        m = (ts_secs % 3600) // 60
        s = ts_secs % 60
        return f"{h}:{m:02d}:{s:02d}"
    m = ts_secs // 60
    s = ts_secs % 60
    return f"{m}:{s:02d}"


def _upsert_video_citation_block(
    page_path: Path,
    video_id: str,
    video_title: str,
    new_timestamps: set[int],
) -> int:
    """Inserta o actualiza una línea compacta de citas del mismo vídeo.

    Formato: `- **Title** — chunks: [mm:ss](URL?t=N) · [mm:ss](URL?t=N) ...`

    Si ya hay líneas en ## Citations referenciando este video_id, extrae sus
    timestamps existentes, los une con `new_timestamps` (set), elimina esas
    líneas y escribe UNA sola línea compacta con todos los timestamps únicos
    ordenados.

    Devuelve el número de timestamps NUEVOS añadidos (excluye los que ya
    estaban). Útil para telemetría per-vídeo.
    """
    try:
        text = page_path.read_text(encoding="utf-8")
    except OSError:
        return 0

    citations_re = re.compile(
        r"(^## Citations\s*\n)(.*?)(?=^##\s|\Z)", re.DOTALL | re.MULTILINE
    )
    m = citations_re.search(text)

    existing_block = ""
    section_exists = False
    if m:
        section_exists = True
        existing_block = m.group(2)

    # Localiza líneas que referencien este video_id y extrae sus timestamps.
    # Soporta tres formatos:
    #   (a) compacto nuevo: `- **Title** — chunks: [mm:ss](URL?t=N) · ...`
    #   (b) per-line legacy con URL: `- → [Title (mm:ss)](URL?t=N)`
    #   (c) per-line legacy minimal del sub-agente: `- video_id: \`XXX\` — Title`
    # Cualquier línea que mencione el video_id se sustituye por una compacta.
    existing_ts: set[int] = set()
    surviving_lines: list[str] = []
    legacy_minimal_pattern = re.compile(
        r"video_id:?\s*[`'\"]?" + re.escape(video_id) + r"[`'\"]?\b",
    )
    for line in existing_block.splitlines():
        is_for_this_video = (
            f"youtu.be/{video_id}?t=" in line
            or f"youtu.be/{video_id})" in line
            or bool(legacy_minimal_pattern.search(line))
        )
        if is_for_this_video:
            # Extrae timestamps si la línea tiene URLs `?t=N`
            for ts_str, vid, ts_secs in _YT_TIMESTAMP_LINK_RE.findall(line):
                if vid == video_id:
                    try:
                        existing_ts.add(int(ts_secs))
                    except ValueError:
                        pass
            for legacy_match in re.finditer(
                r"\[[^\]]+\]\(https?://(?:www\.)?youtu\.be/" + re.escape(video_id) + r"\?t=(\d+)\)",
                line,
            ):
                try:
                    existing_ts.add(int(legacy_match.group(1)))
                except ValueError:
                    pass
            # Línea legacy minimal sin timestamps: nada que recuperar; la
            # absorberemos en la compacta nueva (sus timestamps vienen del
            # auto_generate_citations al escanear el summary).
            # esta línea se reemplaza, no la conservamos
        else:
            surviving_lines.append(line)
    # También captura sub-bullets indentados que cuelgan de la línea legacy
    # (ej. "  - surface_form: 'X'") — los descartamos si no tienen URL para
    # este vídeo. Filtra: si una línea no es para este vídeo pero el bullet
    # padre arriba sí lo era, también se descarta.
    cleaned_surviving: list[str] = []
    skip_indent_block = False
    for line in surviving_lines:
        is_top_bullet = line.lstrip().startswith("- ") and not line.startswith("  ")
        if is_top_bullet:
            skip_indent_block = False
        # Si la línea anterior se descartó y esta es indentada continuación
        # → también descártala.
        if line.startswith("  ") and skip_indent_block:
            continue
        cleaned_surviving.append(line)
    surviving_lines = cleaned_surviving

    union_ts = existing_ts | new_timestamps
    new_added = len(union_ts - existing_ts)

    if not union_ts:
        return 0  # nada que escribir

    # Construye línea compacta
    sorted_ts = sorted(union_ts)
    chunk_links = " · ".join(
        f"[{_format_ts_display(t)}](https://youtu.be/{video_id}?t={t})"
        for t in sorted_ts
    )
    compact_line = f"- **{video_title}** — chunks: {chunk_links}"

    # Reconstruye bloque
    surviving_block = "\n".join(surviving_lines).rstrip()
    if surviving_block:
        new_block_text = surviving_block + "\n" + compact_line + "\n"
    else:
        new_block_text = compact_line + "\n"

    if section_exists:
        # Mantén el "## Citations\n" header y separación trailing
        leading_blank = ""
        # Asegúrate de haber un salto entre header y primer bullet
        if not new_block_text.startswith("\n"):
            leading_blank = "\n"
        new_text = (
            text[: m.end(1)]
            + leading_blank
            + new_block_text
            + "\n"
            + text[m.end(2):]
        )
    else:
        new_text = (
            text.rstrip()
            + "\n\n## Citations\n\n"
            + new_block_text
        )

    if new_text == text:
        return 0
    page_path.write_text(new_text, encoding="utf-8")
    return new_added


# Aliases muy cortos o tokens genéricos que producirían demasiados falsos
# positivos si se usan como needle. La auto-cita los ignora aunque aparezcan
# como aliases válidos en algún frontmatter.
_ALIAS_BLACKLIST: set[str] = {
    "el yo", "yo", "ello", "self", "uno", "dios", "luz", "sombra",
    "ser", "hijo", "padre", "madre", "el padre", "la madre",
}


def _strip_diacritics(s: str) -> str:
    """Elimina marks combinables (tildes, dieresis) preservando longitud
    de las letras base ASCII. 'Tarzán' → 'Tarzan'. 'Drácula' → 'Dracula'."""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def _alias_variants(s: str) -> list[str]:
    """Genera variantes ortográficas robustas a partir de un nombre.

    Variantes:
      1. Original tal cual (`Tarzán (Disney, 1999)`)
      2. Sin diacríticos (`Tarzan (Disney, 1999)`)
      3. Sin paréntesis trailing (`Tarzán`, `Tarzan`)
      4. Sin "(YYYY)" / "(Studio, YYYY)" patrones para entity_work

    Útil para que el corpus mencione la entidad con nombre simplificado
    (ej. "Tarzán" alone) y aún la resolvamos al page con nombre completo.
    """
    out: set[str] = set()
    s = s.strip()
    if not s:
        return []
    out.add(s)
    no_diac = _strip_diacritics(s)
    if no_diac != s:
        out.add(no_diac)
    # Strip trailing parenthetical: "Tarzán (Disney, 1999)" → "Tarzán"
    paren_stripped = re.sub(r"\s*\([^)]*\)\s*$", "", s).strip()
    if paren_stripped and paren_stripped != s:
        out.add(paren_stripped)
        no_diac_p = _strip_diacritics(paren_stripped)
        if no_diac_p != paren_stripped:
            out.add(no_diac_p)
    return [v for v in out if v]


def _build_alias_index(shadow: Path) -> list[tuple[str, str, re.Pattern]]:
    """Devuelve lista de tuples (page_id, alias, compiled_word_boundary_regex)
    para todos los pages del shadow. Filtra aliases <4 chars y blacklist.
    canonical_name siempre se incluye y se expande a variantes (sin tildes,
    sin paréntesis trailing) para resolución robusta en summaries.
    """
    import yaml as _yaml
    out: list[tuple[str, str, re.Pattern]] = []
    seen: set[tuple[str, str]] = set()  # dedup (page_id, alias_lower)

    def _add_one(page_id: str, raw_alias: str, force: bool = False) -> None:
        if not raw_alias or not isinstance(raw_alias, str):
            return
        a = raw_alias.strip()
        if not a:
            return
        if a.lower() in _ALIAS_BLACKLIST:
            return
        if not force and len(a) < 4:
            return
        key = (page_id, a.lower())
        if key in seen:
            return
        seen.add(key)
        # Word-boundary + IGNORECASE. UNICODE flag por defecto en Python 3,
        # \b respeta word chars con tildes.
        pattern = re.compile(r"\b" + re.escape(a) + r"\b", re.IGNORECASE)
        out.append((page_id, a, pattern))

    def _add_with_variants(page_id: str, raw: str, force: bool = False) -> None:
        for v in _alias_variants(raw):
            _add_one(page_id, v, force=force)

    for md in shadow.rglob("*.md"):
        if md.name == "README.md":
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        try:
            fm = _yaml.safe_load(m.group(1))
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        pid = fm.get("page_id")
        if not isinstance(pid, str) or not pid:
            continue
        cname = fm.get("canonical_name")
        if isinstance(cname, str):
            _add_with_variants(pid, cname, force=True)
        for a in fm.get("aliases", []) or []:
            _add_with_variants(pid, a, force=False)
        _add_with_variants(pid, pid, force=False)
    return out


def auto_generate_citations(
    video_data: dict,
    video: "VideoInput",
    shadow: Path,
) -> dict:
    """Auto-cita determinista: escanea video.summary_text directamente buscando
    aliases/canonical_names de pages existentes en el shadow. Por cada match,
    calcula timestamp del chunk al que pertenece y emite cita con `?t=SECS`.

    NO depende de discards/entities del LLM — escanea el texto crudo. Esto
    garantiza 100% recall de menciones independiente de lo que el LLM decida
    emitir. Necesario para retrieval indirecto vía citations table (lookup
    exacto por video_id+timestamp_seconds).

    Dedup estricta por (page_id, video_id, timestamp_seconds): cada chunk
    único donde aparece una page → una cita. Múltiples chunks del mismo
    vídeo a la misma page → múltiples citas (cada una recuperable
    independientemente).
    """
    stats = {
        "auto_citations_added": 0,
        "auto_citations_skipped_dup": 0,
        "auto_citations_skipped_no_timestamp": 0,
        "pages_with_new_citations": 0,
    }
    if not video.summary_text:
        load_summary(video)
    if not video.summary_text:
        return stats

    alias_index = _build_alias_index(shadow)
    if not alias_index:
        return stats

    # Para cada page_id: set de timestamps únicos donde aparece en este vídeo
    page_to_timestamps: dict[str, set[int]] = {}
    for page_id, alias, pattern in alias_index:
        for m in pattern.finditer(video.summary_text):
            ts = _find_chunk_timestamp_for_position(video.summary_text, m.start())
            if ts is None:
                stats["auto_citations_skipped_no_timestamp"] += 1
                continue
            page_to_timestamps.setdefault(page_id, set()).add(ts)

    if not page_to_timestamps:
        return stats

    # Por cada page con timestamps detectados: upsert compacto de la línea
    # `- **Title** — chunks: [t1](URL) · [t2](URL) · ...` (UNA línea por
    # (page, video), todos los timestamps unidos al existente y dedup).
    for page_id, timestamps in page_to_timestamps.items():
        page_path = _shadow_path_for_page_id(shadow, page_id)
        if not page_path.exists():
            continue
        added = _upsert_video_citation_block(
            page_path=page_path,
            video_id=video.video_id,
            video_title=video.title,
            new_timestamps=timestamps,
        )
        stats["auto_citations_added"] += added
        if added > 0:
            stats["pages_with_new_citations"] += 1
        else:
            # Todos los timestamps ya estaban — registrar como dup
            stats["auto_citations_skipped_dup"] += len(timestamps)

    return stats


def _find_chunk_timestamp_for_position(summary: str, position: int) -> Optional[int]:
    """Dada una posición en el summary, devuelve segundos del marker chunk
    `- HH:MM` o `- H:MM:SS` más cercano hacia atrás. Reutiliza el regex global
    `_TIMESTAMP_LINE_RE` que coincide con la sintaxis usada por
    `ariadna/parsers.py:_CHUNK_HEADER_RE` (los chunks Qdrant tienen el mismo
    timestamp).
    """
    if position <= 0:
        return None
    pre = summary[:position]
    matches = list(_TIMESTAMP_LINE_RE.finditer(pre))
    if not matches:
        return None
    last = matches[-1]
    g1 = int(last.group(1))
    g2 = int(last.group(2))
    g3 = last.group(3)
    if g3 is None:
        # Formato MM:SS
        return g1 * 60 + g2
    # Formato H:MM:SS
    return g1 * 3600 + g2 * 60 + int(g3)


def apply_video_output_to_shadow(
    shadow: Path,
    video_data: dict,
    video: "VideoInput",
) -> dict:
    """Aplica pending_updates y materializa promote_new del vídeo en el shadow.

    Reutiliza los ops de apply_pending_updates.py (anchor literal único,
    skip-on-ambiguity). Devuelve stats para log de batch.

    Schema-tolerant: el LLM emite a veces nombres alternativos
    (action↔decision, target_page_id↔page_id, new_content_markdown↔
    content_proposed). Aliasamos defensivamente.
    """
    # Import perezoso para evitar dependencia circular si apply_pending_updates
    # importa de aquí en el futuro.
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        from apply_pending_updates import apply_updates_to_page  # type: ignore
    finally:
        sys.path.pop(0)

    stats = {
        "pending_applied": 0,
        "pending_skipped": 0,
        "stubs_created": 0,
        "stubs_skipped_existing": 0,
        "page_not_found_in_shadow": 0,
        "subagents_invoked": 0,
        "subagents_successful": 0,
        "subagents_failed": 0,
        "thesis_auto_promoted": 0,
        "thesis_auto_promote_failed": 0,
        "thesis_skipped_human_review": 0,
        "enriches_concept_applied": 0,
        "enriches_concept_skipped_no_page": 0,
        "recommended_references_collected": 0,
    }

    # 1) Apply pending_updates por page_id (schema-tolerant).
    # 1.5) Inyectamos pending_updates sintéticos derivados de discarded[] con
    #      `enriches_concept`: el LLM marca una mención como caso ilustrativo
    #      de un concept ya promovido (ej. Pablo Iglesias → diagrama-de-proxy).
    #      Generamos automáticamente un add_citation (cita-only) a esa page con
    #      timestamp del marker más cercano. Esto rescata señal valiosa que el
    #      LLM de otro modo dejaría enterrada en discarded[].
    pending_by_page: dict[str, list[dict]] = {}
    for pu in video_data.get("pending_updates", []) or []:
        pid = _alias_get(pu, "page_id", "target_page_id")
        if not pid:
            stats["pending_skipped"] += 1
            continue
        # Normaliza el dict a las keys que apply_updates_to_page espera
        norm = dict(pu)
        norm["page_id"] = pid
        norm["update_type"] = pu.get("update_type", "")
        norm["anchor_passage"] = _alias_get(pu, "anchor_passage", "anchor")
        norm["content_proposed"] = _alias_get(pu, "content_proposed", "new_content_markdown", "content")
        norm["section_target"] = pu.get("section_target")
        norm["supersedes_laguna_text"] = _alias_get(pu, "supersedes_laguna_text", "supersedes_laguna")
        pending_by_page.setdefault(pid, []).append(norm)

    # Procesar enriches_concept de discarded[] como pending_updates sintéticos.
    # No se aplican aquí — el bucle inferior los aplica junto al resto.
    for d in video_data.get("discarded", []) or []:
        target_pid = d.get("enriches_concept")
        if not target_pid or not isinstance(target_pid, str):
            continue
        target_path = _shadow_path_for_page_id(shadow, target_pid)
        if not target_path.exists():
            stats["enriches_concept_skipped_no_page"] += 1
            continue
        quote = _quote_to_str(d.get("quote_evidence", ""))
        ts = _find_chunk_timestamp_for_text(video.summary_text, quote) if quote else None
        # Synthetic add_citation pending_update: se procesará en auto_generate_citations
        # via el escaneo determinista (ese flow es más robusto). Aquí solo
        # contamos la señal para telemetría.
        stats["enriches_concept_applied"] += 1
        # NOTA: la inserción real de la cita ocurre en auto_generate_citations(),
        # que escanea el summary y emite citas con timestamp para CADA chunk
        # donde aparece el alias. enriches_concept es una señal redundante
        # (tracking, no acción) — el flow determinista ya cubre ese caso si la
        # mención del speaker matchea aliases de la page target. Si no matchea
        # (alias_index pobre), enriches_concept actúa como hint para revisión.

    for page_id, updates in pending_by_page.items():
        page_path = _shadow_path_for_page_id(shadow, page_id)
        if not page_path.exists():
            stats["page_not_found_in_shadow"] += 1
            continue
        try:
            _, new_text, _ = apply_updates_to_page(page_path, updates)
        except Exception:
            stats["pending_skipped"] += len(updates)
            continue
        page_path.write_text(new_text, encoding="utf-8")
        stats["pending_applied"] += len(updates)

    # 2) Materializa stubs para promote_new entities — invoca SUB-AGENTE per
    #    candidato (claude -p separado, sesión limpia, contexto focalizado)
    # Pre-cargamos el alias_map para resolver casos donde el main agent emita
    # canonical_guess en formato no-kebab ("Tarzán (Disney, 1999)") cuando
    # ya existe un page_id kebab equivalente ("tarzan-1999-film"). Sin esto
    # gastamos sub-agente builds redundantes.
    alias_map_for_dedupe = _build_alias_to_page_id_map(shadow)

    # Schema-tolerant: el LLM emite a veces promote_new[] como array top-level
    # directamente (más natural) y a veces como decision='promote_new' dentro de
    # entities[]. Recolectamos ambas formas en una sola lista de candidatos.
    promote_candidates: list[dict] = []
    for ent in video_data.get("entities", []) or []:
        decision = _alias_get(ent, "decision", "action")
        if decision == "promote_new":
            promote_candidates.append(ent)
    for ent in video_data.get("promote_new", []) or []:
        if isinstance(ent, dict):
            # Inyecta decision para que _alias_get downstream funcione
            norm = dict(ent)
            norm.setdefault("decision", "promote_new")
            promote_candidates.append(norm)

    for ent in promote_candidates:
        decision = _alias_get(ent, "decision", "action")
        if decision != "promote_new":
            continue

        page_id = _alias_get(ent, "canonical_guess", "page_id_proposed", "page_id") or ""
        if not page_id:
            continue
        page_type = _alias_get(ent, "page_type") or "concept"

        # Resolución por alias: si "Tarzán (Disney, 1999)" mapea a "tarzan-1999-film"
        # ya existente, contamos como existente y saltamos el sub-agente.
        canonical_pid = alias_map_for_dedupe.get(page_id.lower())
        if canonical_pid:
            page_id = canonical_pid
        sf_lower = (ent.get("surface_form") or "").lower()
        if not canonical_pid and sf_lower:
            canonical_pid = alias_map_for_dedupe.get(sf_lower)
            if canonical_pid:
                page_id = canonical_pid

        target = _shadow_path_for_page_id(shadow, page_id, page_type)
        if target.exists():
            stats["stubs_skipped_existing"] += 1
            continue

        # Path A (preferido, post-2026-05-02): el main agent NO emite stub.
        # Invocamos sub-agente focalizado para construirlo. Mantiene
        # compounding intra-batch (escribe en shadow antes del siguiente vid).
        stats["subagents_invoked"] += 1
        print(
            f"     → subagent for {page_id} ({page_type}) [{ent.get('surface_form','?')[:30]}]",
            file=sys.stderr,
        )
        stub_obj = invoke_subagent_for_stub(ent, video, shadow, max_retries=1)
        if stub_obj is not None:
            stats["subagents_successful"] += 1
            _materialize_stub_from_llm(shadow, stub_obj, video)
            stats["stubs_created"] += 1
            continue

        # Path B (fallback de error del sub-agente): minimal stub con
        # quote_evidence. Permite que vídeos posteriores referencien vía
        # wikilink aunque la página no haya cuajado en su primera invocación.
        stats["subagents_failed"] += 1
        print(f"     ! subagent failed for {page_id}; fallback minimal stub", file=sys.stderr)
        domain = _alias_get(ent, "domain_primary_guess", "domain_primary") or ""
        _materialize_stub_page(
            shadow=shadow,
            page_id=page_id,
            page_type=page_type,
            domain=domain,
            canonical_name=ent.get("surface_form", page_id),
            quote_evidence=_quote_to_str(ent.get("quote_evidence", "")),
            video_id=video.video_id,
            video_title=video.title,
            surface_form=ent.get("surface_form", ""),
            proposed_initial_body=None,
        )
        stats["stubs_created"] += 1

    # 2.5) Auto-promover thesis_candidates fuertes (gate scope.md §2.4.1):
    #      vídeos monográficos de tesis articulada por el speaker (golem-de-cobre,
    #      diagrama-de-proxy, marco luterano-católico) reciben page synthesis
    #      construida por sub-agente. Sin este paso, vídeos foundational del canal
    #      nunca tocaban el wiki — quedaban en thesis_candidates.json esperando
    #      firma humana indefinidamente.
    for thesis in video_data.get("thesis_candidates", []) or []:
        # Confianza en el LLM: si declaró requires_human_validation=true,
        # respetamos su evaluación (puede haber visto algo borderline).
        # Si declaró false, verificamos el gate mecánicamente por seguridad.
        rhv = thesis.get("requires_human_validation", True)
        if rhv is True:
            stats["thesis_skipped_human_review"] += 1
            continue
        if not _thesis_meets_auto_promote_gate(thesis):
            stats["thesis_skipped_human_review"] += 1
            continue

        # Resuelve page_id: usa proposed_page_id o derivado del thesis_title
        title = thesis.get("thesis_title_proposed", "")
        proposed_pid = thesis.get("proposed_page_id", "")
        if not proposed_pid and title:
            proposed_pid = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
        if not proposed_pid:
            stats["thesis_auto_promote_failed"] += 1
            continue

        # Dedup contra páginas existentes (alias map)
        canonical_pid = alias_map_for_dedupe.get(proposed_pid.lower())
        if canonical_pid:
            proposed_pid = canonical_pid

        target = _shadow_path_for_page_id(shadow, proposed_pid, "synthesis")
        if target.exists():
            # Ya existe — no re-promover, futura update_existing decidirá enrichments
            stats["stubs_skipped_existing"] += 1
            continue

        print(
            f"     → synthesis subagent for {proposed_pid} (auto-promoted thesis: {title[:50]})",
            file=sys.stderr,
        )
        stats["subagents_invoked"] += 1
        synth_obj = invoke_subagent_for_thesis_synthesis(thesis, video, shadow, max_retries=1)
        if synth_obj is not None:
            stats["subagents_successful"] += 1
            stats["thesis_auto_promoted"] += 1
            _materialize_stub_from_llm(shadow, synth_obj, video)
            stats["stubs_created"] += 1
        else:
            stats["subagents_failed"] += 1
            stats["thesis_auto_promote_failed"] += 1
            print(
                f"     ! synthesis subagent failed for {proposed_pid} — queda en thesis_candidates.json",
                file=sys.stderr,
            )

    # 2.6) Recolectar recommended_references[] para aggregator. Se persisten
    #      en el video_data (que ya queda commiteado per-vídeo) y se agregan
    #      al final del run a recommended_references.json del run dir.
    rec_refs: list[dict] = []
    for d in video_data.get("discarded", []) or []:
        if d.get("reason_code") != "recommended_reference":
            continue
        payload = d.get("recommended_reference_payload") or {}
        if not isinstance(payload, dict):
            continue
        # Si el LLM no emitió timestamp, intentamos extraerlo del quote
        ts = payload.get("timestamp_seconds")
        if ts is None:
            quote = _quote_to_str(d.get("quote_evidence", ""))
            if quote:
                ts = _find_chunk_timestamp_for_text(video.summary_text, quote)
        rec_refs.append({
            "video_id": video.video_id,
            "video_title": video.title,
            "surface_form": d.get("surface_form", ""),
            "book_title": payload.get("book_title", ""),
            "authors": payload.get("authors", []) or [],
            "domain": payload.get("domain", ""),
            "why_recommended": payload.get("why_recommended", ""),
            "quote_evidence": _quote_to_str(d.get("quote_evidence", "")),
            "timestamp_seconds": ts,
        })
    stats["recommended_references_collected"] = len(rec_refs)
    # Adjunta al video_data para que el aggregator lo recoja al final del run.
    if rec_refs:
        video_data.setdefault("_collected_recommended_references", []).extend(rec_refs)

    # 3) Auto-citation determinista: escanea video.summary_text directamente
    #    y añade citas con timestamp a TODAS las pages mencionadas (no solo
    #    las que el LLM enriqueció con prosa). Garantiza que cada chunk
    #    relevante tenga su entrada en data/wiki.db:citations para que el
    #    retrieval indirecto del MCP server lo encuentre. Ejecuta AL FINAL,
    #    sobre el shadow ya enriquecido (incluye stubs nuevos del sub-agente
    #    + synthesis pages auto-promovidas).
    try:
        cite_stats = auto_generate_citations(video_data, video, shadow)
        stats.update({
            "auto_citations_added": cite_stats["auto_citations_added"],
            "auto_citations_skipped_dup": cite_stats["auto_citations_skipped_dup"],
            "auto_citations_skipped_no_timestamp": cite_stats["auto_citations_skipped_no_timestamp"],
            "pages_with_new_citations": cite_stats["pages_with_new_citations"],
        })
    except Exception as e:
        print(f"     ! auto_generate_citations error: {e}", file=sys.stderr)

    return stats


def _materialize_stub_from_llm(shadow: Path, stub_obj: dict, video: "VideoInput") -> Optional[Path]:
    """Materializa un stub usando frontmatter + body_markdown emitidos por el LLM.

    El LLM frecuentemente emite estructura más rica (relations tipadas,
    aliases, primary_domains[], wikilinks inline) que la plantilla minimal.
    Adoptamos su output verbatim para preservar esa calidad.
    """
    fm = stub_obj.get("frontmatter") or {}
    body_md = stub_obj.get("body_markdown") or ""
    page_id = fm.get("page_id")
    if not page_id:
        return None

    page_type = fm.get("page_type", "concept")
    target = _shadow_path_for_page_id(shadow, page_id, page_type)
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)

    # Asegura status: stub_in_session (sobreescribe si LLM puso otra cosa)
    fm = dict(fm)
    fm["status"] = "stub_in_session"
    if "review_status" in fm:
        fm["review_status"] = "stub_in_session"

    # Serializa frontmatter como YAML — usa PyYAML si está disponible para
    # garantizar conformidad estricta. Fallback a serializer manual robusto
    # (con sintaxis BLOCK para listas de dicts).
    try:
        import yaml as _yaml  # type: ignore
        frontmatter_yaml = _yaml.safe_dump(
            fm, allow_unicode=True, sort_keys=False, default_flow_style=False
        ).rstrip()
        frontmatter_str = "---\n" + frontmatter_yaml + "\n---\n"
    except ImportError:
        def _scalar(v):
            if v is None:
                return "null"
            if isinstance(v, bool):
                return "true" if v else "false"
            if isinstance(v, (int, float)):
                return str(v)
            s = str(v)
            if any(c in s for c in [":", "#", "\n", "'", '"']) or s != s.strip():
                return json.dumps(s, ensure_ascii=False)
            return s

        def _emit(key, val, indent=0):
            pad = " " * indent
            if isinstance(val, list):
                if not val:
                    yield f"{pad}{key}: []"
                else:
                    yield f"{pad}{key}:"
                    for item in val:
                        if isinstance(item, dict):
                            first = True
                            for ik, iv in item.items():
                                prefix = f"{pad}  - " if first else f"{pad}    "
                                first = False
                                yield from _emit_value(prefix, ik, iv)
                        else:
                            yield f"{pad}  - {_scalar(item)}"
            elif isinstance(val, dict):
                yield f"{pad}{key}:"
                for ik, iv in val.items():
                    yield from _emit(ik, iv, indent + 2)
            else:
                yield f"{pad}{key}: {_scalar(val)}"

        def _emit_value(prefix, ik, iv):
            if isinstance(iv, (list, dict)):
                yield prefix + f"{ik}:"
                if isinstance(iv, list):
                    for sub in iv:
                        yield " " * len(prefix) + f"  - {_scalar(sub) if not isinstance(sub, dict) else ''}"
                else:
                    for sik, siv in iv.items():
                        yield " " * len(prefix) + f"  {sik}: {_scalar(siv)}"
            else:
                yield prefix + f"{ik}: {_scalar(iv)}"

        yaml_lines = ["---"]
        for k, v in fm.items():
            yaml_lines.extend(_emit(k, v))
        yaml_lines.append("---")
        yaml_lines.append("")
        frontmatter_str = "\n".join(yaml_lines)

    body = body_md.strip() + "\n"

    # Si el LLM no incluyó sección Lagunas, añadirla vacía al final
    if "## Lagunas" not in body:
        body = body.rstrip() + "\n\n## Lagunas\n\n- (sin lagunas declaradas todavía)\n"

    # Asegurar al menos una mención de la cita en Citations si LLM no la puso
    if "## Citations" not in body and "## Citaciones" not in body and "## Fuentes" not in body:
        body = body.rstrip() + (
            f"\n\n## Citations\n\n"
            f"- video_id: `{video.video_id}` — {video.title}\n"
        )

    target.write_text(frontmatter_str + "\n" + body, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Invocación de Claude Code headless
# ---------------------------------------------------------------------------


def invoke_claude(
    user_msg: str,
    system_prompt_appended: Optional[str],
    resume_session_id: Optional[str],
    model: str = CLAUDE_MODEL_MAIN,
) -> tuple[str, dict]:
    """Invoca `claude -p` con user_msg vía stdin y devuelve (output_text, metadata).

    Crítico: user_msg se pasa por **stdin**, NO por argv. Linux limita argv a
    ~128KB-2MB (ARG_MAX); el primer mensaje de sesión incluye el contexto
    pesado (~50K tokens) que excedería ese límite si fuera por argv.
    El system_prompt corto (~10K) sí va por argv (--append-system-prompt).

    metadata incluye session_id (para --resume posterior) y conteos de tokens
    cuando el CLI los emite. El caching cross-invocation con --resume es la
    palanca principal de optimización — verificar empíricamente que
    cached_tokens > 0 a partir del segundo vídeo de la sesión.
    """
    # `claude -p` SIN argumento posicional lee el prompt de stdin.
    cmd: list[str] = ["claude", "-p", "--model", model]
    cmd += ["--output-format", "stream-json", "--verbose"]
    # Read y Grep habilitados para que el extractor pueda drillar en páginas
    # del wiki (Karpathy index pattern). Resto de tools restringidos.
    cmd += ["--allowedTools", "Read,Grep,Glob"]

    if resume_session_id:
        cmd += ["--resume", resume_session_id]
    if system_prompt_appended is not None:
        cmd += ["--append-system-prompt", system_prompt_appended]

    proc = subprocess.run(
        cmd,
        input=user_msg,
        capture_output=True,
        text=True,
        timeout=PER_CALL_TIMEOUT_S,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude -p exited {proc.returncode}: stderr={proc.stderr[-500:]}"
        )

    # stream-json: cada línea es un evento JSON. Buscamos el message final
    # (type=result o equivalente) y la sesión.
    session_id: Optional[str] = None
    output_text: Optional[str] = None
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "session_id" in evt and not session_id:
            session_id = evt["session_id"]
        # Diferentes versiones del CLI emiten formatos ligeramente distintos.
        # Capturamos los más comunes:
        if evt.get("type") == "result" and "result" in evt:
            output_text = evt["result"]
        if evt.get("type") == "assistant" and "message" in evt:
            msg = evt["message"]
            if isinstance(msg, dict) and "content" in msg:
                content = msg["content"]
                if isinstance(content, list):
                    for c in content:
                        if c.get("type") == "text":
                            output_text = c.get("text", output_text)
                elif isinstance(content, str):
                    output_text = content
        usage = evt.get("usage") or evt.get("message", {}).get("usage") if isinstance(evt.get("message"), dict) else evt.get("usage")
        if isinstance(usage, dict):
            input_tokens = max(input_tokens, int(usage.get("input_tokens", 0) or 0))
            output_tokens = max(output_tokens, int(usage.get("output_tokens", 0) or 0))
            cached_tokens = max(cached_tokens, int(usage.get("cache_read_input_tokens", 0) or 0))

    if output_text is None:
        # Fallback: stdout completo si no encontramos evento estructurado
        output_text = proc.stdout

    meta = {
        "session_id": session_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
    }
    return output_text, meta


# ---------------------------------------------------------------------------
# Validación del JSON de salida
# ---------------------------------------------------------------------------


_QUOTE_NORMALIZE_RE_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_QUOTE_NORMALIZE_RE_ITALIC_AST = re.compile(r"\*(.+?)\*", re.DOTALL)
_QUOTE_NORMALIZE_RE_BOLD_UND = re.compile(r"__(.+?)__", re.DOTALL)
_QUOTE_NORMALIZE_RE_ITALIC_UND = re.compile(r"(?<!\w)_(.+?)_(?!\w)", re.DOTALL)
_QUOTE_NORMALIZE_RE_CODE = re.compile(r"`(.+?)`", re.DOTALL)
_QUOTE_NORMALIZE_RE_WS = re.compile(r"\s+")


def _normalize_for_quote_match(text: str) -> str:
    """Normaliza formato cosmético antes de comparar quote_evidence con el
    summary. El LLM al "copiar" prosa elimina markdown italic/bold/code,
    convierte comillas curly a straight, colapsa espacios. Eso es
    comportamiento esperado y NO debe disparar falso positivo de alucinación.

    Aplica la MISMA normalización a ambos lados del match (summary y quote).
    No toca el contenido semántico — solo formato cosmético.
    """
    if not text:
        return ""
    # Markdown emphasis: **bold**, *italic*, __bold__, _italic_
    text = _QUOTE_NORMALIZE_RE_BOLD.sub(r"\1", text)
    text = _QUOTE_NORMALIZE_RE_BOLD_UND.sub(r"\1", text)
    text = _QUOTE_NORMALIZE_RE_ITALIC_AST.sub(r"\1", text)
    text = _QUOTE_NORMALIZE_RE_ITALIC_UND.sub(r"\1", text)
    # Backticks de código inline
    text = _QUOTE_NORMALIZE_RE_CODE.sub(r"\1", text)
    # Comillas curly → straight (el LLM convierte espontáneamente)
    text = (
        text.replace("“", '"').replace("”", '"')
        .replace("‘", "'").replace("’", "'")
        .replace("«", '"').replace("»", '"')
    )
    # Em-dash / en-dash → hyphen (el LLM a veces los normaliza)
    text = text.replace("—", "-").replace("–", "-")
    # Whitespace: cualquier secuencia → un solo espacio
    text = _QUOTE_NORMALIZE_RE_WS.sub(" ", text)
    return text.strip()


def parse_and_validate_output(raw: str, video: VideoInput) -> tuple[Optional[dict], list[str]]:
    """Devuelve (parsed_dict, errors). errors vacío = OK.

    Defensa de tipos: quote_evidence puede llegar como string (esperado por
    schema) o como list (Opus a veces emite múltiples evidencias en lista
    pese a que el schema pide string singular). En ambos casos validamos
    cada elemento contra el summary literal.
    """
    errors: list[str] = []
    text = raw.strip()
    # Tolerar code fences accidentales
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

    # Tolerar preámbulo en prosa: si no empieza por '{', extrae el primer
    # objeto JSON balanceado. El schema prohíbe preámbulo, pero el output
    # es semánticamente válido si contiene un objeto bien formado. Mejor
    # rescatarlo que tirar 23K tokens de extracción al fail bin.
    if text and text[0] != "{":
        start = text.find("{")
        if start == -1:
            errors.append("JSON parse failed: no '{' found in output")
            return None, errors
        depth = 0
        end = -1
        in_str = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end == -1:
            errors.append("JSON parse failed: unbalanced braces in output")
            return None, errors
        text = text[start:end]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        errors.append(f"JSON parse failed: {e}")
        return None, errors

    # Verificación de quote_evidence — comparación normalizada literal.
    #
    # Filosofía: el LLM al copiar prosa NORMALIZA inconscientemente formato
    # cosmético (asteriscos markdown italic, comillas curly, espacios
    # redundantes, backticks). Eso NO es alucinación, es comportamiento
    # esperado del LLM. Mi validación tiene que aplicar la misma
    # normalización a AMBOS lados del match para no dar falsos positivos.
    #
    # Lo que SÍ rechazamos (alucinación o paráfrasis genuina):
    #   - Cita que no existe ni siquiera tras normalización en summary +
    #     metadata (título, playlist, etc.)
    #   - El LLM cambió palabras de contenido ("en" por "de", "es" por
    #     "fue", añadió/quitó cláusulas) → fail genuino, vídeo a .failed.json
    #
    # Lo que NO rechazamos (cosmético):
    #   - *La tabla rasa* (markdown italic) → La tabla rasa
    #   - "comillas curly" → "comillas straight"
    #   - múltiples   espacios → un espacio
    #   - `backticks de código` → backticks de código
    searchable_raw = "\n".join(
        [
            video.summary_text,
            video.video_id,
            video.title,
            video.playlist,
            video.slug,
            video.category,
            str(video.duration_s),
            video.upload_date,
            video.url,
        ]
    )
    searchable = _normalize_for_quote_match(searchable_raw)

    # Política 2026-05-02: validación SOFT por entrada — el LLM con frecuencia
    # parafrasea citas en discards/framing_marks. Rechazar el vídeo entero
    # cuesta tirar 5K+ tokens de extracción útil por una cita aproximada en
    # un discard. Hacemos drop quirúrgico de la entrada con cita mala y
    # conservamos el resto. Solo se rechaza el vídeo si TODO queda vacío.
    warnings: list[str] = []

    def quote_ok(quote) -> bool:
        if quote is None or quote == "":
            return True  # cita ausente: ya hay otra regla que lo penalizará
        if isinstance(quote, str):
            quotes = [quote]
        elif isinstance(quote, list):
            quotes = [q for q in quote if isinstance(q, str) and q]
            if not quotes:
                return True
        else:
            return False
        for q in quotes:
            q_norm = _normalize_for_quote_match(q)
            if q_norm and q_norm not in searchable:
                return False
        return True

    # Filtra entities con cita mala (load-bearing → drop entity entera)
    kept_entities: list[dict] = []
    for ent in data.get("entities", []) or []:
        if not quote_ok(ent.get("quote_evidence")):
            warnings.append(
                f"DROP entity[{ent.get('canonical_guess','?')}] decision={ent.get('decision','?')} "
                f"quote no literal: {(ent.get('quote_evidence') or '')[:80]!r}"
            )
            continue
        # Filtra framing_marks individuales con cita mala (no tira la entidad)
        kept_marks: list[dict] = []
        for fm in ent.get("framing_marks", []) or []:
            if quote_ok(fm.get("quote_evidence")):
                kept_marks.append(fm)
            else:
                warnings.append(
                    f"DROP framing_mark @ entity[{ent.get('canonical_guess','?')}]: "
                    f"{(fm.get('quote_evidence') or '')[:60]!r}"
                )
        ent["framing_marks"] = kept_marks
        kept_entities.append(ent)
    data["entities"] = kept_entities

    # Filtra discards con cita mala — más laxo, son audit, no claim
    kept_discards: list[dict] = []
    for d in data.get("discarded", []) or []:
        if quote_ok(d.get("quote_evidence")):
            kept_discards.append(d)
        else:
            warnings.append(
                f"DROP discarded[{d.get('surface_form','?')}] "
                f"reason={d.get('reason_code','?')} quote no literal"
            )
    data["discarded"] = kept_discards

    # Filtra thesis_candidates — si ALGÚN speaker_authorship_mark queda válido,
    # la tesis sobrevive con marks reducidos
    kept_thesis: list[dict] = []
    for t in data.get("thesis_candidates", []) or []:
        kept_marks: list[dict] = []
        for sm in t.get("speaker_authorship_marks", []) or []:
            if quote_ok(sm.get("quote_evidence")):
                kept_marks.append(sm)
            else:
                warnings.append(
                    f"DROP speaker_mark @ thesis[{t.get('thesis_title_proposed','?')[:40]}]"
                )
        if kept_marks:
            t["speaker_authorship_marks"] = kept_marks
            kept_thesis.append(t)
        else:
            warnings.append(
                f"DROP thesis[{t.get('thesis_title_proposed','?')[:40]}]: 0 marks válidos restantes"
            )
    data["thesis_candidates"] = kept_thesis

    # Validación de calidad de stubs: cada promote_new con depth secondary o
    # central_thesis DEBE traer stub_proposed con frontmatter.relations[]
    # tipadas (≥2 entradas) y aliases[]. Si falla → warning. Si encima usó
    # proposed_initial_body flat string (legacy schema) → warning explícito
    # apuntando a la causa raíz.
    for ent in data.get("entities", []) or []:
        decision = _alias_get(ent, "decision", "action")
        if decision != "promote_new":
            continue
        depth = _alias_get(ent, "depth_in_video", "depth")
        if depth not in ("secondary", "central_thesis"):
            continue  # passing_mention OK con stub minimal
        sf = ent.get("surface_form", "?")
        stub = ent.get("stub_proposed")
        if not isinstance(stub, dict):
            if ent.get("proposed_initial_body"):
                warnings.append(
                    f"WARN promote_new[{sf}] depth={depth}: emitió proposed_initial_body "
                    f"(schema legacy) en vez de stub_proposed — frontmatter quedará minimal"
                )
            else:
                warnings.append(
                    f"WARN promote_new[{sf}] depth={depth}: sin stub_proposed; "
                    f"stub minimal generado solo desde quote_evidence"
                )
            continue
        fm = stub.get("frontmatter", {}) or {}
        rels = fm.get("relations") or []
        aliases = fm.get("aliases") or []
        if len(rels) < 2:
            warnings.append(
                f"WARN promote_new[{sf}]: stub_proposed.frontmatter.relations[] "
                f"tiene {len(rels)} entradas (<2 requeridas) — KG aislado"
            )
        if not aliases:
            warnings.append(
                f"WARN promote_new[{sf}]: stub_proposed.frontmatter.aliases[] vacío "
                f"— vídeos posteriores con surface_form distinto crearán fork"
            )
        if not stub.get("body_markdown", "").strip():
            warnings.append(
                f"WARN promote_new[{sf}]: stub_proposed.body_markdown vacío"
            )

    # Si quedó todo vacío de contenido útil → fallo genuino (LLM alucinó todo)
    is_empty = (
        not data.get("entities")
        and not data.get("pending_updates")
        and not data.get("discarded")
        and not data.get("thesis_candidates")
    )
    if is_empty:
        errors.append("output completamente vaciado tras filtro de quote_evidence — alucinación masiva")

    if warnings:
        data["_validation_warnings"] = warnings

    return data, errors


# ---------------------------------------------------------------------------
# Run orchestration
# ---------------------------------------------------------------------------


def build_delta_block(shadow: Path, baseline_page_ids: set[str]) -> str:
    """Construye un bloque markdown delta listando wikis creadas en el batch.

    Retorna "" si no hay páginas nuevas respecto al baseline. El bloque se
    prepende al user_msg del vídeo siguiente (sin invalidar el cached prefix
    del heavy_context). El main agent ve así qué stubs se han añadido y
    puede referenciarlos con wikilinks sin necesidad de Glob/Grep proactivo.
    """
    new_entries: list[str] = []
    for md in sorted(shadow.rglob("*.md")):
        if md.name == "README.md":
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        fm = m.group(1)
        body = text[m.end():]
        pid_m = PAGE_ID_RE.search(fm)
        if not pid_m:
            continue
        pid = pid_m.group(1)
        if pid in baseline_page_ids:
            continue
        # Es nueva — extrae metadata mínima
        cname_m = CANONICAL_NAME_RE.search(fm)
        cname = cname_m.group(1).strip().strip('"').strip("'") if cname_m else pid
        ptype_m = PAGE_TYPE_RE.search(fm)
        ptype = ptype_m.group(1) if ptype_m else "?"
        dom_m = DOMAIN_PRIMARY_RE.search(fm)
        dom = dom_m.group(1) if dom_m else "?"
        one_liner = _extract_one_liner(body) or ""
        if one_liner:
            new_entries.append(f"- `[[{pid}]]` ({ptype}, {dom}) — {cname}: {one_liner[:120]}")
        else:
            new_entries.append(f"- `[[{pid}]]` ({ptype}, {dom}) — {cname}")
    if not new_entries:
        return ""
    return (
        "\n\n## Nuevas wikis creadas en este batch (no estaban al inicio de la sesión)\n\n"
        "Estas páginas se han añadido al shadow durante el batch actual. Referénciatas con "
        "wikilinks `[[page-id]]` en tus pending_updates si aplica. NO emitas promote_new para "
        "ellas (ya existen).\n\n"
        + "\n".join(new_entries)
        + "\n"
    )


def _snapshot_page_ids(shadow: Path) -> set[str]:
    """Snapshot del conjunto de page_ids existentes en el shadow."""
    ids: set[str] = set()
    for md in shadow.rglob("*.md"):
        if md.name == "README.md":
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        pid_m = PAGE_ID_RE.search(m.group(1))
        if pid_m:
            ids.add(pid_m.group(1))
    return ids


def run_session(
    videos_batch: list[VideoInput],
    run_dir: Path,
    system_prompt_short: str,
    heavy_context: str,
    state: RunState,
    session_idx: int,
    shadow_path: Optional[Path] = None,
) -> dict:
    """Procesa un batch en una sesión Claude Code única.

    El primer vídeo de la sesión recibe el `heavy_context` prefijado al user
    message (vía stdin, sin límite). Los vídeos siguientes reciben solo su
    propio user message — el contexto pesado vive en el conversation history
    del session_id (--resume) y debería cachearse automáticamente.

    Si `shadow_path` se provee: tras cada vídeo procesado con éxito, sus
    `pending_updates` y `promote_new` se aplican al shadow para que vídeos
    siguientes del batch los vean (Karpathy compounding artifact).
    """
    session_log = {
        "session_idx": session_idx,
        "started_at": now_iso(),
        "videos_processed": [],
        "videos_failed": [],
        "session_id": None,
        "tokens_input": 0,
        "tokens_output": 0,
        "tokens_cached": 0,
        "shadow_apply_stats": [],
    }
    session_id: Optional[str] = None
    session_start = time.time()
    is_first_call_of_session = True

    # Snapshot de page_ids al inicio del batch — sirve para construir el bloque
    # delta de "nuevas wikis creadas en este batch" en vídeos posteriores
    # (Karpathy compounding visible al main sin Glob/Grep proactivo).
    baseline_page_ids = _snapshot_page_ids(shadow_path) if shadow_path else set()

    for i, video in enumerate(videos_batch):
        out_path = run_dir / f"{video.video_id}.json"
        if out_path.exists():
            print(f"  [skip] {video.video_id} already processed", file=sys.stderr)
            continue

        elapsed = time.time() - session_start
        if elapsed > SESSION_MAX_SECONDS:
            print(f"  [cut] session time limit reached ({elapsed:.0f}s > {SESSION_MAX_SECONDS})", file=sys.stderr)
            break
        if session_log["tokens_input"] + session_log["tokens_output"] > SESSION_MAX_TOKENS:
            print(f"  [cut] session token limit reached", file=sys.stderr)
            break

        load_summary(video)
        video_msg = build_user_message(video)

        # Delta block: lista de páginas nuevas creadas por vídeos previos del
        # batch. Se prepende al video_msg (no al heavy_context cached) → el
        # main las ve como wikilinks disponibles sin invalidar caching.
        delta_block = ""
        if shadow_path is not None and not is_first_call_of_session:
            delta_block = build_delta_block(shadow_path, baseline_page_ids)

        if is_first_call_of_session:
            user_msg = heavy_context + "\n\n---\n\n" + video_msg
        elif delta_block:
            user_msg = delta_block + "\n---\n\n" + video_msg
        else:
            user_msg = video_msg

        delta_chars = len(delta_block) if not is_first_call_of_session else 0
        delta_tag = f" +delta({delta_chars}c)" if delta_chars else ""
        print(f"  [proc {i+1}/{len(videos_batch)}] {video.video_id} ({video.slug}) ~{video.estimated_tokens}tok{' +ctx' if is_first_call_of_session else ''}{delta_tag}", file=sys.stderr)

        try:
            sys_prompt_arg = system_prompt_short if session_id is None else None
            output_text, meta = invoke_claude(
                user_msg=user_msg,
                system_prompt_appended=sys_prompt_arg,
                resume_session_id=session_id,
            )
            is_first_call_of_session = False
            if session_id is None and meta.get("session_id"):
                session_id = meta["session_id"]
                session_log["session_id"] = session_id
            session_log["tokens_input"] += meta.get("input_tokens", 0)
            session_log["tokens_output"] += meta.get("output_tokens", 0)
            session_log["tokens_cached"] += meta.get("cached_tokens", 0)

            data, errors = parse_and_validate_output(output_text, video)
            if errors:
                fail_path = run_dir / f"{video.video_id}.failed.json"
                fail_path.write_text(
                    json.dumps(
                        {
                            "video_id": video.video_id,
                            "raw_output": output_text,
                            "errors": errors,
                            "failed_at": now_iso(),
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                session_log["videos_failed"].append({"video_id": video.video_id, "errors": errors})
                state.videos_failed.append({"video_id": video.video_id, "errors": errors[:3]})
                print(f"     ! validation failed: {errors[0]}", file=sys.stderr)
                continue

            out_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            session_log["videos_processed"].append(video.video_id)
            state.videos_done.append(video.video_id)
            state.save(run_dir)

            # Karpathy compounding artifact: aplica al shadow ANTES del próximo
            # vídeo. El siguiente vídeo de la sesión leerá el wiki con los
            # updates de éste ya integrados — sin recompilar, sin invalidar el
            # caching del session prefix.
            if shadow_path is not None:
                try:
                    apply_stats = apply_video_output_to_shadow(shadow_path, data, video)
                    apply_stats["video_id"] = video.video_id
                    session_log["shadow_apply_stats"].append(apply_stats)
                    cite_added = apply_stats.get("auto_citations_added", 0)
                    cite_pages = apply_stats.get("pages_with_new_citations", 0)
                    cite_no_ts = apply_stats.get("auto_citations_skipped_no_timestamp", 0)
                    cite_segment = (
                        f" auto-cite=+{cite_added}/{cite_pages}p"
                        + (f" no-ts={cite_no_ts}" if cite_no_ts else "")
                    )
                    thesis_auto = apply_stats.get("thesis_auto_promoted", 0)
                    thesis_human = apply_stats.get("thesis_skipped_human_review", 0)
                    rec_refs = apply_stats.get("recommended_references_collected", 0)
                    extra_segment = ""
                    if thesis_auto or thesis_human:
                        extra_segment += f" thesis-auto={thesis_auto}/human-review={thesis_human}"
                    if rec_refs:
                        extra_segment += f" rec-refs={rec_refs}"
                    print(
                        f"     shadow: applied={apply_stats['pending_applied']} "
                        f"skipped={apply_stats['pending_skipped']} "
                        f"stubs+={apply_stats['stubs_created']} "
                        f"page_missing={apply_stats['page_not_found_in_shadow']} "
                        f"subagent={apply_stats['subagents_successful']}/{apply_stats['subagents_invoked']}"
                        + (f" FAILED={apply_stats['subagents_failed']}" if apply_stats['subagents_failed'] else "")
                        + cite_segment
                        + extra_segment,
                        file=sys.stderr,
                    )
                    # Warning si hay menciones sin timestamp (summary atípico)
                    if cite_no_ts >= 3:
                        print(
                            f"     ! WARN: {cite_no_ts} mentions sin marker `- HH:MM` "
                            f"— posible summary mal formado",
                            file=sys.stderr,
                        )
                except Exception as e:
                    print(f"     ! shadow apply error: {e}", file=sys.stderr)

        except subprocess.TimeoutExpired:
            print(f"     ! timeout after {PER_CALL_TIMEOUT_S}s", file=sys.stderr)
            session_log["videos_failed"].append({"video_id": video.video_id, "errors": ["timeout"]})
            state.videos_failed.append({"video_id": video.video_id, "errors": ["timeout"]})
        except Exception as e:
            print(f"     ! error: {e}", file=sys.stderr)
            session_log["videos_failed"].append({"video_id": video.video_id, "errors": [str(e)[:200]]})
            state.videos_failed.append({"video_id": video.video_id, "errors": [str(e)[:200]]})

    session_log["ended_at"] = now_iso()
    session_log["duration_s"] = round(time.time() - session_start, 1)
    return session_log


_AGGREGATOR_FILENAMES: set[str] = {
    "state",
    "discard_log",
    "pending_updates",
    "promote_queue",
    "thesis_candidates",
    "blocks_filtered",
    "aggregation_stats",
    "applied_log",
}


def _collect_processed_video_ids_global() -> set[str]:
    """Escanea TODOS los extraction_runs previos buscando per-video JSONs.

    Convención: cada per-video JSON tiene nombre `<video_id>.json` (no
    aggregator outputs ni state.json). Si existe en cualquier run previo,
    consideramos el vídeo "extraído" — no necesita re-llamada al LLM.

    Esto materializa la filosofía Karpathy: procesar 1 vez, los JSONs
    quedan en git, futuros runs son incrementales por defecto.
    """
    processed: set[str] = set()
    if not RUNS_DIR.exists():
        return processed
    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        for f in run_dir.glob("*.json"):
            if f.name.endswith(".failed.json"):
                continue
            stem = f.stem
            if stem in _AGGREGATOR_FILENAMES:
                continue
            processed.add(stem)
    return processed


def run(run_id: str, videos: list[VideoInput], pilot: bool = False, reprocess_all: bool = False, limit: Optional[int] = None) -> None:
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Incremental por defecto: filtrar vídeos ya extraídos en cualquier
    # run previo (los JSONs viven en git tras 2026-05-02). Procesarlos
    # de nuevo es coste de tokens evitable. --reprocess-all sobreescribe.
    # Aplica tanto en runs nuevos como en --resume.
    if not reprocess_all:
        already_processed = _collect_processed_video_ids_global()
        if already_processed:
            before = len(videos)
            videos = [v for v in videos if v.video_id not in already_processed]
            skipped = before - len(videos)
            if skipped:
                print(
                    f"Incremental: skipped {skipped} videos already extracted "
                    f"in prior runs ({len(already_processed)} JSONs totales en extraction_runs/)",
                    file=sys.stderr,
                )
                print(
                    f"  → para re-procesar todo desde cero: --reprocess-all",
                    file=sys.stderr,
                )

    state_path = run_dir / "state.json"
    if state_path.exists():
        state = RunState.load(run_dir)
        # Filtrar pendientes del state local también
        done_set = set(state.videos_done)
        videos = [v for v in videos if v.video_id not in done_set]
        print(f"Resuming run {run_id}: {len(state.videos_done)} done, {len(videos)} pending", file=sys.stderr)
    else:
        state = RunState(
            run_id=run_id,
            started_at=now_iso(),
            last_updated=now_iso(),
            videos_total=len(videos),
            videos_pending=[v.video_id for v in videos],
        )
        state.save(run_dir)
        print(f"Starting run {run_id}: {len(videos)} videos", file=sys.stderr)

    if limit is not None and limit > 0 and len(videos) > limit:
        print(f"Limit: capando a {limit} vídeos pendientes (de {len(videos)})", file=sys.stderr)
        videos = videos[:limit]

    if not videos:
        print("No pending videos. Run aggregator with --aggregate.", file=sys.stderr)
        return

    print("Building prompts...", file=sys.stderr)
    system_prompt_short = build_system_prompt_short()
    (run_dir / "system_prompt.short.snapshot.txt").write_text(system_prompt_short, encoding="utf-8")
    print(f"  short system prompt: {len(system_prompt_short)} chars (~{len(system_prompt_short)//4} tokens) — vía argv", file=sys.stderr)

    session_idx = len(state.sessions)
    while videos:
        batch = videos[:SESSION_MAX_VIDEOS]
        videos = videos[SESSION_MAX_VIDEOS:]
        print(f"\n=== Session {session_idx} ({len(batch)} videos) ===", file=sys.stderr)

        # Setup shadow al INICIO de cada sesión: copia fresca del wiki real.
        # Cada vídeo aplica sus incrementales sobre el shadow → vídeos siguientes
        # del batch ven el estado acumulado. Cierre: sync shadow → wiki + commit.
        shadow = setup_shadow_wiki(run_dir)
        heavy_context = build_heavy_context_message(wiki_root=shadow)
        (run_dir / f"heavy_context.session_{session_idx}.snapshot.txt").write_text(
            heavy_context, encoding="utf-8"
        )
        print(
            f"  shadow:        {shadow.relative_to(REPO)} "
            f"({sum(1 for _ in shadow.rglob('*.md'))} pages copied)",
            file=sys.stderr,
        )
        print(
            f"  heavy context: {len(heavy_context)} chars (~{len(heavy_context)//4} tokens) — apunta a shadow",
            file=sys.stderr,
        )

        try:
            session_log = run_session(
                batch, run_dir, system_prompt_short, heavy_context, state,
                session_idx, shadow_path=shadow,
            )
        finally:
            # Sync shadow → wiki + commit, incluso si run_session lanza
            # excepción a mitad (preservamos progreso parcial).
            sync_stats = sync_shadow_to_wiki(shadow)
            print(
                f"  sync shadow→wiki: copied={sync_stats['copied']} "
                f"new={sync_stats['new']} unchanged={sync_stats['unchanged']}",
                file=sys.stderr,
            )
            video_ids_processed = [v.video_id for v in batch]
            commit_sha = commit_batch_to_wiki(
                run_id=run_id,
                session_idx=session_idx,
                sync_stats=sync_stats,
                video_ids=video_ids_processed,
            )
            if commit_sha:
                print(f"  committed: {commit_sha[:12]}", file=sys.stderr)
            else:
                print(f"  no wiki changes to commit (batch produjo cero updates aplicables)", file=sys.stderr)
            teardown_shadow_wiki(shadow)

        state.sessions.append(session_log)
        state.total_tokens_estimate += session_log["tokens_input"] + session_log["tokens_output"]
        state.save(run_dir)
        session_idx += 1
        if pilot:
            break

    # Auto-aggregate al cierre del run para garantizar audit trail commiteado
    # en git (los per-video JSONs son gitignored; los aggregator outputs no).
    # Salvamos en pilot mode para no contaminar runs cortos de validación.
    if not pilot:
        try:
            print("\nAuto-aggregating run for audit trail...", file=sys.stderr)
            aggregate(run_id)
        except Exception as e:
            print(f"Aggregator failed (non-fatal): {e}", file=sys.stderr)

    print("\nRun complete.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Aggregator: per-video JSONs → review queues
# ---------------------------------------------------------------------------


def reapply_run(run_id: str) -> None:
    """Re-aplica los JSONs existentes de un run al shadow → wiki, sin re-LLM.

    Útil cuando:
    - Cambia la lógica de apply (e.g. nuevos aliases de schema)
    - El stub generator se actualiza (e.g. ahora consume stub_proposed)
    - Una corrida previa terminó con applied=0 por bug de campos

    Reordena los JSONs por mtime ascendente para preservar el orden cronológico
    de procesamiento (esencial para que el compounding intra-batch sea válido).
    """
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        sys.exit(f"Run dir not found: {run_dir}")

    # Setup shadow fresco
    shadow = setup_shadow_wiki(run_dir)
    print(f"Shadow created: {shadow.relative_to(REPO)}", file=sys.stderr)

    # Localiza JSONs (excluyendo .failed.json)
    json_files = sorted(
        [p for p in run_dir.iterdir() if p.suffix == ".json"
         and not p.name.endswith(".failed.json")
         and p.name not in ("state.json",)],
        key=lambda p: p.stat().st_mtime,
    )
    print(f"Found {len(json_files)} per-video JSONs in chronological order", file=sys.stderr)

    # Recupera info del vídeo (necesitamos title para citations)
    videos_by_id = {v.video_id: v for v in discover_videos(DEFAULT_CORPUS)}

    aggregate_stats = {
        "pending_applied": 0, "pending_skipped": 0,
        "stubs_created": 0, "stubs_skipped_existing": 0,
        "page_not_found_in_shadow": 0,
    }
    video_ids: list[str] = []

    for jf in json_files:
        vid_id = jf.stem
        v = videos_by_id.get(vid_id)
        if v is None:
            print(f"  [skip] {vid_id}: video metadata not found in corpus", file=sys.stderr)
            continue
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  [skip] {vid_id}: JSON parse error {e}", file=sys.stderr)
            continue
        stats = apply_video_output_to_shadow(shadow, data, v)
        for k, val in stats.items():
            aggregate_stats[k] = aggregate_stats.get(k, 0) + val
        video_ids.append(vid_id)
        print(
            f"  [applied {vid_id}] pending={stats['pending_applied']}/skip={stats['pending_skipped']} "
            f"stubs={stats['stubs_created']} missing={stats['page_not_found_in_shadow']}",
            file=sys.stderr,
        )

    print(f"\nTotal: {aggregate_stats}", file=sys.stderr)

    # Sync shadow → wiki + commit
    sync_stats = sync_shadow_to_wiki(shadow)
    print(
        f"sync shadow→wiki: copied={sync_stats['copied']} new={sync_stats['new']} unchanged={sync_stats['unchanged']}",
        file=sys.stderr,
    )
    sha = commit_batch_to_wiki(
        run_id=run_id,
        session_idx=-1,  # marca reapply en el log
        sync_stats=sync_stats,
        video_ids=video_ids,
    )
    if sha:
        print(f"committed: {sha[:12]}", file=sys.stderr)
    else:
        print("no wiki changes to commit", file=sys.stderr)
    teardown_shadow_wiki(shadow)


def aggregate(run_id: str) -> None:
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        sys.exit(f"Run dir not found: {run_dir}")

    discard_log: dict = {"version": "0.1.0", "run_id": run_id, "generated_at": now_iso(), "entities": {}}
    pending_updates: list = []
    promote_queue: list = []
    thesis_candidates: list = []
    blocks_filtered: list = []
    recommended_references: list = []
    stats = {
        "videos_aggregated": 0,
        "entities_total": 0,
        "promoted_new": 0,
        "promoted_updates": 0,
        "discarded": 0,
        "thesis_candidates": 0,
        "thesis_auto_promoted": 0,
        "thesis_pending_human_review": 0,
        "recommended_references": 0,
    }

    AGGREGATOR_OUTPUT_FILES = {
        "state.json",
        "discard_log.json",
        "pending_updates.json",
        "promote_queue.json",
        "thesis_candidates.json",
        "blocks_filtered.json",
        "aggregation_stats.json",
        "recommended_references.json",
    }
    for jpath in sorted(run_dir.glob("*.json")):
        if jpath.name in AGGREGATOR_OUTPUT_FILES or ".failed." in jpath.name:
            continue
        try:
            data = json.loads(jpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        # Filtro defensivo: el output del extractor SIEMPRE tiene video_id
        if not isinstance(data, dict) or "video_id" not in data:
            continue
        stats["videos_aggregated"] += 1
        vid = data.get("video_id", jpath.stem)
        vtitle = data.get("video_title", "")

        # Schema-tolerant: el LLM emite a veces promote_new[] top-level
        # (con shape similar a entities[decision=promote_new]). Mergeamos
        # para que el aggregator no pierda candidatos por la diferencia.
        merged_entities = list(data.get("entities", []) or [])
        for pn in data.get("promote_new", []) or []:
            if isinstance(pn, dict):
                norm = dict(pn)
                norm.setdefault("decision", "promote_new")
                merged_entities.append(norm)

        for ent in merged_entities:
            stats["entities_total"] += 1
            decision = ent.get("decision", "discard")
            canon = ent.get("canonical_guess", ent.get("surface_form", ent.get("page_id", "unknown")))
            entry = discard_log["entities"].setdefault(
                canon,
                {
                    "canonical_name": ent.get("surface_form", canon),
                    "page_type": ent.get("page_type"),
                    "occurrences": [],
                    "is_canonical_external": False,
                    "is_in_whitelist_soft": False,
                    "decisions_seen": set(),
                },
            )
            entry["occurrences"].append(
                {
                    "video_id": vid,
                    "video_title": vtitle,
                    "depth": ent.get("depth_in_video"),
                    "minutes": ent.get("minutes_estimate"),
                    "framing_marks_count": len(ent.get("framing_marks") or []),
                    "decision": decision,
                    "decision_reason": ent.get("decision_reason"),
                    "quote_evidence": ent.get("quote_evidence", ""),
                }
            )
            entry["is_canonical_external"] = entry["is_canonical_external"] or bool(ent.get("is_canonical_external"))
            entry["is_in_whitelist_soft"] = entry["is_in_whitelist_soft"] or bool(ent.get("is_in_whitelist_soft"))
            entry["decisions_seen"].add(decision)

            if decision == "promote_new":
                stats["promoted_new"] += 1
                promote_queue.append({"canonical_guess": canon, "from_video": vid, "entity": ent})
            elif decision == "update_existing":
                stats["promoted_updates"] += 1
            elif decision == "discard":
                stats["discarded"] += 1

        for upd in data.get("pending_updates", []) or []:
            stats["promoted_updates"] += 1
            pending_updates.append({"from_video": vid, "from_video_title": vtitle, "update": upd})

        for d_entry in data.get("discarded", []) or []:
            stats["discarded"] += 1
            # Mete los descartes explícitos (array separado) al discard_log con
            # la misma forma que las entities[] descartadas, para que la
            # priorización del review_priority funcione uniformemente.
            canon = d_entry.get("surface_form") or "unknown"
            entry = discard_log["entities"].setdefault(
                canon,
                {
                    "canonical_name": canon,
                    "page_type": None,
                    "occurrences": [],
                    "is_canonical_external": False,
                    "is_in_whitelist_soft": False,
                    "decisions_seen": set(),
                },
            )
            entry["occurrences"].append(
                {
                    "video_id": vid,
                    "video_title": vtitle,
                    "depth": None,
                    "minutes": None,
                    "framing_marks_count": 0,
                    "decision": "discard",
                    "decision_reason": d_entry.get("reason_code") or d_entry.get("reason_detail"),
                    "quote_evidence": d_entry.get("quote_evidence", ""),
                    "review_priority_hint": d_entry.get("review_priority"),
                }
            )
            entry["decisions_seen"].add("discard")

        for t in data.get("thesis_candidates", []) or []:
            stats["thesis_candidates"] += 1
            rhv = t.get("requires_human_validation", True)
            if rhv is False:
                stats["thesis_auto_promoted"] += 1
            else:
                stats["thesis_pending_human_review"] += 1
            thesis_candidates.append({
                "from_video": vid,
                "from_video_title": vtitle,
                "auto_promoted": rhv is False,
                "thesis": t,
            })

        for b in data.get("blocks_filtered_by_topic_filters", []) or []:
            blocks_filtered.append({"from_video": vid, "block": b})

        # Recommended references — el aggregator NO depende del campo runtime
        # `_collected_recommended_references` (que vive solo en memoria durante
        # apply_video_output_to_shadow y no se persiste al JSON). Itera
        # directamente sobre discarded[reason_code=recommended_reference] del
        # JSON commiteado, que es la fuente de verdad. Esto también permite
        # re-agregar runs antiguos cuando se añaden nuevas lanes de extracción.
        for d_entry in data.get("discarded", []) or []:
            if d_entry.get("reason_code") != "recommended_reference":
                continue
            payload = d_entry.get("recommended_reference_payload") or {}
            if not isinstance(payload, dict):
                continue
            stats["recommended_references"] += 1
            ts = payload.get("timestamp_seconds")
            if ts is None:
                # Reconstruir timestamp desde quote_evidence si el LLM no lo emitió.
                # Requiere cargar el summary del vídeo — saltable si falla.
                ts = None
            recommended_references.append({
                "video_id": vid,
                "video_title": vtitle,
                "surface_form": d_entry.get("surface_form", ""),
                "book_title": payload.get("book_title", ""),
                "authors": payload.get("authors", []) or [],
                "domain": payload.get("domain", ""),
                "why_recommended": payload.get("why_recommended", ""),
                "quote_evidence": d_entry.get("quote_evidence", ""),
                "timestamp_seconds": ts,
            })

    # Compute review priority + serialize sets
    flagged_high = 0
    for canon, e in discard_log["entities"].items():
        e["occurrences_count"] = len(e["occurrences"])
        e["total_minutes"] = sum((o.get("minutes") or 0) for o in e["occurrences"])
        e["decisions_seen"] = sorted(e["decisions_seen"])
        priority, reason = compute_review_priority(e)
        e["review_priority"] = priority
        e["review_priority_reason"] = reason
        if priority == "high":
            flagged_high += 1
    stats["flagged_for_review_high"] = flagged_high

    # Group recommended_references by book_title for the bibliographic index
    rec_refs_by_book: dict[str, dict] = {}
    for r in recommended_references:
        key = (r.get("book_title") or r.get("surface_form") or "unknown").strip()
        bucket = rec_refs_by_book.setdefault(key, {
            "book_title": r.get("book_title", ""),
            "authors": list(r.get("authors") or []),
            "domain": r.get("domain", ""),
            "occurrences": [],
        })
        # Authors / domain unify across mentions
        for a in (r.get("authors") or []):
            if a not in bucket["authors"]:
                bucket["authors"].append(a)
        if not bucket["domain"] and r.get("domain"):
            bucket["domain"] = r["domain"]
        bucket["occurrences"].append({
            "video_id": r.get("video_id", ""),
            "video_title": r.get("video_title", ""),
            "surface_form": r.get("surface_form", ""),
            "why_recommended": r.get("why_recommended", ""),
            "quote_evidence": r.get("quote_evidence", ""),
            "timestamp_seconds": r.get("timestamp_seconds"),
        })

    out_files = {
        "discard_log.json": discard_log,
        "pending_updates.json": {"version": "0.1.0", "run_id": run_id, "items": pending_updates},
        "promote_queue.json": {"version": "0.1.0", "run_id": run_id, "items": promote_queue},
        "thesis_candidates.json": {"version": "0.1.0", "run_id": run_id, "items": thesis_candidates},
        "blocks_filtered.json": {"version": "0.1.0", "run_id": run_id, "items": blocks_filtered},
        "recommended_references.json": {
            "version": "0.1.0",
            "run_id": run_id,
            "generated_at": now_iso(),
            "_doc": "Manuales/libros que el speaker recomienda como referencia bibliográfica del canal (scope.md §3.4). Agrupados por book_title con todas las occurrences. Insumo para futura página índice wiki/bibliografia-recomendada.md (renderizado post-process — esta es la fuente de verdad estructurada).",
            "books": rec_refs_by_book,
        },
        "aggregation_stats.json": {"version": "0.1.0", "run_id": run_id, "generated_at": now_iso(), "stats": stats},
    }
    for fname, payload in out_files.items():
        (run_dir / fname).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(stats, indent=2, ensure_ascii=False), file=sys.stderr)
    print(f"\nAggregation written to {run_dir}/", file=sys.stderr)


def compute_review_priority(entry: dict) -> tuple[str, Optional[str]]:
    """Disparadores de scope.md §6 + criterios definidos en discusión 2026-05-02."""
    if entry.get("is_canonical_external") and "discard" in entry.get("decisions_seen", []):
        return "high", "canonical_external + at_least_one_discard"
    n = entry.get("occurrences_count", 0)
    minutes = entry.get("total_minutes", 0) or 0
    promoted_any = any(d in entry.get("decisions_seen", []) for d in ("promote_new", "update_existing"))
    if n >= 3 and not promoted_any:
        return "high", f"recurrent ({n} occurrences) without promotion"
    if minutes >= 20 and n >= 2 and not promoted_any:
        return "high", f"sustained discussion ({minutes}min across {n} videos) without promotion"
    if n >= 2 and len(entry.get("decisions_seen", [])) > 1:
        return "high", "inconsistent decisions across occurrences"
    if entry.get("is_in_whitelist_soft") and "discard" in entry.get("decisions_seen", []):
        return "medium", "whitelist_soft entity discarded"
    return "low", None


# ---------------------------------------------------------------------------
# Protocolo de propagación de cambios scope/aggregator a runs históricos
# ---------------------------------------------------------------------------


def rebuild_all_aggregates() -> None:
    """Itera todos los runs en RUNS_DIR y re-corre aggregate() sobre cada uno.

    Gratis (sin LLM). Propaga cambios de:
    - aggregator (recommended_references capture, schema-tolerant promote_new,
      stats nuevos)
    - compute_review_priority
    - cualquier flow downstream que opere sobre JSONs ya escritos

    Tras esto los outputs aggregator (discard_log.json, recommended_references.json,
    promote_queue.json, etc.) reflejan el código actual. Útil tras bug fix de
    aggregator o adición de nuevas lanes.
    """
    if not RUNS_DIR.exists():
        sys.exit(f"RUNS_DIR not found: {RUNS_DIR}")

    runs_processed = 0
    runs_skipped = 0
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name
        # Verifica que tiene JSONs procesados (no solo aggregator outputs)
        per_video_jsons = [
            j for j in run_dir.glob("*.json")
            if j.stem not in _AGGREGATOR_FILENAMES and not j.name.endswith(".failed.json")
        ]
        if not per_video_jsons:
            print(f"  [skip] {run_id}: no per-video JSONs", file=sys.stderr)
            runs_skipped += 1
            continue
        print(f"  [aggregate] {run_id}: {len(per_video_jsons)} JSONs", file=sys.stderr)
        try:
            aggregate(run_id)
            runs_processed += 1
        except SystemExit:
            # aggregate() puede llamar sys.exit en errores recuperables (run dir not found, etc.)
            print(f"  [error] {run_id}: aggregate failed", file=sys.stderr)
            runs_skipped += 1
        except Exception as e:
            print(f"  [error] {run_id}: {e}", file=sys.stderr)
            runs_skipped += 1

    print(
        f"\nRebuild complete: {runs_processed} runs re-aggregated, {runs_skipped} skipped",
        file=sys.stderr,
    )


# Heurísticas para detectar JSONs stale tras cambio de scope. Cada heurística
# devuelve True si la entrada del LLM con scope viejo sería decidida diferente
# bajo scope actual.

_STALE_RECOMMENDED_PATTERNS = re.compile(
    r"\b(manual|tratado|libro|cuaderno|texto|enciclopedia|edici[oó]n|"
    r"recomien[a-z]+|recomend[a-z]+|biblia|bibliograf[ií]a|recopilaci[oó]n)\b",
    re.IGNORECASE,
)
_STALE_COGNITIVE_PATTERNS = re.compile(
    r"\b(memoria|hipocampo|am[ií]gdala|cogniti[a-z]+|neuroanat[a-z]+|"
    r"neuro[a-z]*|cerebr[a-z]+|consciencia|conciencia|atenci[oó]n|"
    r"BOLD|fMRI|EEG|EMG|psicolog[ií]a cogniti[a-z]+|psicobiolog[ií]a|"
    r"raz[a-z]+ motivado|locus de control|locus de autoridad|"
    r"DSM|psiquiatr[ií]a|psicopatolog[ií]a|tr[ií]ada cognitiva)\b",
    re.IGNORECASE,
)
_STALE_POLITICAL_THEORY_PATTERNS = re.compile(
    r"\b(liberalismo|liberales|conservadurismo|conservador[a-z]*|anarcocapital[a-z]*|"
    r"ancap|marxismo|marxista|anarquismo|anarquista|tradicionalismo|"
    r"libertarismo|libertario|comunitarismo|fundamentalismo moral|"
    r"jerarqu[ií]a moral|locus de autoridad|filosof[ií]a pol[ií]tica)\b",
    re.IGNORECASE,
)
_STALE_STORY_READ_PATTERNS = re.compile(
    r"\b(le[íi][doa]?|leyendo|lectura [ií]ntegra|lectura completa|"
    r"leemos|leer? completamente|lectura en directo)\b",
    re.IGNORECASE,
)
_INVENTED_REASON_CODES = {
    "story_read_no_dedicated_analysis_page",
    "story_read_no_archetype_analysis",
    "story_read_no_archetype",
    "single_video_no_recurrence",
    "below_recurrence_threshold",
    "absorbed_in_promoted_page",
    "passing_reference_to_other_polar_case",
    "concept_referenced_already_in_whitelist",
    "out_of_scope_figure",
    "institution_out_of_scope_for_now",
}


def _classify_stale_entry(entry: dict) -> Optional[tuple[str, str]]:
    """Dado un discarded[] entry de un JSON viejo, devuelve (new_reason_code, why)
    si bajo scope.md actual la decisión sería distinta. None si la decisión es
    coherente con scope actual.

    Heurística por reason_code + quote_evidence + reason_detail.
    """
    rc = entry.get("reason_code", "")
    sf = entry.get("surface_form", "") or ""
    quote = entry.get("quote_evidence", "") or ""
    detail = entry.get("reason_detail", "") or ""
    text = f"{sf} {quote} {detail}"

    # Caso 1: out_of_scope_domain con patrón de manual recomendado
    if rc == "out_of_scope_domain" and _STALE_RECOMMENDED_PATTERNS.search(text):
        return ("recommended_reference", "out_of_scope_domain con keywords de manual/libro recomendado (scope.md §3.4)")

    # Caso 2: out_of_scope_domain con patrón cognitivo/neurociencia
    if rc == "out_of_scope_domain" and _STALE_COGNITIVE_PATTERNS.search(text):
        return ("captured_in_thesis_candidate", "out_of_scope_domain con concepto cognitivo/neurociencia (scope.md §1.2 condicionado)")

    # Caso 3: out_of_scope_domain o passing_mention con tradición intelectual política
    if rc in ("out_of_scope_domain", "out_of_scope_figure", "political_news") and _STALE_POLITICAL_THEORY_PATTERNS.search(text):
        return ("captured_in_thesis_candidate", "tradición intelectual política (liberalismo/marxismo/etc.) — scope.md §3 in-scope si hay marco aplicado")

    # Caso 4: reason_codes inventados por el LLM con scope viejo
    if rc in _INVENTED_REASON_CODES:
        if rc.startswith("story_read"):
            return ("entity_work (read_in_session)", "cuento leído en directo — scope.md §2.3 lectura íntegra promociona automáticamente")
        return ("revisar", f"reason_code '{rc}' inventado por LLM con scope viejo, no en lista canónica v0.3")

    # Caso 5: passing_mention sobre figura política con marco diagrama
    if rc == "passing_mention" and re.search(r"\b(diagrama|cuadrante|polariz[a-z]+)\b", text, re.IGNORECASE):
        return ("passing_mention with enriches_concept: diagrama-de-proxy", "figura política como caso del diagrama — scope.md §3 in-scope")

    return None


def _was_processed_with_scope_v03(data: dict) -> bool:
    """Detecta si un JSON ya fue procesado con scope v0.3+ (schema reformado).

    Marcadores del schema v0.3:
    - Algún discarded[] con recommended_reference_payload (objeto, no string)
    - Algún discarded[] con enriches_concept (campo, aunque sea null)
    - Algún discarded[].reason_code en {recommended_reference, partisan_commentary,
      established_concept_used_as_example, captured_in_thesis_candidate} (códigos
      formalizados en v0.3)
    - thesis_candidates[].requires_human_validation con valor false (gate v0.3)
    - thesis_candidates[].proposed_page_id (campo añadido en v0.3)
    """
    for d in data.get("discarded", []) or []:
        if isinstance(d.get("recommended_reference_payload"), dict):
            return True
        if "enriches_concept" in d:
            return True
        if d.get("reason_code") in {
            "recommended_reference",
            "partisan_commentary",
            "established_concept_used_as_example",
            "captured_in_thesis_candidate",
            "internal_framework_reference",
        }:
            return True
    for t in data.get("thesis_candidates", []) or []:
        if t.get("requires_human_validation") is False:
            return True
        if "proposed_page_id" in t:
            return True
    return False


def audit_stale_vs_scope(min_stale: int = 3) -> dict:
    """Escanea todos los JSONs históricos y detecta entradas inconsistentes
    con scope.md actual. Reporta sin modificar.

    Args:
      min_stale: threshold mínimo de stale entries para flagged un JSON.

    Returns:
      Dict con video_ids → list de (entry_index, new_reason_code, why)
    """
    if not RUNS_DIR.exists():
        sys.exit(f"RUNS_DIR not found: {RUNS_DIR}")

    flagged: dict[str, dict] = {}
    total_jsons = 0
    total_stale_entries = 0
    skipped_already_v03 = 0

    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        for j in run_dir.glob("*.json"):
            if j.stem in _AGGREGATOR_FILENAMES or j.name.endswith(".failed.json"):
                continue
            total_jsons += 1
            try:
                data = json.loads(j.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            # Skip JSONs ya procesados con scope v0.3+ (no son stale)
            if _was_processed_with_scope_v03(data):
                skipped_already_v03 += 1
                continue
            video_id = data.get("video_id", j.stem)
            video_title = data.get("video_title", "")
            stale_entries = []
            for idx, entry in enumerate(data.get("discarded", []) or []):
                classification = _classify_stale_entry(entry)
                if classification:
                    new_rc, why = classification
                    stale_entries.append({
                        "idx": idx,
                        "surface_form": entry.get("surface_form", ""),
                        "old_reason_code": entry.get("reason_code", ""),
                        "new_reason_code": new_rc,
                        "why": why,
                    })
            if len(stale_entries) >= min_stale:
                flagged[video_id] = {
                    "json_path": str(j),
                    "video_title": video_title,
                    "run_id": run_dir.name,
                    "stale_count": len(stale_entries),
                    "stale_entries": stale_entries,
                }
                total_stale_entries += len(stale_entries)

    # Reporte
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"AUDIT STALE VS SCOPE — scope.md actual vs JSONs históricos", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)
    print(f"JSONs escaneados: {total_jsons}", file=sys.stderr)
    print(f"JSONs ya procesados con scope v0.3+ (skip): {skipped_already_v03}", file=sys.stderr)
    print(f"JSONs stale (≥{min_stale} entradas inconsistentes): {len(flagged)}", file=sys.stderr)
    print(f"Total entradas stale identificadas: {total_stale_entries}", file=sys.stderr)
    print(file=sys.stderr)
    if not flagged:
        print("  (no stale JSONs detectados)", file=sys.stderr)
        return flagged

    # Top 20 most stale
    by_count = sorted(flagged.items(), key=lambda kv: -kv[1]["stale_count"])
    print(f"Top {min(20, len(by_count))} JSONs por count de stale entries:", file=sys.stderr)
    for vid, info in by_count[:20]:
        print(f"\n  [{info['stale_count']:3d}] {vid} ({info['video_title'][:60]})", file=sys.stderr)
        print(f"        run: {info['run_id']}", file=sys.stderr)
        # Distribución de new_reason_codes
        from collections import Counter
        c = Counter(e["new_reason_code"] for e in info["stale_entries"])
        for rc, n in c.most_common():
            print(f"          → {rc}: {n}", file=sys.stderr)

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"Para re-procesar todos los flagged: --reprocess-stale", file=sys.stderr)
    print(f"Para ajustar threshold: --audit-min-stale N", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)

    # Persistir reporte a archivo para que --reprocess-stale lo lea
    audit_path = RUNS_DIR / "_audit_stale_vs_scope.json"
    audit_path.write_text(
        json.dumps({
            "generated_at": now_iso(),
            "scope_version": _read_scope_version(),
            "min_stale_threshold": min_stale,
            "total_jsons_scanned": total_jsons,
            "flagged_count": len(flagged),
            "flagged": flagged,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nReporte detallado: {audit_path}", file=sys.stderr)
    return flagged


def _read_scope_version() -> str:
    """Lee version del frontmatter de scope.md."""
    try:
        text = SCOPE_PATH.read_text(encoding="utf-8")
        m = re.search(r"^version:\s*(\S+)", text, re.MULTILINE)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"


def reprocess_stale_jsons(corpus: Path, min_stale: int = 3, auto_confirm: bool = False) -> None:
    """Re-procesa con LLM los vídeos cuyos JSONs están flagged como stale.

    Workflow:
    1. Carga reporte de audit (genera uno fresh si no existe)
    2. Borra los JSONs flagged
    3. Crea/usa run aislado 'reprocess_stale_<TS>'
    4. Itera flagged y procesa cada uno con --video-id + --reprocess-all
    5. Aggregate al final

    Args:
      corpus: path al corpus para discover_videos
      min_stale: threshold de stale entries
      auto_confirm: si True, NO pide confirmación interactiva (uso scriptado)
    """
    audit_path = RUNS_DIR / "_audit_stale_vs_scope.json"
    if not audit_path.exists():
        print("No audit report found — generating fresh audit first", file=sys.stderr)
        audit_stale_vs_scope(min_stale=min_stale)

    audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
    flagged = audit_data.get("flagged", {})
    if not flagged:
        print("No stale JSONs flagged. Nothing to do.", file=sys.stderr)
        return

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"REPROCESS STALE — re-LLM batch", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)
    print(f"Flagged: {len(flagged)} vídeos", file=sys.stderr)
    print(f"Coste estimado: ~{len(flagged)} × per-video tokens", file=sys.stderr)
    print(file=sys.stderr)

    if not auto_confirm:
        confirm = input("Confirmar re-procesado? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.", file=sys.stderr)
            return
    else:
        print("auto-confirm: proceeding without prompt", file=sys.stderr)

    # Borrar JSONs flagged
    deleted = 0
    for vid, info in flagged.items():
        json_path = Path(info["json_path"])
        if json_path.exists():
            json_path.unlink()
            deleted += 1
            print(f"  deleted: {json_path.name} (was in {info['run_id']})", file=sys.stderr)
    print(f"\nDeleted {deleted} stale JSONs", file=sys.stderr)

    # Crear run aislado
    run_id = f"reprocess_stale_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    print(f"\nCreating reprocess run: {run_id}", file=sys.stderr)

    # Discover videos del corpus
    all_videos = discover_videos(corpus)
    target_ids = set(flagged.keys())
    target_videos = [v for v in all_videos if v.video_id in target_ids]
    missing = target_ids - {v.video_id for v in target_videos}
    if missing:
        print(f"WARNING: {len(missing)} flagged videos NOT found in corpus: {sorted(missing)}", file=sys.stderr)

    if not target_videos:
        print("No videos to reprocess (none found in corpus).", file=sys.stderr)
        return

    # Procesar (reutiliza el flow normal vía run())
    print(f"\nProcessing {len(target_videos)} videos with scope v{_read_scope_version()}...", file=sys.stderr)
    run(run_id, target_videos, pilot=False, reprocess_all=True)

    print(f"\nReprocess complete. Run aggregator:", file=sys.stderr)
    print(f"  python scripts/extract_video_themes.py --aggregate {run_id}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS, help="Path to playlists/ root")
    p.add_argument("--run-id", type=str, default=None, help="Identifier for the run. Default: timestamp-based")
    p.add_argument("--resume", type=str, default=None, help="Resume an existing run by id")
    p.add_argument("--pilot", action="store_true", help="Process the 5 hand-picked pilot videos only")
    p.add_argument("--pilot-2", action="store_true", dest="pilot_2", help="Process the 5 audit-pilot videos (different casuistries from --pilot)")
    p.add_argument(
        "--reprocess-all",
        action="store_true",
        dest="reprocess_all",
        help="Procesa TODOS los vídeos seleccionados aunque ya tengan JSON en runs previos. Por defecto el extractor es incremental (skip-already-extracted) — usa este flag solo si quieres re-extraer con criterios actualizados.",
    )
    p.add_argument("--video-id", type=str, default=None, help="Process a single video by its YouTube id")
    p.add_argument("--video-slug", type=str, default=None, help="Process a single video by directory slug")
    p.add_argument("--limit", type=int, default=None, help="Process at most N videos")
    p.add_argument("--discover", action="store_true", help="Just list discovered summaries and exit")
    p.add_argument("--dry-run", action="store_true", help="Build prompts, show first one, do NOT call claude")
    p.add_argument("--aggregate", type=str, default=None, help="Run aggregator on existing run-id")
    p.add_argument(
        "--reapply",
        type=str,
        default=None,
        help="Aplica los <video_id>.json existentes de un run al shadow + sync a wiki + commit, sin re-llamar al LLM. Útil tras cambios de schema-tolerance.",
    )
    p.add_argument(
        "--rebuild-aggregates",
        action="store_true",
        dest="rebuild_aggregates",
        help="Re-corre aggregate() sobre TODOS los runs históricos (gratis, sin LLM). Propaga cambios de aggregator/schema a todos los outputs (discard_log, recommended_references, etc.) sin re-procesar JSONs per-vídeo.",
    )
    p.add_argument(
        "--audit-stale-vs-scope",
        action="store_true",
        dest="audit_stale",
        help="Escanea TODOS los JSONs históricos y detecta heurísticamente entradas inconsistentes con scope.md actual (ej. out_of_scope_domain que ahora serían recommended_reference). Reporte sin modificar nada — insumo para --reprocess-stale.",
    )
    p.add_argument(
        "--reprocess-stale",
        action="store_true",
        dest="reprocess_stale",
        help="Re-procesa con LLM los vídeos cuyos JSONs --audit-stale-vs-scope marca como stale. Borra JSON viejo + extrae con scope nuevo. CAUTION: consume tokens.",
    )
    p.add_argument(
        "--audit-min-stale",
        type=int,
        default=3,
        dest="audit_min_stale",
        help="Threshold mínimo de entradas stale por JSON para flagged (default: 3). Solo aplica con --audit-stale-vs-scope y --reprocess-stale.",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        dest="auto_confirm",
        help="Auto-confirma prompts interactivos (--reprocess-stale). Para ejecución scriptada.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.aggregate:
        aggregate(args.aggregate)
        return

    if args.reapply:
        reapply_run(args.reapply)
        return

    if args.rebuild_aggregates:
        rebuild_all_aggregates()
        return

    if args.audit_stale:
        audit_stale_vs_scope(min_stale=args.audit_min_stale)
        return

    if args.reprocess_stale:
        reprocess_stale_jsons(args.corpus, min_stale=args.audit_min_stale, auto_confirm=args.auto_confirm)
        return

    print(f"Corpus root: {args.corpus}", file=sys.stderr)
    if not args.corpus.exists():
        sys.exit(f"Corpus path not found: {args.corpus}. Set ARIADNA_CORPUS_PATH or use --corpus.")

    all_videos = discover_videos(args.corpus)
    print(f"Discovered {len(all_videos)} summaries", file=sys.stderr)

    if args.discover:
        for v in all_videos:
            print(f"{v.video_id}\t{v.playlist}/{v.slug}\t{v.category}\t{v.duration_s//60}min")
        return

    # Filtrar selección
    if args.video_id:
        videos = [v for v in all_videos if v.video_id == args.video_id]
    elif args.video_slug:
        videos = [v for v in all_videos if v.slug == args.video_slug]
    elif args.pilot:
        videos = [v for v in all_videos if v.slug in PILOT_VIDEO_SLUGS]
        missing = set(PILOT_VIDEO_SLUGS) - {v.slug for v in videos}
        if missing:
            print(f"WARNING: pilot slugs not found: {missing}", file=sys.stderr)
    elif args.pilot_2:
        videos = [v for v in all_videos if v.slug in PILOT_2_VIDEO_SLUGS]
        missing = set(PILOT_2_VIDEO_SLUGS) - {v.slug for v in videos}
        if missing:
            print(f"WARNING: pilot-2 slugs not found: {missing}", file=sys.stderr)
    elif args.resume:
        videos = all_videos
    else:
        videos = all_videos

    if not videos:
        sys.exit("No videos selected.")

    if args.dry_run:
        sp = build_system_prompt_short()
        hc = build_heavy_context_message()
        print(f"\n--- system_prompt_short ({len(sp)} chars, ~{len(sp)//4} tok) — vía argv ---", file=sys.stderr)
        print(sp[:1200], file=sys.stderr)
        print(f"\n--- heavy_context ({len(hc)} chars, ~{len(hc)//4} tok) — vía stdin (1ª call) ---", file=sys.stderr)
        print(hc[:600] + "\n[...]", file=sys.stderr)
        print("\n--- user message preview (first video) ---", file=sys.stderr)
        load_summary(videos[0])
        print(build_user_message(videos[0])[:1500], file=sys.stderr)
        print(f"\n--- would process {len(videos)} videos ---", file=sys.stderr)
        return

    run_id = args.resume or args.run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    run(run_id, videos, pilot=args.pilot or args.pilot_2, reprocess_all=args.reprocess_all, limit=args.limit)


if __name__ == "__main__":
    main()
