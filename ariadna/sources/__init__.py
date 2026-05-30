"""Adaptadores de fuente: encapsulan TODO el acoplamiento a un tipo de fuente
(youtube, paper, web…) detrás de una interfaz común.

Añadir un tipo de fuente = añadir una clase que implemente `SourceAdapter` y
registrarla en `registry.py`. El resto del pipeline (extract → compile →
build_wiki_db → index → search) consume las fuentes por interfaz, sin ramificar
por tipo.

Punto de entrada habitual:

    from ariadna.sources import get_adapter, detect_source_type
    adapter = get_adapter("youtube_video")        # por source_type canónico
    adapter = get_adapter(detect_source_type(url))  # por URL

Ver el plan maestro §C y docs/TAXONOMY_PROPOSAL.md §3.
"""

from __future__ import annotations

from ariadna.sources.base import GenericChunk, Position, SourceAdapter, SourceRecord
from ariadna.sources.registry import (
    detect_source_type,
    get_adapter,
    iter_adapters,
)

__all__ = [
    "GenericChunk",
    "Position",
    "SourceAdapter",
    "SourceRecord",
    "detect_source_type",
    "get_adapter",
    "iter_adapters",
]
