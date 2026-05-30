"""Registro de adaptadores — única fuente de verdad para resolver tipos de fuente.

`get_adapter` acepta tanto el source_type canónico (`youtube_video`, `paper`) como
el scheme del source_id (`youtube`, `doi`, `arxiv`), para que el caller pueda
resolver desde un payload (`source_type`) o desde un `source_id` (`youtube:VID`).
"""

from __future__ import annotations

from typing import Iterator

from ariadna.sources.base import SourceAdapter
from ariadna.sources.paper import PaperAdapter
from ariadna.sources.youtube import YoutubeAdapter

# Instancias singleton (los adaptadores son stateless).
_ADAPTERS: list[SourceAdapter] = [YoutubeAdapter(), PaperAdapter()]

# source_type / scheme → adapter. Ambos resuelven al mismo objeto.
_BY_KEY: dict[str, SourceAdapter] = {}
for _a in _ADAPTERS:
    _BY_KEY[_a.source_type] = _a
    _BY_KEY[_a.scheme] = _a


def get_adapter(key: str) -> SourceAdapter:
    """Resuelve un adaptador por source_type (`youtube_video`) o scheme (`youtube`).

    Acepta también un source_id completo (`youtube:VID` → scheme `youtube`).
    """
    if key in _BY_KEY:
        return _BY_KEY[key]
    scheme = key.split(":", 1)[0]
    if scheme in _BY_KEY:
        return _BY_KEY[scheme]
    raise KeyError(f"No hay adaptador para {key!r} (conocidos: {sorted(_BY_KEY)})")


def adapter_for_source_id(source_id: str) -> SourceAdapter:
    """Resuelve el adaptador a partir del scheme de un source_id (`<scheme>:<id>`)."""
    return get_adapter(source_id.split(":", 1)[0])


def detect_source_type(url: str) -> str:
    """Detecta el source_type canónico de una URL. 'unknown' si ningún adapter la reconoce."""
    for a in _ADAPTERS:
        if a.detect(url):
            return a.source_type
    return "unknown"


def iter_adapters() -> Iterator[SourceAdapter]:
    """Itera todos los adaptadores registrados (p.ej. para probar cada citation_link_re)."""
    yield from _ADAPTERS
