#!/usr/bin/env python3
"""overnight_run.py — orquestador para barrido completo del corpus durante la noche.

Procesa los vídeos pendientes (no en wiki/_meta/processed_videos.json) en
LOTES. Cada lote: extract → aggregate → COMPILE (rewrite coherente página
por página) → commit → rebuild wiki.db → loop.

Nota arquitectónica (postmortem 2026-05-02): la operación primaria del
ingest Karpathy es COMPILE, no apply diff incremental. El bucle anterior
extract→apply→loop producía golem (concatenación de inserts crudos).
El bucle correcto extract→compile→loop hace rewrite coherente por página
tomando seed + nuevo material del batch como inputs unificados.

Para si:
  - 2 lotes consecutivos sin ningún vídeo procesado con éxito (signal de
    problema sistémico: rate-limit, prompt roto, etc.)
  - git commit/apply falla
  - Espacio en disco < 1GB
  - Stderr de claude contiene patrones de rate-limit / quota exhausted

Estado persistente:
  wiki/_meta/processed_videos.json — registro acumulado (extract_incremental)
  wiki/_meta/extraction_runs/overnight_<TS>_b<NNN>/ — un run por lote

Logs:
  wiki/_meta/extraction_runs/overnight_<TS>/orchestrator.log — log master
  wiki/_meta/extraction_runs/overnight_<TS>/STATUS.txt — estado final

Uso:
    # Lanzamiento típico antes de dormir
    nohup python scripts/overnight_run.py > /tmp/overnight.log 2>&1 &

    # Personalizar
    python scripts/overnight_run.py --batch-size 5 --max-batches 60

    # Solo extracción, sin tocar wiki (más conservador)
    python scripts/overnight_run.py --no-apply

    # Reindexar Qdrant tras cada lote (requiere parar MCP server). Default off.
    python scripts/overnight_run.py --reindex-qdrant

A la mañana siguiente:
  cat wiki/_meta/extraction_runs/overnight_<TS>/STATUS.txt
  git log --oneline -30
"""
from __future__ import annotations

import argparse
import json
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_video_themes import (  # noqa: E402
    DEFAULT_CORPUS,
    REPO,
    RUNS_DIR,
    aggregate as extractor_aggregate,
    discover_videos,
    run as extractor_run,
)
from extract_incremental import (  # noqa: E402
    AGG_FILES,
    bootstrap_from_extraction_runs,
    load_processed,
    save_processed,
    update_state_from_run,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MIN_FREE_DISK_GB = 1
SLEEP_BETWEEN_BATCHES_S = 30
MAX_CONSECUTIVE_EMPTY_BATCHES = 2

# Patrones en stderr/stdout que indican fallo crítico de la cuota Max o
# rate-limit del API. Caso-insensitive substring match.
CRITICAL_PATTERNS = [
    "quota exceeded",
    "rate limit",
    "rate_limit",
    "usage limit reached",
    "anthropic error",
    "authentication failed",
    "credentials_error",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class CriticalError(Exception):
    """Disparador de stop en el bucle principal."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str, level: str = "INFO") -> None:
    line = f"[{now_iso()}] {level} {msg}"
    print(line, flush=True)
    if LOG_PATH:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


LOG_PATH: Path | None = None


def free_disk_gb(path: Path) -> float:
    stat = shutil.disk_usage(path)
    return stat.free / (1024**3)


def run_subprocess(cmd: list[str], description: str, timeout: int = 600) -> tuple[int, str, str]:
    """Ejecuta subprocess capturando stdout/stderr. Devuelve (rc, stdout, stderr)."""
    log(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=REPO)
    if proc.stdout.strip():
        log(f"stdout: {proc.stdout.strip()[-500:]}", level="DEBUG")
    if proc.stderr.strip():
        log(f"stderr: {proc.stderr.strip()[-500:]}", level="DEBUG")
    return proc.returncode, proc.stdout, proc.stderr


def detect_critical_in_output(text: str) -> str | None:
    low = text.lower()
    for pat in CRITICAL_PATTERNS:
        if pat in low:
            return pat
    return None


# ---------------------------------------------------------------------------
# Operaciones por lote
# ---------------------------------------------------------------------------


def extract_batch(batch, run_id: str) -> tuple[int, int, str]:
    """Ejecuta el extractor sobre un batch. Devuelve (n_done, n_failed, stderr)."""
    log(f"extract: {len(batch)} videos → {run_id}")
    try:
        extractor_run(run_id, batch, pilot=False)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        log(f"extractor crashed: {e}", level="ERROR")
        return 0, len(batch), str(e)

    # Lee state.json del run para contar done/failed reales
    state_path = RUNS_DIR / run_id / "state.json"
    if not state_path.exists():
        return 0, len(batch), "no state.json after extractor_run"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    n_done = len(state.get("videos_done", []))
    n_failed = len(state.get("videos_failed", []))
    return n_done, n_failed, ""


def aggregate_batch(run_id: str) -> dict:
    log(f"aggregate: {run_id}")
    extractor_aggregate(run_id)
    stats_path = RUNS_DIR / run_id / "aggregation_stats.json"
    if stats_path.exists():
        return json.loads(stats_path.read_text(encoding="utf-8"))
    return {}


COMMITTABLE_AGG_FILES = {
    "discard_log.json",
    "pending_updates.json",
    "promote_queue.json",
    "thesis_candidates.json",
    "blocks_filtered.json",
    "aggregation_stats.json",
    # state.json y applied_log.json se excluyen aquí:
    # - state.json: gitignored (control efímero, no se commitea)
    # - applied_log.json: se commitea junto al apply, no aquí
}


def commit_aggregator_outputs(run_id: str) -> bool:
    """git add + commit de los aggregator outputs (queue de revisión)."""
    run_dir = RUNS_DIR / run_id
    files_to_add: list[str] = []
    for name in COMMITTABLE_AGG_FILES:
        f = run_dir / name
        if f.exists():
            files_to_add.append(str(f.relative_to(REPO)))
    if not files_to_add:
        log(f"no aggregator outputs to commit for {run_id}")
        return True

    rc, out, err = run_subprocess(["git", "add"] + files_to_add, "stage aggregator outputs")
    if rc != 0:
        log(f"git add falló: {err}", level="ERROR")
        return False

    msg = f"extractor({run_id}): aggregate decisions"
    rc, out, err = run_subprocess(["git", "commit", "-m", msg], "commit aggregator outputs")
    if rc != 0:
        if "nothing to commit" in err.lower() or "nothing to commit" in out.lower():
            return True
        log(f"git commit falló: {err}", level="ERROR")
        return False
    return True


def housekeeping_commit(message_prefix: str) -> int:
    """Stage + commit cualquier archivo untracked/modified relevante.

    Stagea: aggregator outputs de runs, applied_log.json, processed_videos.json,
    cambios en wiki/*.md. Devuelve el número de archivos staged. Si no hay
    nada que commitear, devuelve 0.

    Política: el orchestrator gestiona git de forma autónoma. Esto desbloquea
    el problema "dirty tree" sin tener que abortar runs largos.
    """
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=REPO,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return 0
    paths_to_stage: list[str] = []
    for line in proc.stdout.splitlines():
        # Formato: "XY path"
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        # Solo nos interesan los archivos del pipeline; ignoramos cosas como
        # cambios en código fuera del pipeline (que no debería haber)
        if path.startswith("wiki/_meta/extraction_runs/"):
            paths_to_stage.append(path)
        elif path == "wiki/_meta/processed_videos.json":
            paths_to_stage.append(path)
        elif path.startswith("wiki/") and path.endswith(".md"):
            paths_to_stage.append(path)
    if not paths_to_stage:
        return 0
    rc, out, err = run_subprocess(["git", "add"] + paths_to_stage, "stage housekeeping")
    if rc != 0:
        log(f"git add housekeeping falló: {err}", level="WARN")
        return 0
    msg = f"chore(extractor): {message_prefix} ({len(paths_to_stage)} files)"
    rc, out, err = run_subprocess(["git", "commit", "-m", msg], "commit housekeeping")
    if rc != 0:
        if "nothing to commit" in err.lower() or "nothing to commit" in out.lower():
            return 0
        log(f"git commit housekeeping falló: {err}", level="WARN")
        return 0
    return len(paths_to_stage)


def compile_batch(run_id: str) -> bool:
    """Operación PRIMARIA del ingest tras extract+aggregate (postmortem 2026-05-02):
    rewrite coherente página por página tomando inputs del batch.

    Sustituye a apply_pending_updates como pieza del ingest masivo.
    apply_pending_updates queda relegado a herramienta de correcciones humanas
    asistidas (no se invoca aquí).
    """
    log(f"compile pages from run: {run_id}")
    cmd = [
        sys.executable,
        "scripts/compile_wiki_pages.py",
        "--from-run",
        run_id,
        "--auto-commit",
    ]
    rc, out, err = run_subprocess(cmd, "compile", timeout=1800)  # hasta 30min por batch
    if rc != 0:
        crit = detect_critical_in_output(out + err)
        if crit:
            raise CriticalError(f"compile detectó patrón crítico: {crit}")
        log(f"compile falló rc={rc}: {err[-400:]}", level="WARN")
        return False
    return True


def rebuild_wiki_db() -> bool:
    log("rebuild data/wiki.db")
    rc, out, err = run_subprocess(
        [sys.executable, "scripts/build_wiki_db.py"],
        "build_wiki_db",
        timeout=120,
    )
    if rc != 0:
        log(f"build_wiki_db falló rc={rc}: {err[-300:]}", level="WARN")
        return False
    return True


def reindex_qdrant() -> bool:
    """Parar MCP, reindexar wiki en Qdrant, levantar MCP. ~30s downtime."""
    log("reindex Qdrant: stopping MCP server")
    subprocess.run(["pkill", "-f", "ariadna.mcp_server"], cwd=REPO)
    time.sleep(2)
    rc, out, err = run_subprocess(
        [sys.executable, "scripts/index_wiki_to_qdrant.py"],
        "index_wiki_to_qdrant",
        timeout=300,
    )
    if rc != 0:
        log(f"index_wiki_to_qdrant falló rc={rc}: {err[-300:]}", level="ERROR")
        return False
    log("restarting MCP server")
    subprocess.Popen(
        [sys.executable, "-m", "ariadna.mcp_server", "--port", "8765", "--warm"],
        cwd=REPO,
        stdout=open("/tmp/ariadna.log", "ab"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    time.sleep(5)
    return True


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_overnight(args: argparse.Namespace) -> str:
    """Devuelve el string de status final."""
    global LOG_PATH

    overnight_id = f"overnight_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    overnight_dir = RUNS_DIR / overnight_id
    overnight_dir.mkdir(parents=True, exist_ok=True)
    LOG_PATH = overnight_dir / "orchestrator.log"

    log(f"=== overnight_run start ===  id={overnight_id}")
    log(f"args: {vars(args)}")

    # Bootstrap del registro si no existe
    state = load_processed()
    if not state["videos"]:
        log("processed_videos.json vacío → bootstrapping desde extraction_runs/")
        n = bootstrap_from_extraction_runs(state)
        save_processed(state)
        log(f"  bootstrap: +{n} videos")

    all_videos = discover_videos(args.corpus)
    processed_ids = set(state["videos"].keys())
    pending = [v for v in all_videos if v.video_id not in processed_ids]
    log(f"corpus: {len(all_videos)} videos, processed: {len(processed_ids)}, pending: {len(pending)}")

    if not pending:
        log("nada que procesar — exit OK")
        return "EXHAUSTED_NOTHING_PENDING"

    # Housekeeping inicial: si hay untracked relevantes (aggregator outputs
    # huérfanos de un run anterior, applied_log.json sin commitear,
    # processed_videos.json modificado), los commitea bajo un mensaje
    # claro antes de empezar. Política: el orchestrator GESTIONA git,
    # no aborta por dirty.
    cleanup_committed = housekeeping_commit("pre-overnight housekeeping")
    if cleanup_committed:
        log(f"housekeeping pre-run: {cleanup_committed} archivos commiteados")

    consecutive_empty = 0
    batch_idx = 0
    total_done = 0
    total_failed = 0
    total_apply_ok = 0
    total_apply_fail = 0

    while pending and (args.max_batches is None or batch_idx < args.max_batches):
        # Disk check
        free = free_disk_gb(REPO)
        if free < MIN_FREE_DISK_GB:
            log(f"disco libre {free:.2f} GB < {MIN_FREE_DISK_GB} GB → STOP CRITICAL", level="ERROR")
            return f"STOPPED_DISK_LOW_{free:.1f}GB"

        batch = pending[: args.batch_size]
        pending = pending[args.batch_size :]
        batch_idx += 1
        run_id = f"{overnight_id}_b{batch_idx:03d}"

        log(f"--- batch {batch_idx} ({len(batch)} videos) → {run_id} ---")
        for v in batch:
            log(f"    {v.video_id}  {v.playlist}/{v.slug}")

        # 1. Extract
        try:
            n_done, n_failed, err = extract_batch(batch, run_id)
        except CriticalError as e:
            log(f"CRITICAL during extract: {e}", level="ERROR")
            return f"STOPPED_CRITICAL_{e}"

        total_done += n_done
        total_failed += n_failed
        log(f"batch {batch_idx} extract: {n_done} done, {n_failed} failed")

        if n_done == 0:
            consecutive_empty += 1
            log(f"empty batch ({consecutive_empty}/{MAX_CONSECUTIVE_EMPTY_BATCHES} consecutivas)", level="WARN")
            if consecutive_empty >= MAX_CONSECUTIVE_EMPTY_BATCHES:
                log("CRITICAL: demasiados batches vacíos — STOP", level="ERROR")
                return "STOPPED_CONSECUTIVE_EMPTY_BATCHES"
            time.sleep(SLEEP_BETWEEN_BATCHES_S)
            continue
        else:
            consecutive_empty = 0

        # 2. Aggregate
        try:
            stats = aggregate_batch(run_id)
            log(f"batch {batch_idx} aggregate: {stats}")
        except Exception as e:
            log(f"aggregate falló: {e}", level="ERROR")
            time.sleep(SLEEP_BETWEEN_BATCHES_S)
            continue

        # 3. Commit aggregator outputs (queue de revisión)
        if not commit_aggregator_outputs(run_id):
            log("commit aggregator falló — paro para no romper history", level="ERROR")
            return "STOPPED_GIT_COMMIT_FAIL"

        # 4. COMPILE páginas afectadas — operación primaria del ingest Karpathy
        #    (rewrite coherente, no apply diff incremental — corrección postmortem 2026-05-02)
        if args.apply:
            try:
                ok = compile_batch(run_id)
                if ok:
                    total_apply_ok += 1
                else:
                    total_apply_fail += 1
            except CriticalError as e:
                log(f"CRITICAL during compile: {e}", level="ERROR")
                return f"STOPPED_CRITICAL_{e}"

            # 5. Rebuild wiki.db
            rebuild_wiki_db()

            # 6. Reindex Qdrant (opt-in)
            if args.reindex_qdrant:
                reindex_qdrant()

        # 7. Update processed_videos.json
        added = update_state_from_run(state, run_id)
        save_processed(state)
        log(f"processed_videos.json +{added} (total: {len(state['videos'])})")

        # 8. Housekeeping commit — recoge applied_log.json + processed_videos.json
        #    + cualquier output del aggregator/apply que no haya sido commiteado
        #    por el subscript. Mantiene el tree limpio entre lotes.
        n_committed = housekeeping_commit(f"batch {batch_idx} ({run_id})")
        if n_committed:
            log(f"housekeeping batch {batch_idx}: +{n_committed} archivos")

        # Pausa entre batches (gentle con rate-limit)
        log(f"sleep {SLEEP_BETWEEN_BATCHES_S}s")
        time.sleep(SLEEP_BETWEEN_BATCHES_S)

    log("=== overnight_run end ===")
    log(f"summary: batches={batch_idx} done={total_done} failed={total_failed} apply_ok={total_apply_ok} apply_fail={total_apply_fail}")
    return "EXHAUSTED_OK"


def write_status_file(overnight_id: str, status: str) -> None:
    """Pequeño fichero legible a primera vista."""
    overnight_dir = RUNS_DIR / overnight_id
    if not overnight_dir.exists():
        overnight_dir = RUNS_DIR
    status_path = overnight_dir / "STATUS.txt"
    status_path.write_text(
        f"overnight_run terminó: {now_iso()}\n"
        f"status: {status}\n"
        f"\n"
        f"Comandos para revisar:\n"
        f"  cat {LOG_PATH.relative_to(REPO) if LOG_PATH else 'orchestrator.log'}\n"
        f"  git log --oneline -30\n"
        f"  cat wiki/_meta/processed_videos.json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(\"total:\", len(d[\"videos\"]))'\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--batch-size", type=int, default=5)
    ap.add_argument("--max-batches", type=int, default=None, help="Default: hasta agotar pending")
    ap.add_argument("--apply", action="store_true", default=True, help="Apply pending_updates por lote (default: True)")
    ap.add_argument("--no-apply", dest="apply", action="store_false", help="Solo extract+aggregate, no aplica al wiki")
    ap.add_argument("--reindex-qdrant", action="store_true", default=False, help="Reindexar Qdrant tras cada apply (default: off, hazlo a mano por la mañana)")
    ap.add_argument("--allow-dirty-start", action="store_true", help="No abortar si git tree no está limpio al iniciar")
    return ap.parse_args()


def main() -> None:
    args = parse_args()

    overnight_id = f"overnight_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    def _on_signal(signum, frame):
        log(f"señal {signum} recibida — escribiendo STATUS y saliendo", level="WARN")
        write_status_file(overnight_id, f"INTERRUPTED_BY_SIGNAL_{signum}")
        sys.exit(130)

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    try:
        status = run_overnight(args)
    except CriticalError as e:
        log(f"CRITICAL: {e}", level="ERROR")
        status = f"STOPPED_CRITICAL_{e}"
    except KeyboardInterrupt:
        log("KeyboardInterrupt", level="WARN")
        status = "INTERRUPTED_BY_KEYBOARD"
    except Exception as e:
        log(f"unhandled exception: {e}", level="ERROR")
        status = f"STOPPED_EXCEPTION_{type(e).__name__}"

    log(f"FINAL STATUS: {status}")
    write_status_file(overnight_id, status)


if __name__ == "__main__":
    main()
