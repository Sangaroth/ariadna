"""Parser de summary.md de ProxySummaries a chunks con metadata."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator

from ariadna.config import youtube_url

# Regex que captura cabeceras de chunk:
#   - MM:SS emoji titulo
#   - H:MM:SS emoji titulo
# El timestamp tiene 2 o 3 componentes separados por ":".
_CHUNK_HEADER_RE = re.compile(
    r"^- (?P<ts>\d{1,2}(?::\d{2}){1,2})\s+(?P<theme>\S.*?)$",
    re.MULTILINE,
)

# Bullets dentro de un chunk: linea indentada con 2 espacios + "- "
_BULLET_RE = re.compile(r"^\s{2,}- (.+?)[,.]?$", re.MULTILINE)


@dataclass
class Chunk:
    """Un chunk tematico del corpus, listo para indexar."""

    # Identidad
    video_id: str
    video_title: str
    timestamp: str            # formato original (MM:SS o H:MM:SS)
    timestamp_seconds: int    # timestamp convertido a segundos
    theme: str                # emoji + titulo del tema

    # Contenido
    content: str              # bullets unidos por \n

    # Metadata del video
    category: str             # "analisis de obra" | ...
    playlist: str             # slug de playlist
    channel: str              # "Proxy"
    upload_date: str          # YYYYMMDD
    duration: int             # segundos del video completo

    # Conveniencia
    youtube_url: str          # URL con timestamp

    # Texto completo para embedding (theme + content)
    full_text: str = field(init=False)

    def __post_init__(self) -> None:
        self.full_text = f"{self.theme}\n\n{self.content}"

    @property
    def chunk_id(self) -> str:
        """ID estable: video_id + timestamp_seconds."""
        return f"{self.video_id}_{self.timestamp_seconds}"

    def to_payload(self) -> dict:
        """Payload para Qdrant (todo serializable)."""
        return asdict(self)


def parse_timestamp(ts: str) -> int:
    """Convierte MM:SS o H:MM:SS a segundos."""
    parts = [int(p) for p in ts.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return hours * 3600 + minutes * 60 + seconds
    raise ValueError(f"Timestamp invalido: {ts!r}")


def parse_summary_file(
    summary_path: Path,
    meta_path: Path,
    playlist_slug: str,
) -> list[Chunk]:
    """Extrae chunks de un summary.md + meta.json.

    Args:
        summary_path: ruta al summary.md
        meta_path: ruta al meta.json del mismo video
        playlist_slug: nombre de la carpeta playlist (ej. "analisis-arquetipico")

    Returns:
        Lista de Chunks. Vacia si el archivo esta mal formado o no tiene entradas.
    """
    if not summary_path.exists() or not meta_path.exists():
        return []

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    video_id = meta.get("video_id", "")
    if not video_id:
        return []

    video_title = meta.get("title", "")
    category = meta.get("category", "")
    channel = meta.get("channel", "Proxy")
    upload_date = meta.get("upload_date", "")
    duration = int(meta.get("duration", 0))

    content_text = summary_path.read_text(encoding="utf-8")
    headers = list(_CHUNK_HEADER_RE.finditer(content_text))
    if not headers:
        return []

    chunks: list[Chunk] = []
    for i, match in enumerate(headers):
        ts = match.group("ts")
        theme = match.group("theme").strip()

        # El cuerpo del chunk va desde el final del header actual hasta el
        # inicio del siguiente header (o fin del documento).
        body_start = match.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(content_text)
        body = content_text[body_start:body_end]

        bullets = [b.group(1).strip() for b in _BULLET_RE.finditer(body)]
        if not bullets:
            # Chunk sin bullets: saltar (probablemente cabecera huerfana)
            continue

        content = "\n".join(f"- {b}" for b in bullets)

        try:
            ts_seconds = parse_timestamp(ts)
        except ValueError:
            continue

        chunk = Chunk(
            video_id=video_id,
            video_title=video_title,
            timestamp=ts,
            timestamp_seconds=ts_seconds,
            theme=theme,
            content=content,
            category=category,
            playlist=playlist_slug,
            channel=channel,
            upload_date=upload_date,
            duration=duration,
            youtube_url=youtube_url(video_id, ts_seconds),
        )
        chunks.append(chunk)

    return chunks


def iter_corpus(corpus_root: Path) -> Iterator[tuple[Path, Path, str]]:
    """Itera sobre (summary_path, meta_path, playlist_slug) del corpus completo.

    Estructura esperada:
        corpus_root/
          <playlist-slug>/
            <video-slug>/
              summary.md
              meta.json
    """
    if not corpus_root.exists():
        return

    for playlist_dir in sorted(corpus_root.iterdir()):
        if not playlist_dir.is_dir():
            continue
        for video_dir in sorted(playlist_dir.iterdir()):
            if not video_dir.is_dir():
                continue
            summary = video_dir / "summary.md"
            meta = video_dir / "meta.json"
            if summary.exists() and meta.exists():
                yield summary, meta, playlist_dir.name


def parse_corpus(corpus_root: Path) -> list[Chunk]:
    """Parsea el corpus completo. Util para scripts simples; para streaming usar iter_corpus."""
    all_chunks: list[Chunk] = []
    for summary, meta, playlist in iter_corpus(corpus_root):
        all_chunks.extend(parse_summary_file(summary, meta, playlist))
    return all_chunks
