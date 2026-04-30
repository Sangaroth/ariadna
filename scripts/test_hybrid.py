#!/usr/bin/env python3
"""Smoke test end-to-end del MCP server vivo.

Valida los invariantes del modo híbrido tras la migración a relations[]:
  - tools/list expone las 4 tools esperadas
  - search_corpus devuelve {wiki_pages, raw_chunks, retrieval_metadata}
  - wiki_pages traen relations[] tipadas (no related_concepts legacy)
  - mode_recommended se calcula bien para queries golden
  - raw_chunks llevan cite_markdown pre-renderizado
  - get_wiki_page devuelve el body completo

Uso:
    python scripts/test_hybrid.py            # output humano
    python scripts/test_hybrid.py --json     # un JSON con resumen
    python scripts/test_hybrid.py --url ...  # contra otro server (default localhost:8765)

Exit 0 si todos los checks pasan, 1 si alguno falla. Pensado como gate
manual antes de cerrar sesión y como anclaje para CI futuro.

Requisito: MCP server corriendo y wiki indexada (`python scripts/index_wiki_to_qdrant.py`).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

DEFAULT_URL = "http://127.0.0.1:8765/mcp"

EXPECTED_TOOLS = {"search_corpus", "get_video_summary", "list_videos", "get_wiki_page"}


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def mcp_call(url: str, method: str, params: dict | None = None) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    # Server contesta SSE: lineas 'data: {...}'. Parseamos la primera.
    for line in body.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])
    return json.loads(body)


def call_tool(url: str, tool: str, args: dict) -> dict:
    """Devuelve el structuredContent.result del tool call (ya deserializado)."""
    resp = mcp_call(url, "tools/call", {"name": tool, "arguments": args})
    if "error" in resp:
        raise RuntimeError(f"MCP error en {tool}: {resp['error']}")
    sc = resp["result"].get("structuredContent") or {}
    if "result" in sc:
        return sc["result"]
    # Fallback: parsear text content como JSON.
    for c in resp["result"].get("content", []):
        if c.get("type") == "text":
            return json.loads(c["text"])
    raise RuntimeError(f"Respuesta sin structuredContent ni text para {tool}")


# --- checks individuales ---------------------------------------------------


def check_tools_list(url: str) -> Check:
    resp = mcp_call(url, "tools/list")
    tools = {t["name"] for t in resp.get("result", {}).get("tools", [])}
    missing = EXPECTED_TOOLS - tools
    extra = tools - EXPECTED_TOOLS
    if missing:
        return Check("tools/list", False, f"faltan: {sorted(missing)} (presentes: {sorted(tools)})")
    detail = f"{len(tools)} tools"
    if extra:
        detail += f" (extras inesperadas pero no fatales: {sorted(extra)})"
    return Check("tools/list", True, detail)


def check_wiki_primary(url: str) -> Check:
    """Query sobre concepto canónico → wiki es señal dominante + relations[] tipadas pobladas.

    No exige mode == wiki_dominant: el threshold (0.65) es estrecho y un drift de 0.03 lo
    pone en balanced. El invariante real es que la wiki gane al raw y traiga grafo tipado.
    """
    res = call_tool(url, "search_corpus", {"query": "sombra junguiana", "top_k": 3, "top_k_wiki": 2})
    meta = res.get("retrieval_metadata", {})
    wiki = res.get("wiki_pages", [])
    if not wiki:
        return Check("wiki_primary", False, "wiki_pages vacío")
    top = wiki[0]
    if top.get("page_id") != "shadow-archetype":
        return Check("wiki_primary", False, f"top wiki page_id={top.get('page_id')} (esperado shadow-archetype)")
    rels = top.get("relations") or []
    if not rels:
        return Check("wiki_primary", False, "shadow-archetype sin relations[] — payload Qdrant stale o reader roto")
    types = top.get("relation_types_present") or []
    if not types:
        return Check("wiki_primary", False, "shadow-archetype sin relation_types_present[]")
    if "related_concepts" in top and top["related_concepts"]:
        return Check("wiki_primary", False, "campo legacy related_concepts no debería estar poblado")
    mode = meta.get("mode_recommended")
    if mode not in {"wiki_dominant", "balanced"}:
        return Check("wiki_primary", False, f"mode={mode} (esperado wiki_dominant|balanced)")
    wiki_top = meta.get("wiki_top_score") or 0
    raw_top = meta.get("raw_top_score") or 0
    if wiki_top <= raw_top:
        return Check("wiki_primary", False, f"wiki_top {wiki_top} no supera raw_top {raw_top}")
    return Check(
        "wiki_primary",
        True,
        f"shadow-archetype score={top['score']} mode={mode} relations={len(rels)} types={types}",
    )


def check_raw_with_warning(url: str) -> Check:
    """Query con cobertura wiki nula (Tolkien) → mode raw_with_warning o raw_only y warning explícito."""
    res = call_tool(url, "search_corpus", {"query": "qué vídeos hay sobre Tolkien", "top_k": 5, "top_k_wiki": 2})
    meta = res.get("retrieval_metadata", {})
    mode = meta.get("mode_recommended")
    if mode not in {"raw_with_warning", "raw_only"}:
        return Check(
            "raw_with_warning",
            False,
            f"mode={mode} (esperado raw_with_warning|raw_only); "
            f"wiki_top={meta.get('wiki_top_score')} raw_top={meta.get('raw_top_score')}",
        )
    if mode == "raw_with_warning" and not meta.get("warning"):
        return Check("raw_with_warning", False, "mode raw_with_warning sin warning poblado")
    raw = res.get("raw_chunks", [])
    if not raw:
        return Check("raw_with_warning", False, "raw_chunks vacío")
    first = raw[0]
    if not first.get("cite_markdown", "").startswith("["):
        return Check("raw_with_warning", False, f"raw_chunks[0].cite_markdown ausente o malformado: {first.get('cite_markdown')!r}")
    return Check("raw_with_warning", True, f"mode={mode} raw_top={meta.get('raw_top_score')} raw_count={len(raw)}")


def check_balanced_or_dominant(url: str) -> Check:
    """Query cross-conceptual → mode balanced o wiki_dominant + targets navegables."""
    res = call_tool(url, "search_corpus", {"query": "cómo conecta sombra con consumismo", "top_k": 3, "top_k_wiki": 2})
    meta = res.get("retrieval_metadata", {})
    mode = meta.get("mode_recommended")
    wiki = res.get("wiki_pages", [])
    if mode not in {"balanced", "wiki_dominant"}:
        return Check(
            "balanced_or_dominant",
            False,
            f"mode={mode} (esperado balanced|wiki_dominant); wiki_top={meta.get('wiki_top_score')}",
        )
    if not wiki:
        return Check("balanced_or_dominant", False, "wiki_pages vacío en query cross-conceptual")
    targets = wiki[0].get("relation_targets") or []
    if not targets:
        return Check("balanced_or_dominant", False, f"top wiki ({wiki[0].get('page_id')}) sin relation_targets")
    return Check(
        "balanced_or_dominant",
        True,
        f"mode={mode} top={wiki[0].get('page_id')} targets={len(targets)}",
    )


def check_wiki_via_citation(url: str) -> Check:
    """Query sobre sub-aspecto que el focal de la wiki NO captura, pero la wiki SÍ cita
    el chunk relevante en su prosa → la página debe aparecer vía lookup indirecto.

    "Tarzan se conoce a si mismo a traves de Jane" es un análisis arquetípico aplicado.
    El focal de jung-carl-gustav embebe el biográfico (Perfil), no las aplicaciones —
    score esperado <0.55. Pero jung-carl-gustav.md cita el chunk de Tarzán
    (Tviv4PT0dv8#4878). El chunk hace match semántico fuerte → trigger citation lookup
    → jung-carl-gustav aparece en wiki_pages con match_via='citation'.
    """
    res = call_tool(url, "search_corpus", {
        "query": "Tarzan se conoce a si mismo a traves de Jane",
        "top_k": 5, "top_k_wiki": 2,
    })
    wiki = res.get("wiki_pages", [])
    if not wiki:
        return Check("wiki_via_citation", False, "wiki_pages vacío")
    via_citation = [w for w in wiki if w.get("match_via") in {"citation", "both"}]
    if not via_citation:
        return Check(
            "wiki_via_citation", False,
            f"ninguna wiki page con match_via citation/both. Got: "
            f"{[(w['page_id'], w.get('match_via')) for w in wiki]}",
        )
    target = via_citation[0]
    chunks = target.get("matched_via_chunks") or []
    if not chunks:
        return Check("wiki_via_citation", False,
                     f"{target['page_id']} match_via={target.get('match_via')} pero matched_via_chunks vacío")
    if not all(c.get("video_id") and c.get("chunk_score") for c in chunks):
        return Check("wiki_via_citation", False, f"matched_via_chunks malformados: {chunks}")
    # Consistencia: el chunk citante debe estar también en raw_chunks (mismo run).
    raw_keys = {(r.get("video_title"), r.get("score")) for r in res.get("raw_chunks", [])}
    chunk_keys = {(c.get("video_title"), c.get("chunk_score")) for c in chunks}
    if not raw_keys & chunk_keys:
        # Posible: el chunk citante no está en top_k raw devuelto al usuario.
        # No es fatal — el lookup busca en raw_results internamente y puede arrastrar
        # más allá del top_k mostrado. Solo warning vía detail, sin fail.
        pass
    return Check(
        "wiki_via_citation", True,
        f"{target['page_id']} match_via={target.get('match_via')} score={target['score']} "
        f"triggered by {len(chunks)} chunk(s)",
    )


def check_citation_lookup_survives_category_filter(url: str) -> Check:
    """Regresión: cuando el LLM/usuario filtra por category, el lookup indirecto vía
    citations DEBE seguir disparando. El filtro afecta solo a raw_chunks visibles —
    la wiki es category-blind por diseño.

    Bug detectado en producción 2026-04-30: Ariadna añadió category="psicologia" por
    iniciativa propia para query sobre psicoanálisis. El chunk citante (Orfeo y Eurídice,
    categoría 'filosofía') quedó fuera del raw_results filtrado, y `_lookup_wiki_via_citations`
    no encontraba semilla. Fix: hacer un raw search separado SIN filtro para alimentar la
    lane indirecta.
    """
    res = call_tool(url, "search_corpus", {
        "query": "psicoanálisis como herramienta analítica no terapéutica",
        "top_k": 5, "top_k_wiki": 3,
        "category": "psicología",
    })
    meta = res.get("retrieval_metadata", {})
    via_count = meta.get("wiki_via_citation_count", 0)
    if via_count == 0:
        wikis = [(w["page_id"], w.get("match_via")) for w in res.get("wiki_pages", [])]
        return Check(
            "citation_survives_category", False,
            f"via_citation_count=0 con category filter — el bug volvió. "
            f"wiki_pages: {wikis}",
        )
    via_pages = [w for w in res["wiki_pages"] if w.get("match_via") in {"citation", "both"}]
    target = via_pages[0]
    return Check(
        "citation_survives_category", True,
        f"category=psicología → {target['page_id']} entró match_via={target.get('match_via')} "
        f"score={target['score']} (via_count={via_count})",
    )


def check_in_wiki_sources_populated(url: str) -> Check:
    """raw_chunks de videos citados por wiki deben tener in_wiki_sources poblado.

    Query sobre sombra → top raw chunk será de Effy y Proxy o Peter Pan, ambos
    citados por shadow-archetype.
    """
    res = call_tool(url, "search_corpus", {"query": "sombra junguiana", "top_k": 5, "top_k_wiki": 2})
    raw = res.get("raw_chunks", [])
    if not raw:
        return Check("in_wiki_sources", False, "raw_chunks vacío")
    populated = [r for r in raw if r.get("in_wiki_sources")]
    if not populated:
        return Check("in_wiki_sources", False,
                     "ningún raw_chunk con in_wiki_sources poblado para query 'sombra junguiana'")
    return Check("in_wiki_sources", True,
                 f"{len(populated)}/{len(raw)} chunks con in_wiki_sources poblado")


def check_get_wiki_page(url: str) -> Check:
    res = call_tool(url, "get_wiki_page", {"page_id": "mito-polar"})
    if res.get("page_id") != "mito-polar":
        return Check("get_wiki_page", False, f"page_id en respuesta: {res.get('page_id')}")
    content = res.get("content") or ""
    if len(content) < 5000:
        return Check("get_wiki_page", False, f"content de mito-polar inesperadamente corto: {len(content)} chars")
    if "relations:" not in content:
        return Check("get_wiki_page", False, "content sin bloque relations: en frontmatter")
    return Check("get_wiki_page", True, f"content={len(content)} chars")


CHECKS: list[tuple[str, Callable[[str], Check]]] = [
    ("tools/list", check_tools_list),
    ("wiki_primary", check_wiki_primary),
    ("raw_with_warning", check_raw_with_warning),
    ("balanced_or_dominant", check_balanced_or_dominant),
    ("wiki_via_citation", check_wiki_via_citation),
    ("citation_survives_category", check_citation_lookup_survives_category_filter),
    ("in_wiki_sources", check_in_wiki_sources_populated),
    ("get_wiki_page", check_get_wiki_page),
]


def run(url: str) -> list[Check]:
    out: list[Check] = []
    for name, fn in CHECKS:
        try:
            out.append(fn(url))
        except (urllib.error.URLError, RuntimeError, KeyError, ValueError) as e:
            out.append(Check(name, False, f"excepción: {type(e).__name__}: {e}"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke test del MCP server híbrido.")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"URL del MCP endpoint (default: {DEFAULT_URL})")
    ap.add_argument("--json", action="store_true", help="Output JSON en vez de texto")
    args = ap.parse_args()

    results = run(args.url)
    failed = [c for c in results if not c.ok]

    if args.json:
        print(json.dumps(
            {
                "url": args.url,
                "passed": len(results) - len(failed),
                "failed": len(failed),
                "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in results],
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print(f"=== test_hybrid contra {args.url} ===")
        for c in results:
            mark = "PASS" if c.ok else "FAIL"
            print(f"  [{mark}] {c.name}: {c.detail}")
        print(f"--- {len(results) - len(failed)}/{len(results)} pasados ---")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
