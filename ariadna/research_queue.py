"""Cola de ingesta (research_queue): add / cancel / list (lógica, sin MCP).

Aislado del server para reuso por el worker (F7, que añadirá el lock optimista
`UPDATE ... RETURNING` para pending→processing). Contrato: spec §6.1/§6.2 + FSM §4.2.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ariadna.config import PROJECT_ROOT

ARIADNA_DB = PROJECT_ROOT / "data" / "ariadna.db"

# Enum del source_type de la COLA (corto), distinto del sources.source_type canónico.
QUEUE_SOURCE_TYPES = {"youtube", "paper", "web", "pdf", "unknown"}
QUEUE_STATUSES = {"pending", "processing", "done", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    db_path: Path = ARIADNA_DB,
) -> dict:
    """Añade item a la cola. Idempotente sobre (project, url) en pending/processing.

    Precedencia caller>detector (spec §6.6): si el caller pasa source_type explícito
    se respeta sin warning; si lo omite, se aplica detect_source_type(url).
    """
    if not source_url or not source_url.strip():
        return _err("INVALID_URL", "source_url vacío")
    if source_type is not None and source_type not in QUEUE_SOURCE_TYPES:
        return _err("INVALID_SOURCE_TYPE", f"source_type {source_type!r} no en {sorted(QUEUE_SOURCE_TYPES)}")

    detected = source_type or detect_source_type(source_url)

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
               (request_id, project_id, source_url, source_type, status, priority, created_at, notes)
               VALUES (?,?,?,?,'pending',?,?,?)""",
            (request_id, project, source_url, detected, priority, _now(), notes or None),
        )
        conn.commit()
        return {
            "request_id": request_id, "detected_source_type": detected,
            "status": "pending", "was_duplicate": False,
            "message": f"encolado como {detected}",
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
