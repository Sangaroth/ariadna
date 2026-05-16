"""Carga los bloques marcados como `blocks_filtered_by_topic_filters` por el
pipeline de extracción wiki y los expone como un mapa `(video_id, ts_seconds) →
policy_filter_dict` para que build_index los propague al payload de Qdrant.

La razón del descarte vive en los per-video JSONs del run; este módulo no
recalcula nada, sólo agrega.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ariadna.parsers import parse_timestamp

log = logging.getLogger("ariadna.policy_filters")

# Claves del per-video JSON que se propagan al payload del chunk.
_FIELDS = ("reason_code", "matched_pattern", "reason_detail", "block_minute_start")


def build_policy_filter_map(
    extraction_runs_dir: Path,
) -> dict[tuple[str, int], dict[str, Any]]:
    """Escanea todos los runs y devuelve `(video_id, ts_seconds) → policy_filter`.

    Cuando el mismo (video_id, ts_seconds) aparece en múltiples runs se queda
    con el JSON más reciente por mtime.
    """
    if not extraction_runs_dir.exists():
        log.warning("extraction_runs dir not found: %s", extraction_runs_dir)
        return {}

    candidates: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}
    files_scanned = 0
    blocks_seen = 0
    blocks_unparseable = 0

    for json_path in extraction_runs_dir.glob("*/*.json"):
        name = json_path.name
        if name == "state.json":
            continue
        if name.startswith(
            (
                "pending_",
                "promote_",
                "thesis_",
                "discard_",
                "recommended_",
                "aggregation_",
            )
        ):
            continue
        video_id = json_path.stem
        if len(video_id) != 11:
            continue
        try:
            doc = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("skip %s: %s", json_path, exc)
            continue
        files_scanned += 1
        run_id = doc.get("extraction_metadata", {}).get("run_id") or json_path.parent.name
        mtime = json_path.stat().st_mtime
        for block in doc.get("blocks_filtered_by_topic_filters") or []:
            blocks_seen += 1
            ts_raw = block.get("block_minute_start")
            if not ts_raw:
                blocks_unparseable += 1
                continue
            try:
                ts_seconds = parse_timestamp(str(ts_raw))
            except ValueError:
                blocks_unparseable += 1
                continue
            entry = {k: block.get(k) for k in _FIELDS if block.get(k) is not None}
            entry["source_run"] = run_id
            key = (video_id, ts_seconds)
            existing = candidates.get(key)
            if existing is None or mtime > existing[0]:
                candidates[key] = (mtime, entry)

    log.info(
        "policy filters: %d files scanned, %d blocks seen, %d unparseable, %d unique (video,ts)",
        files_scanned,
        blocks_seen,
        blocks_unparseable,
        len(candidates),
    )
    return {k: v[1] for k, v in candidates.items()}
