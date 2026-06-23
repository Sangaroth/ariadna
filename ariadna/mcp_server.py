"""Servidor MCP HTTP que expone tools de consulta al corpus Proxy.

Arranca con `ariadna-server` (transport streamable-http, path /mcp).
Mattermost AI plugin consume las tools mediante Enable MCP Client.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ariadna.config import ARIADNA_DB_PATH, MCP_HOST, MCP_PORT, PROJECT_ROOT, WIKI_BODY_MODE
from ariadna import projects as projects_mod
from ariadna import research_queue as queue_mod
from ariadna.project_config import ProjectConfig, list_project_ids
from ariadna.search import Searcher
from ariadna.wiki_utils import strip_citations_section as _strip_citations_section

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


def _db_project_ids() -> set[str]:
    """Slugs en la tabla projects de ariadna.db."""
    if not ARIADNA_DB_PATH.exists():
        return set()
    conn = sqlite3.connect(f"file:{ARIADNA_DB_PATH}?mode=ro", uri=True)
    try:
        return {r[0] for r in conn.execute("SELECT project_id FROM projects")}
    except sqlite3.Error:
        return set()
    finally:
        conn.close()


def _resolve_wiki_page(page_id: str, project: str | None) -> list[tuple[str, str]]:
    """Resuelve (project_id, file_path) de una page_id desde ariadna.db.pages.

    Cross-all (project=None): todos los proyectos que tienen ese page_id, ordenados
    por indexed_at ascendente (el más antiguo gana el desempate). Scoped: solo ese
    proyecto. Fallback a filesystem si la página no está aún en el índice.
    """
    out: list[tuple[str, str]] = []
    if ARIADNA_DB_PATH.exists():
        conn = sqlite3.connect(f"file:{ARIADNA_DB_PATH}?mode=ro", uri=True)
        try:
            if project is not None:
                rows = conn.execute(
                    "SELECT project_id, file_path FROM pages WHERE page_id=? AND project_id=? "
                    "ORDER BY indexed_at ASC", (page_id, project)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT project_id, file_path FROM pages WHERE page_id=? ORDER BY indexed_at ASC",
                    (page_id,)).fetchall()
            out = [(p, fp) for p, fp in rows]
        finally:
            conn.close()
    if out:
        return out
    # Fallback filesystem (página en disco aún sin indexar).
    scope = [project] if project else list_project_ids()
    for slug in scope:
        for md in ProjectConfig(slug).wiki_root.rglob(f"{page_id}.md"):
            out.append((slug, str(md.relative_to(PROJECT_ROOT))))
    return out


def _db_page_body(page_id: str, project_id: str) -> str | None:
    """Devuelve body_md de una página desde ariadna.db, o None si no está.

    Fallback para servir el contenido cuando el .md no resuelve en disco (en prod
    se despliega el índice ariadna.db pero no necesariamente el árbol projects/).
    body_md está poblado para todas las páginas indexadas.
    """
    if not ARIADNA_DB_PATH.exists():
        return None
    conn = sqlite3.connect(f"file:{ARIADNA_DB_PATH}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT body_md FROM pages WHERE page_id=? AND project_id=?",
            (page_id, project_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None or row[0] is None:
        return None
    return row[0]


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
        "Busca en el corpus del canal Proxy (296 videos + 223 paginas wiki "
        "estructuradas). Devuelve DOS tipos de resultado en paralelo:\n"
        "  - wiki_pages: paginas wiki sintetizadas por concepto/autor/obra. Cada una "
        "trae metadata estructural (canonical_name, aliases, relations[] con grafo "
        "tipado) y un body_snippet (~800 chars: H1 + tesis central). Para el contenido "
        "COMPLETO de una pagina llama a get_wiki_page(page_id) — el snippet es solo "
        "para decidir si la pagina es relevante. Con wiki_body='full' (o si el "
        "servidor lo trae por defecto) cada wiki_page incluye ademas el campo 'body' "
        "con la pagina COMPLETA (citations stripped), evitando ese get_wiki_page salvo "
        "para saltos de grafo a paginas no devueltas. CUANDO USAR full: si la "
        "consulta pide el desarrollo profundo de un concepto/autor/obra concreto (o "
        "si de otro modo abririas get_wiki_page del primer resultado), pasa "
        "wiki_body='full'; para triaje amplio, exploratorio o multi-pagina deja el "
        "default (snippet) y profundiza solo en lo relevante con get_wiki_page.\n"
        "  - raw_chunks: chunks tematicos del corpus. Cada uno trae un campo "
        "cite_markdown con la cita ya formateada en markdown.\n"
        "Tambien retrieval_metadata con mode_recommended (wiki_dominant / raw_only / "
        "raw_with_warning / balanced) que orienta como usar los resultados.\n"
        "\n"
        "PARA NAVEGAR EL GRAFO:\n"
        "Las wiki_pages traen un campo relations[] con conexiones tipadas hacia otras "
        "paginas (type=exemplifies/manifestation_of/inverts/references/..., to=page_id, "
        "weight=canonical/strong/passing). Si una relacion canonical/strong apunta a un "
        "page_id que no aparece en los resultados pero es relevante para la query, llama "
        "a get_wiki_page para profundizar (2-3 saltos maximo).\n"
        "\n"
        "FORMATO DE CITAS (CRITICO):\n"
        "Cuando cites un raw_chunk, COPIA LITERALMENTE el campo cite_markdown — es un "
        "string ya formateado tipo '[Titulo del video (mm:ss)](https://youtu.be/...?t=N)'. "
        "NO construyas tus propias citas. NO uses sistema interno de annotations o "
        "citation tokens. Pegalo TAL CUAL en tu respuesta.\n"
        "Cuando cites el body completo de una wiki_page (obtenido via get_wiki_page), "
        "sus citas markdown internas (formato '→ [titulo, timestamp](url)') tambien se "
        "copian literalmente, no se regeneran.\n"
        "\n"
        "Permite filtrar por categoria ('analisis de obra', 'mitologia y religion', "
        "'psicologia', 'filosofia y teoria', 'cultura y actualidad') o playlist; "
        "los filtros aplican solo a raw_chunks (la wiki tiene su propia taxonomia).\n"
        "\n"
        "MULTI-PROYECTO: el parametro 'project' acota el corpus. Omitelo (None) para "
        "buscar en TODOS los proyectos; pasa un slug ('proxy') para uno; pasa una lista "
        "(['proxy','atlas-teleosemantico']) para cruzar varios. Cada resultado lleva su "
        "'project_id' de procedencia para que cites indicando el corpus."
    ),
)
def search_corpus(
    query: str,
    top_k: int = 5,
    top_k_wiki: int = 2,
    category: str | None = None,
    playlist: str | None = None,
    include_filtered: bool = False,
    project: str | list[str] | None = None,
    wiki_body: str | None = None,
) -> dict[str, Any]:
    """Búsqueda híbrida raw + wiki sobre el corpus.

    include_filtered: si True, incluye chunks que el pipeline marcó como
    politiqueo/promocional/casual via topic_filters.json. Por defecto se excluyen.

    project: aislamiento por proyecto (str | list[str] | None). None = todos.

    wiki_body: 'snippet' | 'full' | None. Controla si cada wiki_page trae solo
    body_snippet (~800 chars) o el body completo (campo `body`, citations stripped).
    None usa el default del servidor (config.WIKI_BODY_MODE). En 'full' normalmente
    NO necesitas get_wiki_page salvo para saltos de grafo a páginas no devueltas.
    """
    mode = wiki_body if wiki_body in ("snippet", "full") else WIKI_BODY_MODE
    searcher = get_searcher()
    try:
        return searcher.search_hybrid(
            query,
            top_k_raw=top_k,
            top_k_wiki=top_k_wiki,
            category=category,
            playlist=playlist,
            include_filtered=include_filtered,
            project=project,
            wiki_full=(mode == "full"),
        )
    except ValueError as e:
        if str(e).startswith("PROJECT_NOT_FOUND"):
            return {"error": str(e), "hint": "Usa list_projects para ver los slugs disponibles"}
        raise


@mcp.tool(
    name="get_wiki_page",
    description=(
        "Devuelve el contenido de una pagina wiki por su page_id "
        "(ej. 'shadow-archetype', 'jung-carl-gustav', 'mito-polar'). "
        "Usa esta tool cuando search_corpus devuelva un wiki_page con wikilinks "
        "salientes ([[otro-page-id]]) y necesites profundizar en una pagina relacionada "
        "para responder al usuario. Tambien para presentar al usuario el contenido "
        "completo de una pagina wiki que mencionaste. Si el page_id no existe, "
        "devuelve un error con sugerencia de buscar via search_corpus. "
        "Por defecto OMITE la seccion '## Citations' al pie (provenance al corpus "
        "YouTube; puede ocupar varios KB). Si necesitas las citas (ej. el usuario "
        "pide ver de que video sale una afirmacion), pasa include_citations=true."
    ),
)
def get_wiki_page(
    page_id: str,
    project: str | None = None,
    include_citations: bool = False,
) -> dict[str, Any]:
    """Lee una página wiki por page_id. project=None busca cross-all (desempata
    por indexed_at ascendente y expone projects_with_this_id); project='proxy' solo
    ese proyecto. Error WIKI_PAGE_NOT_FOUND si no existe."""
    if project is not None and project not in set(list_project_ids()) | _db_project_ids():
        return {"error": f"proyecto {project!r} no existe", "code": "PROJECT_NOT_FOUND"}

    # Resolución cross-project vía ariadna.db (file_path + indexed_at por proyecto).
    candidates = _resolve_wiki_page(page_id, project)
    if not candidates:
        return {
            "error": f"No se encontró página wiki con page_id={page_id!r}"
                     + (f" en project={project!r}" if project else ""),
            "code": "WIKI_PAGE_NOT_FOUND",
            "hint": "Usa search_corpus para descubrir page_ids existentes",
        }
    chosen_project, file_path = candidates[0]
    md_path = PROJECT_ROOT / file_path
    if md_path.exists():
        content = md_path.read_text(encoding="utf-8")
    else:
        # El corpus markdown puede no estar desplegado junto al índice (en prod
        # se despliega ariadna.db pero no siempre el árbol projects/). body_md
        # guarda el cuerpo completo, así que servimos desde la db como fallback.
        content = _db_page_body(page_id, chosen_project)
        if content is None:
            return {
                "error": f"file_path no resuelve en disco ni hay body_md: {file_path}",
                "code": "WIKI_PAGE_NOT_FOUND",
            }
    chars_trimmed = 0
    if not include_citations:
        content, chars_trimmed = _strip_citations_section(content)
    return {
        "page_id": page_id,
        "project_id": chosen_project,
        "file_path": file_path,
        "content": content,
        "citations_trimmed": chars_trimmed > 0,
        "citations_chars_omitted": chars_trimmed,
        "projects_with_this_id": [p for p, _ in candidates],
    }


# ---------------------------------------------------------------------------
# Tools write: gestión de proyectos y cola de ingesta (multi-proyecto)
# ---------------------------------------------------------------------------


@mcp.tool(
    name="create_project",
    description=(
        "Crea un proyecto nuevo (corpus aislado con su propia wiki, cola y scope). "
        "slug en kebab-case (^[a-z][a-z0-9-]{1,40}[a-z0-9]$). seed_from_templates=true "
        "copia las plantillas editoriales por defecto como punto de partida; "
        "inherit_from='<slug>' copia la config de otro proyecto (mutuamente excluyentes). "
        "Devuelve {project_id, paths_created} o {error, code}."
    ),
)
def create_project(
    slug: str,
    name: str,
    description: str = "",
    seed_from_templates: bool = False,
    inherit_from: str | None = None,
) -> dict[str, Any]:
    return projects_mod.create_project(
        slug, name, description, seed_from_templates, inherit_from)


@mcp.tool(
    name="add_to_research_queue",
    description=(
        "Encola una fuente (URL) para que el worker la procese e integre en el corpus "
        "del proyecto. source_type se auto-detecta (youtube/paper/web/pdf/unknown) si se "
        "omite; el caller puede forzarlo. Idempotente sobre (project, url) pendiente.\n"
        "BYPASS: si la fuente YA viene sumarizada (p.ej. un gestor de canal externo como "
        "ProxySummaries), pasa el sumario en `summary` y los metadatos en `source_metadata` "
        "(title, playlist, category…); el worker salta la sumarización e integra directo.\n"
        "Devuelve {request_id, detected_source_type, status, was_duplicate, has_summary} o {error, code}."
    ),
)
def add_to_research_queue(
    project: str,
    source_url: str,
    source_type: str | None = None,
    notes: str = "",
    priority: int = 0,
    summary: str | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return queue_mod.add_request(project, source_url, source_type, notes, priority,
                                 summary=summary, source_metadata=source_metadata)


@mcp.tool(
    name="cancel_request",
    description=(
        "Cancela un request de la cola por su request_id. pending/failed → cancelled; "
        "processing/done/cancelled → no-op (deja terminar al worker). "
        "Devuelve {request_id, previous_status, current_status} o {error, code}."
    ),
)
def cancel_request(request_id: str, reason: str = "") -> dict[str, Any]:
    return queue_mod.cancel_request(request_id, reason)


@mcp.tool(
    name="list_projects",
    description=(
        "Lista los proyectos con sus contadores (n_pages, n_chunks, n_queue_pending). "
        "include_archived=true incluye los archivados."
    ),
)
def list_projects(include_archived: bool = False) -> dict[str, Any]:
    return projects_mod.list_projects(include_archived=include_archived, store=get_searcher().store)


@mcp.tool(
    name="list_research_queue",
    description=(
        "Lista items de la cola de ingesta. project=None cruza todos; status='all' "
        "devuelve todos los estados (default 'pending'). Filtros opcionales por "
        "source_type. Devuelve {items, total_matching, filters_applied} o {error, code}."
    ),
)
def list_research_queue(
    project: str | None = None,
    status: str = "pending",
    source_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    return queue_mod.list_research_queue(project, status, source_type, limit)


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
