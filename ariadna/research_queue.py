"""Cola de ingesta (research_queue): add / cancel / list (lógica, sin MCP).

Aislado del server para reuso por el worker (F7, que añadirá el lock optimista
`UPDATE ... RETURNING` para pending→processing). Contrato: spec §6.1/§6.2 + FSM §4.2.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ariadna.config import PROJECT_ROOT

ARIADNA_DB = PROJECT_ROOT / "data" / "ariadna.db"

# Enum del source_type de la COLA (corto), distinto del sources.source_type canónico.
QUEUE_SOURCE_TYPES = {"youtube", "paper", "web", "pdf", "unknown"}
QUEUE_STATUSES = {"pending", "processing", "done", "failed", "cancelled"}

# Backoff de reintentos (segundos) y tope (plan §4.2.1: 60/300/900, max_retries=3).
RETRY_BACKOFF_S = [60, 300, 900]
MAX_RETRIES = 3

# Columnas devueltas al worker (orden estable para mapear RETURNING/SELECT).
_ITEM_COLS = [
    "request_id", "project_id", "source_url", "source_type", "status", "priority",
    "created_at", "picked_up_at", "completed_at", "assigned_worker", "retry_count",
    "error_msg", "notes", "metadata", "source_file_hash",
]


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return _now_dt().isoformat(timespec="seconds")


def _row_to_item(row: tuple) -> dict:
    item = dict(zip(_ITEM_COLS, row))
    # metadata JSON → dict (incluye summary inline / source_metadata del bypass).
    raw = item.get("metadata")
    item["metadata"] = json.loads(raw) if raw else {}
    return item


def _err(code: str, msg: str) -> dict:
    return {"error": msg, "code": code}


def detect_source_type(url: str) -> str:
    """Auto-detect del source_type de la cola (spec §6.6). Enum corto."""
    u = url or ""
    if "youtube.com/watch" in u or "youtu.be/" in u:
        return "youtube"
    if "arxiv.org/" in u:
        return "paper"
    if "doi.org/" in u:
        return "paper"
    if u.lower().endswith(".pdf"):
        return "pdf"
    if u.startswith("http"):
        return "web"
    return "unknown"


def add_request(
    project: str,
    source_url: str,
    source_type: str | None = None,
    notes: str = "",
    priority: int = 0,
    summary: str | None = None,
    source_metadata: dict | None = None,
    source_file_hash: str | None = None,
    db_path: Path = ARIADNA_DB,
) -> dict:
    """Añade item a la cola. Idempotente sobre (project, url) en pending/processing.

    Precedencia caller>detector (spec §6.6): si el caller pasa source_type explícito
    se respeta sin warning; si lo omite, se aplica detect_source_type(url).

    BYPASS bring-your-own-summary: si `summary` viene (p.ej. ProxySummaries para el
    canal), se guarda en metadata y el worker SALTA la sumarización. `source_metadata`
    (title, playlist, category…) acompaña al sumario para construir el registro/wiki.
    """
    if not source_url or not source_url.strip():
        return _err("INVALID_URL", "source_url vacío")
    if source_type is not None and source_type not in QUEUE_SOURCE_TYPES:
        return _err("INVALID_SOURCE_TYPE", f"source_type {source_type!r} no en {sorted(QUEUE_SOURCE_TYPES)}")

    detected = source_type or detect_source_type(source_url)

    metadata: dict = {}
    if summary is not None:
        metadata["summary"] = summary
    if source_metadata:
        metadata["source_metadata"] = source_metadata
    metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        if conn.execute("SELECT 1 FROM projects WHERE project_id=?", (project,)).fetchone() is None:
            return _err("PROJECT_NOT_FOUND", f"proyecto {project!r} no existe")

        # Dedup: misma (project, url) en pending/processing (idx_queue_dedup).
        dup = conn.execute(
            """SELECT request_id, status FROM research_queue
               WHERE project_id=? AND source_url=? AND status IN ('pending','processing')""",
            (project, source_url),
        ).fetchone()
        if dup:
            return {
                "request_id": dup[0], "detected_source_type": detected,
                "status": dup[1], "was_duplicate": True,
                "message": "ya en cola (pending/processing)",
            }

        request_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO research_queue
               (request_id, project_id, source_url, source_type, status, priority, created_at,
                notes, metadata, source_file_hash)
               VALUES (?,?,?,?,'pending',?,?,?,?,?)""",
            (request_id, project, source_url, detected, priority, _now(), notes or None,
             metadata_json, source_file_hash),
        )
        conn.commit()
        return {
            "request_id": request_id, "detected_source_type": detected,
            "status": "pending", "was_duplicate": False,
            "has_summary": summary is not None,
            "message": f"encolado como {detected}" + (" (con sumario, bypass)" if summary else ""),
        }
    finally:
        conn.close()


def cancel_request(request_id: str, reason: str = "", db_path: Path = ARIADNA_DB) -> dict:
    """Cancela un request. pending|failed → cancelled; processing|done|cancelled → no-op.

    Devuelve {request_id, previous_status, current_status} o {error, code}.
    """
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT status FROM research_queue WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return _err("REQUEST_NOT_FOUND", f"request {request_id!r} no existe")
        prev = row[0]
        if prev in ("pending", "failed"):
            note = f"cancelled: {reason}" if reason else "cancelled"
            conn.execute(
                "UPDATE research_queue SET status='cancelled', completed_at=?, notes=? WHERE request_id=?",
                (_now(), note, request_id),
            )
            conn.commit()
            current = "cancelled"
        else:
            # processing / done / cancelled → terminal o en curso: no-op.
            current = prev
        return {"request_id": request_id, "previous_status": prev, "current_status": current}
    finally:
        conn.close()


def list_research_queue(
    project: str | None = None,
    status: str = "pending",
    source_type: str | None = None,
    limit: int = 50,
    db_path: Path = ARIADNA_DB,
) -> dict:
    """Lista items de la cola. status='all' = todos. Devuelve {items, total_matching, filters_applied}."""
    if status != "all" and status not in QUEUE_STATUSES:
        return _err("INVALID_STATUS", f"status {status!r} no en {sorted(QUEUE_STATUSES)} ni 'all'")
    if source_type is not None and source_type not in QUEUE_SOURCE_TYPES:
        return _err("INVALID_SOURCE_TYPE", f"source_type {source_type!r} no en {sorted(QUEUE_SOURCE_TYPES)}")

    clauses: list[str] = []
    params: list = []
    if project is not None:
        clauses.append("project_id=?"); params.append(project)
    if status != "all":
        clauses.append("status=?"); params.append(status)
    if source_type is not None:
        clauses.append("source_type=?"); params.append(source_type)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM research_queue{where}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT request_id, project_id, source_url, source_type, status, priority,
                       created_at, picked_up_at, completed_at, retry_count, error_msg, notes
                FROM research_queue{where}
                ORDER BY priority DESC, created_at ASC LIMIT ?""",
            (*params, limit),
        ).fetchall()
        cols = ["request_id", "project_id", "source_url", "source_type", "status", "priority",
                "created_at", "picked_up_at", "completed_at", "retry_count", "error_msg", "notes"]
        items = [dict(zip(cols, r)) for r in rows]
        return {
            "items": items,
            "total_matching": total,
            "filters_applied": {"project": project, "status": status, "source_type": source_type, "limit": limit},
        }
    finally:
        conn.close()


# --- FSM del worker: claim (lock optimista) / done / failed (backoff) -------


def claim_next(
    worker_id: str,
    source_type: str | None = None,
    project: str | None = None,
    db_path: Path = ARIADNA_DB,
) -> dict | None:
    """Reclama atómicamente el próximo item pending (pending→processing).

    Lock optimista `UPDATE … WHERE request_id=(SELECT … LIMIT 1) RETURNING *`: bajo el
    write-lock de SQLite, dos workers no reclaman el mismo item (el 2º re-evalúa el
    subquery y coge otro). Respeta el backoff de reintentos (metadata.next_attempt_at).
    Devuelve el item (dict, metadata ya deserializada) o None si no hay nada elegible.
    """
    now = _now()
    sub_clauses = ["status='pending'"]
    sub_params: list = []
    if source_type is not None:
        sub_clauses.append("source_type=?"); sub_params.append(source_type)
    if project is not None:
        sub_clauses.append("project_id=?"); sub_params.append(project)
    sub_clauses.append(
        "(json_extract(metadata,'$.next_attempt_at') IS NULL "
        "OR json_extract(metadata,'$.next_attempt_at') <= ?)")
    sub_params.append(now)
    sub_where = " AND ".join(sub_clauses)

    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        cols = ", ".join(_ITEM_COLS)
        row = conn.execute(
            f"""UPDATE research_queue
                SET status='processing', picked_up_at=?, assigned_worker=?, error_msg=NULL
                WHERE request_id = (
                    SELECT request_id FROM research_queue
                    WHERE {sub_where}
                    ORDER BY priority DESC, created_at ASC LIMIT 1
                )
                RETURNING {cols}""",
            (now, worker_id, *sub_params),
        ).fetchone()
        conn.commit()
        return _row_to_item(row) if row else None
    finally:
        conn.close()


def mark_done(request_id: str, notes: str | None = None, db_path: Path = ARIADNA_DB) -> dict:
    """processing→done. completed_at=now, error_msg=NULL."""
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        row = conn.execute(
            "UPDATE research_queue SET status='done', completed_at=?, error_msg=NULL, "
            "notes=COALESCE(?, notes) WHERE request_id=? RETURNING status",
            (_now(), notes, request_id),
        ).fetchone()
        conn.commit()
        if row is None:
            return _err("REQUEST_NOT_FOUND", request_id)
        return {"request_id": request_id, "status": "done"}
    finally:
        conn.close()


def mark_failed(
    request_id: str,
    error: str,
    max_retries: int = MAX_RETRIES,
    db_path: Path = ARIADNA_DB,
) -> dict:
    """processing→pending (retry con backoff) hasta max_retries, luego →failed (perm).

    El backoff se guarda en metadata.next_attempt_at (no hay columna dedicada); claim_next
    lo respeta. Devuelve {request_id, status, retry_count, next_attempt_at?}.
    """
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        row = conn.execute(
            "SELECT retry_count, metadata FROM research_queue WHERE request_id=?", (request_id,)
        ).fetchone()
        if row is None:
            return _err("REQUEST_NOT_FOUND", request_id)
        retry_count = (row[0] or 0) + 1
        meta = json.loads(row[1]) if row[1] else {}
        err_short = (error or "")[:1000]

        if retry_count <= max_retries:
            delay = RETRY_BACKOFF_S[min(retry_count - 1, len(RETRY_BACKOFF_S) - 1)]
            next_at = (_now_dt() + timedelta(seconds=delay)).isoformat(timespec="seconds")
            meta["next_attempt_at"] = next_at
            conn.execute(
                "UPDATE research_queue SET status='pending', retry_count=?, error_msg=?, "
                "metadata=?, picked_up_at=NULL, assigned_worker=NULL WHERE request_id=?",
                (retry_count, err_short, json.dumps(meta, ensure_ascii=False), request_id),
            )
            conn.commit()
            return {"request_id": request_id, "status": "pending", "retry_count": retry_count,
                    "next_attempt_at": next_at}
        else:
            meta.pop("next_attempt_at", None)
            conn.execute(
                "UPDATE research_queue SET status='failed', retry_count=?, error_msg=?, "
                "completed_at=?, metadata=? WHERE request_id=?",
                (retry_count, err_short, _now(), json.dumps(meta, ensure_ascii=False), request_id),
            )
            conn.commit()
            return {"request_id": request_id, "status": "failed", "retry_count": retry_count}
    finally:
        conn.close()
