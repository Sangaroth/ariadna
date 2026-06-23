"""Genera un eval nuevo (v3) de queries REALISTAS contra el índice vivo.

El eval viejo (v1/v2) quedó obsoleto: sus gold chunks ya no están en data/qdrant.
Este muestrea chunks de vídeo Proxy reales del índice y, con `claude -p`, genera
una pregunta natural (estilo usuario de Mattermost tras la reformulación del
plugin) cuyo gold es ESE chunk. El gold se identifica por (video_id,
timestamp_seconds), que sí viaja en el payload devuelto por store.search.

Salida: data/eval/queries_eval_v3.jsonl
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict

from ariadna.config import PROJECT_ROOT
from ariadna.storage import CorpusStore

OUT = PROJECT_ROOT / "data" / "eval" / "queries_eval_v3.jsonl"
N_QUERIES = 50
BATCH = 10
MIN_CONTENT = 200

PROMPT_HEAD = (
    "Eres un usuario de un chat de equipo (Mattermost) que consulta una base de "
    "conocimiento sobre análisis de obras, cine, cultura, psicología y temas afines.\n\n"
    "Para cada FRAGMENTO numerado, escribe UNA pregunta realista y natural en español, "
    "como la que un usuario escribiría en el chat buscando justo esa información, y que "
    "ese fragmento responde. Reglas:\n"
    "- Natural y concreta; ni genérica de más ni copiando el texto literal.\n"
    "- Sin meta-referencias ('según el fragmento', 'en este texto').\n"
    "- Puede nombrar la obra/tema si resulta natural.\n"
    "- Una sola frase.\n\n"
    "Devuelve SOLO un JSON array, sin markdown ni texto extra: "
    '[{"i": <n>, "query": "<pregunta>"}]\n\nFRAGMENTOS:\n'
)


def load_candidates(store: CorpusStore) -> list[dict]:
    """Chunks de vídeo Proxy (project=None, con content y video_id) del índice."""
    c = store.client
    cands: list[dict] = []
    off = None
    while True:
        pts, off = c.scroll(store.collection_name, limit=1000, offset=off, with_payload=True)
        for p in pts:
            pl = p.payload or {}
            content = pl.get("content") or ""
            if (
                pl.get("project_id") is None
                and pl.get("video_id")
                and pl.get("timestamp_seconds") is not None
                and len(content) >= MIN_CONTENT
            ):
                cands.append({"point_id": p.id, **pl})
        if off is None:
            break
    return cands


def diverse_sample(cands: list[dict], n: int) -> list[dict]:
    """Round-robin por categoría sobre candidatos ordenados por id (determinista)."""
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for c in sorted(cands, key=lambda x: x["point_id"]):
        by_cat[c.get("category") or "?"].append(c)
    cats = sorted(by_cat)
    picked: list[dict] = []
    idx = 0
    while len(picked) < n and any(by_cat.values()):
        cat = cats[idx % len(cats)]
        if by_cat[cat]:
            picked.append(by_cat[cat].pop(0))
        idx += 1
        if idx > len(cats) * len(cands):
            break
    return picked[:n]


def gen_batch(batch: list[dict]) -> dict[int, str]:
    """Llama a claude -p con un lote y devuelve {i: query}."""
    lines = []
    for i, c in enumerate(batch):
        snippet = (c.get("content") or "").strip().replace("\n", " ")[:600]
        lines.append(
            f"[{i}] Obra: {c.get('video_title', '?')} | Cat: {c.get('category', '?')} | "
            f"Tema: {c.get('theme', '')} | Contenido: {snippet}"
        )
    prompt = PROMPT_HEAD + "\n".join(lines)
    res = subprocess.run(
        ["claude", "-p", prompt], capture_output=True, text=True, timeout=180
    )
    out = res.stdout.strip()
    a, b = out.find("["), out.rfind("]")
    if a == -1 or b == -1:
        raise RuntimeError(f"Sin JSON en salida: {out[:200]}")
    arr = json.loads(out[a : b + 1])
    return {int(d["i"]): d["query"].strip() for d in arr if d.get("query")}


def main() -> int:
    store = CorpusStore()
    cands = load_candidates(store)
    print(f"Candidatos (chunks vídeo proxy con content): {len(cands)}")
    sample = diverse_sample(cands, N_QUERIES)
    print(f"Muestreados: {len(sample)} (categorías: "
          f"{sorted(set(c.get('category') for c in sample))})")

    rows: list[dict] = []
    qid = 0
    for start in range(0, len(sample), BATCH):
        batch = sample[start : start + BATCH]
        print(f"Generando queries {start}-{start + len(batch) - 1} vía claude -p...")
        try:
            qmap = gen_batch(batch)
        except Exception as e:
            print(f"  fallo en lote {start}: {e}")
            continue
        for i, c in enumerate(batch):
            q = qmap.get(i)
            if not q:
                continue
            qid += 1
            rows.append({
                "query_id": f"v3_{qid:03d}",
                "query": q,
                "query_type": "realistic",
                "gold_video_id": c["video_id"],
                "gold_timestamp_seconds": c["timestamp_seconds"],
                "gold_point_id": c["point_id"],
                "gold_theme": c.get("theme", ""),
                "video_title": c.get("video_title", ""),
                "category": c.get("category", ""),
                "playlist": c.get("playlist", ""),
            })

    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"\nEscrito {len(rows)} queries en {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
