#!/usr/bin/env python3
"""Verifica los criterios de la Fase 5 (tools MCP de proyectos + cola + cross-project).

MODO: server VIVO (tests vía MCP HTTP, como Mattermost). Crea proyectos de prueba
con prefijo `vp2-` y los LIMPIA al final (dirs + filas DB). Idempotente.

    python scripts/verify_phase2.py
    python scripts/verify_phase2.py --json --url http://127.0.0.1:8080/mcp
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ARIADNA_DB = REPO / "data" / "ariadna.db"
DEFAULT_URL = "http://127.0.0.1:8080/mcp"
PREFIX = "vp2-"


class CheckResult:
    def __init__(self, name: str, passed: bool, details: str = ""):
        self.name = name
        self.passed = passed
        self.details = details


def mcp_call(url: str, method: str, params: dict | None = None) -> dict:
    payload: dict = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    for line in body.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])
    return json.loads(body)


def tool(url: str, name: str, args: dict) -> dict:
    resp = mcp_call(url, "tools/call", {"name": name, "arguments": args})
    if "error" in resp:
        raise RuntimeError(f"MCP error en {name}: {resp['error']}")
    sc = resp["result"].get("structuredContent") or {}
    if "result" in sc:
        return sc["result"]
    for c in resp["result"].get("content", []):
        if c.get("type") == "text":
            return json.loads(c["text"])
    return sc


def list_tool_names(url: str) -> set[str]:
    return {t["name"] for t in mcp_call(url, "tools/list").get("result", {}).get("tools", [])}


def cleanup() -> None:
    """Borra proyectos vp2-* (filas DB + dirs)."""
    conn = sqlite3.connect(ARIADNA_DB)
    try:
        conn.execute("DELETE FROM research_queue WHERE project_id LIKE ?", (PREFIX + "%",))
        conn.execute("DELETE FROM projects WHERE project_id LIKE ?", (PREFIX + "%",))
        conn.commit()
    finally:
        conn.close()
    projects_dir = REPO / "projects"
    if projects_dir.is_dir():
        for d in projects_dir.glob(PREFIX + "*"):
            shutil.rmtree(d, ignore_errors=True)


# --- checks: create_project --------------------------------------------------


def check_create_project_basic(url: str) -> CheckResult:
    r = tool(url, "create_project", {"slug": PREFIX + "basic", "name": "VP2 Basic"})
    if r.get("project_id") != PREFIX + "basic":
        return CheckResult("create_project_basic", False, f"sin project_id: {r}")
    meta = REPO / "projects" / (PREFIX + "basic") / "_meta"
    wiki = REPO / "projects" / (PREFIX + "basic") / "wiki" / "concepts" / ".gitkeep"
    if not (meta / "relation_types_ext.json").exists() or not wiki.exists():
        return CheckResult("create_project_basic", False, "estructura de dirs incompleta")
    return CheckResult("create_project_basic", True, f"{len(r.get('paths_created', []))} rutas creadas")


def check_create_project_duplicate(url: str) -> CheckResult:
    r = tool(url, "create_project", {"slug": PREFIX + "basic", "name": "dup"})
    return CheckResult("create_project_duplicate", r.get("code") == "SLUG_DUPLICATE", r.get("code", str(r)))


def check_create_project_invalid_slug(url: str) -> CheckResult:
    bad = ["VP2-Bad", "vp2 bad", "-vp2bad", "vp2bad--", "1vp2bad", "ab_cd"]
    for slug in bad:
        r = tool(url, "create_project", {"slug": slug, "name": "x"})
        if r.get("code") != "SLUG_INVALID":
            return CheckResult("create_project_invalid_slug", False, f"{slug!r} no rechazado: {r.get('code')}")
    return CheckResult("create_project_invalid_slug", True, f"{len(bad)} slugs inválidos rechazados")


def check_create_project_incompatible_options(url: str) -> CheckResult:
    r = tool(url, "create_project", {"slug": PREFIX + "combo", "name": "x",
                                      "seed_from_templates": True, "inherit_from": "proxy"})
    if r.get("code") != "INCOMPATIBLE_OPTIONS":
        return CheckResult("create_project_incompatible_options", False, str(r))
    if (REPO / "projects" / (PREFIX + "combo")).exists():
        return CheckResult("create_project_incompatible_options", False, "creó estado pese al error")
    return CheckResult("create_project_incompatible_options", True, "INCOMPATIBLE_OPTIONS sin estado")


def check_create_project_seed_from_templates(url: str) -> CheckResult:
    tool(url, "create_project", {"slug": PREFIX + "seed", "name": "x", "seed_from_templates": True})
    meta = REPO / "projects" / (PREFIX + "seed") / "_meta"
    gmeta = REPO / "wiki" / "_meta"
    pairs = [("scope.md", "scope_default.md"), ("topic_filters.json", "topic_filters_default.json"),
             ("subagent_prompt.md", "subagent_prompt_default.md"),
             ("canonical_whitelist.json", "canonical_whitelist_default.json")]
    for local, default in pairs:
        lp, dp = meta / local, gmeta / default
        if not dp.exists():
            continue  # default no existe → no exigible
        if not lp.exists() or lp.read_bytes() != dp.read_bytes():
            return CheckResult("create_project_seed_from_templates", False, f"{local} != {default}")
    return CheckResult("create_project_seed_from_templates", True, "overrides idénticos a los defaults")


def check_create_project_inherit_from(url: str) -> CheckResult:
    r = tool(url, "create_project", {"slug": PREFIX + "inherit", "name": "x", "inherit_from": "proxy"})
    if "error" in r:
        return CheckResult("create_project_inherit_from", False, str(r))
    meta = REPO / "projects" / (PREFIX + "inherit") / "_meta"
    proxy_meta = REPO / "projects" / "proxy" / "_meta"
    copied = [f for f in proxy_meta.iterdir() if f.is_file()]
    for f in copied:
        if not (meta / f.name).exists() or (meta / f.name).read_bytes() != f.read_bytes():
            return CheckResult("create_project_inherit_from", False, f"{f.name} no heredado idéntico")
    return CheckResult("create_project_inherit_from", True, f"{len(copied)} overrides heredados de proxy")


# --- checks: add_to_research_queue ------------------------------------------


def check_add_youtube_url(url: str) -> CheckResult:
    r = tool(url, "add_to_research_queue", {"project": PREFIX + "q", "source_url": "https://youtu.be/abc"})
    return CheckResult("add_youtube_url", r.get("detected_source_type") == "youtube", r.get("detected_source_type", str(r)))


def check_add_arxiv_url(url: str) -> CheckResult:
    r = tool(url, "add_to_research_queue", {"project": PREFIX + "q", "source_url": "https://arxiv.org/abs/2401.1"})
    return CheckResult("add_arxiv_url", r.get("detected_source_type") == "paper", r.get("detected_source_type", str(r)))


def check_add_pdf_url(url: str) -> CheckResult:
    r = tool(url, "add_to_research_queue", {"project": PREFIX + "q", "source_url": "http://x.org/doc.pdf"})
    return CheckResult("add_pdf_url", r.get("detected_source_type") == "pdf", r.get("detected_source_type", str(r)))


def check_add_web_url(url: str) -> CheckResult:
    r = tool(url, "add_to_research_queue", {"project": PREFIX + "q", "source_url": "https://example.com/post"})
    return CheckResult("add_web_url", r.get("detected_source_type") == "web", r.get("detected_source_type", str(r)))


def check_add_unknown_url(url: str) -> CheckResult:
    r = tool(url, "add_to_research_queue", {"project": PREFIX + "q", "source_url": "ftp://x/y"})
    return CheckResult("add_unknown_url", r.get("detected_source_type") == "unknown", r.get("detected_source_type", str(r)))


def check_add_duplicate(url: str) -> CheckResult:
    u = "https://youtu.be/dupcheck"
    a = tool(url, "add_to_research_queue", {"project": PREFIX + "q", "source_url": u})
    b = tool(url, "add_to_research_queue", {"project": PREFIX + "q", "source_url": u})
    ok = a.get("was_duplicate") is False and b.get("was_duplicate") is True and a.get("request_id") == b.get("request_id")
    return CheckResult("add_duplicate", ok, f"add1={a.get('was_duplicate')} add2={b.get('was_duplicate')}")


def check_add_explicit_source_type_respected(url: str) -> CheckResult:
    # URL youtube pero el caller fuerza source_type=paper → se respeta.
    r = tool(url, "add_to_research_queue",
             {"project": PREFIX + "q", "source_url": "https://youtu.be/forced", "source_type": "paper"})
    return CheckResult("add_explicit_source_type_respected", r.get("detected_source_type") == "paper",
                       r.get("detected_source_type", str(r)))


def check_add_project_not_found(url: str) -> CheckResult:
    r = tool(url, "add_to_research_queue", {"project": PREFIX + "ghost", "source_url": "https://youtu.be/x"})
    return CheckResult("add_project_not_found", r.get("code") == "PROJECT_NOT_FOUND", r.get("code", str(r)))


# --- checks: list_research_queue / cancel -----------------------------------


def check_list_queue_filtered(url: str) -> CheckResult:
    r = tool(url, "list_research_queue", {"project": PREFIX + "q", "status": "pending", "source_type": "paper"})
    if "items" not in r:
        return CheckResult("list_queue_filtered", False, str(r))
    bad = [i for i in r["items"] if i["source_type"] != "paper" or i["status"] != "pending"]
    return CheckResult("list_queue_filtered", not bad, f"{len(r['items'])} items paper/pending, {len(bad)} fuera de filtro")


def check_list_queue_cross_all(url: str) -> CheckResult:
    r = tool(url, "list_research_queue", {"project": None, "status": "all", "limit": 200})
    projs = {i["project_id"] for i in r.get("items", [])}
    return CheckResult("list_queue_cross_all", (PREFIX + "q") in projs, f"projects en cola: {sorted(projs)}")


def check_list_queue_invalid_status(url: str) -> CheckResult:
    r = tool(url, "list_research_queue", {"status": "bogus"})
    return CheckResult("list_queue_invalid_status", r.get("code") == "INVALID_STATUS", r.get("code", str(r)))


def check_cancel_pending(url: str) -> CheckResult:
    a = tool(url, "add_to_research_queue", {"project": PREFIX + "q", "source_url": "https://youtu.be/tocancel"})
    r = tool(url, "cancel_request", {"request_id": a["request_id"]})
    ok = r.get("previous_status") == "pending" and r.get("current_status") == "cancelled"
    return CheckResult("cancel_pending", ok, f"{r.get('previous_status')}→{r.get('current_status')}")


def check_cancel_already_cancelled(url: str) -> CheckResult:
    a = tool(url, "add_to_research_queue", {"project": PREFIX + "q", "source_url": "https://youtu.be/twice"})
    tool(url, "cancel_request", {"request_id": a["request_id"]})
    r = tool(url, "cancel_request", {"request_id": a["request_id"]})
    ok = r.get("previous_status") == "cancelled" and r.get("current_status") == "cancelled"
    return CheckResult("cancel_already_cancelled", ok, f"no-op {r.get('current_status')}")


def check_cancel_not_found(url: str) -> CheckResult:
    r = tool(url, "cancel_request", {"request_id": "no-such-id"})
    return CheckResult("cancel_not_found", r.get("code") == "REQUEST_NOT_FOUND", r.get("code", str(r)))


# --- checks: list_projects / obsolete tools / cross-project search ----------


def check_list_projects_counts(url: str) -> CheckResult:
    r = tool(url, "list_projects", {})
    by_id = {p["project_id"]: p for p in r.get("projects", [])}
    if "proxy" not in by_id:
        return CheckResult("list_projects_counts", False, "proxy ausente")
    p = by_id["proxy"]
    if p["n_pages"] < 200 or p["n_chunks"] < 1000:
        return CheckResult("list_projects_counts", False, f"counts proxy bajos: {p}")
    return CheckResult("list_projects_counts", True, f"proxy n_pages={p['n_pages']} n_chunks={p['n_chunks']}")


def check_obsolete_tools_removed(url: str) -> CheckResult:
    names = list_tool_names(url)
    leftover = {"get_video_summary", "list_videos"} & names
    return CheckResult("obsolete_tools_removed", not leftover, f"presentes: {sorted(leftover) or 'ninguna'}; tools={sorted(names)}")


def check_search_project_list(url: str) -> CheckResult:
    r = tool(url, "search_corpus", {"query": "sombra junguiana", "top_k": 3, "project": ["proxy"]})
    raw = r.get("raw_chunks", [])
    if not raw:
        return CheckResult("search_project_list", False, "sin raw_chunks con project=['proxy']")
    projs = {c.get("project_id") for c in raw}
    return CheckResult("search_project_list", projs == {"proxy"}, f"project_ids={projs}")


def check_search_project_provenance(url: str) -> CheckResult:
    r = tool(url, "search_corpus", {"query": "mito polar", "top_k": 3})
    raw = r.get("raw_chunks", [])
    meta = r.get("retrieval_metadata", {})
    if not raw or not all(c.get("project_id") for c in raw):
        return CheckResult("search_project_provenance", False, "algún hit sin project_id")
    if "projects_seen" not in meta:
        return CheckResult("search_project_provenance", False, "retrieval_metadata sin projects_seen")
    return CheckResult("search_project_provenance", True, f"projects_seen={meta['projects_seen']}")


CHECKS = [
    check_create_project_basic,
    check_create_project_duplicate,
    check_create_project_invalid_slug,
    check_create_project_incompatible_options,
    check_create_project_seed_from_templates,
    check_create_project_inherit_from,
    check_add_youtube_url,
    check_add_arxiv_url,
    check_add_pdf_url,
    check_add_web_url,
    check_add_unknown_url,
    check_add_duplicate,
    check_add_explicit_source_type_respected,
    check_add_project_not_found,
    check_list_queue_filtered,
    check_list_queue_cross_all,
    check_list_queue_invalid_status,
    check_cancel_pending,
    check_cancel_already_cancelled,
    check_cancel_not_found,
    check_list_projects_counts,
    check_obsolete_tools_removed,
    check_search_project_list,
    check_search_project_provenance,
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cleanup()
    # Proyecto base para las checks de cola.
    tool(args.url, "create_project", {"slug": PREFIX + "q", "name": "VP2 queue"})

    results: list[CheckResult] = []
    try:
        for check in CHECKS:
            try:
                results.append(check(args.url))
            except Exception as e:  # noqa: BLE001
                results.append(CheckResult(check.__name__.replace("check_", ""), False,
                                           f"EXCEPTION: {type(e).__name__}: {e}"))
    finally:
        cleanup()

    failed = [r for r in results if not r.passed]
    if args.json:
        print(json.dumps({"passed": len(results) - len(failed), "failed": len(failed),
                          "checks": [{"name": r.name, "passed": r.passed, "details": r.details} for r in results]},
                         ensure_ascii=False, indent=2))
    else:
        print(f"Verify Phase 2 — {len(CHECKS)} checks (server vivo)\n")
        for r in results:
            print(f"  {'✓' if r.passed else '✗'} {r.name}{': ' + r.details if r.details else ''}")
        print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
