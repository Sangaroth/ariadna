#!/usr/bin/env python3
"""Worker de la cola de ingesta (research_queue). FSM con lock optimista.

Pipeline por item (plan §F):
  paper SIN bypass: download_paper (acquirer) → source_archive.store → summarize
                    (PaperAdapter) → extract_paper_to_pages + materialize → build_wiki_db.
  con bypass (summary inline, p.ej. ProxySummaries): salta acquire+summarize.
  común: registra la fuente en `sources`/`source_projects` (para que las citations
         resuelvan) y reconstruye las tablas wiki del proyecto en ariadna.db.

LOCK QDRANT (MVP): el worker NO indexa en Qdrant inline (lock embebido con el server).
Marca el item `done` (la wiki .md + ariadna.db son fuente de verdad, Qdrant es
reconstruible) y la indexación corre en VENTANA BATCH: `--index <project>` (con el
server parado) llama a index_wiki_to_qdrant.

Uso:
    python scripts/worker.py --project atlas --max 5            # procesa hasta 5 items
    python scripts/worker.py --once --project atlas            # un item y sale
    python scripts/worker.py --index atlas                     # ventana batch Qdrant (server parado)
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ariadna import research_queue as Q  # noqa: E402
from ariadna import source_archive as SA  # noqa: E402
from ariadna.acquire import ClaudePaperAcquirer  # noqa: E402
from ariadna.config import ARIADNA_DB_PATH, DATA_DIR  # noqa: E402
from ariadna.extract.paper import extract_paper_to_pages, materialize_pages  # noqa: E402
from ariadna.project_config import ProjectConfig  # noqa: E402
from ariadna.sources.registry import get_adapter  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("ariadna.worker")

STAGING_DIR = DATA_DIR / "sources" / "_staging"

# source_type de la cola (corto) → source_type canónico de `sources`.
_CANONICAL_SOURCE_TYPE = {"youtube": "youtube_video", "paper": "paper", "pdf": "paper",
                          "web": "web_article", "unknown": "note"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def register_source(db_path: Path, source_id: str, source_type: str, title: str,
                    source_file_hash: str | None, project: str, *,
                    ingest_method: str, abstract: str | None = None) -> None:
    """Inserta la fuente en `sources` (global, dedup) + `source_projects` (uso)."""
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute(
            """INSERT OR IGNORE INTO sources
               (source_id, source_type, title, abstract, ingest_method, source_file_hash,
                schema_version, created_at)
               VALUES (?,?,?,?,?,?,'2.0.0',?)""",
            (source_id, source_type, title, abstract, ingest_method, source_file_hash, _now()),
        )
        # actualiza el hash si llega tarde (fuente ya existía sin archivo).
        if source_file_hash:
            conn.execute(
                "UPDATE sources SET source_file_hash=COALESCE(source_file_hash, ?) WHERE source_id=?",
                (source_file_hash, source_id))
        conn.execute(
            "INSERT OR IGNORE INTO source_projects (source_id, project_id, ingested_at) VALUES (?,?,?)",
            (source_id, project, _now()))
        conn.commit()
    finally:
        conn.close()


def process_item(
    item: dict,
    *,
    acquirer=None,
    summarize_fn=None,
    extract_fn=extract_paper_to_pages,
    db_path: Path = ARIADNA_DB_PATH,
    staging_dir: Path = STAGING_DIR,
    sources_dir: Path = SA.SOURCES_DIR,
    scope_text: str = "",
) -> dict:
    """Procesa UN item ya reclamado (status=processing). Devuelve resumen.

    Inyectable (acquirer/summarize_fn/extract_fn) para test sin red/LLM. NO indexa en
    Qdrant (ventana batch aparte). Lanza excepción si algo falla (el caller marca failed).
    """
    import scripts.build_wiki_db as build_wiki_db

    project = item["project_id"]
    url = item["source_url"]
    qtype = item["source_type"]
    meta = item.get("metadata") or {}
    adapter = get_adapter(qtype)
    source_id = adapter.normalize_source_id(url)
    canonical_type = _CANONICAL_SOURCE_TYPE.get(qtype, "note")

    if meta.get("summary"):  # --- BYPASS bring-your-own-summary ---
        smeta = meta.get("source_metadata") or {}
        title = smeta.get("title") or source_id
        summary = meta["summary"]
        file_hash = None
        ingest_method = "external_summary"
        abstract = smeta.get("abstract")
    else:  # --- adquirir + sumarizar nativo ---
        if summarize_fn is None:
            summarize_fn = lambda blob, t: adapter.summarize(blob, t)  # noqa: E731
        doi = source_id.split(":", 1)[1] if ":" in source_id else source_id
        # bring-your-own-PDF SEGURO: referencia por content-hash del source_archive
        # (NUNCA un path crudo del cliente — sería lectura arbitraria de ficheros). El
        # hash llega en la columna source_file_hash (no en el source_metadata expuesto por MCP).
        pre_hash = item.get("source_file_hash")
        if pre_hash:
            pdf_bytes = SA.read_by_hash(pre_hash, db_path=db_path, sources_dir=sources_dir)
            file_hash = pre_hash
            pmeta = meta.get("source_metadata") or {}
        else:
            if acquirer is None:
                acquirer = ClaudePaperAcquirer()
            acquired = acquirer.download(doi, staging_dir)
            pdf_bytes = Path(acquired.path).read_bytes()
            arch = SA.store(pdf_bytes, "pdf", url, db_path=db_path, sources_dir=sources_dir)
            file_hash = arch["source_file_hash"]
            pmeta = acquirer.metadata(doi)
        title = pmeta.get("title") or source_id
        abstract = pmeta.get("abstract")
        ingest_method = "claude_summarizer"
        summary = summarize_fn(pdf_bytes, title)

    register_source(db_path, source_id, canonical_type, title, file_hash, project,
                    ingest_method=ingest_method, abstract=abstract)

    existing = _existing_page_ids(db_path, project)
    pages = extract_fn(summary, source_id, title, project,
                       existing_page_ids=existing, scope_text=scope_text)
    written = materialize_pages(pages, source_id, title, project)
    # build_wiki_db reconstruye ariadna.db (sin Qdrant → seguro inline con el server vivo).
    counts = build_wiki_db.rebuild(db_path, project)

    return {
        "source_id": source_id, "title": title, "source_file_hash": file_hash,
        "pages_written": [str(p.relative_to(REPO)) for p in written],
        "n_pages_written": len(written), "wiki_counts": counts, "indexed": False,
    }


def _existing_page_ids(db_path: Path, project: str) -> list[str]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return [r[0] for r in conn.execute(
            "SELECT page_id FROM pages WHERE project_id=?", (project,))]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _scope_text(project: str) -> str:
    p = ProjectConfig(project).scope
    return p.read_text(encoding="utf-8") if p.exists() else ""


def run_loop(project: str | None, worker_id: str, max_items: int, db_path: Path) -> int:
    processed = 0
    while max_items <= 0 or processed < max_items:
        item = Q.claim_next(worker_id, project=project, db_path=db_path)
        if item is None:
            log.info("cola vacía (project=%s) — fin", project)
            break
        rid = item["request_id"]
        log.info("procesando %s (%s · %s)", rid, item["source_type"], item["source_url"])
        try:
            res = process_item(item, db_path=db_path, scope_text=_scope_text(item["project_id"]))
            Q.mark_done(rid, notes=f"{res['n_pages_written']} páginas; index pendiente (batch)", db_path=db_path)
            log.info("done %s → %d páginas wiki", rid, res["n_pages_written"])
            processed += 1
        except Exception as e:  # noqa: BLE001
            r = Q.mark_failed(rid, f"{type(e).__name__}: {e}", db_path=db_path)
            log.error("failed %s (%s): %s", rid, r["status"], e)
            processed += 1
    return processed


def index_batch(project: str) -> int:
    """Ventana batch: indexa la wiki del proyecto en Qdrant (server DEBE estar parado)."""
    import subprocess
    log.info("ventana batch: index_wiki_to_qdrant --project %s (server debe estar parado)", project)
    r = subprocess.run([sys.executable, "scripts/index_wiki_to_qdrant.py", "--project", project],
                       cwd=REPO)
    return r.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default=None, help="acotar a un proyecto (None = cualquiera)")
    ap.add_argument("--worker-id", default="worker-1")
    ap.add_argument("--max", type=int, default=0, help="máximo de items (0 = hasta vaciar)")
    ap.add_argument("--once", action="store_true", help="procesa un solo item")
    ap.add_argument("--index", metavar="PROJECT", help="ventana batch: indexa la wiki del proyecto en Qdrant")
    ap.add_argument("--db", type=Path, default=ARIADNA_DB_PATH)
    args = ap.parse_args()

    if args.index:
        return index_batch(args.index)

    n = run_loop(args.project, args.worker_id, 1 if args.once else args.max, args.db)
    log.info("worker fin: %d items procesados", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
