#!/usr/bin/env python3
"""compile_wiki_pages.py — operación PRIMARIA del ingest Karpathy

Compila/recompila páginas wiki tomando como input:
  - el .md actual de la página (si existe — caso "rewrite") o vacío (caso "new")
  - los summaries fuente del corpus que mencionan la entidad
  - las decisiones del extractor sobre la entidad (entities[] + pending_updates +
    promote_queue items que tocan esta página)

Produce un .md COHERENTE como wiki, no append crudo. Es la corrección al error
de diseño documentado en docs/POSTMORTEM_2026-05-02.md: el ingest Karpathy
exige rewrite por página, no apply diff por source.

Pipeline en una llamada por página:
  1. Recolecta inputs (prior text, decisions, source summaries)
  2. Construye prompt con scope + whitelist + relation_types + index slim
  3. Invoca Claude Opus 4.7 (vía Max) en sesión cacheada
  4. Valida markdown emitido (frontmatter + sections + relations[])
  5. Escribe wiki/<page_type>/<page_id>.md (atómico, con backup del prior)

Uso:
    # Listar candidatos en cola (deduped, ordenados por demanda)
    python scripts/compile_wiki_pages.py --list

    # Compilar/recompilar páginas afectadas por UN run de extract
    python scripts/compile_wiki_pages.py --from-run <extraction_run_id>

    # Compilar candidatos top-N de promote_queue agregada cross-runs
    python scripts/compile_wiki_pages.py --top 80

    # Compilar uno concreto
    python scripts/compile_wiki_pages.py --candidate realismo-cognitivo

    # Dry-run (construye prompts, no invoca Claude)
    python scripts/compile_wiki_pages.py --top 3 --dry-run

    # Auto-commit por página
    python scripts/compile_wiki_pages.py --from-run X --auto-commit
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_video_themes import (  # noqa: E402
    DEFAULT_CORPUS,
    REPO,
    RUNS_DIR,
    SCOPE_PATH,
    WHITELIST_PATH,
    RELATION_TYPES_PATH,
    TOPIC_FILTERS_PATH,
    CLAUDE_MODEL,
    PER_CALL_TIMEOUT_S,
    VideoInput,
    build_wiki_index,
    discover_videos,
    invoke_claude,
    load_summary,
)

WIKI = REPO / "wiki"
META = WIKI / "_meta"
COMPILE_RUNS_DIR = META / "compile_runs"

PAGE_TYPE_DIR = {
    "concept": "concepts",
    "author": "authors",
    "entity_work": "entities/works",
    "entity_institution": "entities/institutions",
    "synthesis": "synthesis",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Tipos de input agregado
# ---------------------------------------------------------------------------


@dataclass
class PageCompileInput:
    """Todo lo que el LLM necesita para compilar/recompilar UNA página."""
    page_id: str
    page_type: str
    domain_primary: str
    is_new: bool                                  # True = página nueva, False = rewrite de existente
    prior_text: Optional[str] = None              # contenido actual del .md si existe
    prior_path: Optional[Path] = None
    source_video_ids: set[str] = field(default_factory=set)
    extractor_decisions: list[dict] = field(default_factory=list)  # entities/pending_updates relevantes
    pending_updates: list[dict] = field(default_factory=list)      # los pending_updates específicos a esta página
    n_proposed_total: int = 0


# ---------------------------------------------------------------------------
# Localizar página existente en wiki/
# ---------------------------------------------------------------------------


def find_existing_page(page_id: str) -> Optional[Path]:
    for md in WIKI.rglob(f"{page_id}.md"):
        return md
    return None


def infer_page_type_from_path(path: Path) -> str:
    rel = path.relative_to(WIKI)
    parts = rel.parts
    if not parts:
        return "concept"
    if parts[0] == "authors":
        return "author"
    if parts[0] == "concepts":
        return "concept"
    if parts[0] == "synthesis":
        return "synthesis"
    if parts[0] == "entities":
        if len(parts) > 1 and parts[1] == "works":
            return "entity_work"
        if len(parts) > 1 and parts[1] == "institutions":
            return "entity_institution"
    return "concept"


# ---------------------------------------------------------------------------
# Agregación de inputs por página (cross-run o per-run)
# ---------------------------------------------------------------------------


def aggregate_page_inputs_from_runs(run_ids: Optional[list[str]] = None) -> dict[str, PageCompileInput]:
    """Agrega inputs por page_id a partir de runs de extract_video_themes.

    Si run_ids es None: lee TODOS los runs en wiki/_meta/extraction_runs/.
    Si run_ids es lista: solo esos.

    Para cada page_id:
      - Si existe ya en wiki: agrega como rewrite (is_new=False)
      - Si está en promote_queue: agrega como new (is_new=True)
      - Si tiene pending_updates: agrega los updates específicos
    """
    if run_ids is None:
        run_dirs = sorted(d for d in RUNS_DIR.glob("*") if d.is_dir())
    else:
        run_dirs = [RUNS_DIR / r for r in run_ids if (RUNS_DIR / r).is_dir()]

    by_page: dict[str, PageCompileInput] = {}

    for run_dir in run_dirs:
        # promote_queue: candidatos a página nueva
        pq_path = run_dir / "promote_queue.json"
        if pq_path.exists():
            try:
                pq = json.loads(pq_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pq = {"items": []}
            for it in pq.get("items", []) or []:
                ent = it.get("entity") or {}
                page_id = ent.get("canonical_guess") or ent.get("surface_form")
                if not page_id:
                    continue
                page_type = ent.get("page_type", "concept")
                domain = ent.get("domain_primary_guess", "")
                inp = by_page.setdefault(
                    page_id,
                    PageCompileInput(
                        page_id=page_id,
                        page_type=page_type,
                        domain_primary=domain,
                        is_new=True,
                    ),
                )
                inp.extractor_decisions.append(ent)
                if it.get("from_video"):
                    inp.source_video_ids.add(it["from_video"])
                inp.n_proposed_total += 1

        # pending_updates: cambios a páginas existentes
        pu_path = run_dir / "pending_updates.json"
        if pu_path.exists():
            try:
                pu = json.loads(pu_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pu = {"items": []}
            for it in pu.get("items", []) or []:
                u = it.get("update") or {}
                page_id = u.get("page_id")
                if not page_id:
                    continue
                inp = by_page.setdefault(
                    page_id,
                    PageCompileInput(
                        page_id=page_id,
                        page_type="concept",  # se ajusta abajo si encontramos página existente
                        domain_primary="",
                        is_new=False,
                    ),
                )
                inp.pending_updates.append(u)
                if it.get("from_video"):
                    inp.source_video_ids.add(it["from_video"])

    # Ajusta is_new + lee prior text para páginas que existen
    for page_id, inp in list(by_page.items()):
        existing = find_existing_page(page_id)
        if existing:
            inp.is_new = False
            inp.prior_path = existing
            inp.prior_text = existing.read_text(encoding="utf-8")
            inp.page_type = infer_page_type_from_path(existing)
            # Conserva el domain del extractor si tenía info, si no infiere de frontmatter
            if not inp.domain_primary and inp.prior_text:
                m = re.search(r"^domain_primary:\s*(\S+)", inp.prior_text, re.MULTILINE)
                if m:
                    inp.domain_primary = m.group(1)
        else:
            inp.is_new = True

    return by_page


# ---------------------------------------------------------------------------
# Recolección de source summaries
# ---------------------------------------------------------------------------


def index_videos_by_id(corpus_path: Path) -> dict[str, VideoInput]:
    return {v.video_id: v for v in discover_videos(corpus_path)}


def gather_summaries(inp: PageCompileInput, video_index: dict[str, VideoInput]) -> list[VideoInput]:
    out: list[VideoInput] = []
    for vid in inp.source_video_ids:
        v = video_index.get(vid)
        if v is None:
            continue
        if not v.summary_text:
            load_summary(v)
        out.append(v)
    return out


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


COMPILER_ROLE_PROMPT = """
Eres un compilador de páginas wiki Ariadna.

CONTEXTO: Ariadna es un wiki markdown que documenta el corpus YouTube del canal Proxy
(análisis arquetípico, mitología comparada, psicología junguiana, crítica cultural).
Las páginas existentes han sido escritas siguiendo wiki/_meta/scope.md y forman
un grafo emergente vía relations[] tipadas en frontmatter + [[wikilinks]] en cuerpo.

TU TAREA: dado un PAGE_ID + page_type + domain + N source summaries del corpus
que mencionan la entidad + (opcionalmente) el contenido ACTUAL de la página
si ya existe, escribe la versión COHERENTE y UNIFICADA de la página .md.

Modo "REWRITE de página existente":
  - Recibes prior_text con la versión actual
  - Recibes N source summaries con material nuevo
  - Recibes (opcionalmente) decisions del extractor sobre esta entidad
  - Tu output es la página REESCRITA fusionando seed + nuevo material en una
    sola voz editorial coherente. NO concatenas párrafos al final. Reorganizas
    si es necesario, priorizas, transiciones suaves entre sub-cases. La
    estructura editorial original (Definición → Manifestaciones → Lagunas)
    se mantiene salvo que el material nuevo justifique reorganización.

Modo "NEW página":
  - prior_text vacío
  - Recibes N source summaries que el extractor identificó como cubriendo
    sustancialmente esta entidad
  - Tu output es la página COMPLETA escrita desde cero siguiendo scope.md §7
"""


COMPILER_OUTPUT_SCHEMA = """
# Salida — formato exacto

```
---
page_id: <page_id objetivo>
page_type: concept | author | entity_work | entity_institution | synthesis
canonical_name: <Nombre humano legible>
aliases: [..., ..., ...]
domain:
  - <dominio OpenAlex>
domain_primary: <dominio OpenAlex>
relations:
  - {type: <type>, to: <page_id>, note: <note opcional>}
  - ...
sources_count: <N — número de chunks únicos citados>
last_compiled: <ISO 8601>
compiler: claude-opus-4-7-compile_wiki_pages
schema_version: 1.0.0
review_status: auto_generated
---

# <Canonical Name>

## Definición

Prosa enciclopédica del concepto/autor/obra. Citas con formato:
→ [Título del vídeo, mm:ss](https://youtu.be/VIDEOID?t=SECONDS)

## Manifestaciones según el corpus  (concept)
## Pensamiento / Obra                (author)
## Sinopsis y arquetipos             (entity_work)
## Tesis general / Piezas            (synthesis)

(Estructura adaptada al page_type)

## Conexión con otros conceptos
- Relacionado con [[other-page-id]] porque ...

## Lagunas detectadas

- Sub-dimensiones del concepto que el corpus no aborda
- Tradiciones/marcos no presentes
- Preguntas abiertas

(Sección OBLIGATORIA — vacía con bullet "(no hay lagunas detectadas)" si no hay)
```

# Reglas duras

1. **page_id en frontmatter == page_id objetivo que recibes**. NO renombrar.

2. **Citas LITERALES de los summaries fuente**. Cada afirmación rastrea a
   ≥1 cita con formato `→ [Título, mm:ss](URL)`. Las citas se extraen
   literalmente del campo "→ [...]" presente en cada bullet del summary.

3. **REWRITE coherente, NO concatenación** (modo rewrite):
   - Si el prior_text trataba un sub-case con 3 bullets, y el material nuevo
     aporta 2 bullets más al mismo sub-case, FUSIONA los 5 en orden lógico.
     NO añadas los 2 nuevos al final como bloque separado.
   - Si el material nuevo justifica un sub-case nuevo, créalo respetando la
     numeración/jerarquía editorial.
   - Mantén voz unificada — no se debe notar que vienen de extractores distintos.
   - Citas verificables en TODAS las afirmaciones.

4. **Wikilinks `[[page_id]]` solo a**:
   - Páginas EXISTENTES en el wiki snapshot que recibes (puedes verificar
     con tool Read sobre el file_path indicado en el index)
   - Páginas DECLARADAS en relations[] del frontmatter de esta misma página

5. **relations[] tipadas con vocabulario CANÓNICO** de relation_types.json.

6. **Vocabulario PROHIBIDO en el cuerpo** (scope.md §7.4):
   - "este batch", "del batch", "estos chunks", "top-N"
   - "discovery via Qdrant", "summary.md", "chunks recuperados"
   - "Sprint", "piloto", "sucesivas iteraciones"
   - Cualquier auto-referencia al sistema RAG, pipeline o proceso de compilación.

7. **Lagunas honestas y acotadas** (scope.md §7.1):
   - Sub-dimensión del concepto NO tematizada en los summaries recibidos
   - Tradición/marco ausente del material disponible
   - Pregunta abierta que el canal afirma sin desarrollar
   - **PROHIBIDO** declarar laguna "X obra no aparece" cuando X aparece — eso
     es laguna del extractor previo, no del corpus.

8. **NO corregir terminología canal-específica** (scope.md §5).

9. **Salida estricta**. Sin preámbulo, sin epílogo, sin code fences. Primer
   carácter `---`, último el final del último párrafo. Si el frontmatter YAML
   o las sections obligatorias fallan, el output va a .failed.md.

10. **Conserva curaduría humana** (modo rewrite): si el prior_text tiene
    secciones que NO están cubiertas por el material nuevo, **manténlas
    intactas**. Solo añades/reorganizas cuando el material nuevo lo aporta.
    No borres material previo a menos que sea factualmente erróneo según
    los summaries fuente.
"""


def build_compiler_system_prompt() -> str:
    return "\n\n".join(
        [
            COMPILER_ROLE_PROMPT,
            "# Contexto cargado en primer mensaje de sesión",
            "El primer user message te entrega scope.md + canonical_whitelist + "
            "relation_types + topic_filters + wiki index slim. Trátalos como "
            "autoritativos durante toda esta sesión.",
            COMPILER_OUTPUT_SCHEMA,
        ]
    )


def build_compiler_heavy_context() -> str:
    index = build_wiki_index()
    return "\n\n".join(
        [
            "# Documentos autoritativos de la sesión",
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
            "Tras este mensaje recibirás páginas a compilar/recompilar. Para cada "
            "una: page_id + page_type + domain + N summaries fuente + (opcional) "
            "el .md actual de la página + decisiones del extractor sobre la "
            "entidad. Compila la página coherente siguiendo el schema y reglas. "
            "Si necesitas el cuerpo de OTRA página existente para asegurar "
            "coherencia de wikilinks, usa la tool Read sobre su file_path.",
        ]
    )


def build_compile_user_message(inp: PageCompileInput, summaries: list[VideoInput]) -> str:
    parts: list[str] = []
    mode = "REWRITE de página existente" if not inp.is_new else "NEW página"
    parts.append(f"# Compilar página: `{inp.page_id}`  ({mode})")
    parts.append("")
    parts.append(f"**page_type**: `{inp.page_type}`")
    parts.append(f"**domain_primary**: `{inp.domain_primary or '(infiere)'}`")
    parts.append(f"**source_videos**: {len(inp.source_video_ids)} vídeos")
    parts.append(f"**n_proposed cross-runs**: {inp.n_proposed_total}")
    parts.append(f"**pending_updates pending para esta página**: {len(inp.pending_updates)}")
    parts.append("")

    if inp.prior_text:
        parts.append("## Contenido ACTUAL de la página (prior_text)")
        parts.append("")
        parts.append("```markdown")
        parts.append(inp.prior_text)
        parts.append("```")
        parts.append("")

    if inp.extractor_decisions:
        parts.append("## Decisiones del extractor sobre esta entidad (cross-runs)")
        parts.append("")
        for ent in inp.extractor_decisions[:8]:
            parts.append(
                f"- depth={ent.get('depth_in_video','?')} "
                f"min={ent.get('minutes_estimate','?')} "
                f"framing_marks={len(ent.get('framing_marks') or [])} "
                f"reason={(ent.get('decision_reason') or '')[:140]}"
            )
        parts.append("")

    if inp.pending_updates:
        parts.append("## pending_updates propuestos por el extractor (REFERENCIA, no aplicar literal)")
        parts.append("")
        for u in inp.pending_updates[:6]:
            parts.append(f"- type={u.get('update_type')} section={(u.get('section_target') or '')[:60]}")
            content = (u.get('content_proposed') or '')[:240]
            parts.append(f"  content_proposed: {content}")
            if u.get('supersedes_laguna_text'):
                parts.append(f"  supersedes_laguna: {u['supersedes_laguna_text'][:120]}")
        parts.append("")
        parts.append(
            "**Estos pending_updates son material crudo que el extractor sugirió "
            "insertar incrementalmente. Tu trabajo NO es aplicarlos literalmente. "
            "Tu trabajo es FUSIONAR coherentemente con el prior_text y los "
            "summaries fuente.**"
        )
        parts.append("")

    parts.append("## Source summaries de los vídeos que mencionan esta entidad")
    parts.append("")
    for v in summaries:
        parts.append(f"### Vídeo `{v.video_id}` — {v.title}")
        parts.append(
            f"playlist: `{v.playlist}` | category: `{v.category}` | "
            f"duration: {v.duration_s//60}min | url: {v.url}"
        )
        parts.append("")
        parts.append("```markdown")
        parts.append(v.summary_text)
        parts.append("```")
        parts.append("")

    parts.append("---")
    parts.append(
        f"Compila/recompila ahora la página `{inp.page_id}`. "
        f"Devuelve ÚNICAMENTE el contenido del archivo .md (frontmatter YAML "
        f"+ cuerpo). Sin code fences. Primer carácter `---`."
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Validación del markdown emitido
# ---------------------------------------------------------------------------


FRONTMATTER_BLOCK_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
FRONTMATTER_FIELD_RE = re.compile(r"^([a-z_]+):\s*(.+?)\s*$", re.MULTILINE)


def validate_compiled_page(text: str, expected_page_id: str, expected_page_type: str) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not text.startswith("---\n"):
        errors.append("output no empieza con frontmatter '---'")
        return False, errors
    fm_match = FRONTMATTER_BLOCK_RE.match(text)
    if not fm_match:
        errors.append("frontmatter mal formado: no encontrado bloque '---...---'")
        return False, errors
    fm = fm_match.group(1)
    fields = dict(FRONTMATTER_FIELD_RE.findall(fm))
    pid = fields.get("page_id", "").strip()
    if pid != expected_page_id:
        errors.append(f"page_id={pid!r} != expected={expected_page_id!r}")
    pt = fields.get("page_type", "").strip()
    if expected_page_type and pt != expected_page_type:
        errors.append(f"page_type={pt!r} != expected={expected_page_type!r}")
    if "canonical_name" not in fields:
        errors.append("falta canonical_name en frontmatter")
    if "domain_primary" not in fields:
        errors.append("falta domain_primary en frontmatter")
    body = text[fm_match.end():]
    if not re.search(r"^##\s+Lagunas", body, re.MULTILINE):
        errors.append("falta sección obligatoria '## Lagunas'")
    if len(body.strip()) < 200:
        errors.append(f"cuerpo demasiado corto ({len(body.strip())} chars) — sospechoso")
    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Compilación de una página
# ---------------------------------------------------------------------------


def compile_one_page(
    inp: PageCompileInput,
    video_index: dict[str, VideoInput],
    system_prompt_short: str,
    heavy_context: str,
    session_id: Optional[str],
    is_first_call: bool,
    run_dir: Path,
    dry_run: bool = False,
) -> tuple[Optional[Path], Optional[str], list[str]]:
    summaries = gather_summaries(inp, video_index)
    if not summaries and inp.is_new:
        return None, session_id, [f"no source summaries para nueva página {inp.page_id}"]

    user_msg_body = build_compile_user_message(inp, summaries)
    if is_first_call:
        user_msg = heavy_context + "\n\n---\n\n" + user_msg_body
    else:
        user_msg = user_msg_body

    if dry_run:
        print(f"\n=== DRY RUN: {inp.page_id} ({inp.page_type}, {'rewrite' if not inp.is_new else 'new'}) ===")
        print(f"  source summaries: {len(summaries)}")
        print(f"  user_msg size: {len(user_msg)} chars (~{len(user_msg)//4} tokens)")
        print(f"  primer 800 chars del msg:")
        print(user_msg[:800])
        return None, session_id, []

    try:
        sys_prompt_arg = system_prompt_short if session_id is None else None
        output_text, meta = invoke_claude(
            user_msg=user_msg,
            system_prompt_appended=sys_prompt_arg,
            resume_session_id=session_id,
        )
        if session_id is None and meta.get("session_id"):
            session_id = meta["session_id"]
    except Exception as e:
        return None, session_id, [f"claude invocation failed: {str(e)[:200]}"]

    ok, errors = validate_compiled_page(output_text, inp.page_id, inp.page_type)
    if not ok:
        fail_path = run_dir / f"{inp.page_id}.failed.md"
        fail_path.write_text(
            f"<!-- ERRORS:\n" + "\n".join(errors) + "\n-->\n" + output_text,
            encoding="utf-8",
        )
        return None, session_id, errors

    target_dir = WIKI / PAGE_TYPE_DIR.get(inp.page_type, inp.page_type)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{inp.page_id}.md"

    if target.exists() and not inp.is_new:
        backup_dir = run_dir / "prior_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"{inp.page_id}.md.prior"
        backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")

    target.write_text(output_text, encoding="utf-8")
    return target, session_id, []


# ---------------------------------------------------------------------------
# Run orchestration
# ---------------------------------------------------------------------------


def run_compile(
    inputs: list[PageCompileInput],
    auto_commit: bool,
    dry_run: bool,
) -> dict:
    if not inputs:
        print("Sin páginas para compilar.", file=sys.stderr)
        return {"compiled": 0, "failed": 0}

    run_id = f"compile_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    run_dir = COMPILE_RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    video_index = index_videos_by_id(DEFAULT_CORPUS)
    print(f"Corpus index: {len(video_index)} videos", file=sys.stderr)

    print("Building prompts...", file=sys.stderr)
    system_prompt_short = build_compiler_system_prompt()
    heavy_context = build_compiler_heavy_context()
    (run_dir / "system_prompt.short.snapshot.txt").write_text(system_prompt_short, encoding="utf-8")
    (run_dir / "heavy_context.snapshot.txt").write_text(heavy_context, encoding="utf-8")
    print(
        f"  short system prompt: {len(system_prompt_short)} chars (~{len(system_prompt_short)//4} tokens)",
        file=sys.stderr,
    )
    print(
        f"  heavy context:       {len(heavy_context)} chars (~{len(heavy_context)//4} tokens)",
        file=sys.stderr,
    )

    written: list[Path] = []
    failed: list[tuple[str, list[str]]] = []
    session_id: Optional[str] = None

    for i, inp in enumerate(inputs):
        mode = "rewrite" if not inp.is_new else "new"
        print(
            f"\n=== {i+1}/{len(inputs)}: {inp.page_id} ({inp.page_type}, {mode}, {len(inp.source_video_ids)} videos) ===",
            file=sys.stderr,
        )
        target, session_id, errors = compile_one_page(
            inp=inp,
            video_index=video_index,
            system_prompt_short=system_prompt_short,
            heavy_context=heavy_context,
            session_id=session_id,
            is_first_call=(i == 0),
            run_dir=run_dir,
            dry_run=dry_run,
        )
        if errors:
            print(f"  ! FAILED: {errors[0]}", file=sys.stderr)
            failed.append((inp.page_id, errors))
            continue
        if target:
            print(f"  ✓ wrote {target.relative_to(REPO)}", file=sys.stderr)
            written.append(target)

    if dry_run:
        print(f"\nDRY RUN: would have processed {len(inputs)} páginas", file=sys.stderr)
        return {"compiled": 0, "failed": 0, "dry_run": True}

    log = {
        "compiled_at": now_iso(),
        "run_id": run_id,
        "inputs_attempted": [{"page_id": i.page_id, "is_new": i.is_new} for i in inputs],
        "written": [str(p.relative_to(REPO)) for p in written],
        "failed": [{"page_id": pid, "errors": err} for pid, err in failed],
    }
    (run_dir / "compile_log.json").write_text(
        json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nLog: {(run_dir / 'compile_log.json').relative_to(REPO)}", file=sys.stderr)

    if auto_commit and written:
        paths = [str(p.relative_to(REPO)) for p in written]
        subprocess.run(["git", "add"] + paths, cwd=REPO, check=False)
        n_new = sum(1 for inp in inputs if inp.is_new and find_existing_page(inp.page_id) is not None)
        n_rewrite = len(written) - n_new
        msg = (
            f"feat(wiki): compile {len(written)} pages ({n_new} new + {n_rewrite} rewrites)\n\n"
            f"Compilador: scripts/compile_wiki_pages.py (run {run_id})\n"
            f"Páginas:\n"
            + "\n".join(f"  - {p.relative_to(REPO)}" for p in written)
        )
        commit = subprocess.run(["git", "commit", "-m", msg], cwd=REPO, capture_output=True, text=True)
        if commit.returncode == 0:
            print(f"  ✓ commit creado", file=sys.stderr)
        else:
            print(f"  ! git commit falló: {commit.stderr[-300:]}", file=sys.stderr)

    if failed:
        print(f"\nFAILED ({len(failed)}):", file=sys.stderr)
        for pid, err in failed:
            print(f"  {pid}: {err[0]}", file=sys.stderr)

    return {"compiled": len(written), "failed": len(failed), "run_id": run_id}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def list_inputs(inputs: dict[str, PageCompileInput]) -> None:
    ordered = sorted(
        inputs.values(),
        key=lambda x: (-x.n_proposed_total, -len(x.pending_updates), x.page_id),
    )
    print(f"{'page_id':35s}  {'mode':8s}  {'type':17s}  {'#vids':>6}  {'n_prop':>7}  {'#upd':>5}")
    print("-" * 90)
    for x in ordered:
        mode = "rewrite" if not x.is_new else "new"
        print(
            f"{x.page_id:35s}  {mode:8s}  {x.page_type:17s}  "
            f"{len(x.source_video_ids):>6}  {x.n_proposed_total:>7}  {len(x.pending_updates):>5}"
        )


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="Listar páginas a compilar (no compila)")
    ap.add_argument("--from-run", type=str, default=None, help="run_id de extract_video_themes a procesar")
    ap.add_argument("--from-runs", type=str, default=None, help="CSV de run_ids")
    ap.add_argument("--top", type=int, default=None, help="Compilar top-N por demanda (n_proposed_total)")
    ap.add_argument("--candidate", type=str, default=None, help="Compilar un page_id concreto")
    ap.add_argument("--candidates", type=str, default=None, help="CSV de page_ids")
    ap.add_argument("--include-rewrites", action="store_true", default=True, help="Incluir páginas existentes que tienen pending_updates (default: True)")
    ap.add_argument("--no-rewrites", dest="include_rewrites", action="store_false", help="Solo compilar páginas nuevas, no recompilar existentes")
    ap.add_argument("--min-proposed", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--auto-commit", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = parse_args()

    if args.from_run:
        run_ids = [args.from_run]
    elif args.from_runs:
        run_ids = [r.strip() for r in args.from_runs.split(",") if r.strip()]
    else:
        run_ids = None  # all runs

    inputs_all = aggregate_page_inputs_from_runs(run_ids)
    if not inputs_all:
        sys.exit("No hay inputs en wiki/_meta/extraction_runs/* — ejecuta primero extract_video_themes.")

    if not args.include_rewrites:
        inputs_all = {k: v for k, v in inputs_all.items() if v.is_new}

    if args.list:
        list_inputs(inputs_all)
        return

    # Selección
    if args.candidate:
        if args.candidate not in inputs_all:
            sys.exit(f"Page no encontrada: {args.candidate}. Usa --list.")
        selected = [inputs_all[args.candidate]]
    elif args.candidates:
        names = [n.strip() for n in args.candidates.split(",") if n.strip()]
        missing = [n for n in names if n not in inputs_all]
        if missing:
            sys.exit(f"Pages no encontradas: {missing}.")
        selected = [inputs_all[n] for n in names]
    elif args.top:
        ordered = sorted(
            inputs_all.values(),
            key=lambda x: (-x.n_proposed_total - len(x.pending_updates), x.page_id),
        )
        selected = [
            x for x in ordered
            if x.n_proposed_total >= args.min_proposed or len(x.pending_updates) > 0
        ][: args.top]
    else:
        # Default: TODAS las páginas afectadas (new + rewrites)
        selected = list(inputs_all.values())

    n_new = sum(1 for x in selected if x.is_new)
    n_rewrite = len(selected) - n_new
    print(f"Seleccionadas {len(selected)} páginas: {n_new} nuevas + {n_rewrite} rewrites", file=sys.stderr)
    print()

    run_compile(selected, auto_commit=args.auto_commit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
