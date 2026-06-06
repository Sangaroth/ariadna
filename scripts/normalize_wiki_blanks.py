#!/usr/bin/env python3
"""normalize_wiki_blanks.py — colapsa rachas de líneas en blanco en las wikis.

Limpieza one-shot del cruft histórico: el writer de citas
(`_upsert_video_citation_block`) acumulaba una línea en blanco por run bajo
`## Citations` (hasta 89 en algunas páginas). Este script normaliza CUALQUIER
racha de ≥2 líneas en blanco a UNA sola, en todo el cuerpo, respetando los
bloques de código fenced (``` … ```), y elimina blancos sobrantes al final.

No toca el contenido real (prosa, citas, frontmatter) — solo el espaciado.

Uso:
    python scripts/normalize_wiki_blanks.py --project proxy --dry-run
    python scripts/normalize_wiki_blanks.py --project proxy
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def normalize(text: str) -> str:
    """Colapsa ≥2 blancos consecutivos a 1, fuera de fences ```; recorta EOF."""
    lines = text.split("\n")
    out: list[str] = []
    in_fence = False
    prev_blank = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(line)
            prev_blank = False
            continue
        if in_fence:
            out.append(line)
            continue
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue  # descarta blanco extra consecutivo
        out.append(line)
        prev_blank = is_blank
    # recorta blancos finales, deja un único salto de línea al final
    while out and out[-1].strip() == "":
        out.pop()
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default="proxy")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    wiki = REPO / "projects" / args.project / "wiki"
    if not wiki.exists():
        print(f"ERROR: no existe {wiki}", file=sys.stderr)
        return 1

    changed = 0
    total_removed = 0
    for md in sorted(wiki.rglob("*.md")):
        if "_meta" in md.parts:
            continue
        orig = md.read_text(encoding="utf-8")
        new = normalize(orig)
        if new != orig:
            removed = orig.count("\n") - new.count("\n")
            total_removed += removed
            changed += 1
            print(f"  {'(dry) ' if args.dry_run else ''}{md.relative_to(wiki)}  −{removed} líneas")
            if not args.dry_run:
                md.write_text(new, encoding="utf-8")

    print(f"\n{'[dry-run] ' if args.dry_run else ''}páginas afectadas: {changed} | líneas en blanco eliminadas: {total_removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
