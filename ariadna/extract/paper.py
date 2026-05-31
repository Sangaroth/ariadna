"""Extractor LEAN de páginas wiki desde un sumario de paper (decisión F6.4).

Una llamada LLM por paper produce páginas candidatas (JSON); la materialización a
`.md` (frontmatter + cuerpo + ## Citations) es DETERMINISTA y testeable sin LLM.
Citas en formato paper vía `PaperAdapter.cite_markdown` (source-agnostic por adapter).

Mucho más simple que el motor de YouTube (sin shadow-wiki/subagentes/synthesis): el
corpus de papers de un proyecto es pequeño y cada paper es autónomo. Si en el futuro
hace falta la maquinaria pesada, se promueve entonces.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from ariadna.project_config import ProjectConfig
from ariadna.sources.paper import PaperAdapter
from ariadna.summarize.run_claude import run_claude as _run_claude

log = logging.getLogger(__name__)

# page_type → subdir bajo projects/<slug>/wiki/.
_SUBDIR_BY_TYPE = {
    "concept": "concepts",
    "author": "authors",
    "entity_work": "entities/works",
    "entity_institution": "entities/institutions",
    "synthesis": "synthesis",
}

PAPER_EXTRACT_PROMPT_ES = """\
Eres un editor enciclopédico. A partir del índice temático de UN paper, extrae las \
páginas wiki que el paper justifica (conceptos, autores, obras, síntesis), como una \
enciclopedia del corpus — NO un resumen del paper.

## Paper
**Título:** {title}
**source_id:** {source_id}

## Índice temático (con marcas de página [p.NN] y temas '- p.NN 🎭 ...')
{summary}

## Páginas wiki ya existentes en el proyecto (para wikilinks [[page-id]])
{existing_pages}

## Scope editorial del proyecto
{scope}

## Salida: SOLO un objeto JSON, sin texto alrededor

{{"pages": [
  {{
    "page_id": "kebab-case-id",
    "page_type": "concept|author|entity_work|entity_institution|synthesis",
    "canonical_name": "Nombre canónico",
    "domain_primary": "dominio OpenAlex principal (p.ej. humanities.philosophy.mind)",
    "primary_domains": ["dominio principal primero", "1-3 dominios OpenAlex (incluye el primario)"],
    "aliases": ["alias1", "alias2"],
    "relations": [{{"type": "developed_by", "to": "otra-page-id", "weight": "canonical"}}],
    "body_markdown": "# {{canonical_name}}\\n\\n## Definición\\n\\nProsa enciclopédica con citas inline al paper en formato [{title}, p.N](https://doi.org/DOI#page=N). Usa [[page-id]] para enlazar otras páginas.",
    "cited_pages": [3, 5, 7]
  }}
]}}

Reglas:
- body_markdown: prosa enciclopédica densa; cada afirmación sustantiva citada con [Título, p.N](url) del paper.
- cited_pages: lista de números de página del paper citados en esta página (para la sección ## Citations).
- relations[].type debe ser de los tipos canónicos del proyecto; to en kebab-case.
- NO incluyas la sección ## Citations en body_markdown (se genera automáticamente).
"""


def _extract_json(text: str) -> dict:
    """Extrae el primer objeto JSON balanceado del texto (tolera fences/preámbulo)."""
    start = text.find("{")
    if start < 0:
        raise ValueError("respuesta del LLM sin objeto JSON")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("objeto JSON no balanceado en la respuesta del LLM")


def extract_paper_to_pages(
    summary_md: str,
    source_id: str,
    title: str,
    project: str,
    *,
    existing_page_ids: list[str] | None = None,
    scope_text: str = "",
    model: str | None = None,
    run_claude_fn=_run_claude,
) -> list[dict]:
    """Llama al LLM y devuelve la lista de páginas candidatas (dicts validados mínimamente)."""
    prompt = PAPER_EXTRACT_PROMPT_ES.format(
        title=title, source_id=source_id, summary=summary_md,
        existing_pages=", ".join(existing_page_ids or []) or "(ninguna)",
        scope=scope_text or "(sin scope definido)",
    )
    out = run_claude_fn(prompt, model=model)
    if not out:
        raise RuntimeError("extract_paper_to_pages: run_claude sin respuesta")
    data = _extract_json(out)
    pages = data.get("pages") or []
    return [p for p in pages if p.get("page_id") and p.get("page_type") and p.get("canonical_name")]


# --- materialización determinista (testeable sin LLM) -----------------------

_PAGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _sanitize_page_id(raw: str) -> str:
    """Normaliza a kebab ASCII: acentos→base (ñ→n, á→a), minúsculas, no-[a-z0-9]→'-'.

    El LLM a veces emite page_ids en español con ñ/acentos (p.ej.
    'señal-de-error-de-la-fibra-trepadora'); sanear evita descartar la página.
    """
    s = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _yaml_scalar(v: str) -> str:
    """Cita el escalar si contiene caracteres YAML problemáticos."""
    if v and re.search(r"[:#\[\]{}\"']", v):
        return '"' + v.replace('"', '\\"') + '"'
    return v


def render_page_markdown(
    page: dict,
    source_id: str,
    title: str,
    adapter: PaperAdapter | None = None,
) -> str:
    """Renderiza una página (frontmatter + cuerpo + ## Citations) de forma determinista."""
    adapter = adapter or PaperAdapter()
    cname = page["canonical_name"]
    aliases = page.get("aliases") or []
    relations = page.get("relations") or []
    body = (page.get("body_markdown") or f"# {cname}\n").rstrip()

    fm: list[str] = ["---"]
    fm.append(f"page_id: {page['page_id']}")
    fm.append(f"page_type: {page['page_type']}")
    fm.append(f"canonical_name: {_yaml_scalar(cname)}")
    if page.get("domain_primary"):
        fm.append(f"domain_primary: {page['domain_primary']}")
    # primary_domains[]: lista OpenAlex (primario primero) — la lee build_wiki_db
    # para poblar page_domains. Sin ella el filtro por dominio queda vacío en atlas.
    domains = list(page.get("primary_domains") or page.get("domains") or [])
    if page.get("domain_primary"):
        domains = [page["domain_primary"], *domains]
    domains = list(dict.fromkeys(d for d in domains if d))  # dedupe, preserva orden
    if domains:
        fm.append("primary_domains:")
        for d in domains:
            fm.append(f"- {d}")
    fm.append("aliases: " + ("[]" if not aliases else ""))
    for a in aliases:
        fm.append(f"- {_yaml_scalar(a)}")
    if relations:
        fm.append("relations:")
        for r in relations:
            fm.append(f"- type: {r['type']}")
            fm.append(f"  to: {r['to']}")
            if r.get("weight"):
                fm.append(f"  weight: {r['weight']}")
            if r.get("note"):
                fm.append(f"  note: {_yaml_scalar(str(r['note']))}")
    else:
        fm.append("relations: []")
    fm.append(f"sources_count: 1")
    fm.append("review_status: stub_in_session")
    fm.append("schema_version: 1.0.0")
    fm.append("status: stub_in_session")
    fm.append("---")

    # ## Citations desde cited_pages, con cite_markdown del adapter (paper).
    cites: list[str] = []
    for pg in page.get("cited_pages") or []:
        pos = {"page": int(pg)}
        url = adapter.format_position_url(source_id, pos)
        cites.append(f"- {adapter.cite_markdown(title, pos, url)}")
    citations_block = ""
    if cites:
        citations_block = "\n\n## Citations\n\n" + "\n".join(cites)

    return "\n".join(fm) + "\n\n" + body + citations_block + "\n"


def materialize_pages(
    pages: list[dict],
    source_id: str,
    title: str,
    project: str,
    *,
    wiki_root: Path | None = None,
    adapter: PaperAdapter | None = None,
) -> list[Path]:
    """Escribe cada página a projects/<project>/wiki/<subdir>/<page_id>.md. Devuelve rutas.

    `wiki_root` override (tests). Salta páginas con page_id inválido o page_type desconocido.
    """
    root = wiki_root or ProjectConfig(project).wiki_root
    written: list[Path] = []
    for page in pages:
        pid = _sanitize_page_id(page.get("page_id", ""))
        ptype = page.get("page_type", "")
        if not _PAGE_ID_RE.match(pid):
            log.warning("page_id inválido, salto: %r", page.get("page_id", ""))
            continue
        page = {**page, "page_id": pid}  # frontmatter/filename usan el id saneado
        subdir = _SUBDIR_BY_TYPE.get(ptype)
        if subdir is None:
            log.warning("page_type desconocido %r en %s, salto", ptype, pid)
            continue
        dest = root / subdir / f"{pid}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(render_page_markdown(page, source_id, title, adapter), encoding="utf-8")
        written.append(dest)
    return written
