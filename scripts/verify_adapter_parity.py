#!/usr/bin/env python3
"""Verifica que YoutubeAdapter NO regresa el parsing legacy (parsers.parse_summary_file).

Hito de la Fase 4: el adaptador envuelve parsers.py verbatim, así que el diff
chunk-a-chunk sobre TODO el corpus debe ser vacío. Comprueba dos cosas:

  1. **Paridad de chunks**: para cada vídeo, YoutubeAdapter.parse_summary_to_chunks
     produce un GenericChunk por cada Chunk de parse_summary_file, con identidad
     (source_id/position) y contenido (theme/content/full_text) equivalentes, y
     los campos legacy preservados en `extra`.
  2. **Round-trip de citas**: citation_link_re()/parse_citation_match() re-extrae
     una cita YouTube renderizada reconstruyendo el source_id/position/url EXACTOS
     que dejó la migración (sin 'www', sin '?t=' cuando ts==0).

Uso:
    python scripts/verify_adapter_parity.py
    python scripts/verify_adapter_parity.py --json
    python scripts/verify_adapter_parity.py --limit 20   # primeros N vídeos

Exit 0 si diff vacío, 1 si hay cualquier discrepancia.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ariadna.config import DEFAULT_CORPUS_PATH  # noqa: E402
from ariadna.parsers import iter_corpus, parse_summary_file  # noqa: E402
from ariadna.sources.youtube import YoutubeAdapter  # noqa: E402


def _chunk_parity_errors(adapter: YoutubeAdapter, summary: Path, meta: Path, playlist: str) -> list[str]:
    legacy = parse_summary_file(summary, meta, playlist)
    universal = adapter.parse_summary_to_chunks(summary, meta, playlist)
    errs: list[str] = []
    if len(legacy) != len(universal):
        errs.append(f"{summary.parent.name}: n_chunks legacy={len(legacy)} universal={len(universal)}")
        return errs
    for i, (c, g) in enumerate(zip(legacy, universal)):
        loc = f"{c.video_id}#{c.timestamp_seconds}"
        if g.source_id != f"youtube:{c.video_id}":
            errs.append(f"{loc}: source_id={g.source_id!r}")
        if g.position.key != str(c.timestamp_seconds):
            errs.append(f"{loc}: position_key={g.position.key!r} != {c.timestamp_seconds}")
        if g.position.data.get("timestamp_seconds") != c.timestamp_seconds:
            errs.append(f"{loc}: position.timestamp_seconds mismatch")
        if g.chunk_id != f"youtube:{c.video_id}#{c.timestamp_seconds}":
            errs.append(f"{loc}: chunk_id={g.chunk_id!r}")
        if g.theme != c.theme:
            errs.append(f"{loc}: theme mismatch")
        if g.content != c.content:
            errs.append(f"{loc}: content mismatch")
        if g.full_text != c.full_text:
            errs.append(f"{loc}: full_text mismatch")
        if g.position_url != c.youtube_url:
            errs.append(f"{loc}: position_url={g.position_url!r} != {c.youtube_url!r}")
        if g.title != c.video_title:
            errs.append(f"{loc}: title mismatch")
        # extra legacy preservado al 100%
        for k, want in {
            "video_id": c.video_id, "video_title": c.video_title,
            "timestamp": c.timestamp, "timestamp_seconds": c.timestamp_seconds,
            "category": c.category, "playlist": c.playlist, "channel": c.channel,
            "upload_date": c.upload_date, "duration": c.duration,
            "youtube_url": c.youtube_url,
        }.items():
            if g.extra.get(k) != want:
                errs.append(f"{loc}: extra[{k}]={g.extra.get(k)!r} != {want!r}")
    return errs


def _citation_roundtrip_errors(adapter: YoutubeAdapter) -> list[str]:
    """Cita renderizada → CitationRef con identidad reconstruida igual que la migración."""
    cases = [
        # (body_link, expected_source_id, expected_position_key, expected_url, expected_cite_md)
        ("[32:25](https://youtu.be/ECN5C9rsaZg?t=1945)", "youtube:ECN5C9rsaZg", "1945",
         "https://youtu.be/ECN5C9rsaZg?t=1945", "[32:25](https://youtu.be/ECN5C9rsaZg?t=1945)"),
        ("[Intro](https://www.youtu.be/ABCDEFGHIJK)", "youtube:ABCDEFGHIJK", "0",
         "https://youtu.be/ABCDEFGHIJK", "[Intro](https://youtu.be/ABCDEFGHIJK)"),
    ]
    rx = adapter.citation_link_re()
    errs: list[str] = []
    for body, sid, pkey, url, cite in cases:
        m = rx.search(body)
        if not m:
            errs.append(f"citation_link_re no matchea: {body!r}")
            continue
        ref = adapter.parse_citation_match(m)
        if ref.source_id != sid:
            errs.append(f"{body!r}: source_id={ref.source_id!r} != {sid!r}")
        if ref.position.key != pkey:
            errs.append(f"{body!r}: position_key={ref.position.key!r} != {pkey!r}")
        if ref.position_url != url:
            errs.append(f"{body!r}: position_url={ref.position_url!r} != {url!r}")
        if ref.cite_markdown != cite:
            errs.append(f"{body!r}: cite_markdown={ref.cite_markdown!r} != {cite!r}")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    ap.add_argument("--limit", type=int, default=0, help="solo primeros N vídeos (0 = todos)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    adapter = YoutubeAdapter()
    all_errs: list[str] = []
    n_videos = n_chunks = 0
    for summary, meta, playlist in iter_corpus(args.corpus):
        if args.limit and n_videos >= args.limit:
            break
        n_videos += 1
        n_chunks += len(parse_summary_file(summary, meta, playlist))
        all_errs.extend(_chunk_parity_errors(adapter, summary, meta, playlist))

    cite_errs = _citation_roundtrip_errors(adapter)
    all_errs.extend(cite_errs)

    ok = not all_errs
    if args.json:
        print(json.dumps({
            "videos": n_videos, "chunks": n_chunks,
            "ok": ok, "errors": all_errs[:50], "n_errors": len(all_errs),
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Paridad YoutubeAdapter ↔ parsers: {n_videos} vídeos, {n_chunks} chunks")
        print(f"Round-trip de citas: {'OK' if not cite_errs else 'FAIL'}")
        if all_errs:
            print(f"\n✗ {len(all_errs)} discrepancias (primeras 50):")
            for e in all_errs[:50]:
                print(f"  · {e}")
        else:
            print("\n✓ diff vacío — el adaptador no regresa el parsing legacy")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
