"""Extracción de páginas wiki desde sumarios, por fuente.

YouTube usa el motor pesado existente (`scripts/extract_video_themes.py`, intacto,
afinado para el corpus Proxy). Los papers usan un extractor LEAN aquí (decisión:
no unificar el motor de 4000 líneas; ambos viven tras la interfaz del adapter).

    from ariadna.extract.paper import extract_paper_to_pages, materialize_pages
"""

from __future__ import annotations

from ariadna.extract.paper import (
    extract_paper_to_pages,
    materialize_pages,
    render_page_markdown,
)

__all__ = ["extract_paper_to_pages", "materialize_pages", "render_page_markdown"]
