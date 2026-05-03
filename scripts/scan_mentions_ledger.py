#!/usr/bin/env python3
"""scan_mentions_ledger.py — recupera referencias débiles previas al crear pages.

Cuando se crea una page nueva (`bueno-gustavo`, `cognicion-humana-vs-ia`, ...) el
sub-agente solo ve el vídeo actual. Pero esa entidad pudo haber aparecido en
vídeos anteriores como `passing_mention`, `out_of_scope_figure`,
`promotion_threshold_not_met`, etc. — discarded[] que con la page nueva
debería convertirse en cita-only o pending_update enriquecedor.

Este script materializa la "memoria operativa" del LLM: escanea TODOS los JSONs
históricos buscando menciones de aliases de pages existentes y reporta señal
recuperable. Opcionalmente genera pending_updates aplicables sin re-LLM.

USO:

    # Modo 1: una sola page (recovery tras crear page nueva)
    python scripts/scan_mentions_ledger.py --page-id bueno-gustavo

    # Modo 2: audit completo de TODAS las pages (qué señal previa hay sin recoger)
    python scripts/scan_mentions_ledger.py --audit-all

    # Modo 3: aplicar (genera pending_updates_retroactive.json)
    python scripts/scan_mentions_ledger.py --page-id bueno-gustavo --apply
    python scripts/scan_mentions_ledger.py --audit-all --apply

Filosofía: process once, leverage forever — los JSONs commiteados son la
memoria del LLM, recuperable retroactivamente sin re-llamada.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

# Reuso helpers del extractor
sys.path.insert(0, str(Path(__file__).parent))
from extract_video_themes import (  # type: ignore
    _AGGREGATOR_FILENAMES,
    _build_alias_to_page_id_map,
    _find_chunk_timestamp_for_text,
    _upsert_video_citation_block,
    FRONTMATTER_RE,
    PAGE_ID_RE,
    CANONICAL_NAME_RE,
    ALIASES_BLOCK_RE,
    RUNS_DIR,
    WIKI,
    discover_videos,
    load_summary,
    now_iso,
)


# Threshold mínimo para considerar mención recuperable
MIN_QUOTE_LEN = 30

# Reason codes que indican mención débil potencialmente recuperable
RECOVERABLE_REASON_CODES = {
    "passing_mention",
    "out_of_scope_figure",
    "promotion_threshold_not_met",
    "below_recurrence_threshold",
    "single_video_no_recurrence",
    "passing_reference_to_other_polar_case",
    "absorbed_in_promoted_page",
    "story_read_no_dedicated_analysis_page",
    "captured_in_thesis_candidate",
    "in_work_character",
    "established_concept_used_as_example",
}


def _strip_diacritics(text: str) -> str:
    nkfd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nkfd if not unicodedata.combining(c))


def _normalize_for_match(text: str) -> str:
    """Lowercase + strip diacritics + collapse whitespace para matching robusto."""
    t = _strip_diacritics(text.lower())
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _build_page_lexicon(wiki_root: Path) -> dict[str, dict]:
    """Para cada page del wiki, devuelve {page_id: {canonical_name, aliases, path, page_type}}.

    Filtra paths bajo `_meta/extraction_runs/` para no incluir shadows/copias de runs.
    """
    lexicon: dict[str, dict] = {}
    for md in wiki_root.rglob("*.md"):
        if md.name == "README.md":
            continue
        # Skip shadow_wikis y otros artefactos bajo _meta/extraction_runs/
        if "_meta/extraction_runs" in str(md):
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        fm_text = m.group(1)
        pid_m = PAGE_ID_RE.search(fm_text)
        if not pid_m:
            continue
        page_id = pid_m.group(1)
        cname_m = CANONICAL_NAME_RE.search(fm_text)
        canonical_name = cname_m.group(1).strip().strip('"').strip("'") if cname_m else page_id
        aliases: list[str] = []
        aliases_m = ALIASES_BLOCK_RE.search(fm_text)
        if aliases_m:
            raw = aliases_m.group(1).replace("\n", " ")
            for chunk in re.split(r",", raw):
                cleaned = chunk.strip().strip('"').strip("'").strip("[]").strip()
                if cleaned and len(cleaned) >= 4:
                    aliases.append(cleaned)
        lexicon[page_id] = {
            "canonical_name": canonical_name,
            "aliases": aliases,
            "path": md,
            "page_type": _extract_page_type(fm_text),
        }
    return lexicon


def _extract_page_type(fm_text: str) -> str:
    m = re.search(r"^page_type:\s*(\S+)", fm_text, re.MULTILINE)
    return m.group(1) if m else ""


def _entry_matches_page(entry: dict, page_terms: set[str]) -> bool:
    """Entry de discarded[] matchea page si surface_form normalizado contiene
    cualquiera de los terms (canonical_name + aliases) normalizados."""
    sf = entry.get("surface_form", "") or ""
    if not sf:
        return False
    sf_norm = _normalize_for_match(sf)
    for term in page_terms:
        if term in sf_norm:
            return True
    return False


def _scan_jsons_for_page(
    page_id: str,
    page_info: dict,
    runs_dir: Path,
) -> list[dict]:
    """Escanea TODOS los JSONs históricos buscando menciones débiles de esta page.

    Returns: list de dicts {video_id, video_title, run_id, json_path, idx,
        old_reason_code, surface_form, quote_evidence, decision_suggested}
    """
    page_terms = {_normalize_for_match(page_info["canonical_name"])}
    for alias in page_info["aliases"]:
        page_terms.add(_normalize_for_match(alias))
    page_terms.add(_normalize_for_match(page_id.replace("-", " ")))
    # Filter trivial terms
    page_terms = {t for t in page_terms if len(t) >= 4}

    findings: list[dict] = []
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        for j in run_dir.glob("*.json"):
            if j.stem in _AGGREGATOR_FILENAMES or j.name.endswith(".failed.json"):
                continue
            try:
                data = json.loads(j.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            video_id = data.get("video_id", j.stem)
            video_title = data.get("video_title", "")
            for idx, entry in enumerate(data.get("discarded", []) or []):
                rc = entry.get("reason_code", "")
                if rc not in RECOVERABLE_REASON_CODES:
                    continue
                quote = entry.get("quote_evidence", "") or ""
                if len(quote) < MIN_QUOTE_LEN:
                    continue
                if not _entry_matches_page(entry, page_terms):
                    continue
                findings.append({
                    "video_id": video_id,
                    "video_title": video_title,
                    "run_id": run_dir.name,
                    "json_path": str(j),
                    "idx": idx,
                    "old_reason_code": rc,
                    "surface_form": entry.get("surface_form", ""),
                    "quote_evidence": quote,
                    "review_priority": entry.get("review_priority", "low"),
                    "reason_detail": entry.get("reason_detail", "")[:200],
                })
    return findings


def _resolve_video_paths(corpus_root: Path) -> dict[str, "VideoInput"]:
    """Mapea video_id → VideoInput para lookup de summary_text."""
    return {v.video_id: v for v in discover_videos(corpus_root)}


def _enrich_findings_with_timestamps(
    findings: list[dict],
    videos_by_id: dict,
) -> None:
    """In-place: añade timestamp_seconds a cada finding cargando summary del vídeo."""
    summaries_loaded: dict[str, str] = {}
    for f in findings:
        vid = f["video_id"]
        if vid not in summaries_loaded:
            video = videos_by_id.get(vid)
            if video is None:
                summaries_loaded[vid] = ""
                continue
            try:
                load_summary(video)
                summaries_loaded[vid] = video.summary_text or ""
            except Exception:
                summaries_loaded[vid] = ""
        summary_text = summaries_loaded[vid]
        if not summary_text:
            f["timestamp_seconds"] = None
            continue
        ts = _find_chunk_timestamp_for_text(summary_text, f["quote_evidence"])
        f["timestamp_seconds"] = ts


def _apply_findings_as_citations(
    page_id: str,
    page_info: dict,
    findings: list[dict],
) -> dict:
    """Para cada finding con timestamp válido, añade citation a la page via
    _upsert_video_citation_block. Idempotente — no duplica.

    Returns stats dict.
    """
    stats = {"added": 0, "skipped_no_timestamp": 0, "skipped_no_video_in_corpus": 0, "by_video": defaultdict(int)}
    page_path = page_info["path"]

    # Group findings by video_id (each video → one citation block with multiple ts)
    by_video: dict[str, dict] = {}
    for f in findings:
        ts = f.get("timestamp_seconds")
        if ts is None:
            stats["skipped_no_timestamp"] += 1
            continue
        vid = f["video_id"]
        bucket = by_video.setdefault(vid, {
            "video_id": vid,
            "video_title": f["video_title"],
            "timestamps": set(),
        })
        bucket["timestamps"].add(ts)
        stats["by_video"][vid] += 1

    for vid, bucket in by_video.items():
        try:
            added = _upsert_video_citation_block(
                page_path,
                bucket["video_id"],
                bucket["video_title"],
                bucket["timestamps"],
            )
            stats["added"] += added
        except Exception as e:
            print(f"  ! error upsert {page_id} ← {vid}: {e}", file=sys.stderr)

    return stats


def cmd_single_page(page_id: str, apply: bool, corpus_root: Path) -> None:
    lexicon = _build_page_lexicon(WIKI)
    if page_id not in lexicon:
        print(f"ERROR: page_id '{page_id}' no encontrado en {WIKI}", file=sys.stderr)
        print(f"  Pages disponibles: {sorted(lexicon.keys())[:10]}...", file=sys.stderr)
        sys.exit(1)

    page_info = lexicon[page_id]
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"SCAN MENTIONS LEDGER — page: {page_id}", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)
    print(f"  canonical_name: {page_info['canonical_name']}", file=sys.stderr)
    print(f"  aliases: {page_info['aliases']}", file=sys.stderr)
    print(f"  page_type: {page_info['page_type']}", file=sys.stderr)
    print(f"  path: {page_info['path']}", file=sys.stderr)
    print(file=sys.stderr)

    findings = _scan_jsons_for_page(page_id, page_info, RUNS_DIR)
    print(f"Menciones débiles encontradas en JSONs históricos: {len(findings)}", file=sys.stderr)

    if not findings:
        print("\n(sin señal previa recuperable)", file=sys.stderr)
        return

    # Enrich with timestamps
    print(f"Resolviendo timestamps desde summaries...", file=sys.stderr)
    videos_by_id = _resolve_video_paths(corpus_root)
    _enrich_findings_with_timestamps(findings, videos_by_id)

    # Reporte
    print(f"\n--- Findings detallados ---", file=sys.stderr)
    by_priority = sorted(findings, key=lambda f: {"high": 0, "medium": 1, "low": 2}.get(f["review_priority"], 3))
    for f in by_priority:
        ts = f.get("timestamp_seconds")
        ts_str = f"t={ts}s" if ts else "(sin ts)"
        print(f"\n  [{f['review_priority']:6}] {f['old_reason_code']} — {f['video_id']} ({f['video_title'][:50]}) {ts_str}", file=sys.stderr)
        print(f"    surface: {f['surface_form'][:70]}", file=sys.stderr)
        print(f"    quote: {f['quote_evidence'][:120]!r}", file=sys.stderr)
        if f["reason_detail"]:
            print(f"    detail: {f['reason_detail'][:120]}", file=sys.stderr)

    if apply:
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"APPLYING citations to {page_info['path']}", file=sys.stderr)
        print(f"{'='*70}", file=sys.stderr)
        stats = _apply_findings_as_citations(page_id, page_info, findings)
        print(f"\nCitations added: {stats['added']}", file=sys.stderr)
        print(f"Skipped (no timestamp): {stats['skipped_no_timestamp']}", file=sys.stderr)
        print(f"\nPor vídeo:", file=sys.stderr)
        for vid, n in stats["by_video"].items():
            print(f"  - {vid}: {n} citations", file=sys.stderr)
    else:
        with_ts = sum(1 for f in findings if f.get("timestamp_seconds"))
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"REPORTE (no aplicado — añade --apply para insertar citations)", file=sys.stderr)
        print(f"{'='*70}", file=sys.stderr)
        print(f"  Findings con timestamp recuperable: {with_ts} / {len(findings)}", file=sys.stderr)
        print(f"  Comando para aplicar:", file=sys.stderr)
        print(f"    python scripts/scan_mentions_ledger.py --page-id {page_id} --apply", file=sys.stderr)


def cmd_audit_all(apply: bool, corpus_root: Path, min_findings: int = 1) -> None:
    lexicon = _build_page_lexicon(WIKI)
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"AUDIT ALL — escaneando {len(lexicon)} pages contra JSONs históricos", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)
    print(f"Filtro: min {min_findings} findings por page para reportar", file=sys.stderr)
    print(file=sys.stderr)

    audit_results: dict[str, list[dict]] = {}
    for page_id, page_info in lexicon.items():
        findings = _scan_jsons_for_page(page_id, page_info, RUNS_DIR)
        if len(findings) >= min_findings:
            audit_results[page_id] = findings

    if not audit_results:
        print("(no pages con findings ≥ threshold)", file=sys.stderr)
        return

    # Reporte sumario
    print(f"Pages con señal previa recuperable: {len(audit_results)} / {len(lexicon)}", file=sys.stderr)
    total_findings = sum(len(v) for v in audit_results.values())
    print(f"Total findings: {total_findings}", file=sys.stderr)
    print(f"\nTop pages por count:\n", file=sys.stderr)
    by_count = sorted(audit_results.items(), key=lambda kv: -len(kv[1]))
    for page_id, findings in by_count:
        priorities = defaultdict(int)
        for f in findings:
            priorities[f["review_priority"]] += 1
        prio_str = " ".join(f"{k}={v}" for k, v in sorted(priorities.items()))
        page_type = lexicon[page_id]["page_type"]
        print(f"  [{len(findings):3d}] {page_id:40} ({page_type:12}) {prio_str}", file=sys.stderr)

    if apply:
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"APPLYING citations a TODAS las pages flagged", file=sys.stderr)
        print(f"{'='*70}", file=sys.stderr)
        videos_by_id = _resolve_video_paths(corpus_root)
        global_stats = {"pages_modified": 0, "total_added": 0, "skipped_no_ts": 0}
        for page_id, findings in audit_results.items():
            page_info = lexicon[page_id]
            _enrich_findings_with_timestamps(findings, videos_by_id)
            stats = _apply_findings_as_citations(page_id, page_info, findings)
            if stats["added"] > 0:
                global_stats["pages_modified"] += 1
                global_stats["total_added"] += stats["added"]
                print(f"  + {page_id}: +{stats['added']} citations", file=sys.stderr)
            global_stats["skipped_no_ts"] += stats["skipped_no_timestamp"]
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"Pages modificadas: {global_stats['pages_modified']}", file=sys.stderr)
        print(f"Total citations añadidas: {global_stats['total_added']}", file=sys.stderr)
        print(f"Skipped (sin timestamp): {global_stats['skipped_no_ts']}", file=sys.stderr)
        print(f"\nProximo paso: python scripts/build_wiki_db.py", file=sys.stderr)
    else:
        # Persist audit a archivo para inspección
        audit_path = RUNS_DIR / "_scan_mentions_ledger_audit.json"
        audit_path.write_text(
            json.dumps({
                "generated_at": now_iso(),
                "min_findings_threshold": min_findings,
                "pages_with_signal": len(audit_results),
                "total_findings": total_findings,
                "results": {
                    pid: [
                        {k: v for k, v in f.items() if k != "json_path"}
                        for f in findings
                    ]
                    for pid, findings in audit_results.items()
                },
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nReporte detallado: {audit_path}", file=sys.stderr)
        print(f"Para aplicar: python scripts/scan_mentions_ledger.py --audit-all --apply", file=sys.stderr)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--page-id", type=str, default=None, help="Escanea menciones débiles de UNA page específica")
    g.add_argument("--audit-all", action="store_true", dest="audit_all", help="Audit completo: todas las pages del wiki")
    p.add_argument("--apply", action="store_true", help="Aplica citations a las pages (sin --apply solo reporta)")
    p.add_argument("--min-findings", type=int, default=1, dest="min_findings", help="Mínimo de findings por page para reportar (default: 1, solo --audit-all)")
    p.add_argument("--corpus", type=Path, default=Path("/home/dae/PycharmProjects/ProxySummaries/data/playlists"), help="Corpus path para resolver summaries")
    args = p.parse_args()

    if not args.corpus.exists():
        print(f"ERROR: corpus path not found: {args.corpus}", file=sys.stderr)
        sys.exit(1)

    if args.page_id:
        cmd_single_page(args.page_id, args.apply, args.corpus)
    elif args.audit_all:
        cmd_audit_all(args.apply, args.corpus, min_findings=args.min_findings)


if __name__ == "__main__":
    main()
