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


# Cap del snippet por wiki_page en search_corpus. Lo justo para que el LLM
# decida si la página merece get_wiki_page completo. Captura H1 + primer H2
# + primer párrafo (convención editorial del extractor: la tesis central
# arranca en el primer H2). El body completo se sirve via get_wiki_page.
SNIPPET_MAX_CHARS = 800


def extract_body_snippet(body: str, max_chars: int = SNIPPET_MAX_CHARS) -> str:
    """Devuelve un snippet del body wiki: H1 + primer H2 + primer párrafo.

    Heurística:
    - Tomamos hasta el primer H2 inclusive (estructura general).
    - Añadimos hasta el siguiente párrafo (la tesis central del concepto).
    - Cap duro a max_chars con elipsis si excede.

    Si el body no tiene H2 (caso raro: stub o frontmatter-only), devuelve
    los primeros max_chars del body crudo.
    """
    if not body or not body.strip():
        return ""

    lines = body.split("\n")
    result_lines: list[str] = []
    first_h2_seen = False
    paragraph_after_h2_started = False

    for line in lines:
        stripped = line.strip()
        is_h2 = stripped.startswith("## ")

        if is_h2:
            if first_h2_seen:
                # Llegamos al segundo H2: cortamos antes
                break
            first_h2_seen = True
            result_lines.append(line)
            continue

        if first_h2_seen:
            if stripped == "":
                if paragraph_after_h2_started:
                    # blank line tras párrafo: corte natural
                    break
                # blank line entre H2 y primer párrafo: la conservamos
                result_lines.append(line)
                continue
            paragraph_after_h2_started = True

        result_lines.append(line)

    snippet = "\n".join(result_lines).rstrip()
    if not snippet:
        snippet = body[:max_chars].rstrip()
    if len(snippet) > max_chars:
        # Corta limpio en el último blank antes del cap, con elipsis
        cut = snippet[:max_chars].rsplit(" ", 1)[0]
        snippet = cut.rstrip() + "..."
    return snippet
