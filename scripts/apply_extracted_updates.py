#!/usr/bin/env python3
"""apply_extracted_updates.py — aplicador determinista de updates extraídos.

Consume la salida del extractor (pending_updates.json + promote_queue.json de
un run) y la aplica DIRECTAMENTE a las páginas wiki, usando el contenido final
que el extractor ya produjo (new_content / draft_body) — sin LLM, verbatim.

Robusto a los DOS esquemas que emite el extractor:
  - nuevo: update.target_page_id / operation / new_content / anchor_passage
  - viejo: update.page_id / update_type / content_proposed / section_target

Salvaguardas (evitan el "golem" del postmortem 2026-05-02):
  - anchor EXACTO y ÚNICO: si aparece 0 o >1 veces, NO inserta — lo reporta.
  - idempotente: si el encabezado del new_content ya está en la página, salta.
  - normaliza espaciado (sin rachas de blancos).
  - dry-run con diff por defecto; --apply para escribir; --commit para 1 commit.
  - reversible por git; sin bucle desatendido.

Uso:
    python scripts/apply_extracted_updates.py --from-run <run_id>            # dry-run
    python scripts/apply_extracted_updates.py --from-run <run_id> --apply
    python scripts/apply_extracted_updates.py --from-run <run_id> --apply --commit
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WIKI = REPO / "projects" / "proxy" / "wiki"
RUNS = REPO / "projects" / "proxy" / "_meta" / "extraction_runs"

PAGE_TYPE_DIR = {
    "concept": "concepts", "author": "authors", "work": "works",
    "entity": "works", "entity_work": "works", "synthesis": "synthesis",
}


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def collapse_blanks(text: str) -> str:
    """Colapsa ≥2 líneas en blanco a 1, fuera de fences; recorta EOF."""
    out, in_fence, prev_blank = [], False, False
    for line in text.split("\n"):
        st = line.lstrip()
        if st.startswith("```") or st.startswith("~~~"):
            in_fence = not in_fence
            out.append(line); prev_blank = False; continue
        if in_fence:
            out.append(line); continue
        blank = line.strip() == ""
        if blank and prev_blank:
            continue
        out.append(line); prev_blank = blank
    while out and out[-1].strip() == "":
        out.pop()
    return "\n".join(out) + "\n"


def find_page(page_id: str) -> Path | None:
    hits = list(WIKI.rglob(f"{page_id}.md"))
    return hits[0] if hits else None


# El extractor (LLM) ha emitido múltiples variantes de nombres de clave a lo
# largo del tiempo — a veces dentro del MISMO run. Normalizamos todas.
_OP_KEYS = ("operation", "update_type", "operation_type", "patch_op")
_ANCHOR_KEYS = (
    "anchor_passage", "anchor", "anchor_quote", "anchor_literal",
    "anchor_passage_literal",
)  # NB: *_unique / *_uniqueness_check son flags, NO el texto del anchor
_CONTENT_KEYS = ("new_content", "content_proposed", "content")


def _first(u: dict, keys: tuple) -> str | None:
    for k in keys:
        v = u.get(k)
        if v:
            return v
    return None


def norm_update(u: dict) -> dict:
    """Mapea TODAS las variantes de esquema a claves canónicas."""
    return {
        "page_id": u.get("target_page_id") or u.get("page_id"),
        "operation": _first(u, _OP_KEYS),
        "anchor": _first(u, _ANCHOR_KEYS) or "",
        "content": (_first(u, _CONTENT_KEYS) or "").strip("\n"),
        "section_target": u.get("section_target") or "",
    }


def apply_one(page_text: str, op: str, anchor: str, content: str, section: str) -> tuple[str | None, str]:
    """Devuelve (nuevo_texto | None, motivo). None = no aplicado (motivo explica)."""
    if not content:
        return None, "new_content vacío"

    head = content.splitlines()[0] if content.splitlines() else content[:60]
    # idempotencia: ¿ya está el encabezado del bloque?
    if norm_ws(head) and norm_ws(head) in norm_ws(page_text):
        return None, "ya aplicado (encabezado presente)"

    if op in ("insert_before_passage", "insert_after_passage", "replace_passage"):
        if not anchor:
            return None, "sin anchor"
        n = page_text.count(anchor)
        if n == 0:
            return None, "anchor NO encontrado"
        if n > 1:
            return None, f"anchor ambiguo (x{n})"
        idx = page_text.index(anchor)
        if op == "insert_before_passage":
            new = page_text[:idx] + content + "\n\n" + page_text[idx:]
        elif op == "insert_after_passage":
            end = idx + len(anchor)
            new = page_text[:end] + "\n\n" + content + page_text[end:]
        else:  # replace_passage
            new = page_text[:idx] + content + page_text[idx + len(anchor):]
        return collapse_blanks(new), "ok"

    if op in ("append_to_section", "enrich_section"):
        if not section:
            return None, "sin section_target"
        # localiza el header de la sección (## section)
        m = re.search(rf"(^##\s+{re.escape(section)}\s*$)", page_text, re.MULTILINE)
        if not m:
            return None, f"sección '{section}' no encontrada"
        # fin de la sección = siguiente '## ' o EOF
        nxt = re.search(r"^##\s", page_text[m.end():], re.MULTILINE)
        insert_at = m.end() + (nxt.start() if nxt else len(page_text) - m.end())
        new = page_text[:insert_at].rstrip() + "\n\n" + content + "\n\n" + page_text[insert_at:]
        return collapse_blanks(new), "ok"

    return None, f"operación no soportada: {op}"


def show_diff(name: str, old: str, new: str) -> None:
    import difflib
    diff = difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile=f"{name} (actual)", tofile=f"{name} (propuesto)", lineterm="", n=1,
    )
    shown = [l for l in diff]
    # solo muestra añadidos/cabeceras para no inundar
    added = [l for l in shown if l.startswith("+") and not l.startswith("+++")]
    print(f"    +{len(added)} líneas. Primeras añadidas:")
    for l in added[:6]:
        print(f"      {l[:100]}")


def write_new_page(entity: dict) -> tuple[Path | None, str]:
    pid = entity.get("page_id")
    if not pid:
        return None, "entity sin page_id"
    if find_page(pid):
        return None, "página ya existe (skip)"
    body = entity.get("draft_body") or ""
    if not body.strip():
        return None, "sin draft_body"
    ptype = entity.get("page_type", "concept")
    subdir = PAGE_TYPE_DIR.get(ptype, "concepts")
    target = WIKI / subdir / f"{pid}.md"
    return target, ("ok:" + collapse_blanks(body) if body.startswith("---") else "needs-frontmatter")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-run", required=True)
    ap.add_argument("--apply", action="store_true", help="escribe (default: dry-run)")
    ap.add_argument("--commit", action="store_true", help="crea 1 commit tras aplicar")
    ap.add_argument("--only-compile-skipped", action="store_true",
                    help="solo updates con target_page_id (huérfanos por bug, no decisiones editoriales)")
    args = ap.parse_args()

    run_dir = RUNS / args.from_run
    if not run_dir.is_dir():
        print(f"ERROR: no existe {run_dir}", file=sys.stderr)
        return 1

    print(f"Run: {args.from_run}  |  modo: {'APPLY' if args.apply else 'DRY-RUN'}\n")

    applied, skipped, touched_pages = 0, 0, set()

    # --- pending_updates ---
    pu_path = run_dir / "pending_updates.json"
    if pu_path.exists():
        items = json.loads(pu_path.read_text()).get("items", [])
        print(f"== pending_updates: {len(items)} ==")
        for it in items:
            u_raw = it.get("update") or {}
            # compile-skipped = usó target_page_id sin page_id → compile lo
            # descartó por bug (no decisión editorial). Con --only-compile-skipped
            # solo recuperamos esos, sin tocar los de esquema viejo.
            compile_skipped = ("page_id" not in u_raw) and ("target_page_id" in u_raw)
            if args.only_compile_skipped and not compile_skipped:
                continue
            u = norm_update(u_raw)
            pid = u["page_id"]
            page = find_page(pid) if pid else None
            if not page:
                print(f"  ✗ {pid}: PÁGINA NO EXISTE"); skipped += 1; continue
            old = page.read_text(encoding="utf-8")
            new, why = apply_one(old, u["operation"], u["anchor"], u["content"], u["section_target"])
            if new is None:
                print(f"  ⊘ {pid} [{u['operation']}]: {why}"); skipped += 1; continue
            print(f"  ✓ {pid} [{u['operation']}]: aplicable")
            show_diff(pid, old, new)
            if args.apply:
                page.write_text(new, encoding="utf-8")
            applied += 1; touched_pages.add(str(page))

    # --- promote_queue (páginas nuevas) ---
    pq_path = run_dir / "promote_queue.json"
    if pq_path.exists():
        pitems = json.loads(pq_path.read_text()).get("items", [])
        print(f"\n== promote_queue (páginas nuevas): {len(pitems)} ==")
        for it in pitems:
            ent = it.get("entity") or {}
            target, res = write_new_page(ent)
            if target is None:
                print(f"  ⊘ {ent.get('page_id')}: {res}"); skipped += 1; continue
            if res.startswith("ok:"):
                print(f"  ✓ {ent.get('page_id')}: crear página nueva ({target.parent.name}/)")
                if args.apply:
                    target.write_text(res[3:], encoding="utf-8")
                applied += 1; touched_pages.add(str(target))
            else:
                print(f"  ⊘ {ent.get('page_id')}: {res} (revisar a mano)"); skipped += 1

    print(f"\nResumen: {applied} aplicados, {skipped} saltados, {len(touched_pages)} páginas tocadas")

    if args.apply and args.commit and touched_pages:
        subprocess.run(["git", "add", *touched_pages], cwd=REPO)
        subprocess.run(
            ["git", "commit", "-q", "-m",
             f"feat(wiki): aplicar {applied} updates extraídos del run {args.from_run}\n\n"
             "Aplicación determinista (apply_extracted_updates.py) del contenido\n"
             "final del extractor (new_content/draft_body) — sin LLM, anchors\n"
             "exactos y únicos verificados.\n\n"
             "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"],
            cwd=REPO,
        )
        print("✓ commiteado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
