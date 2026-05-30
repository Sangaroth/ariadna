"""Smoke test: capture_baseline produce un JSON con el shape esperado.

Requiere el MCP server vivo (por defecto :8080), igual que test_hybrid.py —
capture_baseline mide a través de la tool MCP, no contra Qdrant embedded.
"""
import json
import subprocess
from pathlib import Path


def test_capture_baseline_runs_and_produces_json(tmp_path):
    """Ejecuta el script contra el server vivo y verifica la estructura del JSON."""
    out_file = tmp_path / "baseline.json"
    result = subprocess.run(
        [".venv/bin/python", "scripts/capture_baseline.py", "--out", str(out_file)],
        capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, f"script failed: {result.stderr}"
    assert out_file.exists()

    data = json.loads(out_file.read_text())
    assert "queries" in data
    assert "captured_at" in data
    assert "total_chunks_qdrant" in data       # presente (null intencional vía HTTP)
    assert "total_wiki_pages_qdrant" in data
    assert len(data["queries"]) == 10          # 10 queries canónicas
    for q in data["queries"]:
        assert "query" in q
        assert "raw_chunk_ids" in q            # lista de youtube_url estables
        assert "wiki_page_ids" in q
        assert "raw_top_score" in q
        assert "wiki_top_score" in q
        assert "mode_recommended" in q

    # Al menos una query canónica debe recuperar algo (sanity: el server tiene corpus).
    assert any(q["raw_chunk_ids"] or q["wiki_page_ids"] for q in data["queries"])
