#!/usr/bin/env python3
"""extract_incremental.py — procesa solo vídeos nuevos del corpus

Detecta summaries que NO están registrados como procesados (registro en
wiki/_meta/processed_videos.json) y los pasa al extractor en sesiones
cacheadas. Tras el run, actualiza processed_videos.json con los que se
hayan procesado con éxito.

Pensado para el caso "Proxy publica vídeos nuevos, quiero ingerirlos sin
reprocesar los 288 ya hechos".

Uso típico:
    # Bootstrap inicial: registrar como procesados los vídeos de runs
    # anteriores (extraction_runs/*) que ya tengas hechos
    python scripts/extract_incremental.py --bootstrap

    # Listar pendientes (no invoca Claude)
    python scripts/extract_incremental.py --dry-run

    # Procesar pendientes
    python scripts/extract_incremental.py

    # Procesar máximo N (útil si llegan muchos a la vez)
    python scripts/extract_incremental.py --limit 30

Estado persistente (committed en git):
    wiki/_meta/processed_videos.json — registro {video_id: {first_run, last_run}}

NO toca el wiki ni el server MCP. Solo extracción → JSONs en run_dir.
La aplicación al wiki sigue siendo manual con apply_pending_updates.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Reúsa funciones del extractor principal sin re-implementar
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_video_themes import (  # noqa: E402
    DEFAULT_CORPUS,
    REPO,
    RUNS_DIR,
    discover_videos,
    run as extractor_run,
)

PROCESSED_PATH = REPO / "wiki" / "_meta" / "processed_videos.json"

# Files que el aggregator escribe en run_dir — NO son outputs por-vídeo
AGG_FILES = {
    "state.json",
    "discard_log.json",
    "pending_updates.json",
    "promote_queue.json",
    "thesis_candidates.json",
    "blocks_filtered.json",
    "aggregation_stats.json",
    "applied_log.json",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_processed() -> dict:
    if PROCESSED_PATH.exists():
        return json.loads(PROCESSED_PATH.read_text(encoding="utf-8"))
    return {
        "version": "1.0.0",
        "schema_version": "1.0.0",
        "description": (
            "Registro de vídeos del corpus ingeridos por el extractor. "
            "Mantenido por scripts/extract_incremental.py. Cada entry: "
            "{first_run: <run_id de la primera vez que se procesó>, "
            "last_run: <run_id más reciente>}."
        ),
        "last_updated": None,
        "videos": {},
    }


def save_processed(data: dict) -> None:
    data["last_updated"] = now_iso()
    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  ✓ updated {PROCESSED_PATH.relative_to(REPO)}", file=sys.stderr)


def video_ids_in_run_dir(run_dir: Path) -> list[str]:
    """Lista video_ids de los JSONs por-vídeo de un run dir (no aggregator outputs)."""
    if not run_dir.exists():
        return []
    out: list[str] = []
    for jp in run_dir.glob("*.json"):
        if jp.name in AGG_FILES or ".failed." in jp.name:
            continue
        try:
            d = json.loads(jp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(d, dict) and "video_id" in d:
            out.append(d["video_id"])
    return out


def bootstrap_from_extraction_runs(state: dict) -> int:
    """Escanea extraction_runs/* y registra todos los vídeos ya procesados."""
    if not RUNS_DIR.exists():
        print(f"  no hay {RUNS_DIR.relative_to(REPO)}/ — nada que bootstrap", file=sys.stderr)
        return 0
    added = 0
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name
        n = 0
        for vid in video_ids_in_run_dir(run_dir):
            entry = state["videos"].setdefault(vid, {})
            if "first_run" not in entry:
                entry["first_run"] = run_id
                added += 1
                n += 1
            entry["last_run"] = run_id
        if n:
            print(f"  {run_id}: +{n} videos", file=sys.stderr)
    return added


def update_state_from_run(state: dict, run_id: str) -> int:
    run_dir = RUNS_DIR / run_id
    added = 0
    for vid in video_ids_in_run_dir(run_dir):
        entry = state["videos"].setdefault(vid, {})
        if "first_run" not in entry:
            entry["first_run"] = run_id
            added += 1
        entry["last_run"] = run_id
    return added


def warn_if_run_alive(state: dict) -> None:
    """Heurística: si hay un run con state.json reciente y videos_pending no vacío,
    avisar (puede haber otro extractor corriendo en paralelo, riesgo de rate-limit)."""
    if not RUNS_DIR.exists():
        return
    now = datetime.now(timezone.utc)
    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        sp = run_dir / "state.json"
        if not sp.exists():
            continue
        try:
            sd = json.loads(sp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        last = sd.get("last_updated", "")
        if not last:
            continue
        try:
            t = datetime.fromisoformat(last.replace("Z", "+00:00"))
        except ValueError:
            continue
        age_min = (now - t).total_seconds() / 60
        pending = len(sd.get("videos_pending", [])) - len(sd.get("videos_done", []))
        if age_min < 60 and pending > 0:
            print(
                f"  ⚠ run alive? {run_dir.name}: pending={pending}, "
                f"last_updated hace {age_min:.0f} min. Si está vivo otro proceso, "
                f"riesgo de rate-limit en cuota Max al lanzar este en paralelo.",
                file=sys.stderr,
            )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS, help="Path a playlists/")
    ap.add_argument("--dry-run", action="store_true", help="Listar pendientes sin invocar Claude")
    ap.add_argument(
        "--bootstrap",
        action="store_true",
        help="Registrar como procesados todos los vídeos de extraction_runs/* existentes (no invoca Claude). Idempotente.",
    )
    ap.add_argument("--run-id", type=str, default=None, help="ID del run incremental. Default: incremental_<timestamp>")
    ap.add_argument("--limit", type=int, default=None, help="Procesar máximo N pendientes (default: todos)")
    args = ap.parse_args()

    state = load_processed()

    if args.bootstrap:
        n = bootstrap_from_extraction_runs(state)
        save_processed(state)
        print(f"\nBootstrap completo: {n} videos añadidos a processed_videos.json", file=sys.stderr)
        print(f"Total registrados: {len(state['videos'])}", file=sys.stderr)
        return

    if not args.corpus.exists():
        sys.exit(f"Corpus no encontrado: {args.corpus}")

    all_videos = discover_videos(args.corpus)
    processed_ids = set(state["videos"].keys())
    pending = [v for v in all_videos if v.video_id not in processed_ids]

    print(f"Corpus total: {len(all_videos)} summaries", file=sys.stderr)
    print(f"Ya procesados: {len(processed_ids)}", file=sys.stderr)
    print(f"Pendientes: {len(pending)}", file=sys.stderr)

    if not pending:
        print("\nNada que procesar.", file=sys.stderr)
        return

    if args.limit:
        pending = pending[: args.limit]
        print(f"Limitado a primeros {args.limit}", file=sys.stderr)

    if args.dry_run:
        print("\n--- vídeos pendientes ---", file=sys.stderr)
        for v in pending:
            print(f"{v.video_id}\t{v.playlist}/{v.slug}\t{v.duration_s//60}min\t{v.title[:60]}")
        return

    warn_if_run_alive(state)

    run_id = args.run_id or f"incremental_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    print(f"\nLanzando run {run_id}: {len(pending)} vídeos", file=sys.stderr)
    extractor_run(run_id, pending, pilot=False)

    # Actualizar registro con los procesados con éxito
    added = update_state_from_run(state, run_id)
    save_processed(state)
    print(f"\nRun {run_id} terminado.", file=sys.stderr)
    print(f"  Vídeos añadidos al registro: {added}", file=sys.stderr)
    print(f"  Total acumulado: {len(state['videos'])}", file=sys.stderr)
    print(f"\nPróximo paso: aggregate + apply_pending_updates", file=sys.stderr)
    print(f"  python scripts/extract_video_themes.py --aggregate {run_id}", file=sys.stderr)
    print(f"  python scripts/apply_pending_updates.py --from-run {run_id} --apply --auto-commit", file=sys.stderr)


if __name__ == "__main__":
    main()
