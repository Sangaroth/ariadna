#!/usr/bin/env python3
"""Test de regresión de las piezas PURAS de F6 (sin red ni LLM):
source_archive (dedup/sharding), pdf_extract ([p.NN]), validate_summary,
PaperAdapter.parse_summary_to_chunks + round-trip de citas.

    python scripts/test_summarize.py    # exit 0 = todo verde
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

GOOD = ("- p.1 🧠 Tema A\n\n  - detalle uno,\n  - detalle dos,\n\n"
        "- p.3 🔬 Tema B\n\n  - x,\n  - y,\n\n"
        "- p.5 🎭 Tema C\n\n  - a,\n  - b,\n")


def test_source_archive() -> None:
    from ariadna import source_archive as SA
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        dbp = td / "t.db"
        sqlite3.connect(dbp).executescript(
            "CREATE TABLE source_files (source_file_hash TEXT PRIMARY KEY, ext TEXT, "
            "byte_size INT, original_url TEXT, archived_at TEXT);")
        blob = b"%PDF-fake-123"
        srcdir = td / "sources"
        r1 = SA.store(blob, "pdf", "http://x/y.pdf", db_path=dbp, sources_dir=srcdir)
        r2 = SA.store(blob, "pdf", "http://x/y.pdf", db_path=dbp, sources_dir=srcdir)
        assert r1["was_duplicate"] is False and r2["was_duplicate"] is True
        assert r1["source_file_hash"] == r2["source_file_hash"]
        assert Path(r1["path"]).exists()
        h = r1["source_file_hash"]
        assert r1["path"].endswith(f"{h[:2]}/{h}.pdf")
        assert sqlite3.connect(dbp).execute("SELECT COUNT(*) FROM source_files").fetchone()[0] == 1
        # read_by_hash: roundtrip + rechazos de seguridad (anti-traversal / no archivado)
        assert SA.read_by_hash(h, db_path=dbp, sources_dir=srcdir) == blob
        for bad in ["../../etc/passwd", "not-hex", "", "a" * 63]:
            try:
                SA.read_by_hash(bad, db_path=dbp, sources_dir=srcdir)
                raise AssertionError(f"hash inválido aceptado: {bad!r}")
            except ValueError:
                pass
        try:
            SA.read_by_hash("b" * 64, db_path=dbp, sources_dir=srcdir)
            raise AssertionError("hash no archivado aceptado")
        except FileNotFoundError:
            pass


def test_pdf_extract() -> None:
    import fitz
    from ariadna.summarize.pdf_extract import extract_pages, pdf_to_summary_input
    doc = fitz.open()
    for txt in ["Pagina uno teleosemantica.", "Pagina dos contenido."]:
        doc.new_page().insert_text((72, 72), txt)
    data = doc.tobytes(); doc.close()
    pages = extract_pages(data)
    assert len(pages) == 2 and pages[0][0] == 1
    inp = pdf_to_summary_input(pages)
    assert "[p.1]" in inp and "[p.2]" in inp


def test_validate_summary() -> None:
    from ariadna.summarize.prompts import validate_summary
    assert validate_summary(GOOD) == []
    assert validate_summary("sin markers")  # sin temas
    assert validate_summary("- p.5 x\n\n  - a,\n  - b,\n\n- p.2 y\n\n  - c,\n  - d,\n\n- p.9 z\n\n  - e,\n  - f,\n")  # no creciente
    few = "- p.1 X\n\n  - solo uno,\n\n- p.2 Y\n\n  - a,\n  - b,\n\n- p.3 Z\n\n  - c,\n  - d,\n"
    assert any("detalle" in i for i in validate_summary(few))


def test_paper_adapter_parse_and_roundtrip() -> None:
    from ariadna.sources.paper import PaperAdapter
    pa = PaperAdapter()
    ch = pa.parse_summary_to_chunks(GOOD, "doi:10.1234/abc", "Un Paper Teleo")
    assert len(ch) == 3
    assert ch[0].position.key == "p1"
    assert ch[0].chunk_id == "doi:10.1234/abc#p1"
    assert ch[0].cite_markdown == "[Un Paper Teleo, p.1](https://doi.org/10.1234/abc#page=1)"
    m = pa.citation_link_re().search(ch[0].cite_markdown)
    ref = pa.parse_citation_match(m)
    assert ref.source_id == "doi:10.1234/abc" and ref.position.key == "p1"
    assert ref.position_url == "https://doi.org/10.1234/abc#page=1"
    # sección opcional p.NNsX.Y
    s = ("- p.7s3.2 🧠 T\n\n  - a,\n  - b,\n\n- p.8 🔬 U\n\n  - c,\n  - d,\n\n"
         "- p.9 🎭 V\n\n  - e,\n  - f,\n")
    ch2 = pa.parse_summary_to_chunks(s, "doi:10.5/z", "Z")
    assert ch2[0].position.key == "p7s3.2"


TESTS = [test_source_archive, test_pdf_extract, test_validate_summary,
         test_paper_adapter_parse_and_roundtrip]


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
