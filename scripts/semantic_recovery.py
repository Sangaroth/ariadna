#!/usr/bin/env python3
"""CLI thin wrapper para semantic_recovery.

Uso:
    # Dry-run (solo reporta, cache se actualiza pero no toca wiki)
    python scripts/semantic_recovery.py

    # Aplicar matches high-confidence: citations + aliases
    python scripts/semantic_recovery.py --apply

    # Subir threshold de cosine para reducir LLM calls
    python scripts/semantic_recovery.py --min-cosine 0.60

Ver ariadna/semantic_recovery.py para arquitectura completa.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ariadna.semantic_recovery import run_semantic_recovery


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true", help="Materializa citations + aliases para matches high (default: dry-run)")
    p.add_argument("--top-k", type=int, default=5, help="Candidatos por discarded (default: 5)")
    p.add_argument("--min-cosine", type=float, default=0.50, help="Skip LLM judge si top cosine < threshold (default: 0.50)")
    p.add_argument(
        "--corpus",
        type=Path,
        default=Path("/home/dae/PycharmProjects/ProxySummaries/data/playlists"),
        help="Corpus path para resolver video metadata",
    )
    args = p.parse_args()

    if not args.corpus.exists():
        print(f"ERROR: corpus path not found: {args.corpus}", file=sys.stderr)
        return 1

    stats = run_semantic_recovery(
        corpus_root=args.corpus,
        apply=args.apply,
        top_k=args.top_k,
        min_cosine=args.min_cosine,
    )

    import json
    print("\n=== STATS ===", file=sys.stderr)
    print(json.dumps(stats, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
