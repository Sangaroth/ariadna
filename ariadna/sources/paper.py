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

# Cita de paper en la prosa: '[Título, p.7](https://doi.org/10.x#page=7)'. El DOI no
# contiene '#', así que se corta en el fragmento (la página ya va en el grupo p.NN).
_PAPER_CITATION_RE = re.compile(
    r"\[([^\]]+?),\s*p\.(\d+)(?:s([\w.]+))?\]\(https?://(?:dx\.)?doi\.org/([^)#\s]+)"
    r"(?:#[^)\s]*)?\)"
)

# Marker de página en el summary del paper: '- p.7 🎭 Título' (análogo a '- MM:SS …').
_PAGE_MARKER_RE = re.compile(r"^- p\.(\d+)(?:s([\w.]+))?\s+(?P<theme>\S.*?)$", re.MULTILINE)

# Bullets dentro de un tema: línea indentada con 2+ espacios + '- ' (igual que youtube).
_BULLET_RE = re.compile(r"^\s{2,}- (.+?)[,.]?$", re.MULTILINE)

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

    # --- parsing de sumarios a chunks -------------------------------------- #
    def parse_summary_to_chunks(
        self,
        summary_md: str,
        source_id: str,
        title: str,
    ) -> list[GenericChunk]:
        """Parsea un summary.md de paper ('- p.NN 🎭 Título' + bullets) a GenericChunk.

        Paralelo a YoutubeAdapter.parse_summary_to_chunks: a diferencia del youtube
        (que saca video_id/title de meta.json), aquí el caller pasa el source_id
        canónico ('doi:...') y el título del paper.
        """
        headers = list(_PAGE_MARKER_RE.finditer(summary_md))
        out: list[GenericChunk] = []
        for i, m in enumerate(headers):
            page = int(m.group(1))
            section = m.group(2)
            theme = m.group("theme").strip()
            body_start = m.end()
            body_end = headers[i + 1].start() if i + 1 < len(headers) else len(summary_md)
            bullets = [b.group(1).strip() for b in _BULLET_RE.finditer(summary_md[body_start:body_end])]
            if not bullets:
                continue
            content = "\n".join(f"- {b}" for b in bullets)
            pos_data: dict[str, Any] = {"page": page}
            if section:
                pos_data["section"] = section
            position = Position(pos_data, key=self.position_key(pos_data))
            url = self.format_position_url(source_id, pos_data)
            out.append(
                GenericChunk(
                    source_id=source_id,
                    source_type=self.source_type,
                    title=title,
                    position=position,
                    position_url=url,
                    cite_markdown=self.cite_markdown(title, pos_data, url),
                    theme=theme,
                    content=content,
                    full_text=f"{theme}\n\n{content}",
                    extra={"page": page, "section": section},
                )
            )
        return out

    # --- adquisición / sumarización (F6/F7) -------------------------------- #
    def summarize(self, blob: bytes, title: str, *, model: str | None = None) -> str:
        """PDF → summary.md (markers [p.NN]) vía el summarizer nativo de Ariadna."""
        from ariadna.summarize import generate_paper_summary
        return generate_paper_summary(blob, title=title, model=model)

    def fetch_metadata(self, url: str) -> Any:
        raise NotImplementedError("PaperAdapter.fetch_metadata (paper-search) llega en F6")

    def acquire(self, *args: Any, **kwargs: Any) -> bytes:
        raise NotImplementedError("PaperAdapter.acquire (download_paper) llega en F7")
