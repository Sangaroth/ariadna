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
        """Version compacta para respuestas MCP.

        Incluye cite_markdown pre-renderizado: el LLM hot debe COPIARLO
        literalmente al citar, en vez de construir su propia cita o usar
        annotations internas (que el plugin Mattermost v2.0.0-rc6 renderiza
        como tokens basura tipo 'citeturn0searchN').
        """
        cite_md = f"[{self.video_title} ({self.timestamp})]({self.youtube_url})"
        return {
            "score": round(self.score, 4),
            "video_title": self.video_title,
            "timestamp": self.timestamp,
            "theme": self.theme,
            "content": self.content,
            "category": self.category,
            "playlist": self.playlist,
            "youtube_url": self.youtube_url,
            "cite_markdown": cite_md,
        }


class Searcher:
    """Encapsula embedder + store para busquedas."""

    # Thresholds para mode_recommended del modo híbrido. Provisionales — tunear con uso real.
    WIKI_DOMINANT_SCORE = 0.65
    RAW_FALLBACK_THRESHOLD = 0.45
    WIKI_THIN_THRESHOLD = 0.55

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
        """Busqueda semantica solo sobre chunks raw (excluye wiki_pages).

        Mantiene contrato anterior para compatibilidad con CLI ariadna-search.
        """
        query_vec = self.embedder.embed_query(query)
        filters = {
            "category": category,
            "playlist": playlist,
            "video_id": video_id,
        }
        raw = self.store.search(
            query_vec,
            top_k=top_k,
            filters=filters,
            must_not_filters={"source_type": "wiki_page"},
        )
        return [SearchResult.from_payload(r) for r in raw]

    def search_hybrid(
        self,
        query: str,
        top_k_raw: int = 5,
        top_k_wiki: int = 2,
        category: str | None = None,
        playlist: str | None = None,
    ) -> dict:
        """Búsqueda híbrida raw + wiki en una sola query.

        Devuelve estructura definida en docs/RESPONSE_FLOW.md §2.4: wiki_pages
        + raw_chunks + retrieval_metadata. El LLM hot decide qué pesa más
        según mode_recommended.
        """
        query_vec = self.embedder.embed_query(query)

        raw_filters = {"category": category, "playlist": playlist}
        raw_results = self.store.search(
            query_vec,
            top_k=top_k_raw,
            filters=raw_filters,
            must_not_filters={"source_type": "wiki_page"},
        )

        # La wiki no se filtra por category/playlist (tiene su propia taxonomía OpenAlex).
        wiki_results = self.store.search(
            query_vec,
            top_k=top_k_wiki,
            filters={"source_type": "wiki_page"},
        )

        # Marca in_wiki_sources en chunks raw (drift detection).
        # Cada wiki_page tiene una lista implícita de fuentes en su body via "youtube:VID#SEC".
        # Para el primer prototipo dejamos in_wiki_sources=null (TODO: extraer chunk_ids
        # del cuerpo de la wiki en el indexador y emparejar aquí).
        for r in raw_results:
            r.setdefault("in_wiki_sources", None)

        wiki_top = wiki_results[0]["score"] if wiki_results else None
        raw_top = raw_results[0]["score"] if raw_results else None

        if wiki_top is None and raw_top is None:
            mode = "no_results"
        elif wiki_top is None:
            mode = "raw_only"
        elif wiki_top >= self.WIKI_DOMINANT_SCORE and (raw_top is None or wiki_top > raw_top):
            mode = "wiki_dominant"
        elif wiki_top < self.WIKI_THIN_THRESHOLD:
            mode = "raw_with_warning"
        else:
            mode = "balanced"

        warning: str | None = None
        if mode == "raw_with_warning":
            warning = (
                f"Wiki coverage thin (top score {wiki_top:.3f}). Considera el resultado wiki "
                "como contexto débil; apóyate principalmente en los raw_chunks."
            )

        return {
            "wiki_pages": [_wiki_payload_to_compact(w) for w in wiki_results],
            "raw_chunks": [
                SearchResult.from_payload(r).to_compact_dict() | {"in_wiki_sources": r.get("in_wiki_sources")}
                for r in raw_results
            ],
            "retrieval_metadata": {
                "wiki_top_score": round(wiki_top, 4) if wiki_top is not None else None,
                "raw_top_score": round(raw_top, 4) if raw_top is not None else None,
                "mode_recommended": mode,
                "warning": warning,
                "wiki_pages_count": len(wiki_results),
                "raw_chunks_count": len(raw_results),
            },
        }


def _wiki_payload_to_compact(payload: dict) -> dict:
    """Versión compacta de un wiki_page para output MCP.

    Las wiki_pages NO llevan cite_markdown propio: el body ya contiene
    las citas a YouTube como markdown ('→ [titulo, timestamp](url)').
    El LLM hot debe COPIAR esas citas literalmente del body, NO regenerarlas
    con annotations internas (que producen tokens basura citeturnN).
    """
    return {
        "score": round(float(payload["score"]), 4),
        "page_id": payload.get("page_id"),
        "page_type": payload.get("page_type"),
        "canonical_name": payload.get("canonical_name"),
        "domain_primary": payload.get("domain_primary"),
        "aliases": payload.get("aliases", []),
        "related_concepts": payload.get("related_concepts", []),
        "related_authors": payload.get("related_authors", []),
        "related_works": payload.get("related_works", []),
        "file_path": payload.get("file_path"),
        "body": payload.get("body"),
    }


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
