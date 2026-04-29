#!/usr/bin/env python3
"""Valida coherencia del grafo wiki: relations[] en frontmatter + wikilinks en cuerpo.

Comprobaciones (errores ⇒ exit 1):
  E1. Cada relations[].type existe en wiki/_meta/relation_types.json
  E2. Cada relations[].to es page_id sintácticamente válido (kebab-case)
  E3. Frontmatter sin relations[] ⇒ error (todas las páginas migradas deben tenerlo)
  E4. Frontmatter con related_concepts/related_authors/related_works ⇒ error (campos legacy
      eliminados en la migración a typed-relations)

Comprobaciones (warnings ⇒ stderr, no fallan):
  W1. relations[].to apunta a página NO existente — candidato a compilar en próximo batch
  W2. [[wikilink]] aparece en el cuerpo pero NO está declarado en relations[] (drift de coherencia)
  W3. Combinación from/to del type fuera de los hints declarados en relation_types.json
  W4. Relación "developed_by → A" sin recíproca "developed → B" en la página A (sólo orientativo)

Uso:
  python scripts/validate_wiki_relations.py
  python scripts/validate_wiki_relations.py --strict  # warnings también devuelven exit 1
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
WIKI = REPO / "wiki"
META = WIKI / "_meta"
RELATION_TYPES_FILE = META / "relation_types.json"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
WIKILINK_BODY_RE = re.compile(r"\[\[([a-z0-9][a-z0-9_-]*)(?:\|[^\]]+)?\]\]")
PAGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
RELATIONS_BLOCK_RE = re.compile(r"^relations:\s*\n((?:\s+-\s*[^\n]+\n)+)", re.MULTILINE)
RELATION_LINE_RE = re.compile(r"^\s+-\s*\{(.+)\}\s*$")
KV_RE = re.compile(r"(\w+)\s*:\s*([^,}]+?)(?=\s*,|\s*$)")
SCALAR_FRONT_RE = re.compile(r"^([a-z_][a-z_0-9]*):\s*([^\n]+)$", re.MULTILINE)
LEGACY_BLOCK_RE = re.compile(r"^(related_concepts|related_authors|related_works):", re.MULTILINE)


class ValidationReport:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.pages_checked = 0
        self.relations_checked = 0

    def err(self, page: str, msg: str) -> None:
        self.errors.append(f"  ✗ {page}: {msg}")

    def warn(self, page: str, msg: str) -> None:
        self.warnings.append(f"  ⚠ {page}: {msg}")


def parse_relations_yaml(fm_text: str) -> list[dict[str, Any]]:
    """Parsea el bloque relations: del frontmatter (sintaxis YAML flow per item)."""
    block = RELATIONS_BLOCK_RE.search(fm_text)
    if not block:
        return []
    rels: list[dict[str, Any]] = []
    for line in block.group(1).splitlines():
        m = RELATION_LINE_RE.match(line)
        if not m:
            continue
        kv_text = m.group(1)
        rel: dict[str, Any] = {}
        for k, v in KV_RE.findall(kv_text):
            v_clean = v.strip().strip('"').strip("'")
            rel[k.strip()] = v_clean
        rels.append(rel)
    return rels


def parse_frontmatter(text: str) -> tuple[str, str] | None:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    return m.group(1), text[m.end():]


def get_scalar(fm_text: str, key: str) -> str | None:
    for m in SCALAR_FRONT_RE.finditer(fm_text):
        if m.group(1) == key:
            return m.group(2).strip().strip('"').strip("'") or None
    return None


def collect_page_index() -> dict[str, dict[str, Any]]:
    """page_id → {page_type, file_path, body, fm_text}."""
    index: dict[str, dict[str, Any]] = {}
    for md in sorted(WIKI.rglob("*.md")):
        if md.name == "README.md":
            continue
        text = md.read_text(encoding="utf-8")
        parsed = parse_frontmatter(text)
        if not parsed:
            continue
        fm_text, body = parsed
        page_id = get_scalar(fm_text, "page_id")
        if not page_id:
            continue
        index[page_id] = {
            "page_type": get_scalar(fm_text, "page_type"),
            "file_path": str(md.relative_to(REPO)),
            "fm_text": fm_text,
            "body": body,
        }
    return index


def check_type_compatibility(
    rt_def: dict[str, Any],
    src_type: str | None,
    tgt_type: str | None,
) -> str | None:
    """Devuelve mensaje de warning si la combinación from/to es inesperada, None si OK."""
    expected_from = rt_def.get("from") or []
    expected_to = rt_def.get("to") or []
    if expected_from and expected_from != ["any"] and src_type and src_type not in expected_from:
        return f"page_type={src_type} no listado en from={expected_from}"
    if expected_to and expected_to != ["any"] and tgt_type and tgt_type not in expected_to:
        return f"target page_type={tgt_type} no listado en to={expected_to}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida coherencia del grafo wiki.")
    parser.add_argument("--strict", action="store_true", help="warnings también devuelven exit 1")
    args = parser.parse_args()

    if not RELATION_TYPES_FILE.exists():
        print(f"ERROR: {RELATION_TYPES_FILE} no existe", file=sys.stderr)
        return 1

    rt_data = json.loads(RELATION_TYPES_FILE.read_text(encoding="utf-8"))
    relation_types: dict[str, Any] = rt_data.get("types", {})
    valid_types = set(relation_types.keys())

    report = ValidationReport()
    pages = collect_page_index()
    report.pages_checked = len(pages)

    if not pages:
        print("No se encontraron páginas wiki con frontmatter válido", file=sys.stderr)
        return 1

    incoming_by_page: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)

    for page_id, info in sorted(pages.items()):
        fm_text = info["fm_text"]
        body = info["body"]
        page_type = info["page_type"]

        # E4: legacy fields
        legacy_match = LEGACY_BLOCK_RE.search(fm_text)
        if legacy_match:
            report.err(page_id, f"contiene campo legacy '{legacy_match.group(1)}' — debe migrarse a relations[]")

        relations = parse_relations_yaml(fm_text)

        # E3: relations[] obligatorio
        if not relations:
            report.err(page_id, "frontmatter sin bloque relations[] (toda página migrada debe declarar al menos sus relaciones canónicas)")
            continue

        body_wikilinks = {m.group(1) for m in WIKILINK_BODY_RE.finditer(body)}
        declared_targets: set[str] = set()

        for i, rel in enumerate(relations):
            report.relations_checked += 1
            rel_loc = f"relations[{i}]"
            rtype = rel.get("type")
            rto = rel.get("to")

            # E1: type válido
            if not rtype or rtype not in valid_types:
                report.err(page_id, f"{rel_loc} type={rtype!r} no está en relation_types.json")
                continue

            # E2: to válido sintácticamente
            if not rto or not PAGE_ID_RE.match(rto):
                report.err(page_id, f"{rel_loc} to={rto!r} no es un page_id válido (kebab-case)")
                continue

            declared_targets.add(rto)
            incoming_by_page[rto].append((page_id, rtype))

            # W1: target existe
            target_info = pages.get(rto)
            if target_info is None:
                report.warn(page_id, f"{rel_loc} to={rto!r} no es página existente (candidato a próximo batch)")
                continue

            # W3: from/to compatibility
            rt_def = relation_types[rtype]
            mismatch = check_type_compatibility(rt_def, page_type, target_info.get("page_type"))
            if mismatch:
                report.warn(page_id, f"{rel_loc} type={rtype} — {mismatch}")

        # W2: cada wikilink del cuerpo está en relations[]
        for wl in body_wikilinks:
            if wl == page_id:
                continue
            if wl not in declared_targets:
                report.warn(page_id, f"[[{wl}]] aparece en el cuerpo pero no está declarado en relations[]")

    # W4: chequeo orientativo de inversos (solo informativo, no bloqueante)
    # Saltado en V1 — implementación futura si decidimos forzar reciprocidad explícita

    print(f"\nValidación de wiki/_meta + wiki/")
    print(f"  Páginas verificadas:  {report.pages_checked}")
    print(f"  Relaciones revisadas: {report.relations_checked}")
    print(f"  Errores:              {len(report.errors)}")
    print(f"  Warnings:             {len(report.warnings)}")

    if report.errors:
        print("\nERRORES:")
        for e in report.errors:
            print(e)

    if report.warnings:
        print("\nWARNINGS (no bloqueantes salvo --strict):")
        for w in report.warnings:
            print(w)

    if report.errors:
        return 1
    if args.strict and report.warnings:
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
