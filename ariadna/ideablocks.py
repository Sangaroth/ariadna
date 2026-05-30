"""IdeaBlocks: persistencia del sumario + indexación de chunks Layer 0.

Un **IdeaBlock** es un tema de sumario (theme + afirmaciones sintetizadas), NO un
chunk crudo. El sumario es el paso CARO/no-determinista del pipeline (1 llamada
LLM por fuente). Persistirlo permite re-ejecutar la lógica downstream
(extract → wiki, index → Qdrant) SIN re-sumarizar ni re-descargar.

Dos responsabilidades:

  1. **Persistencia** (`write_summary`/`read_summary`/`summary_path`): guarda el
     sumario en `projects/<slug>/summaries/<sanitize(source_id)>.md` con
     frontmatter (`source_id, source_type, title, generated_at`) + cuerpo (el
     índice de IdeaBlocks tal cual lo emite el summarizer). El worker lo reusa.

  2. **Indexación Layer 0** (`index_project_chunks`): lee los sumarios
     persistidos, los parsea a `GenericChunk` vía el adapter de la fuente, los
     embebe (BGE-M3) y los upserta en Qdrant con payload universal +
     `embedding_role="chunk"`. Idempotente (borra los chunks del proyecto antes).

LOCK QDRANT: `index_project_chunks` abre el store embebido → el server MCP debe
estar PARADO (ventana batch). El worker la llama desde `index_batch`.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from ariadna.project_config import ProjectConfig
from ariadna.sources.registry import get_adapter

log = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
# Cualquier char fuera del set seguro de filename → '_'. No necesita ser reversible:
# el source_id canónico vive en el frontmatter.
_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

EMBEDDING_MODEL = "BAAI/bge-m3:1024:dense:v1"  # idéntico al de la migración universal


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sanitize(source_id: str) -> str:
    """source_id canónico ('doi:10.1016/j.x') → nombre de fichero seguro."""
    return _UNSAFE_RE.sub("_", source_id).strip("_")


def summary_path(project: str, source_id: str) -> Path:
    """Ruta del sumario persistido de una fuente dentro de un proyecto."""
    return ProjectConfig(project).summaries_dir / f"{sanitize(source_id)}.md"


def _yaml_scalar(value: str) -> str:
    """Escapa un escalar para frontmatter (entrecomilla si tiene chars conflictivos)."""
    if value and re.search(r"[:#\[\]{}\"']|^\s|\s$", value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def write_summary(
    project: str,
    source_id: str,
    summary_md: str,
    *,
    source_type: str,
    title: str,
    generated_at: str | None = None,
) -> Path:
    """Persiste el sumario (índice de IdeaBlocks) con frontmatter. Devuelve la ruta.

    Sobrescribe si ya existe (idempotente por source_id). El cuerpo es el sumario
    tal cual lo emite el summarizer — la fuente de verdad para reusar y reindexar.
    """
    path = summary_path(project, source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = [
        "---",
        f"source_id: {_yaml_scalar(source_id)}",
        f"source_type: {_yaml_scalar(source_type)}",
        f"title: {_yaml_scalar(title)}",
        f"generated_at: {generated_at or _now()}",
        "---",
    ]
    path.write_text("\n".join(fm) + "\n\n" + summary_md.strip() + "\n", encoding="utf-8")
    return path


def read_summary(project: str, source_id: str) -> dict[str, Any] | None:
    """Lee un sumario persistido. None si no existe.

    Devuelve {source_id, source_type, title, generated_at, body}. `body` es el
    sumario sin frontmatter (lo que consumen extract/parse_summary_to_chunks).
    """
    path = summary_path(project, source_id)
    if not path.exists():
        return None
    return _parse_summary_file(path)


def _parse_summary_file(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        log.warning("sumario sin frontmatter, salto: %s", path)
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        log.warning("frontmatter ilegible, salto: %s", path)
        return None
    if not fm.get("source_id"):
        return None
    return {
        "source_id": str(fm["source_id"]),
        "source_type": fm.get("source_type"),
        "title": fm.get("title") or str(fm["source_id"]),
        "generated_at": fm.get("generated_at"),
        "body": text[m.end():].strip(),
    }


def iter_summaries(project: str) -> list[dict[str, Any]]:
    """Todos los sumarios persistidos de un proyecto (parseados)."""
    d = ProjectConfig(project).summaries_dir
    if not d.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.md")):
        parsed = _parse_summary_file(p)
        if parsed:
            out.append(parsed)
    return out


def _chunk_int_id(unique_key: str) -> int:
    """ID entero estable del punto Qdrant. Namespace 'chunk:' evita colisión con
    el namespace de wiki_pages ('wiki:<project>:') y con los raw youtube legacy.

    `unique_key` es el chunk_id desambiguado (chunk_id + '#b<ordinal>'): un paper
    puede tener N IdeaBlocks en la MISMA página (position_key 'pN' compartido), así
    que el chunk_id semántico colisiona. El ordinal por fuente lo hace único sin
    tocar el position_key (que debe seguir siendo 'pN' para que el lookup de citas
    case ambos bloques con las páginas wiki que citan esa página)."""
    return int(sha256(f"chunk:{unique_key}".encode()).hexdigest()[:15], 16)


def _chunk_to_payload(chunk: Any, project: str, block_index: int) -> dict[str, Any]:
    """Payload universal de un GenericChunk (paralelo a la migración raw youtube)."""
    extra = chunk.extra or {}
    return {
        "project_id": project,
        "source_id": chunk.source_id,
        "source_type": chunk.source_type,
        "embedding_role": "chunk",
        "position": chunk.position.as_json_dict(),
        "position_url": chunk.position_url,
        "cite_markdown": chunk.cite_markdown,
        "chunk_id": chunk.chunk_id,
        "block_index": block_index,  # ordinal del IdeaBlock dentro de su (fuente, página)
        "title": chunk.title,
        "theme": chunk.theme,
        "content": chunk.content,
        "domain": extra.get("domain") or [],
        "domain_primary": extra.get("domain_primary"),
        "source_file_hash": None,
        "embedding_model": EMBEDDING_MODEL,
        "schema_version": "2.0.0",
    }


def index_project_chunks(project: str, *, embedder=None, store=None) -> int:
    """Indexa los chunks Layer 0 de los sumarios persistidos del proyecto en Qdrant.

    Lee `summaries/*.md` → adapter.parse_summary_to_chunks → embed → upsert con
    payload universal (`embedding_role="chunk"`). Idempotente: borra los chunks
    de ESTE proyecto antes (delete_by_filter project_id + embedding_role=chunk),
    sin tocar los wiki_pages ni los chunks de otros proyectos.

    Requiere el server MCP PARADO (lock Qdrant embebido). Devuelve nº de chunks
    indexados.
    """
    from ariadna.embeddings import DenseEmbedder
    from ariadna.storage import CorpusStore

    summaries = iter_summaries(project)
    if not summaries:
        log.info("sin sumarios persistidos para %s — nada que indexar", project)
        return 0

    chunks: list[Any] = []
    for s in summaries:
        adapter = get_adapter(s["source_type"] or s["source_id"])
        chunks.extend(adapter.parse_summary_to_chunks(s["body"], s["source_id"], s["title"]))
    if not chunks:
        log.info("%d sumarios pero 0 chunks parseados (project=%s)", len(summaries), project)
        return 0

    embedder = embedder or DenseEmbedder()
    vectors = embedder.embed([c.full_text for c in chunks], batch_size=16)
    store = store or CorpusStore(vector_dim=vectors.shape[1])
    store.ensure_collection(recreate=False)

    n_deleted = store.delete_by_filter({"project_id": project, "embedding_role": "chunk"})
    if n_deleted:
        log.info("borrados %d chunks Layer 0 antiguos de %s (idempotencia)", n_deleted, project)

    # Desambigua chunk_ids repetidos (N IdeaBlocks en la misma página) con un ordinal
    # estable por chunk_id → IDs únicos en el batch e idempotentes entre re-runs.
    seen: dict[str, int] = {}
    ids: list[int] = []
    payloads: list[dict[str, Any]] = []
    for c in chunks:
        n = seen.get(c.chunk_id, 0)
        seen[c.chunk_id] = n + 1
        ids.append(_chunk_int_id(f"{c.chunk_id}#b{n}"))
        payloads.append(_chunk_to_payload(c, project, n))
    if len(set(ids)) != len(ids):  # invariante: cero colisiones tras desambiguar
        raise RuntimeError(f"colisión de IDs Layer 0 en {project} ({len(ids)-len(set(ids))} dup)")
    store.upsert_batch(ids, vectors, payloads)
    log.info("indexados %d chunks Layer 0 de %d fuentes (project=%s)",
             len(chunks), len(summaries), project)
    return len(chunks)
