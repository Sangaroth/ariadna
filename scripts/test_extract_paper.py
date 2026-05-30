#!/usr/bin/env python3
"""Test de regresión del extractor LEAN de papers (parte DETERMINISTA, sin LLM):
_extract_json, render_page_markdown, materialize_pages, y la integración con
build_wiki_db (las citas paper del cuerpo generado se extraen al modelo universal).

    python scripts/test_extract_paper.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PAGE = {
    "page_id": "teleosemantica", "page_type": "concept",
    "canonical_name": "Teleosemántica", "domain_primary": "humanities.philosophy.mind",
    "aliases": ["teleosemantics"],
    "relations": [{"type": "developed_by", "to": "millikan-ruth", "weight": "canonical"}],
    "body_markdown": ("# Teleosemántica\n\n## Definición\n\nDeriva contenido de la función "
                      "[Un Paper, p.3](https://doi.org/10.1/x#page=3). Ver [[millikan-ruth]]."),
    "cited_pages": [3, 5],
}


def test_extract_json() -> None:
    from ariadna.extract.paper import _extract_json
    raw = 'Aquí:\n```json\n{"pages":[{"page_id":"x","page_type":"concept","canonical_name":"X"}]}\n```\nfin'
    assert _extract_json(raw)["pages"][0]["page_id"] == "x"


def test_render_page_markdown() -> None:
    from ariadna.extract.paper import render_page_markdown
    md = render_page_markdown(PAGE, "doi:10.1/x", "Un Paper")
    assert md.startswith("---\npage_id: teleosemantica")
    assert "page_type: concept" in md and "developed_by" in md
    assert "## Citations" in md
    assert "[Un Paper, p.3](https://doi.org/10.1/x#page=3)" in md


def test_citations_extracted_by_build_wiki_db() -> None:
    from ariadna.extract.paper import render_page_markdown
    import scripts.build_wiki_db as B
    md = render_page_markdown(PAGE, "doi:10.1/x", "Un Paper")
    body = md.split("---", 2)[2]
    cites = B._extract_citations(body)
    keys = {(c["source_id"], c["position_key"]) for c in cites}
    assert ("doi:10.1/x", "p3") in keys and ("doi:10.1/x", "p5") in keys, keys
    assert all(c["position"].startswith('{"page"') for c in cites)


def test_materialize_pages() -> None:
    from ariadna.extract.paper import materialize_pages
    with tempfile.TemporaryDirectory() as td:
        wroot = Path(td) / "wiki"
        paths = materialize_pages([
            PAGE,
            {"page_id": "millikan-ruth", "page_type": "author", "canonical_name": "Ruth Millikan", "cited_pages": [1]},
            {"page_id": "BAD ID", "page_type": "concept", "canonical_name": "x"},  # inválido → skip
            {"page_id": "ok", "page_type": "tipo-raro", "canonical_name": "y"},     # type desconocido → skip
        ], "doi:10.1/x", "Un Paper", "atlas-test", wiki_root=wroot)
        names = sorted(p.relative_to(wroot).as_posix() for p in paths)
        assert names == ["authors/millikan-ruth.md", "concepts/teleosemantica.md"], names


TESTS = [test_extract_json, test_render_page_markdown,
         test_citations_extracted_by_build_wiki_db, test_materialize_pages]


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
