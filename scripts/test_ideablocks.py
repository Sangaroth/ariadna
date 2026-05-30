#!/usr/bin/env python3
"""Test de IdeaBlocks (DETERMINISTA, sin red/LLM/Qdrant real):
persistencia (write/read/sanitize round-trip) + indexación Layer 0 con store/embedder
mock (parse_summary_to_chunks → payload universal con embedding_role=chunk + idempotencia).

    python scripts/test_ideablocks.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ariadna import ideablocks as IB  # noqa: E402

PAPER_SUMMARY = (
    "- p.1 🧠 Metacognición\n\n  - se mide con meta-d prime,\n  - índice de conciencia,\n\n"
    "- p.2 🔬 SDT tipo-2\n\n  - AUROC2 y Brier,\n  - sensibilidad vs sesgo,\n\n"
    # Segundo IdeaBlock en LA MISMA página 2: chunk_id colisiona (mismo position_key 'p2').
    "- p.2 ⚠️ Sesgo metacognitivo\n\n  - over/underconfidence,\n  - phi y gamma contaminadas,\n"
)


def test_sanitize_and_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as td:
        # Redirige PROJECTS_DIR vía monkeypatch del ProjectConfig.root.
        slug = "ibtest-rt"
        proj_root = Path(td) / "projects" / slug
        import ariadna.project_config as PC
        orig = PC.PROJECTS_DIR
        PC.PROJECTS_DIR = Path(td) / "projects"
        try:
            sid = "doi:10.3389/fpsyg.2014.01"
            assert IB.sanitize(sid) == "doi_10.3389_fpsyg.2014.01"
            p = IB.write_summary(slug, sid, PAPER_SUMMARY, source_type="paper",
                                 title="How to measure metacognition")
            assert p.exists() and p.parent == proj_root / "summaries"
            got = IB.read_summary(slug, sid)
            assert got is not None
            assert got["source_id"] == sid and got["source_type"] == "paper"
            assert got["title"] == "How to measure metacognition"
            assert got["generated_at"]  # se estampó
            assert got["body"].strip() == PAPER_SUMMARY.strip()
            # missing → None
            assert IB.read_summary(slug, "doi:nope") is None
            # iter_summaries
            assert len(IB.iter_summaries(slug)) == 1
        finally:
            PC.PROJECTS_DIR = orig


class _FakeEmbedder:
    def embed(self, texts, batch_size=16):
        return np.ones((len(texts), 4), dtype=np.float32)


class _FakeStore:
    def __init__(self):
        self.deleted = []
        self.upserted_ids = []
        self.upserted_payloads = []

    def ensure_collection(self, recreate=False):
        pass

    def delete_by_filter(self, filters):
        self.deleted.append(filters)
        return 0

    def upsert_batch(self, ids, vectors, payloads):
        self.upserted_ids = ids
        self.upserted_payloads = payloads


def test_index_project_chunks_payload() -> None:
    with tempfile.TemporaryDirectory() as td:
        slug = "ibtest-idx"
        import ariadna.project_config as PC
        orig = PC.PROJECTS_DIR
        PC.PROJECTS_DIR = Path(td) / "projects"
        try:
            sid = "doi:10.3389/fpsyg.2014.01"
            IB.write_summary(slug, sid, PAPER_SUMMARY, source_type="paper", title="Meta paper")
            store = _FakeStore()
            n = IB.index_project_chunks(slug, embedder=_FakeEmbedder(), store=store)
            assert n == 3, n  # 3 IdeaBlocks (p.1, p.2 ×2)
            # idempotencia: borra los chunks de ESTE proyecto antes de upsert
            assert store.deleted == [{"project_id": slug, "embedding_role": "chunk"}]
            assert len(store.upserted_ids) == 3
            ids = store.upserted_ids
            # Sin colisión pese a que dos IdeaBlocks comparten page/position_key 'p2'.
            assert len(set(ids)) == 3 and all(isinstance(i, int) for i in ids)
            # Los dos bloques de p.2 comparten chunk_id pero difieren en block_index.
            p2 = [p for p in store.upserted_payloads if p["position"] == {"page": 2}]
            assert len(p2) == 2 and {p["block_index"] for p in p2} == {0, 1}
            assert all(p["chunk_id"] == f"{sid}#p2" for p in p2)
            pl = store.upserted_payloads[0]
            assert pl["project_id"] == slug
            assert pl["source_id"] == sid
            assert pl["source_type"] == "paper"
            assert pl["embedding_role"] == "chunk"
            assert pl["position"] == {"page": 1}
            assert pl["chunk_id"] == f"{sid}#p1"
            assert "doi.org/10.3389/fpsyg.2014.01#page=1" in pl["cite_markdown"]
            assert "meta-d prime" in pl["content"]
            # empty project → 0, sin tocar el store
            assert IB.index_project_chunks("ibtest-empty", embedder=_FakeEmbedder(),
                                           store=_FakeStore()) == 0
        finally:
            PC.PROJECTS_DIR = orig


TESTS = [test_sanitize_and_roundtrip, test_index_project_chunks_payload]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
