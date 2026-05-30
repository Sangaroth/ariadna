"""Tests del schema unificado de data/ariadna.db.

Nota: requiere pytest. Si no está instalado, la verificación equivalente se puede
correr a mano con `python scripts/init_ariadna_db.py --db /tmp/x.db` (incluye --check).
"""
import sqlite3

from init_ariadna_db import EXPECTED_TABLES, init_db


def test_creates_all_tables_with_wal(tmp_path):
    db = tmp_path / "ariadna.db"
    init_db(db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("PRAGMA journal_mode;").fetchone()[0].lower() == "wal"
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        assert tables == EXPECTED_TABLES
        assert conn.execute("PRAGMA integrity_check;").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_idempotent(tmp_path):
    db = tmp_path / "ariadna.db"
    init_db(db)
    init_db(db)  # no debe lanzar
    conn = sqlite3.connect(db)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        assert tables == EXPECTED_TABLES
    finally:
        conn.close()


def test_research_queue_dedup_partial_unique(tmp_path):
    """Misma (project, url) en estado pending no se puede duplicar."""
    db = tmp_path / "ariadna.db"
    init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute("INSERT INTO projects(project_id,name,created_at) VALUES('p','P','t')")
        conn.execute("INSERT INTO research_queue(request_id,project_id,source_url,source_type,created_at)"
                     " VALUES('r1','p','http://x','paper','t')")
        try:
            conn.execute("INSERT INTO research_queue(request_id,project_id,source_url,source_type,created_at)"
                         " VALUES('r2','p','http://x','paper','t')")
            assert False, "el partial-unique de dedup no bloqueó"
        except sqlite3.IntegrityError:
            pass
    finally:
        conn.close()


def test_citations_fk_to_pages(tmp_path):
    """Con foreign_keys=ON, una cita a página inexistente debe fallar."""
    db = tmp_path / "ariadna.db"
    init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO projects(project_id,name,created_at) VALUES('p','P','t')")
        try:
            conn.execute("INSERT INTO citations(project_id,page_id,source_id,position_key,position,position_url)"
                         " VALUES('p','nope','youtube:x','0','{}','u')")
            assert False, "la FK citations->pages no bloqueó"
        except sqlite3.IntegrityError:
            pass
    finally:
        conn.close()
