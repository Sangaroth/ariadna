"""Adaptador de papers (DOI/PDF) — primer tipo de fuente nuevo.

F4 entrega la LOCALIZACIÓN completa (detección, source_id canónico, position por
página, URLs y citas), que es lo que search/build_wiki_db/index necesitan para
ser source-agnostic. La ADQUISICIÓN (fetch_metadata vía paper-search, acquire vía
download_paper, parse_summary_to_chunks) llega en F6/F7 — aquí queda como
NotImplementedError declarativo.
"""

from __future__ import annotations

import re
from typing import Any

from ariadna.sources.base import CitationRef, GenericChunk, Position

# Cita de paper en la prosa: '[Título, p.7](https://doi.org/10.x)' (sección opcional).
_PAPER_CITATION_RE = re.compile(
    r"\[([^\]]+?),\s*p\.(\d+)(?:s([\w.]+))?\]\(https?://(?:dx\.)?doi\.org/([^)\s]+)\)"
)

# Marker de página en el summary del paper: '- p.7 🎭 Título' (análogo a '- MM:SS …').
_PAGE_MARKER_RE = re.compile(r"^- p\.(\d+)(?:s([\w.]+))?\s+(?P<theme>\S.*?)$", re.MULTILINE)

# DOI / arXiv en una URL o identificador crudo.
_DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+)")
_ARXIV_RE = re.compile(r"arxiv\.org/abs/([\w.]+)", re.IGNORECASE)


class PaperAdapter:
    """Implementa la parte de localización de `SourceAdapter` para papers."""

    source_type = "paper"
    scheme = "doi"

    # --- detección / identidad --------------------------------------------- #
    def detect(self, url: str) -> bool:
        u = url.lower()
        return (
            "doi.org" in u
            or "arxiv.org" in u
            or u.startswith("doi:")
            or u.endswith(".pdf")
            or bool(_DOI_RE.search(url))
        )

    def normalize_source_id(self, raw: str) -> str:
        """URL/DOI/arXiv crudo → 'doi:<doi>' (o 'arxiv:<id>' si no hay DOI)."""
        if raw.startswith(("doi:", "arxiv:")):
            return raw
        m = _DOI_RE.search(raw)
        if m:
            return f"doi:{m.group(1)}"
        a = _ARXIV_RE.search(raw)
        if a:
            return f"arxiv:{a.group(1)}"
        return f"doi:{raw.strip()}"

    def _bare_id(self, source_id: str) -> str:
        return source_id.split(":", 1)[1] if ":" in source_id else source_id

    # --- localización (position) ------------------------------------------- #
    def position_key(self, position: dict[str, Any]) -> str:
        """'p7' | 'p7s3.2' — estable para la PK de citations."""
        page = int(position["page"])
        section = position.get("section")
        return f"p{page}" + (f"s{section}" if section else "")

    def position_label(self, position: dict[str, Any]) -> str:
        page = int(position["page"])
        section = position.get("section")
        return f"p.{page}" + (f" §{section}" if section else "")

    def format_position_url(self, source_id: str, position: dict[str, Any]) -> str:
        scheme, _, ident = source_id.partition(":")
        page = int(position["page"])
        if scheme == "arxiv":
            return f"https://arxiv.org/abs/{ident}#page={page}"
        return f"https://doi.org/{ident}#page={page}"

    def cite_markdown(self, title: str, position: dict[str, Any], url: str) -> str:
        return f"[{title}, {self.position_label(position)}]({url})"

    # --- extracción inversa (cuerpo wiki → citas canónicas) ---------------- #
    def citation_link_re(self) -> re.Pattern[str]:
        return _PAPER_CITATION_RE

    def parse_citation_match(self, match: re.Match[str]) -> CitationRef:
        title, page, section, doi = match.groups()
        pos_data: dict[str, Any] = {"page": int(page)}
        if section:
            pos_data["section"] = section
        position = Position(pos_data, key=self.position_key(pos_data))
        source_id = f"doi:{doi}"
        url = self.format_position_url(source_id, pos_data)
        title_clean = title.strip()
        return CitationRef(
            source_id=source_id,
            position=position,
            position_url=url,
            cite_markdown=self.cite_markdown(title_clean, pos_data, url),
            title=title_clean,
        )

    def summary_marker_re(self) -> re.Pattern[str]:
        return _PAGE_MARKER_RE

    # --- adquisición / parsing (F6/F7) ------------------------------------- #
    def parse_summary_to_chunks(self, *args: Any, **kwargs: Any) -> list[GenericChunk]:
        raise NotImplementedError("PaperAdapter.parse_summary_to_chunks llega en F6")

    def fetch_metadata(self, url: str) -> Any:
        raise NotImplementedError("PaperAdapter.fetch_metadata (paper-search) llega en F6")

    def acquire(self, *args: Any, **kwargs: Any) -> bytes:
        raise NotImplementedError("PaperAdapter.acquire (download_paper) llega en F7")
