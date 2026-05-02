#!/usr/bin/env python3
"""apply_pending_updates.py

Aplica updates desde wiki/_meta/extraction_runs/<run_id>/pending_updates.json
a las páginas wiki existentes, con seguridad por capas:

  1. Dry-run por defecto — muestra diff sin tocar nada
  2. --apply requiere git tree limpio (rollback fácil con git checkout)
  3. Backup automático del estado pre-edit en
     wiki/_meta/extraction_runs/<run_id>/applied_backup/<page_id>.md
  4. Lagunas declaradas como `supersedes_laguna` NO se borran:
     se marcan con comentario HTML <!-- LAGUNA POSSIBLY RESOLVED... -->
     para que las leas tú al revisar el diff
  5. Tras --apply, corre validate_wiki_relations.py sobre páginas tocadas

Tipos soportados:
  add_citation       — Append `content_proposed` al final de section_target
  enrich_section     — Igual que add_citation (semánticamente prosa nueva)
  add_relation       — Mergea entry nuevo en relations[] del frontmatter
  new_lagunas_resolved — Marca laguna como posiblemente resuelta (HTML comment)

NO soportados (requieren edición humana):
  correct_factual_error — Search/replace en prosa, alto riesgo

Notación de section_target:
  "Definición"               → H2 "## Definición"
  "Manifestaciones → Tarzán" → H2 "## Manifestaciones" / H3 "### Tarzán"
  3+ niveles soportados análogamente

Uso:
    # Ver qué pasaría (default)
    python scripts/apply_pending_updates.py --from-run pilot_2026_05_02_v2

    # Aplicar todo
    python scripts/apply_pending_updates.py --from-run pilot_2026_05_02_v2 --apply

    # Filtrar por tipo o página
    python scripts/apply_pending_updates.py --from-run X --types add_citation,add_relation
    python scripts/apply_pending_updates.py --from-run X --page-id mito-polar

    # Continuar aunque haya fallos parciales (default: para al primero)
    python scripts/apply_pending_updates.py --from-run X --apply --continue-on-error
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
WIKI = REPO / "wiki"
META = WIKI / "_meta"
RUNS_DIR = META / "extraction_runs"

SUPPORTED_TYPES = {
    "insert_after_passage",
    "insert_before_passage",
    "extend_passage",
    "replace_passage",
    "append_to_section",
    "mark_laguna_resolved",
    # Legacy (piloto v2) — mantenidos para compatibilidad
    "add_citation",
    "enrich_section",
    "new_lagunas_resolved",
}
UNSUPPORTED_TYPES = {"correct_factual_error", "add_relation"}

HEADING_RE = re.compile(r"^(#+)\s+(.+?)\s*$")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def find_page_path(page_id: str) -> Optional[Path]:
    for md in WIKI.rglob(f"{page_id}.md"):
        return md
    return None


def parse_heading_path(section_target: str) -> list[str]:
    if not section_target:
        return []
    return [s.strip() for s in re.split(r"→|->", section_target) if s.strip()]


def find_section_insert_index(lines: list[str], heading_path: list[str]) -> Optional[int]:
    """Devuelve el índice de línea ANTES del cual insertar (final de la sección).

    Algoritmo: avanza por lines[] manteniendo qué nivel del path llevamos
    matched. Cuando matchea todos, busca el primer heading de nivel <= al de
    la última coincidencia para marcar el fin de la sección.
    """
    if not heading_path:
        return None
    matched: list[tuple[int, int]] = []  # [(level, line_idx), ...]

    i = 0
    while i < len(lines):
        m = HEADING_RE.match(lines[i])
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()

            if not matched:
                if text.lower() == heading_path[0].lower():
                    matched.append((level, i))
            else:
                last_level, _ = matched[-1]
                if level <= last_level:
                    if len(matched) == len(heading_path):
                        return i  # final de la sección matched
                    return None  # path no completado y salimos de scope
                # Más profundo: ¿matchea siguiente del path?
                next_idx = len(matched)
                if next_idx < len(heading_path) and text.lower() == heading_path[next_idx].lower():
                    matched.append((level, i))
        i += 1

    if matched and len(matched) == len(heading_path):
        return len(lines)
    return None


def insert_content_at(lines: list[str], idx: int, content: str) -> list[str]:
    """Inserta content (string) en idx, con líneas en blanco de respiración."""
    block = ["", content.rstrip(), ""]
    return lines[:idx] + block + lines[idx:]


# ---------------------------------------------------------------------------
# Operaciones por tipo de update
# ---------------------------------------------------------------------------


def op_append_to_section(text: str, update: dict) -> tuple[str, list[str]]:
    """add_citation / enrich_section. Devuelve (new_text, log_messages)."""
    msgs: list[str] = []
    section = update.get("section_target", "")
    path = parse_heading_path(section)
    content = update.get("content_proposed", "")
    if not content:
        msgs.append(f"  ! sin content_proposed; skip")
        return text, msgs
    if not path:
        msgs.append(f"  ! section_target vacío; skip")
        return text, msgs

    lines = text.splitlines()
    idx = find_section_insert_index(lines, path)
    if idx is None:
        msgs.append(f"  ! sección no encontrada: {' → '.join(path)}; skip")
        return text, msgs

    # Comprobar duplicación obvia: si content ya está literalmente en el archivo, skip
    if content.strip() in text:
        msgs.append(f"  ! content_proposed ya presente en página; skip")
        return text, msgs

    new_lines = insert_content_at(lines, idx, content)
    msgs.append(f"  + insert {len(content)} chars en {' → '.join(path)} (línea {idx})")
    return "\n".join(new_lines), msgs


def op_mark_superseded_laguna(text: str, laguna_text: str) -> tuple[str, list[str]]:
    """Marca la laguna con comentario HTML, NO la borra."""
    msgs: list[str] = []
    if not laguna_text:
        return text, msgs
    snippet = laguna_text[:80].strip()
    if not snippet:
        return text, msgs

    lines = text.splitlines()
    # Localizar sección Lagunas
    lag_start = None
    lag_level = None
    for i, ln in enumerate(lines):
        m = HEADING_RE.match(ln)
        if m and m.group(2).strip().lower().startswith("lagunas"):
            lag_start = i
            lag_level = len(m.group(1))
            break
    if lag_start is None:
        msgs.append(f"  ! no hay sección Lagunas; skip mark")
        return text, msgs

    # Final de la sección lagunas
    lag_end = len(lines)
    for j in range(lag_start + 1, len(lines)):
        m = HEADING_RE.match(lines[j])
        if m and len(m.group(1)) <= lag_level:
            lag_end = j
            break

    # Buscar bullet que contenga el snippet
    target_idx = None
    for j in range(lag_start + 1, lag_end):
        if snippet in lines[j]:
            target_idx = j
            break
        # match por palabras significativas si exact substring falla
        words = [w for w in re.findall(r"\w+", snippet.lower()) if len(w) > 4]
        if words and all(w in lines[j].lower() for w in words[:3]):
            target_idx = j
            break

    if target_idx is None:
        msgs.append(f"  ! laguna no localizada: {snippet[:50]!r}; skip mark")
        return text, msgs

    marker = f"<!-- LAGUNA POSSIBLY RESOLVED por update reciente — verificar y borrar este bullet si confirmado: {snippet[:120]} -->"
    if marker in text:
        msgs.append(f"  · laguna ya marcada; skip")
        return text, msgs

    # Insertar marker INMEDIATAMENTE ANTES del bullet
    new_lines = lines[:target_idx] + [marker] + lines[target_idx:]
    msgs.append(f"  + marked laguna en línea {target_idx}: {snippet[:60]!r}")
    return "\n".join(new_lines), msgs


def op_add_relation(text: str, update: dict) -> tuple[str, list[str]]:
    """add_relation: stub — no implementado todavía."""
    return text, [f"  ! add_relation aún no implementado en este script — manual edit del frontmatter"]


def _coerce_str(value, field_name: str) -> tuple[str, list[str]]:
    """LLM a veces emite list donde el schema pide string. Coerce defensivo:
    list → primer elemento str. Otros tipos → str(). Devuelve (string, warnings)."""
    warns: list[str] = []
    if isinstance(value, str):
        return value, warns
    if isinstance(value, list):
        for v in value:
            if isinstance(v, str) and v:
                warns.append(f"  ! {field_name} llegó como list — usando primer elemento")
                return v, warns
        return "", warns
    if value is None:
        return "", warns
    warns.append(f"  ! {field_name} tipo inesperado ({type(value).__name__}); coerce a str")
    return str(value), warns


def op_unique_anchor(
    text: str,
    update: dict,
    placement: str,
) -> tuple[str, list[str]]:
    """Operación común para insert_after_passage / insert_before_passage /
    extend_passage / replace_passage. La regla de oro: anchor_passage debe
    aparecer EXACTAMENTE UNA VEZ en el cuerpo. Si 0 o ≥2 → skip seguro.

    placement ∈ {'after', 'before', 'extend', 'replace'}:
      after   → inserta content tras el anchor (con saltos de línea)
      before  → inserta content antes del anchor
      extend  → inserta content tras el anchor sin separación (continuación
                de la frase/párrafo)
      replace → reemplaza anchor por content
    """
    msgs: list[str] = []
    anchor, w1 = _coerce_str(update.get("anchor_passage"), "anchor_passage")
    content, w2 = _coerce_str(update.get("content_proposed"), "content_proposed")
    msgs.extend(w1)
    msgs.extend(w2)

    if not anchor:
        msgs.append(f"  ! anchor_passage vacío; skip")
        return text, msgs
    if not content and placement != "replace":
        msgs.append(f"  ! content_proposed vacío; skip")
        return text, msgs

    n = text.count(anchor)
    if n == 0:
        msgs.append(f"  ! anchor no encontrado literal en página; skip — anchor[:80]={anchor[:80]!r}")
        return text, msgs
    if n > 1:
        msgs.append(f"  ! anchor matches {n} veces — ambiguo; skip — anchor[:80]={anchor[:80]!r}")
        return text, msgs

    idx = text.index(anchor)
    end = idx + len(anchor)

    if placement == "after":
        new_text = text[:end] + "\n\n" + content.rstrip() + "\n" + text[end:]
        msgs.append(f"  + insert_after ({len(content)} chars) tras anchor único")
    elif placement == "before":
        new_text = text[:idx] + content.rstrip() + "\n\n" + text[idx:]
        msgs.append(f"  + insert_before ({len(content)} chars) antes de anchor único")
    elif placement == "extend":
        # Continuación inmediata del anchor — útil para extender una frase
        # sin saltos de línea adicionales
        sep = " " if not anchor.endswith(("\n", " ")) else ""
        new_text = text[:end] + sep + content.lstrip() + text[end:]
        msgs.append(f"  + extend_passage ({len(content)} chars) tras anchor único")
    elif placement == "replace":
        new_text = text[:idx] + content + text[end:]
        msgs.append(f"  + replace_passage ({len(anchor)} chars → {len(content)} chars)")
    else:
        return text, [f"  ! placement desconocido: {placement}"]

    return new_text, msgs


# ---------------------------------------------------------------------------
# Aplicación por página
# ---------------------------------------------------------------------------


def apply_updates_to_page(page_path: Path, updates: list[dict]) -> tuple[str, str, list[str]]:
    """Aplica todos los updates a una página. Devuelve (original, new, log_messages)."""
    original = page_path.read_text(encoding="utf-8")
    current = original
    msgs: list[str] = []

    for u in updates:
        utype = u.get("update_type", "")
        anchor_preview = (u.get("anchor_passage") or "")[:50]
        section_preview = (u.get("section_target") or "")[:50]
        msgs.append(f" [{utype}] anchor={anchor_preview!r} section={section_preview!r}")

        if utype == "insert_after_passage":
            current, m = op_unique_anchor(current, u, "after")
            msgs.extend(m)
        elif utype == "insert_before_passage":
            current, m = op_unique_anchor(current, u, "before")
            msgs.extend(m)
        elif utype == "extend_passage":
            current, m = op_unique_anchor(current, u, "extend")
            msgs.extend(m)
        elif utype == "replace_passage":
            current, m = op_unique_anchor(current, u, "replace")
            msgs.extend(m)
        elif utype == "append_to_section" or utype in {"add_citation", "enrich_section"}:
            # Legacy / fallback: concat al final de la sección
            current, m = op_append_to_section(current, u)
            msgs.extend(m)
        elif utype == "add_relation":
            current, m = op_add_relation(current, u)
            msgs.extend(m)
        elif utype in {"mark_laguna_resolved", "new_lagunas_resolved"}:
            laguna = u.get("supersedes_laguna_text") or u.get("supersedes_laguna") or ""
            current, m = op_mark_superseded_laguna(current, laguna)
            msgs.extend(m)
        elif utype in UNSUPPORTED_TYPES:
            msgs.append(f"  ! {utype} no soportado por este script — manual")
            continue
        else:
            msgs.append(f"  ! tipo desconocido: {utype}; skip")
            continue

        # Side-effect: si update lleva supersedes_laguna_text, marcar laguna
        sl = u.get("supersedes_laguna_text") or u.get("supersedes_laguna")
        if sl and utype not in {"mark_laguna_resolved", "new_lagunas_resolved"}:
            current, m = op_mark_superseded_laguna(current, sl)
            msgs.extend(m)

    return original, current, msgs


def show_diff(page_id: str, original: str, new: str) -> None:
    """Llama a `diff` del sistema con etiquetas legibles."""
    if original == new:
        print(f"  (no changes for {page_id})")
        return
    proc = subprocess.run(
        ["diff", "-u", "--label", f"{page_id} (original)", "--label", f"{page_id} (proposed)", "-", "/dev/stdin"],
        input=new,
        capture_output=True,
        text=True,
    )
    # diff via subprocess es complicado con dos stdin; uso archivos temporales en su lugar
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".original.md", delete=False) as f1, \
         tempfile.NamedTemporaryFile("w", suffix=".proposed.md", delete=False) as f2:
        f1.write(original)
        f2.write(new)
        f1_path, f2_path = f1.name, f2.name
    try:
        proc = subprocess.run(
            ["diff", "-u", f"--label={page_id} (original)", f"--label={page_id} (proposed)", f1_path, f2_path],
            capture_output=True,
            text=True,
        )
        print(proc.stdout)
    finally:
        Path(f1_path).unlink(missing_ok=True)
        Path(f2_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Verificación previa
# ---------------------------------------------------------------------------


def check_git_clean() -> tuple[bool, str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    if proc.returncode != 0:
        return False, proc.stderr
    if proc.stdout.strip():
        return False, f"git tree no está limpio:\n{proc.stdout}"
    return True, ""


def run_validator(touched_paths: list[Path]) -> int:
    print("\n=== Ejecutando validate_wiki_relations.py ===", file=sys.stderr)
    proc = subprocess.run(
        [sys.executable, "scripts/validate_wiki_relations.py"],
        cwd=REPO,
    )
    return proc.returncode


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-run", required=True, help="run_id en wiki/_meta/extraction_runs/")
    ap.add_argument("--apply", action="store_true", help="Aplicar cambios. Sin esta flag = dry-run.")
    ap.add_argument("--types", default=",".join(SUPPORTED_TYPES), help="CSV de update_types a aplicar")
    ap.add_argument("--page-id", default=None, help="Filtrar por page_id concreto")
    ap.add_argument("--continue-on-error", action="store_true", help="Continuar aunque una página falle")
    ap.add_argument("--no-validator", action="store_true", help="Saltar validate_wiki_relations.py tras --apply")
    ap.add_argument("--no-git-check", action="store_true", help="Saltar verificación de git tree limpio")
    ap.add_argument("--auto-commit", action="store_true", help="Tras --apply, crear 1 commit semántico con los cambios")
    ap.add_argument("--max-updates-per-page", type=int, default=None, help="Si una página recibe más updates que este límite, abortar (señal de que necesita curaduría humana)")
    args = ap.parse_args()

    types_filter = {t.strip() for t in args.types.split(",") if t.strip()}

    run_dir = RUNS_DIR / args.from_run
    pu_path = run_dir / "pending_updates.json"
    if not pu_path.exists():
        sys.exit(f"No se encontró {pu_path}. Ejecuta primero --aggregate {args.from_run}.")

    data = json.loads(pu_path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    if not items:
        print("Sin pending_updates en este run.")
        return

    # Filtrar
    grouped: dict[str, list[dict]] = defaultdict(list)
    skipped_unsupported = 0
    for it in items:
        u = it["update"]
        page_id = u.get("page_id", "")
        utype = u.get("update_type", "")
        if args.page_id and page_id != args.page_id:
            continue
        if utype not in types_filter:
            if utype in UNSUPPORTED_TYPES:
                skipped_unsupported += 1
            continue
        grouped[page_id].append(u)

    print(f"Run: {args.from_run}", file=sys.stderr)
    print(f"Modo: {'APPLY' if args.apply else 'DRY-RUN'}", file=sys.stderr)
    print(f"Páginas afectadas: {len(grouped)} | updates: {sum(len(v) for v in grouped.values())}", file=sys.stderr)
    if skipped_unsupported:
        print(f"  (skipped {skipped_unsupported} updates de tipos no soportados)", file=sys.stderr)
    print()

    if args.apply and not args.no_git_check:
        ok, msg = check_git_clean()
        if not ok:
            sys.exit(f"ABORT: {msg}\nCommit o stash tus cambios antes de --apply (rollback con `git checkout -- wiki/`).")

    if args.max_updates_per_page is not None:
        excess = {pid: len(us) for pid, us in grouped.items() if len(us) > args.max_updates_per_page}
        if excess:
            print(f"ABORT: páginas con > {args.max_updates_per_page} updates (curaduría humana requerida):", file=sys.stderr)
            for pid, n in sorted(excess.items(), key=lambda kv: -kv[1]):
                print(f"  {pid}: {n} updates", file=sys.stderr)
            sys.exit(2)

    backup_dir = run_dir / "applied_backup"
    if args.apply:
        backup_dir.mkdir(parents=True, exist_ok=True)

    touched: list[Path] = []
    failed: list[tuple[str, str]] = []
    apply_log = {
        "applied_at": now_iso(),
        "run_id": args.from_run,
        "types_filter": sorted(types_filter),
        "pages": {},
    }

    for page_id, updates in sorted(grouped.items()):
        page_path = find_page_path(page_id)
        if page_path is None:
            print(f"=== {page_id} === NO ENCONTRADA EN wiki/", file=sys.stderr)
            failed.append((page_id, "page not found"))
            if not args.continue_on_error and args.apply:
                sys.exit(1)
            continue

        rel = page_path.relative_to(REPO)
        print(f"=== {page_id} ({rel}) — {len(updates)} update(s) ===", file=sys.stderr)
        original, new, msgs = apply_updates_to_page(page_path, updates)
        for line in msgs:
            print(line, file=sys.stderr)

        if original == new:
            print("  (sin cambios netos)", file=sys.stderr)
            continue

        if not args.apply:
            print()
            show_diff(page_id, original, new)
            print()
            continue

        # Apply
        backup_dir.joinpath(f"{page_id}.md.original").write_text(original, encoding="utf-8")
        page_path.write_text(new, encoding="utf-8")
        touched.append(page_path)
        apply_log["pages"][page_id] = {
            "file_path": str(rel),
            "updates_applied": len(updates),
            "log": msgs,
        }
        print(f"  ✓ wrote {rel}", file=sys.stderr)

    if args.apply:
        log_path = run_dir / "applied_log.json"
        log_path.write_text(json.dumps(apply_log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nLog: {log_path}", file=sys.stderr)
        print(f"Backup: {backup_dir}/", file=sys.stderr)
        print(f"Touched files: {len(touched)}", file=sys.stderr)
        print(f"\nRollback (si lo necesitas):", file=sys.stderr)
        print(f"  git checkout -- {' '.join(str(p.relative_to(REPO)) for p in touched)}", file=sys.stderr)

        if not args.no_validator and touched:
            rc = run_validator(touched)
            if rc != 0:
                print(f"\n! validate_wiki_relations.py falló (rc={rc}). Revisa errores arriba.", file=sys.stderr)
                if not args.continue_on_error:
                    sys.exit(rc)

        if args.auto_commit and touched:
            n_pages = len(touched)
            n_updates = sum(p["updates_applied"] for p in apply_log["pages"].values())
            page_ids_str = ", ".join(sorted(apply_log["pages"].keys()))
            commit_msg = (
                f"extractor({args.from_run}): apply {n_updates} pending_updates → {n_pages} pages\n\n"
                f"Aplicado por scripts/apply_pending_updates.py.\n"
                f"Run: {args.from_run}\n"
                f"Tipos: {','.join(sorted(types_filter))}\n"
                f"Páginas: {page_ids_str}\n"
                f"Audit trail (gitignored): wiki/_meta/extraction_runs/{args.from_run}/applied_log.json\n"
            )
            # Solo añadimos los archivos del wiki tocados. extraction_runs/ está
            # gitignored — el audit trail vive local en el run dir y el backup.
            paths_to_add = [str(p.relative_to(REPO)) for p in touched]
            subprocess.run(["git", "add"] + paths_to_add, cwd=REPO, check=False)
            commit = subprocess.run(["git", "commit", "-m", commit_msg], cwd=REPO, capture_output=True, text=True)
            if commit.returncode != 0:
                print(f"\n! git commit falló: {commit.stderr.strip()}", file=sys.stderr)
                sys.exit(commit.returncode)
            print(f"\n  ✓ commit creado: {n_updates} updates → {n_pages} pages", file=sys.stderr)

    if failed:
        print(f"\n{len(failed)} fallos:", file=sys.stderr)
        for pid, reason in failed:
            print(f"  {pid}: {reason}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
