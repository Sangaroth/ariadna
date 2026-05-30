"""Archivo content-addressable de fuentes (data/sources/<hash[:2]>/<hash>.<ext>).

GLOBAL y mínimo (plan §A "Source Archive"): 1 blob físico por documento crudo,
direccionado por sha256, con su fila en `source_files`. NUNCA se sirve como
contexto — existe solo para dedup y reproducibilidad (un DOI retirado no deja
chunks huérfanos; un re-proceso parte del mismo blob).

El worker (F7) llama a `store()` tras descargar un PDF; guarda el hash en
`sources.source_file_hash` y en los chunks.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ariadna.config import ARIADNA_DB_PATH, DATA_DIR

SOURCES_DIR = DATA_DIR / "sources"

# sha256 hex: exactamente 64 hex. Validar ANTES de usar el hash en una ruta evita
# path traversal (un "hash" como '../..' envenenaría path_for_hash).
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_blob(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def path_for_hash(file_hash: str, ext: str, sources_dir: Path = SOURCES_DIR) -> Path:
    """data/sources/<hash[:2]>/<hash>.<ext> (sharding por prefijo para no saturar un dir)."""
    ext = ext.lstrip(".")
    return sources_dir / file_hash[:2] / f"{file_hash}.{ext}"


def exists(file_hash: str, db_path: Path = ARIADNA_DB_PATH) -> bool:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return conn.execute(
            "SELECT 1 FROM source_files WHERE source_file_hash=?", (file_hash,)
        ).fetchone() is not None
    finally:
        conn.close()


def read_by_hash(
    file_hash: str,
    db_path: Path = ARIADNA_DB_PATH,
    sources_dir: Path = SOURCES_DIR,
) -> bytes:
    """Lee un blob archivado por su content-hash. Seguro: la ruta se DERIVA del hash
    (content-addressed), no se acepta del cliente. Valida formato sha256 (anti-traversal)
    y que la ruta resuelta caiga dentro de SOURCES_DIR.

    Lanza ValueError (hash inválido / fuera de SOURCES_DIR) o FileNotFoundError.
    """
    if not _SHA256_RE.match(file_hash or ""):
        raise ValueError(f"source_file_hash inválido (no es sha256 hex): {file_hash!r}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT ext FROM source_files WHERE source_file_hash=?", (file_hash,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise FileNotFoundError(f"hash no archivado en source_files: {file_hash}")
    path = path_for_hash(file_hash, row[0], sources_dir).resolve()
    base = sources_dir.resolve()
    if not path.is_relative_to(base):
        raise ValueError(f"ruta fuera de SOURCES_DIR: {path}")
    if not path.exists():
        raise FileNotFoundError(f"blob ausente en disco: {path}")
    return path.read_bytes()


def store(
    blob: bytes,
    ext: str,
    original_url: str | None = None,
    db_path: Path = ARIADNA_DB_PATH,
    sources_dir: Path = SOURCES_DIR,
) -> dict:
    """Archiva un blob. Idempotente por contenido (sha256).

    Devuelve {source_file_hash, path, byte_size, ext, was_duplicate}. Si el hash ya
    estaba archivado, no reescribe el fichero ni duplica la fila (was_duplicate=True).
    """
    ext = ext.lstrip(".")
    file_hash = hash_blob(blob)
    dest = path_for_hash(file_hash, ext, sources_dir)

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT ext, byte_size FROM source_files WHERE source_file_hash=?", (file_hash,)
        ).fetchone()
        was_duplicate = row is not None

        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)

        if not was_duplicate:
            conn.execute(
                "INSERT INTO source_files (source_file_hash, ext, byte_size, original_url, archived_at) "
                "VALUES (?,?,?,?,?)",
                (file_hash, ext, len(blob), original_url, _now()),
            )
            conn.commit()
        return {
            "source_file_hash": file_hash,
            "path": str(dest),
            "byte_size": len(blob),
            "ext": ext,
            "was_duplicate": was_duplicate,
        }
    finally:
        conn.close()
