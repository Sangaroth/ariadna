"""Servidor MCP HTTP que expone tools de consulta al corpus Proxy.

Arranca con `ariadna-server` (transport streamable-http, path /mcp).
Mattermost AI plugin consume las tools mediante Enable MCP Client.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ariadna.config import DEFAULT_CORPUS_PATH, MCP_HOST, MCP_PORT, PROJECT_ROOT
from ariadna.parsers import parse_summary_file
from ariadna.search import Searcher
from ariadna.storage import CorpusStore

WIKI_DIR = PROJECT_ROOT / "wiki"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ariadna.mcp")

# ---------------------------------------------------------------------------
# Singleton: Searcher (comparte modelo + Qdrant client)
# ---------------------------------------------------------------------------

_searcher: Searcher | None = None


def get_searcher() -> Searcher:
    global _searcher
    if _searcher is None:
        log.info("Inicializando searcher (primera llamada)...")
        _searcher = Searcher()
    return _searcher


# ---------------------------------------------------------------------------
# Servidor MCP
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="ariadna",
    instructions=(
        "Servidor MCP que da acceso al corpus del canal Proxy "
        "(288 videos analiticos sobre mitologia, psicologia, filosofia, "
        "analisis de obra, cultura). Usa las tools para consultar contenido "
        "especifico, obtener summaries de videos, y listar con filtros."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path="/mcp",
    stateless_http=True,  # mas simple para Mattermost; sin sesiones
    log_level="INFO",
)


@mcp.tool(
    name="search_corpus",
    description=(
        "Busca en el corpus del canal Proxy (288 videos + wiki estructurada). "
        "Devuelve DOS tipos de resultado en paralelo:\n"
        "  - wiki_pages: paginas wiki sintetizadas por concepto/autor/obra. Si tienen "
        "score alto (>=0.65) son sintesis pre-cocinadas que puedes adaptar.\n"
        "  - raw_chunks: chunks tematicos del corpus con timestamp y URL clicable. "
        "Son la fuente primaria, citables.\n"
        "Tambien retrieval_metadata con mode_recommended (wiki_dominant / raw_only / "
        "raw_with_warning / balanced) que orienta como usar los resultados.\n"
        "Cita siempre los raw_chunks como fuente. Si hay wiki_page con score alto, "
        "apoyate en su sintesis y usa los raw_chunks como verificacion. "
        "Permite filtrar por categoria ('analisis de obra', 'mitologia y religion', "
        "'psicologia', 'filosofia y teoria', 'cultura y actualidad') o playlist; "
        "los filtros aplican solo a raw_chunks (la wiki tiene su propia taxonomia)."
    ),
)
def search_corpus(
    query: str,
    top_k: int = 5,
    top_k_wiki: int = 2,
    category: str | None = None,
    playlist: str | None = None,
) -> dict[str, Any]:
    """Búsqueda híbrida raw + wiki sobre el corpus."""
    searcher = get_searcher()
    return searcher.search_hybrid(
        query,
        top_k_raw=top_k,
        top_k_wiki=top_k_wiki,
        category=category,
        playlist=playlist,
    )


@mcp.tool(
    name="get_wiki_page",
    description=(
        "Devuelve el contenido completo de una pagina wiki por su page_id "
        "(ej. 'shadow-archetype', 'jung-carl-gustav', 'mito-polar'). "
        "Usa esta tool cuando search_corpus devuelva un wiki_page con wikilinks "
        "salientes ([[otro-page-id]]) y necesites profundizar en una pagina relacionada "
        "para responder al usuario. Tambien para presentar al usuario el contenido "
        "completo de una pagina wiki que mencionaste. Si el page_id no existe, "
        "devuelve un error con sugerencia de buscar via search_corpus."
    ),
)
def get_wiki_page(page_id: str) -> dict[str, Any]:
    """Lee una página wiki por page_id desde el filesystem (wiki/)."""
    candidates = list(WIKI_DIR.rglob(f"{page_id}.md"))
    if not candidates:
        return {
            "error": f"No se encontró página wiki con page_id={page_id!r}",
            "hint": "Usa search_corpus para descubrir page_ids existentes en wiki_pages",
        }
    md_path = candidates[0]
    content = md_path.read_text(encoding="utf-8")
    return {
        "page_id": page_id,
        "file_path": str(md_path.relative_to(PROJECT_ROOT)),
        "content": content,
    }


@mcp.tool(
    name="get_video_summary",
    description=(
        "Devuelve el summary completo y ordenado de un video concreto del canal "
        "(todos sus chunks tematicos en orden cronologico). "
        "Usa esta tool tras un search_corpus para profundizar en un video que "
        "parece relevante, o cuando el usuario pide ver el contenido completo "
        "de un video especifico. Requiere el video_id de YouTube."
    ),
)
def get_video_summary(video_id: str) -> dict[str, Any]:
    """Summary completo de un video por su video_id de YouTube."""
    store = CorpusStore()
    chunks = store.get_by_video(video_id)
    if not chunks:
        return {
            "error": f"No se encontro video con id {video_id}",
            "hint": "Usa search_corpus primero para localizar el video_id correcto",
        }

    first = chunks[0]
    return {
        "video_id": video_id,
        "video_title": first["video_title"],
        "category": first["category"],
        "playlist": first["playlist"],
        "upload_date": first["upload_date"],
        "duration_seconds": first["duration"],
        "youtube_url": f"https://youtu.be/{video_id}",
        "num_chunks": len(chunks),
        "chunks": [
            {
                "timestamp": c["timestamp"],
                "theme": c["theme"],
                "content": c["content"],
                "youtube_url": c["youtube_url"],
            }
            for c in chunks
        ],
    }


@mcp.tool(
    name="list_videos",
    description=(
        "Lista videos del corpus con filtros opcionales. "
        "Usa para responder preguntas como 'que videos hay sobre X', "
        "'listame los analisis arqueтipicos', 'que tienes en psicologia'. "
        "Sin filtros devuelve todos los 288 videos (puede ser mucho, mejor filtra)."
    ),
)
def list_videos(
    category: str | None = None,
    playlist: str | None = None,
) -> list[dict[str, Any]]:
    """Lista videos filtrados por categoria y/o playlist."""
    store = CorpusStore()
    videos = store.list_videos(category=category, playlist=playlist)
    return videos


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Ariadna MCP server (HTTP streamable).")
    parser.add_argument("--host", default=MCP_HOST, help="Host de escucha")
    parser.add_argument("--port", type=int, default=MCP_PORT, help="Puerto")
    parser.add_argument(
        "--warm",
        action="store_true",
        help="Precarga el searcher al arrancar (recomendado en produccion)",
    )
    args = parser.parse_args()

    # Actualiza host/port si se pasan por CLI
    mcp.settings.host = args.host
    mcp.settings.port = args.port

    log.info("Arrancando Ariadna MCP en http://%s:%d/mcp", args.host, args.port)

    if args.warm:
        log.info("Precarga: inicializando searcher...")
        get_searcher()
        log.info("Searcher listo.")

    mcp.run(transport="streamable-http")
    return 0


if __name__ == "__main__":
    sys.exit(main())
