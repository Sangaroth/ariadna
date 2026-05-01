#!/usr/bin/env python3
"""Rank wiki candidates for next batch compilation.

Deterministic scoring based on:
  recurrence (0.5)        — chunks in corpus mentioning the candidate
  connectivity (0.3)      — pages already referencing the candidate (broken wikilinks)
  domain_diversity (0.2)  — bonus if the dominant chunk category isn't yet covered

Outputs to wiki/_meta/next_batch_ranking.json. Tie-break alphabetic by page_id.

Requires the MCP server alive on http://127.0.0.1:8765/mcp (uses search_corpus
to count chunks per candidate). Reads wiki/ directly to enumerate existing
pages and broken wikilinks; never imports ariadna.* (no Qdrant lock conflict
with the running server).
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
WIKI = REPO / "wiki"
META = WIKI / "_meta"
MCP_URL = "http://127.0.0.1:8765/mcp"

WIKILINK_RE = re.compile(r"\[\[([a-z0-9][a-z0-9_-]*)(?:\|[^\]]+)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
DOMAIN_BLOCK_RE = re.compile(
    r"^domain:\s*\n((?:\s*-\s*[^\n]+\n)+)", re.MULTILINE
)
DOMAIN_PRIMARY_RE = re.compile(r"^domain_primary:\s*(\S+)", re.MULTILINE)
PAGE_ID_RE = re.compile(r"^page_id:\s*(\S+)", re.MULTILINE)

W_RECURRENCE = 0.5
W_CONNECTIVITY = 0.3
W_DOMAIN_DIVERSITY = 0.2

MIN_CHUNKS = 10
MIN_AVG_SCORE = 0.55
MCP_TOP_K = 30
MCP_TIMEOUT_S = 15
RECURRENCE_SCORE_THRESHOLD = 0.45


def parse_wiki_pages() -> dict[str, dict]:
    pages: dict[str, dict] = {}
    for md in sorted(WIKI.rglob("*.md")):
        if md.name == "README.md":
            continue
        text = md.read_text(encoding="utf-8")
        fm = FRONTMATTER_RE.match(text)
        if not fm:
            continue
        fm_text = fm.group(1)
        page_id_m = PAGE_ID_RE.search(fm_text)
        if not page_id_m:
            continue
        page_id = page_id_m.group(1).strip()

        domains: list[str] = []
        block = DOMAIN_BLOCK_RE.search(fm_text)
        if block:
            for line in block.group(1).splitlines():
                d = line.strip().lstrip("-").strip().strip('"').strip("'")
                if d:
                    domains.append(d)
        primary_m = DOMAIN_PRIMARY_RE.search(fm_text)
        domain_primary = primary_m.group(1).strip() if primary_m else None

        # Wikilinks count from frontmatter (related_*) AND body — both declare graph edges.
        wikilinks_out = list(dict.fromkeys(m.group(1) for m in WIKILINK_RE.finditer(text)))

        pages[page_id] = {
            "file_path": str(md.relative_to(REPO)),
            "domain_primary": domain_primary,
            "domains": domains,
            "wikilinks_out": wikilinks_out,
        }
    return pages


def mcp_search(query: str, top_k: int = MCP_TOP_K) -> list[dict]:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search_corpus",
                "arguments": {"query": query, "top_k": top_k},
            },
        }
    ).encode("utf-8")
    req = Request(
        MCP_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        raw = urlopen(req, timeout=MCP_TIMEOUT_S).read().decode("utf-8")
    except URLError as e:
        raise RuntimeError(f"MCP server unreachable at {MCP_URL}: {e}") from e
    for line in raw.splitlines():
        if line.startswith("data: "):
            obj = json.loads(line[len("data: "):])
            structured = obj.get("result", {}).get("structuredContent", {})
            # Contrato 2026-04-29+: dict {wiki_pages, raw_chunks, retrieval_metadata}.
            # El ranking solo mide recurrencia en el corpus → raw_chunks.
            if isinstance(structured, dict) and "raw_chunks" in structured:
                return structured.get("raw_chunks", [])
            return structured.get("result", []) if isinstance(structured, dict) else []
    return []


_WORK_SUFFIX_RE = re.compile(r"-(\d{4})(?:-(film|book|game|series|album|tv))?$")


def candidate_query_terms(page_id: str) -> list[str]:
    """Generate up-to-3 search query variants from a page_id.

    Heuristics:
      - For `entity_work`-style ids ending in `-YYYY[-suffix]`, prefer the
        bare title (without year/suffix) as the primary query, since corpus
        chunks rarely contain "1999 film" verbatim.
      - For `author`-style ids `lastname-firstname`, also try the reversed
        form, since the corpus may use either order.
      - Fallback: the full page_id with hyphens turned into spaces.
    """
    full = page_id.replace("-", " ").replace("_", " ").strip()
    variants: list[str] = []

    work_match = _WORK_SUFFIX_RE.search(page_id)
    if work_match:
        bare = page_id[: work_match.start()].replace("-", " ").strip()
        if bare:
            variants.append(bare)
        variants.append(full)
    else:
        variants.append(full)
        parts = page_id.split("-")
        if len(parts) == 2:
            variants.append(f"{parts[1]} {parts[0]}")

    out: list[str] = []
    for v in variants:
        if v and v not in out:
            out.append(v)
    return out[:3]


def measure_recurrence(page_id: str) -> tuple[int, float, Counter]:
    """Return (n_chunks_above_threshold, avg_score_top10, category_counter)."""
    seen: dict[str, tuple[float, str]] = {}
    for q in candidate_query_terms(page_id):
        for r in mcp_search(q):
            url = r.get("youtube_url", "")
            ts = str(r.get("timestamp", ""))
            key = f"{url}#{ts}"
            score = float(r.get("score", 0.0))
            cat = str(r.get("category", "")).strip()
            if key not in seen or seen[key][0] < score:
                seen[key] = (score, cat)
    scores = sorted((s for s, _ in seen.values()), reverse=True)
    n_above = sum(1 for s in scores if s >= RECURRENCE_SCORE_THRESHOLD)
    avg_top10 = sum(scores[:10]) / max(1, min(10, len(scores)))
    cats = Counter(c for _, c in seen.values() if c)
    return n_above, avg_top10, cats


def main() -> None:
    pages = parse_wiki_pages()
    existing_ids = set(pages.keys())
    print(f"Existing wiki pages: {len(existing_ids)}", file=sys.stderr)

    incoming: Counter[str] = Counter()
    referencing: defaultdict[str, set[str]] = defaultdict(set)
    for src_id, info in pages.items():
        for tgt in info["wikilinks_out"]:
            if tgt not in existing_ids:
                incoming[tgt] += 1
                referencing[tgt].add(src_id)

    candidates = sorted(incoming.keys())
    print(f"Broken-wikilink candidates: {len(candidates)}", file=sys.stderr)

    covered_domains = sorted({p["domain_primary"] for p in pages.values() if p["domain_primary"]})
    covered_domain_groups = {d.split(".")[0] for d in covered_domains}

    rec_data: dict[str, dict] = {}
    for c in candidates:
        try:
            n, avg, cats = measure_recurrence(c)
        except RuntimeError as e:
            print(f"  ! recurrence query failed for {c}: {e}", file=sys.stderr)
            n, avg, cats = 0, 0.0, Counter()
        dominant_cat = cats.most_common(1)[0][0] if cats else None
        rec_data[c] = {
            "n_chunks": n,
            "avg_score_top10": avg,
            "dominant_category": dominant_cat,
            "category_distribution": dict(cats.most_common()),
        }
        print(
            f"  {c:35s} rec={n:3d}  avg10={avg:.3f}  conn={incoming[c]}  cat={dominant_cat or '-'}",
            file=sys.stderr,
        )

    max_rec = max((d["n_chunks"] for d in rec_data.values()), default=0) or 1
    max_conn = max(incoming.values(), default=0) or 1

    ranked: list[dict] = []
    for c in candidates:
        rec = rec_data[c]
        viable = (
            rec["n_chunks"] >= MIN_CHUNKS
            and rec["avg_score_top10"] >= MIN_AVG_SCORE
        )

        if rec["dominant_category"]:
            cat_group = rec["dominant_category"].split(".")[0] if "." in rec["dominant_category"] else rec["dominant_category"]
            domain_bonus = 1.0 if cat_group not in covered_domain_groups else 0.0
        else:
            domain_bonus = 0.0

        score = (
            W_RECURRENCE * (rec["n_chunks"] / max_rec)
            + W_CONNECTIVITY * (incoming[c] / max_conn)
            + W_DOMAIN_DIVERSITY * domain_bonus
        )
        if rec["n_chunks"] < MIN_CHUNKS:
            viability_reason = f"n_chunks={rec['n_chunks']} < {MIN_CHUNKS}"
        elif rec["avg_score_top10"] < MIN_AVG_SCORE:
            viability_reason = f"avg_score={rec['avg_score_top10']:.3f} < {MIN_AVG_SCORE}"
        else:
            viability_reason = None

        ranked.append(
            {
                "page_id": c,
                "score": round(score, 4),
                "recurrence_n_chunks": rec["n_chunks"],
                "recurrence_avg_top10": round(rec["avg_score_top10"], 4),
                "connectivity_in_count": incoming[c],
                "referencing_pages": sorted(referencing[c]),
                "dominant_category_in_corpus": rec["dominant_category"],
                "domain_diversity_bonus": domain_bonus,
                "viable": viable,
                "viability_reason": viability_reason,
            }
        )

    ranked.sort(key=lambda r: (-r["score"], r["page_id"]))

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "weights": {
            "recurrence": W_RECURRENCE,
            "connectivity": W_CONNECTIVITY,
            "domain_diversity": W_DOMAIN_DIVERSITY,
        },
        "viability_filter": {
            "min_chunks": MIN_CHUNKS,
            "min_avg_score_top10": MIN_AVG_SCORE,
            "recurrence_score_threshold": RECURRENCE_SCORE_THRESHOLD,
        },
        "tie_break": "alphabetic by page_id",
        "existing_pages_count": len(existing_ids),
        "covered_domains": covered_domains,
        "candidates_count": len(candidates),
        "ranking": ranked,
    }
    META.mkdir(parents=True, exist_ok=True)
    out_path = META / "next_batch_ranking.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\nWrote {out_path.relative_to(REPO)}", file=sys.stderr)
    viable_ranked = [r for r in ranked if r["viable"]]
    print(f"Top viable candidates ({len(viable_ranked)} of {len(ranked)}):", file=sys.stderr)
    for r in viable_ranked[:12]:
        print(
            f"  {r['score']:.3f}  {r['page_id']:35s}  rec={r['recurrence_n_chunks']:3d}  "
            f"conn={r['connectivity_in_count']:2d}  bonus={r['domain_diversity_bonus']}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
