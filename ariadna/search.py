"""Retrieval sobre el corpus indexado + CLI de prueba."""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ariadna.config import RERANKER_PREFETCH_N
from ariadna.embeddings import DenseEmbedder
from ariadna.reranker import Reranker
from ariadna.storage import CorpusStore

log = logging.getLogger(__name__)

WIKI_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "wiki.db"


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
    # Score mínimo de un raw_chunk para activar el lookup indirecto wiki vía citations.
    # Chunks débiles no arrastran páginas wiki — evita falsos positivos.
    CITATION_LOOKUP_MIN_SCORE = 0.55
    # Threshold más estricto para el fallback same-video (chunk no halló cita
    # exacta en su timestamp, pero el vídeo entero cita la page en otros chunks).
    # Más estricto porque pass-2 amplifica matches débiles → exigimos que el
    # chunk en sí sea genuinamente relevante antes de heredar wikis del vídeo.
    CITATION_LOOKUP_VIDEO_FALLBACK_MIN_SCORE = 0.60
    # Penalty multiplicativo para video-only matches: el chunk no está citado
    # exactamente; la asociación es por co-pertenencia al mismo vídeo. Score
    # efectivo = chunk_score * MULTIPLIER. Calibrado a 0.3 para que un
    # video-only match con chunk_score=0.7 (≈0.21) quede claramente por
    # debajo de un exact match con chunk_score=0.6 (≈0.6) en el ranking.
    CITATION_VIDEO_FALLBACK_SCORE_MULTIPLIER = 0.3

    def __init__(
        self,
        embedder: DenseEmbedder | None = None,
        store: CorpusStore | None = None,
        reranker: Reranker | None = None,
        wiki_db_path: Path | None = None,
    ) -> None:
        self.embedder = embedder or DenseEmbedder()
        self.store = store or CorpusStore()
        self.reranker = reranker or Reranker()
        self.wiki_db_path = wiki_db_path or WIKI_DB_PATH
        if not self.wiki_db_path.exists():
            log.warning(
                "wiki.db no existe en %s — lookup indirecto vía citations desactivado. "
                "Ejecuta `python scripts/build_wiki_db.py` para activarlo.",
                self.wiki_db_path,
            )

    def _open_wiki_db(self) -> sqlite3.Connection | None:
        """Abre conexión read-only a wiki.db. None si no existe."""
        if not self.wiki_db_path.exists():
            return None
        # Read-only previene escrituras accidentales desde el server.
        return sqlite3.connect(f"file:{self.wiki_db_path}?mode=ro", uri=True)

    def search(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
        playlist: str | None = None,
        video_id: str | None = None,
    ) -> list[SearchResult]:
        """Busqueda semantica sobre chunks raw con reranker cross-encoder.

        Pipeline: dense top-N (N=RERANKER_PREFETCH_N, ~20) -> rerank -> top_k.
        El rerank_score sustituye a 'score' en el output (es lo que ordena).
        Mantiene contrato anterior para compatibilidad con CLI ariadna-search.
        """
        query_vec = self.embedder.embed_query(query)
        filters = {
            "category": category,
            "playlist": playlist,
            "video_id": video_id,
        }
        prefetch_k = max(RERANKER_PREFETCH_N, top_k)
        raw = self.store.search(
            query_vec,
            top_k=prefetch_k,
            filters=filters,
            must_not_filters={"source_type": "wiki_page"},
        )
        reranked = self.reranker.rerank(query, raw, top_k=top_k)
        for r in reranked:
            r["dense_score"] = r["score"]
            r["score"] = r.pop("rerank_score")
        return [SearchResult.from_payload(r) for r in reranked]

    def search_hybrid(
        self,
        query: str,
        top_k_raw: int = 5,
        top_k_wiki: int = 2,
        category: str | None = None,
        playlist: str | None = None,
    ) -> dict:
        """Búsqueda híbrida raw + wiki en una sola query.

        Tres lanes de retrieval sobre la misma fuente de verdad:
          1. Semántica raw — chunks por similitud BGE-M3 (excluye wiki_pages).
          2. Semántica wiki — vector focal de cada página por similitud BGE-M3.
          3. Indirecta wiki vía citations — para los chunks raw con score alto,
             JOIN contra `data/wiki.db:citations` para traer páginas wiki que
             citan literalmente esos chunks como fuente. Solucina queries sobre
             sub-aspectos donde el focal de la wiki no captura por sí solo
             pero la wiki sí cita el chunk relevante en su prosa. Cero índice
             semántico extra: el grafo derivado del filesystem (citations) hace
             el trabajo. Ver docs/RESPONSE_FLOW.md §2.4 y backlog.

        Cada entrada de wiki_pages lleva `match_via`:
          - "semantic"  → matched solo por similitud focal
          - "citation"  → matched solo por citation lookup
          - "both"      → ambos
        Y cuando aplica, `matched_via_chunks[]` lista los chunks que dispararon
        la entrada vía citation (para que el LLM sepa por qué la página entró).
        """
        query_vec = self.embedder.embed_query(query)

        raw_filters = {"category": category, "playlist": playlist}
        # Prefetch ampliado para que el reranker tenga material que reordenar.
        prefetch_k = max(RERANKER_PREFETCH_N, top_k_raw)
        raw_results_dense = self.store.search(
            query_vec,
            top_k=prefetch_k,
            filters=raw_filters,
            must_not_filters={"source_type": "wiki_page"},
        )
        # Guardamos el top cosine ANTES de rerankear: lo usa mode_recommended para
        # comparar con wiki_top (también cosine). El rerank_score no es comparable.
        raw_top_cosine = raw_results_dense[0]["score"] if raw_results_dense else None

        # Rerank cross-encoder: top-N dense -> top_k_raw final.
        raw_results = self.reranker.rerank(query, raw_results_dense, top_k=top_k_raw)
        for r in raw_results:
            r["dense_score"] = r["score"]
            r["score"] = r.pop("rerank_score")

        # La wiki no se filtra por category/playlist (tiene su propia taxonomía OpenAlex).
        # No se rerankea: top_k_wiki=2 típicamente, body es página completa
        # (max_length 512 truncaría), score semantics distintas (focal vector).
        wiki_results = self.store.search(
            query_vec,
            top_k=top_k_wiki,
            filters={"source_type": "wiki_page"},
        )

        # Lookup indirecto vía citations: page_id -> [triggering_chunk_summary, ...].
        # IMPORTANTE: la lane indirecta debe ser CATEGORY-BLIND igual que la wiki semántica.
        # Si el LLM/usuario aplica un filtro de categoría, los chunks "semilla" para citation
        # lookup no deben heredarlo: una wiki page puede sintetizar material que vive en otra
        # categoría (ej. jung-carl-gustav cita Orfeo y Eurídice en categoría 'filosofía' aunque
        # la query sea categoría 'psicología'). Sin esto, el filtro mata silenciosamente el
        # mecanismo indirecto. Coste: una query Qdrant extra solo cuando hay filtros activos.
        if category or playlist:
            citation_seed = self.store.search(
                query_vec,
                top_k=top_k_raw,
                filters={},
                must_not_filters={"source_type": "wiki_page"},
            )
        else:
            citation_seed = raw_results
        citation_hits = self._lookup_wiki_via_citations(citation_seed)

        # Marca in_wiki_sources en los chunks raw que sí devolvemos al LLM (los filtrados).
        # Esto sí respeta el filtro: el campo es metadata sobre los chunks que el LLM ve.
        chunks_to_wiki = self._build_chunk_to_wiki_index(raw_results)
        for r in raw_results:
            key = (r.get("video_id"), r.get("timestamp_seconds"))
            r["in_wiki_sources"] = chunks_to_wiki.get(key, [])

        wiki_pages_compact = self._merge_wiki_lanes(
            semantic=wiki_results,
            citation_hits=citation_hits,
        )

        wiki_top_semantic = wiki_results[0]["score"] if wiki_results else None
        # raw_top en cosine (NO rerank_score) para que sea comparable con wiki_top_semantic.
        raw_top = raw_top_cosine

        # mode_recommended se calcula sobre la wiki SEMÁNTICA. La citation lane es
        # navegación enriquecida, no un canal de ranking — su score deriva del chunk
        # citante y no es comparable directamente con la similitud focal.
        if wiki_top_semantic is None and raw_top is None:
            mode = "no_results"
        elif wiki_top_semantic is None:
            mode = "raw_only" if not citation_hits else "raw_with_wiki_via_citation"
        elif wiki_top_semantic >= self.WIKI_DOMINANT_SCORE and (raw_top is None or wiki_top_semantic > raw_top):
            mode = "wiki_dominant"
        elif wiki_top_semantic < self.WIKI_THIN_THRESHOLD:
            mode = "raw_with_warning"
        else:
            mode = "balanced"

        warning: str | None = None
        if mode == "raw_with_warning":
            warning = (
                f"Wiki coverage thin (top score {wiki_top_semantic:.3f}). Considera el resultado wiki "
                "como contexto débil; apóyate principalmente en los raw_chunks."
            )

        return {
            "wiki_pages": wiki_pages_compact,
            "raw_chunks": [
                SearchResult.from_payload(r).to_compact_dict() | {"in_wiki_sources": r.get("in_wiki_sources")}
                for r in raw_results
            ],
            "retrieval_metadata": {
                "wiki_top_score": round(wiki_top_semantic, 4) if wiki_top_semantic is not None else None,
                "raw_top_score": round(raw_top, 4) if raw_top is not None else None,
                "mode_recommended": mode,
                "warning": warning,
                "wiki_pages_count": len(wiki_pages_compact),
                "wiki_via_citation_count": sum(
                    1 for w in wiki_pages_compact if w.get("match_via") in {"citation", "citation_video", "both"}
                ),
                "wiki_via_citation_exact_count": sum(
                    1 for w in wiki_pages_compact if w.get("match_via") in {"citation", "both"}
                ),
                "wiki_via_citation_video_only_count": sum(
                    1 for w in wiki_pages_compact if w.get("match_via") == "citation_video"
                ),
                "raw_chunks_count": len(raw_results),
            },
        }

    # --- helpers para retrieval indirecto vía citations -----------------

    def _lookup_wiki_via_citations(
        self,
        raw_results: list[dict],
    ) -> dict[str, list[dict]]:
        """Para los raw_chunks con score >= CITATION_LOOKUP_MIN_SCORE, busca en
        data/wiki.db:citations qué wiki pages los citan.

        Dos passes:
          1. **Exact match** (video_id, timestamp_seconds): el chunk está citado
             literalmente en la wiki page. match_strength='exact'.
          2. **Same-video fallback**: chunks que no hallaron exact match (con
             score más estricto: CITATION_LOOKUP_VIDEO_FALLBACK_MIN_SCORE)
             buscan páginas citadas POR EL MISMO VÍDEO (cualquier timestamp).
             match_strength='video_only', score efectivo penalizado por
             CITATION_VIDEO_FALLBACK_SCORE_MULTIPLIER (0.3 por defecto).
             Razón: un vídeo de 2h sobre Tolkien que cita mito-polar en t=300
             arrastra mito-polar para chunks vecinos (t=600, t=900) que el
             extractor no citó explícitamente — recall mejorado con penalty.

        Devuelve un dict {page_id: [chunk_summary, ...]} donde chunk_summary
        contiene info del chunk disparador (video_id, timestamp_seconds,
        video_title, chunk_score, match_strength, effective_score).

        Si wiki.db no existe, devuelve {}.
        """
        conn = self._open_wiki_db()
        if conn is None:
            return {}
        try:
            hits: dict[str, list[dict]] = {}
            # Track chunks que no hallaron exact match para pass 2
            chunks_for_fallback: list[dict] = []

            # --- Pass 1: exact match (video_id, timestamp_seconds) ---
            for r in raw_results:
                dense_score = float(r.get("dense_score", r.get("score", 0.0)))
                if dense_score < self.CITATION_LOOKUP_MIN_SCORE:
                    continue
                video_id = r.get("video_id")
                ts = r.get("timestamp_seconds")
                if not video_id:
                    continue
                rows = conn.execute(
                    """SELECT page_id FROM citations
                       WHERE video_id = ? AND timestamp_seconds = ?""",
                    (video_id, int(ts or 0)),
                ).fetchall()
                if rows:
                    chunk_summary = {
                        "video_id": video_id,
                        "timestamp_seconds": int(ts or 0),
                        "video_title": r.get("video_title"),
                        "chunk_score": round(dense_score, 4),
                        "match_strength": "exact",
                        "effective_score": round(dense_score, 4),
                    }
                    for (page_id,) in rows:
                        hits.setdefault(page_id, []).append(chunk_summary)
                else:
                    # No exact match → candidato para pass 2 si pasa threshold estricto
                    if dense_score >= self.CITATION_LOOKUP_VIDEO_FALLBACK_MIN_SCORE:
                        chunks_for_fallback.append({
                            "video_id": video_id,
                            "timestamp_seconds": int(ts or 0),
                            "video_title": r.get("video_title"),
                            "chunk_score": round(dense_score, 4),
                        })

            # --- Pass 2: same-video fallback ---
            # Pages que ya entraron por exact match para este (video, *): no
            # las contamos otra vez con video-only (sería ruido). Si una page
            # tiene match exact para algún chunk del vídeo, el chunk vecino
            # video-only no aporta info adicional a esa page.
            videos_with_exact_match_per_page: dict[str, set[str]] = {}
            for pid, chunks in hits.items():
                videos_with_exact_match_per_page[pid] = {
                    c["video_id"] for c in chunks if c.get("match_strength") == "exact"
                }

            for chunk in chunks_for_fallback:
                video_id = chunk["video_id"]
                rows = conn.execute(
                    """SELECT DISTINCT page_id FROM citations WHERE video_id = ?""",
                    (video_id,),
                ).fetchall()
                if not rows:
                    continue
                effective = round(
                    chunk["chunk_score"] * self.CITATION_VIDEO_FALLBACK_SCORE_MULTIPLIER, 4
                )
                chunk_summary = {
                    "video_id": video_id,
                    "timestamp_seconds": chunk["timestamp_seconds"],
                    "video_title": chunk["video_title"],
                    "chunk_score": chunk["chunk_score"],
                    "match_strength": "video_only",
                    "effective_score": effective,
                }
                for (page_id,) in rows:
                    # Si la page ya tiene exact match para este vídeo, skip
                    # (no añade info: el chunk video-only es huérfano dentro
                    # del vídeo, pero la page ya está cubierta por otro chunk).
                    if video_id in videos_with_exact_match_per_page.get(page_id, set()):
                        continue
                    hits.setdefault(page_id, []).append(chunk_summary)
            return hits
        finally:
            conn.close()

    def _build_chunk_to_wiki_index(
        self,
        raw_results: list[dict],
    ) -> dict[tuple[str, int], list[str]]:
        """Inversa de _lookup_wiki_via_citations: para cada chunk (sin filtro de score),
        qué wiki pages lo citan. Pobla raw_chunks[].in_wiki_sources.

        Distinto de _lookup_wiki_via_citations en dos cosas:
          - No filtra por score (todos los chunks devueltos quieren saber si están
            cubiertos en wiki — es metadata de navegación, no ranking).
          - Devuelve solo page_ids, no objetos enriquecidos.
        """
        conn = self._open_wiki_db()
        if conn is None:
            return {}
        try:
            out: dict[tuple[str, int], list[str]] = {}
            for r in raw_results:
                video_id = r.get("video_id")
                ts = int(r.get("timestamp_seconds") or 0)
                if not video_id:
                    continue
                rows = conn.execute(
                    """SELECT page_id FROM citations
                       WHERE video_id = ? AND timestamp_seconds = ?""",
                    (video_id, ts),
                ).fetchall()
                if rows:
                    out[(video_id, ts)] = [pid for (pid,) in rows]
            return out
        finally:
            conn.close()

    def _fetch_wiki_pages_from_db(self, page_ids: list[str]) -> dict[str, dict]:
        """Construye dicts compactos de wiki_pages desde wiki.db (paralelo a
        _wiki_payload_to_compact que lo hace desde Qdrant). Usado para entradas
        que entraron solo vía citation y por tanto no tienen vector focal en
        los resultados Qdrant.

        Devuelve {page_id: compact_dict_sin_score}. El caller decide el score
        (típicamente derivado del chunk citante).
        """
        if not page_ids:
            return {}
        conn = self._open_wiki_db()
        if conn is None:
            return {}
        try:
            placeholders = ",".join("?" * len(page_ids))
            pages = conn.execute(
                f"""SELECT page_id, page_type, canonical_name, domain_primary, file_path, body_md
                    FROM pages WHERE page_id IN ({placeholders})""",
                page_ids,
            ).fetchall()
            aliases = conn.execute(
                f"SELECT page_id, alias FROM aliases WHERE page_id IN ({placeholders})",
                page_ids,
            ).fetchall()
            relations = conn.execute(
                f"""SELECT from_page_id, type, to_page_id, note, weight
                    FROM relations WHERE from_page_id IN ({placeholders})""",
                page_ids,
            ).fetchall()

            aliases_by_pid: dict[str, list[str]] = {}
            for pid, a in aliases:
                aliases_by_pid.setdefault(pid, []).append(a)

            relations_by_pid: dict[str, list[dict]] = {}
            for from_pid, rtype, to_pid, note, weight in relations:
                rel: dict[str, Any] = {"type": rtype, "to": to_pid}
                if note:
                    rel["note"] = note
                if weight:
                    rel["weight"] = weight
                relations_by_pid.setdefault(from_pid, []).append(rel)

            out: dict[str, dict] = {}
            for pid, ptype, cname, dprim, fpath, body in pages:
                rels = relations_by_pid.get(pid, [])
                out[pid] = {
                    "page_id": pid,
                    "page_type": ptype,
                    "canonical_name": cname,
                    "domain_primary": dprim,
                    "aliases": sorted(aliases_by_pid.get(pid, [])),
                    "relations": rels,
                    "relation_targets": sorted({r["to"] for r in rels if r.get("to")}),
                    "relation_types_present": sorted({r["type"] for r in rels if r.get("type")}),
                    "file_path": fpath,
                    "body": body,
                }
            return out
        finally:
            conn.close()

    def _merge_wiki_lanes(
        self,
        semantic: list[dict],
        citation_hits: dict[str, list[dict]],
    ) -> list[dict]:
        """Une la wiki lane semántica con la lane indirecta vía citations.

        Reglas:
          - Página en ambas → match_via="both", score = semántico (más fuerte y
            comparable con thresholds). matched_via_chunks listadas.
          - Solo semántica → match_via="semantic".
          - Solo citation → match_via="citation", score = max(chunk_score) de los
            chunks citantes. Página fetched desde wiki.db (no estaba en Qdrant top).

        Resultado ordenado por score desc.
        """
        sem_compact = [_wiki_payload_to_compact(w) for w in semantic]
        sem_pids = {w["page_id"] for w in sem_compact}

        # 1. Anota match_via en las semánticas y attach matched_via_chunks si aplica.
        for w in sem_compact:
            pid = w["page_id"]
            triggering = citation_hits.get(pid)
            if triggering:
                # match_via 'both' aplica aunque las citas sean video-only:
                # la page ya entró semánticamente, las citas son enrichment.
                w["match_via"] = "both"
                w["matched_via_chunks"] = triggering
            else:
                w["match_via"] = "semantic"

        # 2. Para page_ids que están solo en citation_hits, fetch desde wiki.db.
        citation_only_pids = [pid for pid in citation_hits if pid not in sem_pids]
        fetched = self._fetch_wiki_pages_from_db(citation_only_pids)

        for pid, chunks in citation_hits.items():
            if pid in sem_pids:
                continue
            page_dict = fetched.get(pid)
            if page_dict is None:
                # Citation huérfana — el JOIN devolvió un page_id que no existe en pages.
                # Posible si el DB está stale respecto a wiki/. Skip silencioso.
                continue
            # Score = max(effective_score) para que video-only matches ranqueen
            # por debajo de exact matches con scores comparables. Si la page
            # solo tiene chunks video-only, su score se ve correctamente
            # penalizado para no dominar el output sobre semánticas reales.
            effective_scores = [c.get("effective_score", c["chunk_score"]) for c in chunks]
            score = max(effective_scores)
            page_dict["score"] = round(float(score), 4)
            # Distinguir entre citation con al menos un exact y solo-video-only:
            # el LLM puede usar match_via para juzgar la fuerza de la conexión.
            has_exact = any(c.get("match_strength") == "exact" for c in chunks)
            page_dict["match_via"] = "citation" if has_exact else "citation_video"
            page_dict["matched_via_chunks"] = chunks
            sem_compact.append(page_dict)

        sem_compact.sort(key=lambda w: w.get("score", 0), reverse=True)
        return sem_compact


def _wiki_payload_to_compact(payload: dict) -> dict:
    """Versión compacta de un wiki_page para output MCP.

    Las wiki_pages NO llevan cite_markdown propio: el body ya contiene
    las citas a YouTube como markdown ('→ [titulo, timestamp](url)').
    El LLM hot debe COPIAR esas citas literalmente del body, NO regenerarlas
    con annotations internas (que producen tokens basura citeturnN).

    Expone el grafo tipado (relations[] + relation_targets +
    relation_types_present) producido por scripts/index_wiki_to_qdrant.py
    tras la migración de 2026-04-30.
    """
    return {
        "score": round(float(payload["score"]), 4),
        "page_id": payload.get("page_id"),
        "page_type": payload.get("page_type"),
        "canonical_name": payload.get("canonical_name"),
        "domain_primary": payload.get("domain_primary"),
        "aliases": payload.get("aliases", []),
        "relations": payload.get("relations", []),
        "relation_targets": payload.get("relation_targets", []),
        "relation_types_present": payload.get("relation_types_present", []),
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
