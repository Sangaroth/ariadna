"""Extracción de PDF página-a-página con pymupdf → texto con marcas [p.NN].

Análogo a la transcripción con marcas [MM:SS]: cada página queda prefijada por su
marca [p.NN] (1-based) para que el LLM ancle cada tema a una página real. markitdown
se descartó por no preservar páginas (plan §D).
"""

from __future__ import annotations

from pathlib import Path

import fitz  # pymupdf


def extract_pages(pdf: bytes | Path) -> list[tuple[int, str]]:
    """Devuelve [(page_num 1-based, texto)]. Acepta bytes o ruta."""
    if isinstance(pdf, (str, Path)):
        doc = fitz.open(pdf)
    else:
        doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        pages: list[tuple[int, str]] = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            pages.append((i, text))
        return pages
    finally:
        doc.close()


def pdf_to_summary_input(pages: list[tuple[int, str]], skip_empty: bool = True) -> str:
    """Concatena las páginas con marcas [p.NN] como entrada del summarizer.

    Formato (paralelo a la transcripción [MM:SS]):
        [p.1]
        <texto de la página 1>

        [p.2]
        ...
    """
    parts: list[str] = []
    for num, text in pages:
        if skip_empty and not text.strip():
            continue
        parts.append(f"[p.{num}]\n{text}")
    return "\n\n".join(parts)
