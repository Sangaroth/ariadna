"""Helper de texto para rerank, sin dependencias pesadas (torch-free).

Separado de ariadna/reranker.py (que importa sentence-transformers -> torch) para
que metering.py, backends/api.py y otros puedan reusarlo sin arrastrar torch. Así
un despliegue ONNX/API no necesita torch instalado.
"""

from __future__ import annotations

from typing import Any


def default_text_for_chunk(c: dict[str, Any]) -> str:
    """theme + content del chunk -- mismo formato que recibe el LLM downstream."""
    return f"{c.get('theme', '')}\n{c.get('content', '')}"
