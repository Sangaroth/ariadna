"""Embedder BGE-M3 vía ONNX Runtime (CPU), sin torch.

NO es otro modelo: es el mismo BGE-M3 (misma dim 1024, mismo pooling CLS +
normalize), exportado a ONNX y cuantizado a int8. ~4x menos peso (~570MB vs
~2.3GB) y más rápido en CPU. El índice de producción (embebido con fp32 torch)
sigue valiendo: solo se acelera el embed de la query.

Usa onnxruntime directamente (no el wrapper de sentence-transformers, que en
5.5.0 espera 'last_hidden_state' y el grafo exporta 'sentence_embedding'). Como
no importa torch, este backend habilita además el despliegue "sin torch".
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ariadna import config
from ariadna.config import EMBED_BATCH_SIZE, EMBED_DIM

log = logging.getLogger(__name__)


class OnnxEmbedder:
    """BGE-M3 (ONNX int8) con la misma interfaz que DenseEmbedder."""

    def __init__(self, model_path: str | None = None, file_name: str | None = None) -> None:
        import onnxruntime as ort
        from transformers import AutoTokenizer

        model_path = model_path or config.ONNX_MODEL_PATH
        file_name = file_name or config.ONNX_FILE_NAME
        onnx_file = str(Path(model_path) / file_name)
        log.info("Cargando embedder ONNX %s...", onnx_file)
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.session = ort.InferenceSession(onnx_file, providers=["CPUExecutionProvider"])
        self._input_names = {i.name for i in self.session.get_inputs()}
        self.dim = EMBED_DIM
        log.info("Embedder ONNX listo. Dimension: %d", self.dim)

    def embed(
        self,
        texts: list[str],
        batch_size: int = EMBED_BATCH_SIZE,
        show_progress: bool = False,
    ) -> np.ndarray:
        if not isinstance(texts, list):
            texts = list(texts)
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)

        chunks: list[np.ndarray] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            enc = self.tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="np",
            )
            inputs = {
                "input_ids": enc["input_ids"].astype(np.int64),
                "attention_mask": enc["attention_mask"].astype(np.int64),
            }
            inputs = {k: v for k, v in inputs.items() if k in self._input_names}
            emb = self.session.run(["sentence_embedding"], inputs)[0]
            chunks.append(emb.astype(np.float32))

        out = np.concatenate(chunks, axis=0)
        # Normaliza a norma 1 (coseno) — idempotente si el grafo ya normaliza.
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (out / norms).astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed([query], batch_size=1)[0]
