"""Configuracion central: rutas, modelo de embeddings, Qdrant."""

from __future__ import annotations

import os
from pathlib import Path

# Rutas
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
QDRANT_PATH = DATA_DIR / "qdrant"

# Corpus externo (ProxySummaries)
DEFAULT_CORPUS_PATH = Path(
    os.getenv(
        "ARIADNA_CORPUS_PATH",
        str(PROJECT_ROOT.parent / "ProxySummaries" / "data" / "playlists"),
    )
)

# Embeddings
EMBED_MODEL_NAME = os.getenv("ARIADNA_EMBED_MODEL", "BAAI/bge-m3")
EMBED_DIM = 1024  # dimension de BGE-M3 dense
EMBED_DEVICE = os.getenv("ARIADNA_EMBED_DEVICE", "cuda")  # cuda | cpu
EMBED_BATCH_SIZE = int(os.getenv("ARIADNA_EMBED_BATCH", "32"))

# Qdrant collection
COLLECTION_NAME = os.getenv("ARIADNA_COLLECTION", "proxy_corpus")

# Servidor MCP
MCP_HOST = os.getenv("ARIADNA_MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("ARIADNA_MCP_PORT", "8080"))
MCP_AUTH_TOKEN = os.getenv("ARIADNA_MCP_TOKEN", "")  # vacio = sin auth (solo dev local)

# YouTube base para citas clicables
YOUTUBE_WATCH_BASE = "https://youtu.be"


def youtube_url(video_id: str, timestamp_seconds: int | None = None) -> str:
    """Construye URL de YouTube con timestamp opcional."""
    base = f"{YOUTUBE_WATCH_BASE}/{video_id}"
    if timestamp_seconds is not None and timestamp_seconds > 0:
        return f"{base}?t={timestamp_seconds}"
    return base


def ensure_data_dirs() -> None:
    """Crea directorios de datos si no existen."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QDRANT_PATH.mkdir(parents=True, exist_ok=True)
