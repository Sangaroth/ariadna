"""Retrieval sobre el corpus indexado + CLI de prueba."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from typing import Any

from ariadna.embeddings import DenseEmbedder
from ariadna.storage import CorpusStore

log = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Resultado de una busqueda (chunk + score)."""

    score: float
    video_id: str
    video_title: str
    timestamp: str
    timestamp_seconds: int
    theme: str
    content: str
    category: str
    playlist: str
    youtube_url: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> SearchResult:
        return cls(
            score=payload["score"],
            video_id=payload["video_id"],
            video_title=payload["video_title"],
            timestamp=payload["timestamp"],
            timestamp_seconds=payload["timestamp_seconds"],
            theme=payload["theme"],
            content=payload["content"],
            category=payload["category"],
            playlist=payload["playlist"],
            youtube_url=payload["youtube_url"],
        )

    def to_compact_dict(self) -> dict[str, Any]:
        """Version compacta para respuestas MCP."""
        return {
            "score": round(self.score, 4),
            "video_title": self.video_title,
            "timestamp": self.timestamp,
            "theme": self.theme,
            "content": self.content,
            "category": self.category,
            "playlist": self.playlist,
            "youtube_url": self.youtube_url,
        }


class Searcher:
    """Encapsula embedder + store para busquedas."""

    def __init__(
        self,
        embedder: DenseEmbedder | None = None,
        store: CorpusStore | None = None,
    ) -> None:
        self.embedder = embedder or DenseEmbedder()
        self.store = store or CorpusStore()

    def search(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
        playlist: str | None = None,
        video_id: str | None = None,
    ) -> list[SearchResult]:
        """Busqueda semantica con filtros opcionales."""
        query_vec = self.embedder.embed_query(query)
        filters = {
            "category": category,
            "playlist": playlist,
            "video_id": video_id,
        }
        raw = self.store.search(query_vec, top_k=top_k, filters=filters)
        return [SearchResult.from_payload(r) for r in raw]


def _format_result(r: SearchResult, index: int) -> str:
    return (
        f"\n[{index}] score={r.score:.3f}  {r.category} · {r.playlist}\n"
        f"    {r.video_title}  [{r.timestamp}]\n"
        f"    {r.theme}\n"
        f"    → {r.youtube_url}\n"
        f"{r.content}\n"
    )


def cli_main() -> int:
    parser = argparse.ArgumentParser(
        description="Busqueda en el corpus Proxy indexado."
    )
    parser.add_argument("query", type=str, help="Texto de busqueda")
    parser.add_argument("--top-k", type=int, default=5, help="Numero de resultados")
    parser.add_argument("--category", type=str, default=None, help="Filtrar por categoria")
    parser.add_argument("--playlist", type=str, default=None, help="Filtrar por playlist slug")
    parser.add_argument("--video", type=str, default=None, help="Filtrar por video_id")
    parser.add_argument("--json", action="store_true", help="Output JSON en vez de texto")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    searcher = Searcher()
    results = searcher.search(
        args.query,
        top_k=args.top_k,
        category=args.category,
        playlist=args.playlist,
        video_id=args.video,
    )

    if args.json:
        print(json.dumps([r.to_compact_dict() for r in results], ensure_ascii=False, indent=2))
    else:
        print(f"\n=== Query: {args.query!r} ({len(results)} resultados) ===")
        for i, r in enumerate(results, 1):
            print(_format_result(r, i))

    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
