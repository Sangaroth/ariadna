"""Helpers compartidos para servir contenido wiki (sin importar fastmcp)."""

from __future__ import annotations

import re

# Heading de la sección Citations al pie de cada wiki. Se trima por defecto
# tanto en search_corpus (body inline) como en get_wiki_page para no inflar
# context window del LLM con provenance que no aporta a razonamiento
# conceptual (5-8 KB por hub). Variantes en español/inglés soportadas.
_CITATIONS_HEADING_RE = re.compile(
    r"^##\s+(?:Citations?|Referencias?|References?|Sources?|Fuentes?)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def strip_citations_section(content: str) -> tuple[str, int]:
    """Trima la sección Citations al pie. Asume que es la última sección H2
    (convención del extractor). Returns: (content_sin_citations, n_chars_removed)."""
    m = _CITATIONS_HEADING_RE.search(content)
    if not m:
        return content, 0
    trimmed = content[: m.start()].rstrip() + "\n"
    return trimmed, len(content) - len(trimmed)
