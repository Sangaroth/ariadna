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

SESSION_MAX_VIDEOS = 22
SESSION_MAX_SECONDS = 50 * 60
SESSION_MAX_TOKENS = 500_000
PER_CALL_TIMEOUT_S = 600

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

CLAUDE_MODEL = "claude-opus-4-7"


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
      "requires_human_validation": true,
      "rationale": "string — por qué pasa los criterios de §2.4.1 del scope.md"
    }
  ],

  "discarded": [
    {
      "surface_form": "string",
      "reason_code": "topic_filter | passing_mention | out_of_scope_domain | meta_canal | promo | political_news | personal_anecdote | unverifiable",
      "reason_detail": "string — específico",
      "quote_evidence": "string — cita literal del summary",
      "review_priority": "low | medium | high",
      "review_priority_reason": "string|null — si high, por qué"
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

6. **Decisión `update_existing` requiere haber LEÍDO el cuerpo completo de la página existente** vía tool Read sobre el file_path del índice. Sin Read previo NO emites pending_updates a esa página.

7. **`thesis_candidates` requiere ≥2 señales de §2.4.1** (no basta una sola). Si solo hay una, el contenido va a `entities[]` con `page_type: concept` o como `pending_updates` a una página existente.

8. **`is_canonical_external` debe matchear exactamente el campo `auto_promote: true` del whitelist** que recibes. No interpretes laxamente.

9. **Out-of-scope (scope.md §3) → siempre `discard`** con reason_code apropiado. No promover ni siquiera con mentions_index.

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


def build_wiki_index() -> str:
    """Índice slim del wiki — 1 entrada por página, ~150-250 chars cada una.

    Patrón Karpathy: el extractor ve el índice, decide qué páginas son
    relevantes para el summary actual, y usa la tool Read sobre `file_path`
    para fetchear el contenido completo solo de las páginas que va a tocar.

    Esto sustituye la inyección del wiki entero (~43K tok → ~3-5K tok) y
    escala linealmente con páginas tocadas, no con páginas totales.
    """
    entries: list[str] = []
    for md in sorted(WIKI.rglob("*.md")):
        if md.name == "README.md":
            continue
        rel = md.relative_to(REPO)
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


def build_heavy_context_message() -> str:
    """Primer mensaje de usuario de cada sesión: ~10-15K tokens.

    Patrón Karpathy "LLM Wiki": el contexto pesado es un INDEX slim del wiki
    (no los cuerpos completos). El extractor usa la tool Read sobre el
    `file_path` indicado para drillar en páginas relevantes al summary.
    Esto reduce ~43K → ~10K en el prefix, escala lineal con pages tocadas.
    """
    index = build_wiki_index()
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
# Invocación de Claude Code headless
# ---------------------------------------------------------------------------


def invoke_claude(
    user_msg: str,
    system_prompt_appended: Optional[str],
    resume_session_id: Optional[str],
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
    cmd: list[str] = ["claude", "-p", "--model", CLAUDE_MODEL]
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


def parse_and_validate_output(raw: str, video: VideoInput) -> tuple[Optional[dict], list[str]]:
    """Devuelve (parsed_dict, errors). errors vacío = OK."""
    errors: list[str] = []
    text = raw.strip()
    # Tolerar code fences accidentales
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        errors.append(f"JSON parse failed: {e}")
        return None, errors

    # Verificación de quote_evidence literal (regla dura #1)
    summary = video.summary_text

    def check_literal(quote: str, where: str) -> None:
        if quote and quote not in summary:
            errors.append(f"quote_evidence not literal in summary @ {where}: {quote[:80]!r}")

    for ent in data.get("entities", []) or []:
        check_literal(ent.get("quote_evidence", ""), f"entities[{ent.get('canonical_guess','?')}]")
        for fm in ent.get("framing_marks", []) or []:
            check_literal(fm.get("quote_evidence", ""), f"entities.framing_marks")
    for d in data.get("discarded", []) or []:
        check_literal(d.get("quote_evidence", ""), f"discarded[{d.get('surface_form','?')}]")
    for t in data.get("thesis_candidates", []) or []:
        for sm in t.get("speaker_authorship_marks", []) or []:
            check_literal(sm.get("quote_evidence", ""), f"thesis.speaker_authorship_marks")

    return data, errors


# ---------------------------------------------------------------------------
# Run orchestration
# ---------------------------------------------------------------------------


def run_session(
    videos_batch: list[VideoInput],
    run_dir: Path,
    system_prompt_short: str,
    heavy_context: str,
    state: RunState,
    session_idx: int,
) -> dict:
    """Procesa un batch en una sesión Claude Code única.

    El primer vídeo de la sesión recibe el `heavy_context` prefijado al user
    message (vía stdin, sin límite). Los vídeos siguientes reciben solo su
    propio user message — el contexto pesado vive en el conversation history
    del session_id (--resume) y debería cachearse automáticamente.
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
    }
    session_id: Optional[str] = None
    session_start = time.time()
    is_first_call_of_session = True

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
        if is_first_call_of_session:
            user_msg = heavy_context + "\n\n---\n\n" + video_msg
        else:
            user_msg = video_msg

        print(f"  [proc {i+1}/{len(videos_batch)}] {video.video_id} ({video.slug}) ~{video.estimated_tokens}tok{' +ctx' if is_first_call_of_session else ''}", file=sys.stderr)

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


def run(run_id: str, videos: list[VideoInput], pilot: bool = False) -> None:
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    state_path = run_dir / "state.json"
    if state_path.exists():
        state = RunState.load(run_dir)
        # Filtrar pendientes
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

    if not videos:
        print("No pending videos. Run aggregator with --aggregate.", file=sys.stderr)
        return

    print("Building prompts...", file=sys.stderr)
    system_prompt_short = build_system_prompt_short()
    heavy_context = build_heavy_context_message()
    (run_dir / "system_prompt.short.snapshot.txt").write_text(system_prompt_short, encoding="utf-8")
    (run_dir / "heavy_context.snapshot.txt").write_text(heavy_context, encoding="utf-8")
    print(f"  short system prompt: {len(system_prompt_short)} chars (~{len(system_prompt_short)//4} tokens) — vía argv", file=sys.stderr)
    print(f"  heavy context:       {len(heavy_context)} chars (~{len(heavy_context)//4} tokens) — vía stdin (1ª llamada de sesión)", file=sys.stderr)

    session_idx = len(state.sessions)
    while videos:
        batch = videos[:SESSION_MAX_VIDEOS]
        videos = videos[SESSION_MAX_VIDEOS:]
        print(f"\n=== Session {session_idx} ({len(batch)} videos) ===", file=sys.stderr)
        session_log = run_session(batch, run_dir, system_prompt_short, heavy_context, state, session_idx)
        state.sessions.append(session_log)
        state.total_tokens_estimate += session_log["tokens_input"] + session_log["tokens_output"]
        state.save(run_dir)
        session_idx += 1
        if pilot:
            break

    print("\nRun complete. Run aggregator: --aggregate <run_id>", file=sys.stderr)


# ---------------------------------------------------------------------------
# Aggregator: per-video JSONs → review queues
# ---------------------------------------------------------------------------


def aggregate(run_id: str) -> None:
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        sys.exit(f"Run dir not found: {run_dir}")

    discard_log: dict = {"version": "0.1.0", "run_id": run_id, "generated_at": now_iso(), "entities": {}}
    pending_updates: list = []
    promote_queue: list = []
    thesis_candidates: list = []
    blocks_filtered: list = []
    stats = {
        "videos_aggregated": 0,
        "entities_total": 0,
        "promoted_new": 0,
        "promoted_updates": 0,
        "discarded": 0,
        "thesis_candidates": 0,
    }

    AGGREGATOR_OUTPUT_FILES = {
        "state.json",
        "discard_log.json",
        "pending_updates.json",
        "promote_queue.json",
        "thesis_candidates.json",
        "blocks_filtered.json",
        "aggregation_stats.json",
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

        for ent in data.get("entities", []) or []:
            stats["entities_total"] += 1
            decision = ent.get("decision", "discard")
            canon = ent.get("canonical_guess", ent.get("surface_form", "unknown"))
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
            thesis_candidates.append({"from_video": vid, "from_video_title": vtitle, "thesis": t})

        for b in data.get("blocks_filtered_by_topic_filters", []) or []:
            blocks_filtered.append({"from_video": vid, "block": b})

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

    out_files = {
        "discard_log.json": discard_log,
        "pending_updates.json": {"version": "0.1.0", "run_id": run_id, "items": pending_updates},
        "promote_queue.json": {"version": "0.1.0", "run_id": run_id, "items": promote_queue},
        "thesis_candidates.json": {"version": "0.1.0", "run_id": run_id, "items": thesis_candidates},
        "blocks_filtered.json": {"version": "0.1.0", "run_id": run_id, "items": blocks_filtered},
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
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS, help="Path to playlists/ root")
    p.add_argument("--run-id", type=str, default=None, help="Identifier for the run. Default: timestamp-based")
    p.add_argument("--resume", type=str, default=None, help="Resume an existing run by id")
    p.add_argument("--pilot", action="store_true", help="Process the 5 hand-picked pilot videos only")
    p.add_argument("--video-id", type=str, default=None, help="Process a single video by its YouTube id")
    p.add_argument("--video-slug", type=str, default=None, help="Process a single video by directory slug")
    p.add_argument("--limit", type=int, default=None, help="Process at most N videos")
    p.add_argument("--discover", action="store_true", help="Just list discovered summaries and exit")
    p.add_argument("--dry-run", action="store_true", help="Build prompts, show first one, do NOT call claude")
    p.add_argument("--aggregate", type=str, default=None, help="Run aggregator on existing run-id")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.aggregate:
        aggregate(args.aggregate)
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
    elif args.resume:
        videos = all_videos
    else:
        videos = all_videos

    if args.limit:
        videos = videos[: args.limit]

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
    run(run_id, videos, pilot=args.pilot)


if __name__ == "__main__":
    main()
