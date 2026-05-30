"""Adaptador YouTube — ENVUELVE parsers.py/config.py verbatim (cero regresión).

Regex y formatos idénticos a los literales que el pipeline usaba antes del
refactor universal, para garantizar:
  - paridad chunk-a-chunk con `parsers.parse_summary_file` (verify_adapter_parity)
  - que build_wiki_db reconstruya las citations EXACTAMENTE como las dejó la
    migración (`migrate_wiki_db_to_global`): cite_markdown='[título](url)',
    url sin 'www', sin '?t=' cuando timestamp_seconds==0.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ariadna.config import youtube_url
from ariadna.parsers import parse_summary_file
from ariadna.sources.base import CitationRef, GenericChunk, Position

# Regex inverso para re-extraer citas YouTube del cuerpo de una página wiki.
# Idéntico a build_wiki_db.YT_CITATION_RE (contrato preservado).
_YT_CITATION_RE = re.compile(
    r"\[([^\]]+)\]\(https?://(?:www\.)?youtu\.be/([a-zA-Z0-9_-]+)(?:\?t=(\d+))?\)"
)

# video_id desde una URL de YouTube (youtu.be/ID, watch?v=ID, embed/ID, shorts/ID).
_VIDEO_ID_RE = re.compile(
    r"(?:youtu\.be/|watch\?v=|/embed/|/shorts/|/v/)([a-zA-Z0-9_-]{11})"
)


def _fmt_ts(seconds: int) -> str:
    """Segundos → 'mm:ss' o 'h:mm:ss'. Idéntico a migrate_raw_chunks._fmt_ts."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class YoutubeAdapter:
    """Implementa `SourceAdapter` para vídeos de YouTube."""

    source_type = "youtube_video"
    scheme = "youtube"

    # --- detección / identidad --------------------------------------------- #
    def detect(self, url: str) -> bool:
        u = url.lower()
        return "youtube.com" in u or "youtu.be" in u or url.startswith("youtube:")

    def normalize_source_id(self, raw: str) -> str:
        """URL o video_id crudo → 'youtube:<id>'."""
        if raw.startswith("youtube:"):
            return raw
        m = _VIDEO_ID_RE.search(raw)
        video_id = m.group(1) if m else raw.strip()
        return f"youtube:{video_id}"

    def video_id_of(self, source_id: str) -> str:
        return source_id.split(":", 1)[1] if ":" in source_id else source_id

    # --- localización (position) ------------------------------------------- #
    def position_key(self, position: dict[str, Any]) -> str:
        return str(int(position.get("timestamp_seconds") or 0))

    def position_label(self, position: dict[str, Any]) -> str:
        """Etiqueta humana del localizador: 'mm:ss'."""
        ts_str = position.get("timestamp_str")
        if ts_str:
            return str(ts_str)
        return _fmt_ts(int(position.get("timestamp_seconds") or 0))

    def format_position_url(self, source_id: str, position: dict[str, Any]) -> str:
        vid = self.video_id_of(source_id)
        ts = int(position.get("timestamp_seconds") or 0)
        return youtube_url(vid, ts)

    def cite_markdown(self, title: str, position: dict[str, Any], url: str) -> str:
        """Formato de cita de un raw_chunk: '[Título del vídeo (mm:ss)](url)'.

        Coincide con SearchResult.to_compact_dict y migrate_raw_chunks.
        """
        return f"[{title} ({self.position_label(position)})]({url})"

    # --- extracción inversa (cuerpo wiki → citas canónicas) ---------------- #
    def citation_link_re(self) -> re.Pattern[str]:
        return _YT_CITATION_RE

    def parse_citation_match(self, match: re.Match[str]) -> CitationRef:
        """Reconstruye la cita canónica preservando el link verbatim del cuerpo.

        Replica build_wiki_db._extract_citations + migrate_wiki_db_to_global:
          url            = youtu.be/<id>[?t=<secs>] (sin www, sin ?t= si ts==0)
          source_id      = youtube:<id>
          position_key   = str(timestamp_seconds)
          cite_markdown  = '[<title>](<url>)'  (link tal cual aparece en la prosa)
        """
        title, video_id, ts = match.group(1), match.group(2), match.group(3)
        ts_int = int(ts) if ts else 0
        url = f"https://youtu.be/{video_id}"
        if ts_int > 0:
            url += f"?t={ts_int}"
        position = Position({"timestamp_seconds": ts_int}, key=str(ts_int))
        title_clean = title.strip()
        return CitationRef(
            source_id=f"youtube:{video_id}",
            position=position,
            position_url=url,
            cite_markdown=f"[{title_clean}]({url})",
            title=title_clean,
        )

    # --- parsing de sumarios a chunks -------------------------------------- #
    def parse_summary_to_chunks(
        self,
        summary_path: Path,
        meta_path: Path,
        playlist_slug: str,
    ) -> list[GenericChunk]:
        """Envuelve parsers.parse_summary_file → GenericChunk universales.

        Lossless: `extra` transporta todos los campos legacy del Chunk (video_id,
        category, playlist, channel, upload_date, duration…) que el indexador
        sigue escribiendo. La paridad se verifica en verify_adapter_parity.py.
        """
        chunks = parse_summary_file(summary_path, meta_path, playlist_slug)
        out: list[GenericChunk] = []
        for c in chunks:
            source_id = f"youtube:{c.video_id}"
            position = Position(
                {"timestamp_seconds": c.timestamp_seconds, "timestamp_str": c.timestamp},
                key=str(c.timestamp_seconds),
            )
            out.append(
                GenericChunk(
                    source_id=source_id,
                    source_type=self.source_type,
                    title=c.video_title,
                    position=position,
                    position_url=c.youtube_url,
                    cite_markdown=self.cite_markdown(
                        c.video_title, position.data, c.youtube_url
                    ),
                    theme=c.theme,
                    content=c.content,
                    full_text=c.full_text,
                    extra={
                        "video_id": c.video_id,
                        "video_title": c.video_title,
                        "timestamp": c.timestamp,
                        "timestamp_seconds": c.timestamp_seconds,
                        "category": c.category,
                        "playlist": c.playlist,
                        "channel": c.channel,
                        "upload_date": c.upload_date,
                        "duration": c.duration,
                        "youtube_url": c.youtube_url,
                    },
                )
            )
        return out
