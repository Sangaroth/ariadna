"""Exporta BGE-M3 a ONNX + cuantización dinámica int8 (CPU).

ONNX no es otro modelo: es el mismo BGE-M3 (misma dim 1024, misma calidad de
base) corriendo en ONNX Runtime. int8 reduce los pesos fp32->int8 (~4x menos
tamaño, más rápido en CPU). Preset 'avx2' = portable a cualquier x86 (Hetzner
CX23 incluido); si tu CPU tiene AVX-512 VNNI puedes re-exportar con 'avx512_vnni'
para algo más de velocidad.

Salida en data/models/bge-m3-onnx/onnx/:
  - model.onnx               (fp32, referencia)
  - model_qint8_avx2.onnx    (int8, el que desplegarás)
"""

from __future__ import annotations

import os
from pathlib import Path

OUT_DIR = Path("data/models/bge-m3-onnx")
PRESET = os.getenv("ARIADNA_ONNX_PRESET", "avx2")  # arm64 | avx2 | avx512 | avx512_vnni


def main() -> int:
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")  # export en CPU
    from sentence_transformers import SentenceTransformer
    from sentence_transformers.backend import export_dynamic_quantized_onnx_model

    print(f"Cargando BAAI/bge-m3 con backend ONNX (exporta fp32 onnx la 1a vez)...")
    model = SentenceTransformer("BAAI/bge-m3", backend="onnx")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Guardando modelo + onnx fp32 en {OUT_DIR}/ ...")
    model.save_pretrained(str(OUT_DIR))

    # Recargar desde la copia local (archivos reales). El onnx de bge-m3 usa
    # external data >2GB; en la caché HF son symlinks que el quantizer rechaza.
    print("Recargando desde copia local para cuantizar...")
    model_local = SentenceTransformer(str(OUT_DIR), backend="onnx")

    print(f"Cuantizando a int8 (preset={PRESET})...")
    export_dynamic_quantized_onnx_model(model_local, PRESET, str(OUT_DIR))

    print("\nArchivos ONNX generados:")
    onnx_dir = OUT_DIR / "onnx"
    for f in sorted(onnx_dir.glob("*.onnx")):
        print(f"  {f}   {f.stat().st_size / 1e6:8.1f} MB")
    print("\nListo. Úsalo con ARIADNA_EMBED_BACKEND=onnx (ver ariadna/backends).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
