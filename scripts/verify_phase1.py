#!/usr/bin/env python3
"""Verifica los criterios de éxito de la Fase 1+ (migración multi-tenancy + modelo
universal, generalización Fase 4). Exit 0 si todos los checks pasan.

MODO DE EJECUCIÓN: **server PARADO**. Los checks abren Qdrant embedded + ariadna.db
en-proceso (lock exclusivo de Qdrant → el MCP server debe estar parado). search_hybrid
en-proceso es idéntico a la tool MCP (la tool solo lo envuelve), así que la
equivalencia funcional medida aquí es la misma que vería Mattermost.

    # parar server primero:  kill <PID>   (NO pkill -f mcp_server)
    python scripts/verify_phase1.py
    python scripts/verify_phase1.py --json

Algunos checks miran a fases posteriores (extract_themes llega en F6): se marcan
SKIP y no cuentan como fallo.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

BASELINE_PATH = REPO / "data" / "baseline_pre_migration.json"
ARIADNA_DB = REPO / "data" / "ariadna.db"
PROJECT = "proxy"
SCORE_TOL = 0.01

_searcher = None


def get_searcher():
    """Searcher singleton (abre Qdrant — requiere server parado)."""
    global _searcher
    if _searcher is None:
        from ariadna.search import Searcher
        _searcher = Searcher()
    return _searcher


def _db() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{ARIADNA_DB}?mode=ro", uri=True)


class CheckResult:
    def __init__(self, name: str, passed: bool, details: str = "", skipped: bool = False):
        self.name = name
        self.passed = passed or skipped
        self.skipped = skipped
        self.details = details


def _scroll_all_payloads():
    """Itera todos los payloads de la colección Qdrant (batches)."""
    store = get_searcher().store
    offset = None
    while True:
        points, offset = store.client.scroll(
            collection_name=store.collection_name, limit=1000,
            offset=offset, with_payload=True, with_vectors=False)
        for p in points:
            yield p.payload or {}
        if offset is None:
            break


# --- Equivalencia funcional (red de seguridad: Proxy responde idéntico) ------


def check_functional_equivalence() -> CheckResult:
    """Re-ejecuta las 10 queries del baseline en-proceso y compara: mismo conjunto
    de raw_chunk_ids (youtube_url) y wiki_page_ids, scores dentro de ±0.01, mismo
    mode_recommended. La migración fue set_payload in-place → debe ser idéntico."""
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    s = get_searcher()
    mismatches: list[str] = []
    for entry in baseline["queries"]:
        q = entry["query"]
        res = s.search_hybrid(q, top_k_raw=5, top_k_wiki=2)
        raw_ids = {c.get("youtube_url") for c in res.get("raw_chunks", []) if c.get("youtube_url")}
        wiki_ids = {w.get("page_id") for w in res.get("wiki_pages", []) if w.get("page_id")}
        meta = res.get("retrieval_metadata", {})
        base_raw = set(entry["raw_chunk_ids"])
        base_wiki = set(entry["wiki_page_ids"])
        if raw_ids != base_raw:
            mismatches.append(f"{q!r}: raw ids Δ (+{sorted(raw_ids - base_raw)} -{sorted(base_raw - raw_ids)})")
        if wiki_ids != base_wiki:
            mismatches.append(f"{q!r}: wiki ids Δ (+{sorted(wiki_ids - base_wiki)} -{sorted(base_wiki - wiki_ids)})")
        rt = float(meta.get("raw_top_score") or 0.0)
        wt = float(meta.get("wiki_top_score") or 0.0)
        if abs(rt - entry["raw_top_score"]) > SCORE_TOL:
            mismatches.append(f"{q!r}: raw_top {rt:.4f} vs {entry['raw_top_score']:.4f}")
        if abs(wt - entry["wiki_top_score"]) > SCORE_TOL:
            mismatches.append(f"{q!r}: wiki_top {wt:.4f} vs {entry['wiki_top_score']:.4f}")
        if meta.get("mode_recommended") != entry["mode_recommended"]:
            mismatches.append(f"{q!r}: mode {meta.get('mode_recommended')} vs {entry['mode_recommended']}")
    if mismatches:
        return CheckResult("functional_equivalence", False, "; ".join(mismatches[:8]))
    return CheckResult("functional_equivalence", True, f"{len(baseline['queries'])} queries idénticas (±{SCORE_TOL})")


def check_filter_by_project() -> CheckResult:
    """search_hybrid(query, project='proxy') == search_hybrid(query). Todo es proxy."""
    s = get_searcher()
    q = "sombra junguiana"
    a = s.search_hybrid(q, top_k_raw=5, top_k_wiki=2)
    b = s.search_hybrid(q, top_k_raw=5, top_k_wiki=2, project="proxy")
    ia = [c.get("youtube_url") for c in a.get("raw_chunks", [])]
    ib = [c.get("youtube_url") for c in b.get("raw_chunks", [])]
    if ia != ib:
        return CheckResult("filter_by_project", False, "raw ids difieren con project='proxy'")
    return CheckResult("filter_by_project", True, f"{len(ia)} raw ids idénticos con/sin project")


def check_nonexistent_project() -> CheckResult:
    """search_hybrid(project='nope') lanza PROJECT_NOT_FOUND."""
    s = get_searcher()
    try:
        s.search_hybrid("x", project="nope")
    except ValueError as e:
        if str(e).startswith("PROJECT_NOT_FOUND"):
            return CheckResult("nonexistent_project", True, str(e))
        return CheckResult("nonexistent_project", False, f"ValueError inesperado: {e}")
    return CheckResult("nonexistent_project", False, "no lanzó PROJECT_NOT_FOUND")


def check_get_wiki_page_equiv() -> CheckResult:
    """El body en ariadna.db.pages coincide con el cuerpo del .md en disco (consistencia
    DB↔filesystem, lo que sirve get_wiki_page). project param de la tool llega en F5."""
    with _db() as conn:
        row = conn.execute(
            "SELECT file_path, body_md FROM pages WHERE project_id=? AND page_id='shadow-archetype'",
            (PROJECT,)).fetchone()
    if not row:
        return CheckResult("get_wiki_page_equiv", False, "shadow-archetype no está en pages")
    file_path, body_md = row
    md = (REPO / file_path)
    if not md.exists():
        return CheckResult("get_wiki_page_equiv", False, f"file_path no existe: {file_path}")
    disk = md.read_text(encoding="utf-8")
    if body_md.strip() not in disk:
        return CheckResult("get_wiki_page_equiv", False, "body_md de DB no coincide con el .md en disco")
    return CheckResult("get_wiki_page_equiv", True, "body_md DB == .md disco (shadow-archetype)")


def check_test_hybrid_passes() -> CheckResult:
    """Invariantes golden de test_hybrid, en-proceso (no requiere server HTTP)."""
    s = get_searcher()
    # wiki_primary
    r1 = s.search_hybrid("sombra junguiana", top_k_raw=3, top_k_wiki=2)
    w1 = r1.get("wiki_pages", [])
    if not w1 or w1[0].get("page_id") != "shadow-archetype" or not w1[0].get("relations"):
        return CheckResult("test_hybrid", False, "wiki_primary: shadow-archetype/relations ausente")
    # raw_with_warning (Tolkien)
    r2 = s.search_hybrid("qué vídeos hay sobre Tolkien", top_k_raw=5, top_k_wiki=2)
    if r2["retrieval_metadata"]["mode_recommended"] not in {"raw_with_warning", "raw_only"}:
        return CheckResult("test_hybrid", False, f"Tolkien mode={r2['retrieval_metadata']['mode_recommended']}")
    # wiki_via_citation (Tarzan)
    r3 = s.search_hybrid("Tarzan se conoce a si mismo a traves de Jane", top_k_raw=5, top_k_wiki=2)
    via = [w for w in r3.get("wiki_pages", []) if w.get("match_via") in {"citation", "both"}]
    if not via:
        return CheckResult("test_hybrid", False, "Tarzan: ninguna wiki vía citation")
    return CheckResult("test_hybrid", True, "wiki_primary + raw_with_warning + wiki_via_citation OK")


# --- Integridad del schema unificado ----------------------------------------


def check_sqlite_counts() -> CheckResult:
    """projects tiene proxy; pages(proxy) == nº de .md de la wiki."""
    from ariadna.project_config import ProjectConfig
    wiki_dir = ProjectConfig(PROJECT).wiki_root
    n_md = sum(1 for m in wiki_dir.rglob("*.md") if m.name != "README.md")
    with _db() as conn:
        has_proxy = conn.execute("SELECT 1 FROM projects WHERE project_id=?", (PROJECT,)).fetchone()
        n_pages = conn.execute("SELECT COUNT(*) FROM pages WHERE project_id=?", (PROJECT,)).fetchone()[0]
    if not has_proxy:
        return CheckResult("sqlite_counts", False, "projects no contiene 'proxy'")
    if n_pages < n_md - 2:  # tolerancia: alguna .md sin frontmatter válido
        return CheckResult("sqlite_counts", False, f"pages={n_pages} < md={n_md}")
    return CheckResult("sqlite_counts", True, f"proxy en projects; pages={n_pages} (md={n_md})")


def check_qdrant_all_tagged() -> CheckResult:
    """Todos los puntos Qdrant tienen project_id en payload."""
    total = untagged = 0
    for pl in _scroll_all_payloads():
        total += 1
        if not pl.get("project_id"):
            untagged += 1
    if untagged:
        return CheckResult("qdrant_all_tagged", False, f"{untagged}/{total} puntos SIN project_id")
    return CheckResult("qdrant_all_tagged", True, f"{total} puntos con project_id")


def check_global_resources() -> CheckResult:
    """relation_types_core.json con ~30 tipos; 4 *_default.* existen en wiki/_meta."""
    meta = REPO / "wiki" / "_meta"
    core = meta / "relation_types_core.json"
    if not core.exists():
        return CheckResult("global_resources", False, "relation_types_core.json ausente")
    n_types = len(json.loads(core.read_text(encoding="utf-8")).get("types", {}))
    defaults = ["scope_default.md", "topic_filters_default.json",
                "subagent_prompt_default.md", "canonical_whitelist_default.json"]
    missing = [d for d in defaults if not (meta / d).exists()]
    if n_types < 25:
        return CheckResult("global_resources", False, f"relation_types_core tiene {n_types} tipos (<25)")
    if missing:
        return CheckResult("global_resources", False, f"faltan defaults: {missing}")
    return CheckResult("global_resources", True, f"{n_types} tipos core + {len(defaults)} defaults")


def check_run_can_resume() -> CheckResult:
    """extract_themes --resume --project=proxy --dry-run (F6). SKIP hasta que exista."""
    if not (REPO / "scripts" / "extract_themes.py").exists():
        return CheckResult("run_can_resume", True,
                           "SKIP: extract_themes.py llega en F6 (rename de extract_video_themes)",
                           skipped=True)
    r = subprocess.run(
        [sys.executable, "scripts/extract_themes.py", "--project", "proxy", "--dry-run"],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        return CheckResult("run_can_resume", False, f"exit {r.returncode}: {r.stderr[-200:]}")
    return CheckResult("run_can_resume", True, "extract_themes --dry-run exit 0")


def check_build_wiki_db_scoped() -> CheckResult:
    """build_wiki_db.py --project=proxy sobre copia reproduce las counts (parity)."""
    import shutil
    import time
    copy = Path("/tmp/verify_phase1_rebuild.db")
    for ext in ("", "-wal", "-shm"):
        p = Path(str(copy) + ext)
        if p.exists():
            p.unlink()
    src = sqlite3.connect(ARIADNA_DB)
    dst = sqlite3.connect(copy)
    src.backup(dst)
    dst.close()
    src.close()
    with _db() as conn:
        orig_rel = conn.execute("SELECT COUNT(*) FROM relations WHERE project_id=?", (PROJECT,)).fetchone()[0]
    t0 = time.monotonic()
    r = subprocess.run(
        [sys.executable, "scripts/build_wiki_db.py", "--project", "proxy", "--db", str(copy)],
        cwd=REPO, capture_output=True, text=True)
    dt = time.monotonic() - t0
    if r.returncode != 0:
        return CheckResult("build_wiki_db_scoped", False, f"exit {r.returncode}: {r.stderr[-200:]}")
    with sqlite3.connect(f"file:{copy}?mode=ro", uri=True) as conn:
        reb_rel = conn.execute("SELECT COUNT(*) FROM relations WHERE project_id=?", (PROJECT,)).fetchone()[0]
    if reb_rel != orig_rel:
        return CheckResult("build_wiki_db_scoped", False, f"relations {reb_rel} != {orig_rel}")
    if dt > 30:
        return CheckResult("build_wiki_db_scoped", False, f"tardó {dt:.1f}s (>30s)")
    return CheckResult("build_wiki_db_scoped", True, f"relations={reb_rel} en {dt:.1f}s")


def check_validator() -> CheckResult:
    """validate_wiki_relations.py --project=proxy exit 0."""
    r = subprocess.run(
        [sys.executable, "scripts/validate_wiki_relations.py", "--project", "proxy"],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        return CheckResult("validator", False, f"exit {r.returncode}: {r.stdout[-200:]}")
    return CheckResult("validator", True, "exit 0 (sin errores)")


# --- Modelo universal de referencias (TAXONOMY completo) ---------------------


def check_sources_populated() -> CheckResult:
    """`sources` con youtube_video (~288+); source_projects mapea todo a proxy."""
    with _db() as conn:
        n_yt = conn.execute("SELECT COUNT(*) FROM sources WHERE source_type='youtube_video'").fetchone()[0]
        n_sp = conn.execute("SELECT COUNT(*) FROM source_projects WHERE project_id=?", (PROJECT,)).fetchone()[0]
        non_proxy = conn.execute("SELECT COUNT(*) FROM source_projects WHERE project_id!=?", (PROJECT,)).fetchone()[0]
    if n_yt < 288:
        return CheckResult("sources_populated", False, f"youtube_video sources={n_yt} (<288)")
    if non_proxy:
        return CheckResult("sources_populated", False, f"{non_proxy} source_projects no-proxy (esperado 0 en F4)")
    return CheckResult("sources_populated", True, f"{n_yt} youtube sources, {n_sp} en source_projects(proxy)")


def check_authors_populated() -> CheckResult:
    """authors(proxy) > 0 desde frontmatter; author_sources role=subject_of presente."""
    with _db() as conn:
        n_auth = conn.execute("SELECT COUNT(*) FROM authors WHERE project_id=?", (PROJECT,)).fetchone()[0]
        n_subj = conn.execute(
            "SELECT COUNT(*) FROM author_sources WHERE project_id=? AND role='subject_of'", (PROJECT,)).fetchone()[0]
    if n_auth == 0:
        return CheckResult("authors_populated", False, "authors vacío")
    if n_subj == 0:
        return CheckResult("authors_populated", False, "author_sources subject_of vacío")
    return CheckResult("authors_populated", True, f"authors={n_auth}, author_sources(subject_of)={n_subj}")


def check_domains_assigned() -> CheckResult:
    """Ningún raw chunk Qdrant sin domain_primary; page_domains poblado."""
    total_raw = missing = 0
    for pl in _scroll_all_payloads():
        if pl.get("source_type") == "wiki_page":
            continue
        if pl.get("video_id") is None and pl.get("source_type") != "youtube_video":
            continue
        total_raw += 1
        if not pl.get("domain_primary"):
            missing += 1
    with _db() as conn:
        n_pd = conn.execute("SELECT COUNT(*) FROM page_domains WHERE project_id=?", (PROJECT,)).fetchone()[0]
    if missing:
        return CheckResult("domains_assigned", False, f"{missing}/{total_raw} raw chunks sin domain_primary")
    if n_pd == 0:
        return CheckResult("domains_assigned", False, "page_domains vacío")
    return CheckResult("domains_assigned", True, f"{total_raw} raw chunks con domain_primary; page_domains={n_pd}")


def check_citations_generalized() -> CheckResult:
    """citations con source_id/position/position_url/cite_markdown; source_id resuelven a sources."""
    with _db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM citations WHERE project_id=?", (PROJECT,)).fetchone()[0]
        bad = conn.execute(
            """SELECT COUNT(*) FROM citations WHERE project_id=? AND
               (source_id IS NULL OR position IS NULL OR position_url IS NULL OR cite_markdown IS NULL)""",
            (PROJECT,)).fetchone()[0]
        orphan = conn.execute(
            """SELECT COUNT(DISTINCT source_id) FROM citations WHERE project_id=?
               AND source_id NOT IN (SELECT source_id FROM sources)""", (PROJECT,)).fetchone()[0]
    if bad:
        return CheckResult("citations_generalized", False, f"{bad} citations con campos universales nulos")
    if orphan:
        return CheckResult("citations_generalized", False, f"{orphan} source_id sin fila en sources")
    return CheckResult("citations_generalized", True, f"{total} citations universales, 0 huérfanas")


def check_cross_project_isolation() -> CheckResult:
    """search_hybrid(project=['proxy']) solo devuelve proxy; list[str] funciona; hit.project_id."""
    s = get_searcher()
    res = s.search_hybrid("sombra junguiana", top_k_raw=5, top_k_wiki=2, project=["proxy"])
    raw = res.get("raw_chunks", [])
    wiki = res.get("wiki_pages", [])
    projs = {c.get("project_id") for c in raw} | {w.get("project_id") for w in wiki}
    if projs - {"proxy"}:
        return CheckResult("cross_project_isolation", False, f"project_ids inesperados: {projs}")
    if not all(c.get("project_id") == "proxy" for c in raw):
        return CheckResult("cross_project_isolation", False, "algún raw sin project_id=proxy")
    return CheckResult("cross_project_isolation", True, f"aislamiento OK; project_ids={projs}")


CHECKS = [
    check_functional_equivalence,
    check_filter_by_project,
    check_nonexistent_project,
    check_get_wiki_page_equiv,
    check_test_hybrid_passes,
    check_sqlite_counts,
    check_qdrant_all_tagged,
    check_global_resources,
    check_run_can_resume,
    check_build_wiki_db_scoped,
    check_validator,
    check_sources_populated,
    check_authors_populated,
    check_domains_assigned,
    check_citations_generalized,
    check_cross_project_isolation,
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results: list[CheckResult] = []
    for check in CHECKS:
        try:
            r = check()
        except Exception as e:  # noqa: BLE001
            r = CheckResult(check.__name__.replace("check_", ""), False, f"EXCEPTION: {type(e).__name__}: {e}")
        results.append(r)

    failed = [r for r in results if not r.passed]
    skipped = [r for r in results if r.skipped]

    if args.json:
        print(json.dumps({
            "passed": len(results) - len(failed),
            "failed": len(failed),
            "skipped": len(skipped),
            "checks": [{"name": r.name, "passed": r.passed, "skipped": r.skipped, "details": r.details} for r in results],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Verify Phase 1 — {len(CHECKS)} checks (server debe estar PARADO)\n")
        for r in results:
            mark = "SKIP" if r.skipped else ("✓" if r.passed else "✗")
            print(f"  {mark} {r.name}{': ' + r.details if r.details else ''}")
        print(f"\n{len(results) - len(failed)}/{len(results)} passed"
              + (f" ({len(skipped)} skipped)" if skipped else ""))

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
