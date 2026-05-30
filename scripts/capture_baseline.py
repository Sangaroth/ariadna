#!/usr/bin/env python3
"""Captura el estado funcional pre-migración: ejecuta N queries canónicas
contra el MCP server VIVO y serializa los resultados a un JSON. Permite
comparación determinista post-migración para verificar que el sistema sigue
funcionando idénticamente *desde la perspectiva del agente Mattermost* — que
es el criterio binario de la Fase 1 (spec sección 9).

Por qué contra el server vivo (HTTP) y no contra Qdrant embedded:
  - El Qdrant embedded tiene lock exclusivo: el server lo tiene tomado. Capturar
    embedded obligaría a parar el server (disruptivo para Mattermost).
  - El criterio de éxito es "idéntico desde la perspectiva del agente"; medirlo
    a través de la misma tool MCP que usa Mattermost es la señal más fiel.
  - La migración a modelo universal usa `set_payload` in-place (NO re-embed), así
    que los scores cosine deben quedar idénticos (no solo dentro de ±0.01) y el
    conjunto de chunks recuperados por query debe ser el mismo.

Identificadores estables capturados:
  - raw_chunks → `youtube_url` (youtu.be/ID?t=SECS). Sobrevive la migración como
    `position_url`; identifica unívocamente (video_id + timestamp).
  - wiki_pages → `page_id`.

Uso:
    python scripts/capture_baseline.py --out data/baseline_pre_migration.json
    python scripts/capture_baseline.py --url http://127.0.0.1:8080/mcp --out ...

Requisito: MCP server corriendo (por defecto en :8080, el puerto de config.py).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:8080/mcp"

# 10 queries que cubren los tres lanes (wiki_dominant, balanced, raw_with_warning)
# y los 5 pilares editoriales de Proxy. Si la migración no preserva resultados
# en estas queries, algo se rompió.
CANONICAL_QUERIES: list[str] = [
    "sombra junguiana",
    "mito polar",
    "Tolkien",
    "hieros gamos",
    "anima archetype",
    "consumismo crítica",
    "individuation jung",
    "Pinocho análisis arquetípico",
    "viaje del héroe",
    "psicología cognitiva",
]


def mcp_call(url: str, method: str, params: dict | None = None) -> dict:
    """JSON-RPC sobre el endpoint MCP. El server contesta SSE ('data: {...}')."""
    payload: dict = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    for line in body.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])
    return json.loads(body)


def call_tool(url: str, tool: str, args: dict) -> dict:
    resp = mcp_call(url, "tools/call", {"name": tool, "arguments": args})
    if "error" in resp:
        raise RuntimeError(f"MCP error en {tool}: {resp['error']}")
    sc = resp["result"].get("structuredContent") or {}
    if "result" in sc:
        return sc["result"]
    for c in resp["result"].get("content", []):
        if c.get("type") == "text":
            return json.loads(c["text"])
    raise RuntimeError(f"Respuesta sin structuredContent ni text para {tool}")


def capture(url: str, out_path: Path) -> dict:
    queries_data = []
    for q in CANONICAL_QUERIES:
        res = call_tool(url, "search_corpus", {"query": q, "top_k": 5, "top_k_wiki": 2})
        raw_chunks = res.get("raw_chunks", []) or []
        wiki_pages = res.get("wiki_pages", []) or []
        meta = res.get("retrieval_metadata", {}) or {}

        queries_data.append({
            "query": q,
            # youtube_url = identificador estable del raw chunk (sobrevive como position_url)
            "raw_chunk_ids": [c.get("youtube_url") for c in raw_chunks if c.get("youtube_url")],
            "wiki_page_ids": [w.get("page_id") for w in wiki_pages if w.get("page_id")],
            "raw_top_score": float(meta.get("raw_top_score") or 0.0),
            "wiki_top_score": float(meta.get("wiki_top_score") or 0.0),
            "mode_recommended": meta.get("mode_recommended"),
        })

    baseline = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "captured_via": "mcp_http",
        "source_url": url,
        # Totales Qdrant: no expuestos vía MCP (no hay tool de count). Se verifican
        # directamente contra Qdrant en la fase de migración (server parado). Null aquí
        # de forma intencional; el baseline funcional son las queries.
        "total_chunks_qdrant": None,
        "total_wiki_pages_qdrant": None,
        "queries": queries_data,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2))
    n_raw = sum(len(q["raw_chunk_ids"]) for q in queries_data)
    n_wiki = sum(len(q["wiki_page_ids"]) for q in queries_data)
    print(f"baseline written: {out_path} ({len(queries_data)} queries, "
          f"{n_raw} raw refs, {n_wiki} wiki refs)")
    return baseline


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=DEFAULT_URL, help=f"MCP endpoint (default: {DEFAULT_URL})")
    p.add_argument("--out", type=Path, default=Path("data/baseline_pre_migration.json"))
    args = p.parse_args()
    try:
        capture(args.url, args.out)
    except urllib.error.URLError as e:
        print(f"ERROR: no se pudo contactar el MCP server en {args.url}: {e}\n"
              f"¿Está corriendo? (pgrep -af mcp_server)", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
