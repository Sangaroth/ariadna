#!/usr/bin/env python3
"""update_proxy.py — punto único de actualización incremental del corpus Proxy.

Cuando ProxySummaries tiene summaries nuevos (vídeos del canal Proxy recién
sumarizados), este script los integra en Ariadna end-to-end, en el orden
correcto y respetando la idempotencia de cada paso:

  1. SOURCES   scripts/populate_sources_from_proxysummaries.py
               → registra cada vídeo en data/ariadna.db (sources/source_projects).
               Idempotente (INSERT OR IGNORE/REPLACE). Server vivo OK (ariadna.db WAL).

  2. WIKI L1   overnight_run.run_overnight()
               → extract → aggregate → compile → build_wiki_db, por LOTES.
               INCREMENTAL: solo procesa vídeos no registrados en
               processed_videos.json (auto-bootstrap desde extraction_runs/).
               Cuesta LLM (claude -p). Server vivo OK (nada toca Qdrant aquí).

  3. QDRANT    [server PARADO — lock embedded de Qdrant]
                 a. ariadna.build_index           raw chunks / IdeaBlocks del
                                                   summary.md (upsert idempotente
                                                   por chunk_id; re-embeda todo el
                                                   corpus, los nuevos entran solos).
                 b. index_wiki_to_qdrant --project proxy
                                                   full reindex de wiki_pages
                                                   (idempotente: borra+reinserta).
               Reinicia el MCP server si estaba vivo.

Sin paso 3, los vídeos nuevos NO son buscables en search_corpus. El paso 2 es
el único con coste LLM; los pasos 1 y 3a son idempotentes (upsert) y el 3b es
full-reindex rápido.

Uso:
    python scripts/update_proxy.py                  # flujo completo
    python scripts/update_proxy.py --dry-run        # plan + nº pendientes, no ejecuta
    python scripts/update_proxy.py --skip-wiki      # solo sources + raw + qdrant (sin LLM)
    python scripts/update_proxy.py --skip-raw       # no re-indexa raw chunks
    python scripts/update_proxy.py --batch-size 5 --max-batches 10
    python scripts/update_proxy.py --no-restart     # no relanzar el server tras Qdrant
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Re-exec bajo el python del venv ANTES de cualquier import que dependa de
# `ariadna`. Sin esto, lanzar `python scripts/update_proxy.py` sin activar el
# venv usa el python del sistema (sin el paquete `ariadna`) y todos los
# subprocesos —que heredan sys.executable— petan con ModuleNotFoundError.
_REPO = Path(__file__).resolve().parent.parent
_VENV_PY = _REPO / ".venv" / "bin" / "python"
if _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    os.execv(str(_VENV_PY), [str(_VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_video_themes import DEFAULT_CORPUS, REPO, discover_videos  # noqa: E402
from extract_incremental import bootstrap_from_extraction_runs, load_processed  # noqa: E402
from overnight_run import run_overnight  # noqa: E402

PY = sys.executable  # tras el re-exec, esto es el python del venv
MCP_PORTS = (8765, 8080)  # puertos donde el server puede estar escuchando


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def banner(msg: str) -> None:
    print(f"\n{'=' * 70}\n{msg}\n{'=' * 70}", flush=True)


def run_step(cmd: list[str], name: str, timeout: int | None = None) -> bool:
    """Lanza un subproceso, hace stream del rc. Devuelve True si rc==0."""
    print(f"[update_proxy] → {name}: {' '.join(str(c) for c in cmd)}", flush=True)
    rc = subprocess.run(cmd, cwd=REPO, timeout=timeout).returncode
    if rc != 0:
        print(f"[update_proxy] ✗ {name} falló (rc={rc})", flush=True)
        return False
    print(f"[update_proxy] ✓ {name}", flush=True)
    return True


def detect_server() -> tuple[int | None, int | None]:
    """Devuelve (pid, port) del MCP server vivo, o (None, None)."""
    try:
        out = subprocess.run(
            ["pgrep", "-f", "ariadna.mcp_server"],
            capture_output=True, text=True,
        ).stdout.strip()
    except FileNotFoundError:
        out = ""
    pid = int(out.splitlines()[0]) if out else None
    port = None
    if pid is not None:
        ss = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True).stdout
        for p in MCP_PORTS:
            if f":{p} " in ss and f"pid={pid}" in ss:
                port = p
                break
        port = port or MCP_PORTS[0]
    return pid, port


def stop_server(pid: int) -> None:
    print(f"[update_proxy] parando MCP server (pid={pid}) para liberar lock Qdrant", flush=True)
    subprocess.run(["kill", str(pid)])
    time.sleep(3)


def start_server(port: int) -> None:
    print(f"[update_proxy] reiniciando MCP server en :{port} (--warm)", flush=True)
    with open("/tmp/ariadna.log", "ab") as logf:
        subprocess.Popen(
            [PY, "-m", "ariadna.mcp_server", "--port", str(port), "--warm"],
            cwd=REPO, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True,
        )
    time.sleep(5)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--batch-size", type=int, default=5, help="vídeos por lote en la fase wiki")
    ap.add_argument("--max-batches", type=int, default=None, help="default: hasta agotar pendientes")
    ap.add_argument("--skip-sources", action="store_true", help="no repoblar sources en ariadna.db")
    ap.add_argument("--skip-wiki", action="store_true", help="no generar wiki (sin coste LLM)")
    ap.add_argument("--skip-raw", action="store_true", help="no re-indexar raw chunks en Qdrant")
    ap.add_argument("--skip-qdrant", action="store_true", help="no tocar Qdrant (ni raw ni wiki)")
    ap.add_argument("--no-restart", action="store_true", help="no relanzar el server tras Qdrant")
    ap.add_argument("--allow-dirty-start", action="store_true",
                    help="no abortar la fase wiki si el árbol git no está limpio")
    ap.add_argument("--dry-run", action="store_true", help="muestra el plan y los pendientes; no ejecuta")
    args = ap.parse_args()

    # Pendientes (incremental) — para el resumen / dry-run.
    # Si processed_videos.json no existe/está vacío, el estado real vive en
    # extraction_runs/; replicamos en memoria el auto-bootstrap que hace
    # run_overnight para que el conteo sea fiel (no escribimos el archivo aquí).
    all_videos = discover_videos(args.corpus)
    state = load_processed()
    if not state.get("videos"):
        bootstrap_from_extraction_runs(state)
    processed = set(state.get("videos", {}).keys())
    pending = [v for v in all_videos if v.video_id not in processed]

    banner("update_proxy — plan")
    print(f"corpus            : {args.corpus}")
    print(f"vídeos totales    : {len(all_videos)}")
    print(f"ya procesados     : {len(processed)} (processed_videos.json)")
    print(f"pendientes (wiki) : {len(pending)}")
    print(f"pasos             : "
          f"{'sources ' if not args.skip_sources else ''}"
          f"{'wiki ' if not args.skip_wiki else ''}"
          f"{'' if args.skip_qdrant else ('raw ' if not args.skip_raw else '') + 'wiki-qdrant'}")
    if pending:
        for v in pending[:30]:
            print(f"  · {v.video_id}  {getattr(v, 'title', '')[:60]}")
        if len(pending) > 30:
            print(f"  … (+{len(pending) - 30} más)")

    if args.dry_run:
        print("\n[dry-run] nada ejecutado.")
        return 0

    failures: list[str] = []

    # 1) SOURCES
    if not args.skip_sources:
        banner("1/3 · SOURCES → ariadna.db")
        if not run_step(
            [PY, "scripts/populate_sources_from_proxysummaries.py"],
            "populate_sources", timeout=300,
        ):
            failures.append("sources")

    # 2) WIKI L1 (incremental, LLM) — solo si hay pendientes
    if not args.skip_wiki:
        banner("2/3 · WIKI L1 → extract/aggregate/compile/build_wiki_db (incremental)")
        if not pending:
            print("[update_proxy] sin vídeos pendientes — salto la fase wiki.")
        else:
            wiki_args = argparse.Namespace(
                corpus=args.corpus,
                batch_size=args.batch_size,
                max_batches=args.max_batches,
                apply=True,
                reindex_qdrant=False,  # Qdrant lo hace la fase 3 (una vez, server parado)
                allow_dirty_start=args.allow_dirty_start,
            )
            status = run_overnight(wiki_args)
            print(f"[update_proxy] overnight status: {status}")
            if not status.startswith(("EXHAUSTED_OK", "DONE", "OK", "MAX_BATCHES")):
                failures.append(f"wiki({status})")

    # 3) QDRANT (server parado)
    if not args.skip_qdrant:
        banner("3/3 · QDRANT → raw chunks + wiki_pages (server parado)")
        pid, port = detect_server()
        if pid:
            stop_server(pid)
        try:
            if not args.skip_raw:
                if not run_step([PY, "-m", "ariadna.build_index"], "build_index (raw)", timeout=1800):
                    failures.append("raw")
            if not run_step(
                [PY, "scripts/index_wiki_to_qdrant.py", "--project", "proxy"],
                "index_wiki_to_qdrant", timeout=600,
            ):
                failures.append("wiki-qdrant")
        finally:
            if pid and not args.no_restart:
                start_server(port or MCP_PORTS[0])

    banner("update_proxy — fin")
    if failures:
        print(f"✗ con fallos: {', '.join(failures)}")
        return 1
    print("✓ todo correcto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
