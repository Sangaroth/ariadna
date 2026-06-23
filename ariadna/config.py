"""Configuracion central: rutas, modelo de embeddings, Qdrant."""

from __future__ import annotations

import os
from pathlib import Path

# Rutas
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
QDRANT_PATH = DATA_DIR / "qdrant"
# Capa de datos unificada (multi-tenant + modelo universal).
ARIADNA_DB_PATH = DATA_DIR / "ariadna.db"

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

# Reranker (cross-encoder sobre top-N de dense)
RERANKER_MODEL_NAME = os.getenv("ARIADNA_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
RERANKER_PREFETCH_N = int(os.getenv("ARIADNA_RERANKER_PREFETCH", "20"))
RERANKER_MAX_LENGTH = int(os.getenv("ARIADNA_RERANKER_MAX_LENGTH", "512"))

# --- Backend de inferencia: local (sentence-transformers) | api (HTTP) ---
# Conmutables por separado: puedes mantener el reranker local y delegar solo
# embeddings, o viceversa. Default 'local' => comportamiento idéntico al previo.
EMBED_BACKEND = os.getenv("ARIADNA_EMBED_BACKEND", "local")  # local | onnx | api
RERANK_BACKEND = os.getenv("ARIADNA_RERANK_BACKEND", "local")  # local | api | sim

# ONNX backend del embedder: MISMO BGE-M3 (dim 1024, misma calidad base) pero
# en ONNX Runtime + int8 -> ~4x más ligero y más rápido en CPU. Mismo índice.
# Generar con: python -m scripts.export_onnx_embedder
ONNX_MODEL_PATH = os.getenv("ARIADNA_ONNX_PATH", str(DATA_DIR / "models" / "bge-m3-onnx"))
ONNX_FILE_NAME = os.getenv("ARIADNA_ONNX_FILE", "onnx/model_quint8_avx2.onnx")

# API backend (endpoint OpenAI-compatible para embeddings + rerank tipo DeepInfra).
API_BASE_URL = os.getenv("ARIADNA_API_BASE_URL", "https://api.deepinfra.com/v1/openai")
API_KEY = os.getenv("ARIADNA_API_KEY", "")
API_EMBED_MODEL = os.getenv("ARIADNA_API_EMBED_MODEL", "BAAI/bge-m3")
# DeepInfra no hostea bge-reranker-v2-m3; usamos Qwen3-Reranker-0.6B (más nuevo,
# barato ~$0.01/1M tokens). Endpoint inference: {"queries":[q], "documents":[...]}.
API_RERANK_URL = os.getenv(
    "ARIADNA_API_RERANK_URL",
    "https://api.deepinfra.com/v1/inference/Qwen/Qwen3-Reranker-0.6B",
)
API_TIMEOUT_S = float(os.getenv("ARIADNA_API_TIMEOUT", "30"))

# --- Metering / simulación (estimar coste y latencia de API SIN contratar) ---
# Envuelve el backend (local o api) contando tokens, tiempos y coste estimado.
# Con backend=local + metering=1 + sim_latency simulas la API antes de pagar nada.
METERING_ENABLED = os.getenv("ARIADNA_METERING", "0") == "1"
SIM_LATENCY_MS = float(os.getenv("ARIADNA_SIM_LATENCY_MS", "0"))  # latencia de red fake
# Precios orientativos USD por 1M tokens (DeepInfra ~2026; ajusta a tu proveedor).
PRICE_EMBED_PER_MTOK = float(os.getenv("ARIADNA_PRICE_EMBED_PER_MTOK", "0.010"))
PRICE_RERANK_PER_MTOK = float(os.getenv("ARIADNA_PRICE_RERANK_PER_MTOK", "0.030"))

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
