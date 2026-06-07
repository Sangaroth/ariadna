#!/usr/bin/env python3
"""process_recovery.py — extrae + agrega un set explícito de vídeos Proxy.

Flujo correcto (sin el loop de overnight_run, que tiene lógica de "2 lotes
vacíos → stop" y usa el compile roto para el esquema nuevo):

  extract_video_themes.run(lista, reprocess_all=True)   # sesiona 5/sesión,
                                                        # cada sesión COMPLETA,
                                                        # sin stop prematuro
  → aggregate(run_id)                                   # pending/promote + scan

NO aplica nada al wiki: eso se hace después con apply_extracted_updates.py
(determinista, bi-esquema) tras revisar. Así el lote siempre se cierra entero.

Procesa: 7 vídeos pendientes (no procesados) + 9 vídeos fuente de los gaps
huérfanos (reprocess_all para forzar, ya tienen JSON viejo).

Uso:
    python scripts/process_recovery.py            # extract + aggregate
    python scripts/process_recovery.py --run-id X
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_video_themes import (  # noqa: E402
    DEFAULT_CORPUS, discover_videos, run as extractor_run, aggregate as extractor_aggregate,
)
from extract_incremental import load_processed, bootstrap_from_extraction_runs  # noqa: E402

# Vídeos fuente de los 11 gaps huérfanos (ancla muerta → re-extraer fresco)
GAP_VIDEO_IDS = [
    "Dv3caRUYzuc", "J45h7xet8gg", "Lac68XOLtL0", "UZPjezFUrA0", "X4WVHD8hn50",
    "agh46Snf5YI", "hY87a4srcoM", "lw7XI2lQntM", "vqN3ZqRTNCc",
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--ts", default=None, help="timestamp para el run-id (Date no disponible en algunos entornos)")
    args = ap.parse_args()

    all_videos = discover_videos(DEFAULT_CORPUS)
    by_id = {v.video_id: v for v in all_videos}

    # pendientes (incremental, con bootstrap en memoria)
    state = load_processed()
    if not state.get("videos"):
        bootstrap_from_extraction_runs(state)
    processed = set(state.get("videos", {}).keys())
    pending = [v for v in all_videos if v.video_id not in processed]

    # set final = pendientes + gaps (únicos, preservando orden)
    seen, targets = set(), []
    for v in pending + [by_id[g] for g in GAP_VIDEO_IDS if g in by_id]:
        if v.video_id not in seen:
            seen.add(v.video_id)
            targets.append(v)

    run_id = args.run_id or f"recovery_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    print(f"=== process_recovery: {len(targets)} vídeos ({len(pending)} pendientes + gaps) ===", flush=True)
    for v in targets:
        print(f"  · {v.video_id}  {getattr(v, 'title', '')[:55]}", flush=True)
    print(f"run_id: {run_id}\n", flush=True)

    # EXTRACT — reprocess_all=True para no saltar los gaps (ya tienen JSON viejo).
    # Sesiona 5/sesión internamente; cada sesión completa. Sin lógica de stop.
    print("=== EXTRACT (reprocess_all) ===", flush=True)
    extractor_run(run_id, targets, reprocess_all=True)

    # AGGREGATE
    print("\n=== AGGREGATE ===", flush=True)
    extractor_aggregate(run_id)

    print(f"\n✓ extract+aggregate completos. run_id={run_id}", flush=True)
    print("Siguiente: revisar y aplicar con apply_extracted_updates.py --from-run", run_id, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
