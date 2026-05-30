#!/usr/bin/env python3
"""Test de regresión del worker / cola (DETERMINISTA, sin red ni LLM):
FSM + lock optimista (claim/done/fail-backoff/failed-permanente/no-double-claim),
bypass bring-your-own-summary, y process_item E2E con mocks (acquirer/summarize/extract).

    python scripts/test_worker.py
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import scripts.init_ariadna_db as INIT  # noqa: E402
from ariadna import projects as P, research_queue as Q  # noqa: E402


def _add_project(db: Path, pid: str) -> None:
    c = sqlite3.connect(db)
    c.execute("INSERT INTO projects(project_id,name,created_at) VALUES(?,?,?)", (pid, pid, "now"))
    c.commit(); c.close()


def _force_past(db: Path, rid: str) -> None:
    c = sqlite3.connect(db)
    row = c.execute("SELECT metadata FROM research_queue WHERE request_id=?", (rid,)).fetchone()
    meta = json.loads(row[0]) if row and row[0] else {}
    meta["next_attempt_at"] = "2000-01-01T00:00:00+00:00"
    c.execute("UPDATE research_queue SET metadata=? WHERE request_id=?", (json.dumps(meta), rid))
    c.commit(); c.close()


def test_fsm_lock_and_retry() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "a.db"; INIT.init_db(db); _add_project(db, "p2")
        Q.add_request("p2", "https://doi.org/10.1/a", db_path=db)
        Q.add_request("p2", "https://doi.org/10.1/b", db_path=db)
        i1 = Q.claim_next("w1", db_path=db); i2 = Q.claim_next("w2", db_path=db); i3 = Q.claim_next("w3", db_path=db)
        assert i1 and i2 and i3 is None and i1["request_id"] != i2["request_id"]
        assert i1["status"] == "processing" and i1["assigned_worker"] == "w1"
        assert Q.mark_done(i1["request_id"], db_path=db)["status"] == "done"
        f = Q.mark_failed(i2["request_id"], "boom", db_path=db)
        assert f["status"] == "pending" and f["retry_count"] == 1 and "next_attempt_at" in f
        assert Q.claim_next("w4", db_path=db) is None  # backoff futuro
        rid = i2["request_id"]
        for _ in range(4):
            _force_past(db, rid)
            it = Q.claim_next("w5", db_path=db)
            if it is None:
                break
            Q.mark_failed(rid, "boom", db_path=db)
        st = sqlite3.connect(db).execute("SELECT status,retry_count FROM research_queue WHERE request_id=?", (rid,)).fetchone()
        assert st[0] == "failed" and st[1] >= 4, st


def test_bypass_metadata() -> None:
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "a.db"; INIT.init_db(db); _add_project(db, "p2")
        bp = Q.add_request("p2", "youtube:VID", source_type="youtube",
                           summary="- 0:00 X\n\n  - a,\n  - b,\n", source_metadata={"title": "T"}, db_path=db)
        assert bp["has_summary"] is True
        it = Q.claim_next("w1", source_type="youtube", db_path=db)
        assert it["metadata"]["summary"].startswith("- 0:00")
        assert it["metadata"]["source_metadata"]["title"] == "T"


def test_process_item_e2e_mocks() -> None:
    import fitz
    from ariadna.acquire import MockPaperAcquirer
    import scripts.worker as W

    slug = "wtest-reg"
    doc = fitz.open()
    for t in ["Pagina uno.", "Pagina dos."]:
        doc.new_page().insert_text((72, 72), t)
    pdf = doc.tobytes(); doc.close()

    def mock_summarize(blob, title):
        return "- p.1 🧠 Teleo\n\n  - x,\n  - y,\n\n- p.2 🔬 F\n\n  - a,\n  - b,\n"

    def mock_extract(summary, source_id, title, project, **kw):
        doi_url = "https://doi.org/" + source_id.split(":", 1)[1]
        return [{
            "page_id": "teleosemantica", "page_type": "concept", "canonical_name": "Teleosemántica",
            "domain_primary": "humanities.philosophy.mind", "aliases": [],
            "relations": [{"type": "developed_by", "to": "millikan-ruth"}],
            "body_markdown": f"# Teleosemántica\n\n## Definición\n\nDeriva contenido [{title}, p.1]({doi_url}#page=1).",
            "cited_pages": [1, 2],
        }]

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "a.db"; INIT.init_db(db)
        assert "project_id" in P.create_project(slug, "W Test Reg", db_path=db)
        try:
            Q.add_request(slug, "https://doi.org/10.1016/j.x.2020.01", source_type="paper", db_path=db)
            item = Q.claim_next("w1", project=slug, db_path=db)
            res = W.process_item(item, acquirer=MockPaperAcquirer(pdf, {"title": "Un Paper", "abstract": "abs"}),
                                 summarize_fn=mock_summarize, extract_fn=mock_extract,
                                 db_path=db, staging_dir=Path(td) / "staging")
            assert res["source_id"] == "doi:10.1016/j.x.2020.01" and res["n_pages_written"] == 1
            c = sqlite3.connect(db)
            assert c.execute("SELECT source_type FROM sources WHERE source_id=?", (res["source_id"],)).fetchone()[0] == "paper"
            assert c.execute("SELECT 1 FROM source_projects WHERE source_id=? AND project_id=?", (res["source_id"], slug)).fetchone()
            npages = c.execute("SELECT COUNT(*) FROM pages WHERE project_id=?", (slug,)).fetchone()[0]
            ncit = c.execute("SELECT COUNT(*) FROM citations WHERE project_id=? AND source_id=?", (slug, res["source_id"])).fetchone()[0]
            orphan = c.execute("SELECT COUNT(*) FROM citations WHERE project_id=? AND source_id NOT IN (SELECT source_id FROM sources)", (slug,)).fetchone()[0]
            c.close()
            assert npages == 1 and ncit == 2 and orphan == 0, (npages, ncit, orphan)
            md = REPO / "projects" / slug / "wiki" / "concepts" / "teleosemantica.md"
            assert md.exists() and "[Un Paper, p.1]" in md.read_text(encoding="utf-8")
            assert Q.mark_done(item["request_id"], db_path=db)["status"] == "done"
        finally:
            shutil.rmtree(REPO / "projects" / slug, ignore_errors=True)


TESTS = [test_fsm_lock_and_retry, test_bypass_metadata, test_process_item_e2e_mocks]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
