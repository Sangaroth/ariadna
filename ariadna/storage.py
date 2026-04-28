"""Wrapper de Qdrant para almacenar y consultar chunks del corpus.

Usa Qdrant en modo embebido (persistencia en disco local). Cuando despleguemos
en Hetzner se puede migrar facilmente a Qdrant server con el mismo codigo.
"""

from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from ariadna.config import COLLECTION_NAME, EMBED_DIM, QDRANT_PATH, ensure_data_dirs

log = logging.getLogger(__name__)


# Categorias canonicas del corpus (con acentos, tal como las almacena ProxySummaries).
# Permitimos que el LLM o usuario mande variantes sin acentos y normalizamos aqui.
CANONICAL_CATEGORIES = [
    "análisis de obra",
    "cultura y actualidad",
    "filosofía y teoría",
    "mitología y religión",
    "psicología",
]


def _strip_accents(text: str) -> str:
    """Elimina acentos y diacriticos preservando el resto."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_category(value: str | None) -> str | None:
    """Mapea una categoria posiblemente sin acentos a la forma canonica del corpus.

    Si no matchea ninguna, devuelve el valor original (por si el usuario quisiera
    filtrar por una categoria inexistente, para que la consulta devuelva vacio
    en vez de explotar).
    """
    if not value:
        return value
    value_norm = _strip_accents(value).lower().strip()
    for canonical in CANONICAL_CATEGORIES:
        if _strip_accents(canonical).lower() == value_norm:
            return canonical
    return value


class CorpusStore:
    """Storage del corpus indexado sobre Qdrant."""

    def __init__(
        self,
        qdrant_path: Path = QDRANT_PATH,
        collection_name: str = COLLECTION_NAME,
        vector_dim: int = EMBED_DIM,
    ) -> None:
        ensure_data_dirs()
        self.collection_name = collection_name
        self.vector_dim = vector_dim
        self.client = QdrantClient(path=str(qdrant_path))

    def ensure_collection(self, recreate: bool = False) -> None:
        """Crea la coleccion si no existe. Si recreate=True, borra y crea de cero."""
        exists = self.client.collection_exists(self.collection_name)
        if exists and recreate:
            log.info("Borrando coleccion %s (recreate=True)", self.collection_name)
            self.client.delete_collection(self.collection_name)
            exists = False
        if not exists:
            log.info("Creando coleccion %s (dim=%d)", self.collection_name, self.vector_dim)
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_dim,
                    distance=Distance.COSINE,
                ),
            )

    def upsert_batch(
        self,
        ids: list[int],
        vectors: np.ndarray,
        payloads: list[dict[str, Any]],
    ) -> None:
        """Inserta o actualiza puntos en la coleccion."""
        assert len(ids) == len(vectors) == len(payloads), (
            f"Mismatch: {len(ids)} ids, {len(vectors)} vectors, {len(payloads)} payloads"
        )
        points = [
            PointStruct(id=pid, vector=vec.tolist(), payload=payload)
            for pid, vec, payload in zip(ids, vectors, payloads, strict=True)
        ]
        self.client.upsert(collection_name=self.collection_name, points=points)

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Busqueda por similaridad vectorial con filtros opcionales por metadata.

        filters: dict con claves permitidas (category, playlist, video_id).
                 Matching exact por valor.
        """
        qdrant_filter: Filter | None = None
        if filters:
            # Normaliza category para aceptar variantes sin acentos
            normalized = {
                key: (normalize_category(value) if key == "category" else value)
                for key, value in filters.items()
                if value is not None
            }
            must_conditions = [
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in normalized.items()
            ]
            if must_conditions:
                qdrant_filter = Filter(must=must_conditions)

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector.tolist(),
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        ).points

        return [
            {"score": float(p.score), **(p.payload or {})}
            for p in results
        ]

    def count(self) -> int:
        """Numero de puntos en la coleccion."""
        try:
            return self.client.count(self.collection_name).count
        except Exception:
            return 0

    def get_by_video(self, video_id: str) -> list[dict[str, Any]]:
        """Devuelve todos los chunks de un video, ordenados por timestamp."""
        results, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="video_id", match=MatchValue(value=video_id))]
            ),
            limit=500,  # videos largos pueden tener >100 chunks
            with_payload=True,
        )
        chunks = [p.payload for p in results if p.payload]
        chunks.sort(key=lambda c: c.get("timestamp_seconds", 0))
        return chunks

    def list_videos(
        self,
        category: str | None = None,
        playlist: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista videos unicos con su metadata. Filtros opcionales."""
        must_conditions = []
        if category:
            canonical = normalize_category(category)
            must_conditions.append(
                FieldCondition(key="category", match=MatchValue(value=canonical))
            )
        if playlist:
            must_conditions.append(FieldCondition(key="playlist", match=MatchValue(value=playlist)))

        qdrant_filter = Filter(must=must_conditions) if must_conditions else None

        # Scroll paginado para conseguir todos los puntos que coincidan, agrupando por video_id
        seen: dict[str, dict[str, Any]] = {}
        offset = None
        while True:
            results, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=qdrant_filter,
                limit=500,
                offset=offset,
                with_payload=True,
            )
            if not results:
                break
            for p in results:
                payload = p.payload or {}
                vid = payload.get("video_id")
                if vid and vid not in seen:
                    seen[vid] = {
                        "video_id": vid,
                        "video_title": payload.get("video_title"),
                        "category": payload.get("category"),
                        "playlist": payload.get("playlist"),
                        "upload_date": payload.get("upload_date"),
                        "duration": payload.get("duration"),
                    }
            if offset is None:
                break

        videos = list(seen.values())
        videos.sort(key=lambda v: v.get("upload_date") or "", reverse=True)
        return videos
