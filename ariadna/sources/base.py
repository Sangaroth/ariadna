"""Interfaz y tipos comunes de los adaptadores de fuente.

Tres tipos de datos forman la "forma común" a la que todo adaptador traduce su
fuente nativa (TAXONOMY_PROPOSAL §3):

  - `Position`  — localizador polimórfico dentro de una fuente. youtube →
                  {timestamp_seconds}; paper → {page[, section]}. Su `key` es el
                  string estable que indexa SQLite (`position_key` en citations).
  - `SourceRecord` — registro bibliográfico canónico (1 por documento, tabla
                  global `sources`).
  - `GenericChunk` — unidad temática indexable (forma común de un chunk raw),
                  con su `source_id`/`position`/`cite_markdown` ya resueltos.

`SourceAdapter` es el Protocol que encapsula las 4 operaciones acopladas a la
fuente (detectar, adquirir, extraer, citar) + los helpers de localización. El
pipeline depende SOLO de esta interfaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# --------------------------------------------------------------------------- #
# Tipos de datos comunes
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Position:
    """Localizador polimórfico dentro de una fuente.

    `data` es el dict que se serializa a `citations.position` (JSON). `key` es el
    discriminador estable que va en la PK de citations (`position_key`): SQLite no
    indexa JSON, así que necesitamos un string determinista por localizador.

    Ejemplos:
      youtube → Position({"timestamp_seconds": 323}), key="323"
      paper   → Position({"page": 7}), key="p7"
      paper   → Position({"page": 7, "section": "3.2"}), key="p7s3.2"
    """

    data: dict[str, Any]
    key: str

    def as_json_dict(self) -> dict[str, Any]:
        return dict(self.data)


@dataclass
class SourceRecord:
    """Registro bibliográfico canónico de una fuente (tabla global `sources`)."""

    source_id: str                       # <scheme>:<id> — youtube:VID | doi:10.x
    source_type: str                     # youtube_video | paper | web_article | ...
    title: str
    language: str | None = None
    publication_date: str | None = None
    canonical_url: str | None = None
    abstract: str | None = None
    confidence_source: str | None = None
    ingest_method: str | None = None
    source_file_hash: str | None = None
    type_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenericChunk:
    """Unidad temática indexable, forma común de un chunk raw.

    Los campos `source_id`/`source_type`/`position`/`position_url`/`cite_markdown`
    son el shape universal (payload Qdrant + citations). `extra` transporta los
    campos legacy/específicos de la fuente (video_id, category, playlist… para
    youtube) que el indexador sigue escribiendo por compatibilidad.
    """

    source_id: str
    source_type: str
    title: str                  # título de la fuente (video_title / paper title)
    position: Position
    position_url: str
    cite_markdown: str
    theme: str                  # emoji + título del bloque temático
    content: str                # cuerpo del chunk
    full_text: str              # texto a embeber (theme + content)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def chunk_id(self) -> str:
        """ID semántico universal: <source_id>#<position_key>."""
        return f"{self.source_id}#{self.position.key}"


@dataclass
class CitationRef:
    """Cita extraída del cuerpo de una página wiki (regex inverso del adapter).

    Es la contraparte de `cite_markdown`: re-parsea un enlace ya renderizado en
    la prosa para reconstruir su localizador canónico (lo usa build_wiki_db).
    """

    source_id: str
    position: Position
    position_url: str
    cite_markdown: str
    title: str


# --------------------------------------------------------------------------- #
# Protocolo del adaptador
# --------------------------------------------------------------------------- #


@runtime_checkable
class SourceAdapter(Protocol):
    """Encapsula todo lo específico de un tipo de fuente.

    Implementaciones: `ariadna.sources.youtube.YoutubeAdapter` (completa),
    `ariadna.sources.paper.PaperAdapter` (localización completa; adquisición en F6).
    """

    #: source_type canónico que escribe el adaptador (sources.source_type / payload).
    source_type: str
    #: scheme del source_id (`youtube`, `doi`, `url`…).
    scheme: str

    # --- detección / identidad --------------------------------------------- #
    def detect(self, url: str) -> bool:
        """¿Esta URL/identificador corresponde a este adaptador?"""
        ...

    def normalize_source_id(self, raw: str) -> str:
        """Normaliza una URL o id nativo al source_id canónico `<scheme>:<id>`."""
        ...

    # --- localización (position) ------------------------------------------- #
    def position_key(self, position: dict[str, Any]) -> str:
        """String estable para la PK de citations a partir del dict `position`."""
        ...

    def format_position_url(self, source_id: str, position: dict[str, Any]) -> str:
        """URL clicable al localizador (youtu.be/ID?t=N | doi.org/...#page=N)."""
        ...

    def cite_markdown(self, title: str, position: dict[str, Any], url: str) -> str:
        """Markdown precomputado de la cita ('[Título (mm:ss)](url)')."""
        ...

    # --- extracción inversa (del cuerpo wiki a citas canónicas) ------------ #
    def citation_link_re(self) -> re.Pattern[str]:
        """Regex que matchea las citas de este tipo en la prosa de una página."""
        ...

    def parse_citation_match(self, match: re.Match[str]) -> CitationRef:
        """Convierte un match de `citation_link_re()` en una `CitationRef`."""
        ...

    # --- parsing de sumarios a chunks -------------------------------------- #
    def parse_summary_to_chunks(self, *args: Any, **kwargs: Any) -> list[GenericChunk]:
        """Parsea un summary.md a chunks universales."""
        ...
