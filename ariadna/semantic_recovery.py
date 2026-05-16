"""Semantic recovery: pasada 2 de scan_mentions_ledger.

Mientras scan_mentions_ledger hace sub-string match (rápido, free) sobre
aliases declarados, este módulo hace **semantic match** vía embeddings
+ LLM judge para capturar el caso donde la variante lingüística NO está
declarada como alias.

Pipeline:
    1. Cargar discarded entries con reason_code recoverable (filtro previo laxo)
    2. Cargar pages del wiki (canonical_name + aliases + page_id)
    3. Embedding BGE-M3 sobre canonicals (in-memory, no Qdrant)
    4. Top-K por cosine
    5. Cache lookup; LLM judge para misses. El judge devuelve:
       - match_page_id + confidence + rationale (decisión semántica)
       - alias_candidate (subcadena LITERAL del surface_form que funciona
         como nombre canónico; null si no se puede extraer)
       - alias_exists (si el candidato ya está en aliases/canonical)
    6. Apply matches high-confidence:
       - citation: siempre (corpus valioso, decisión semántica del LLM)
       - alias: SOLO si alias_candidate != null, alias_exists==false,
         pasa validación numérica (≤60 chars, ≤7 palabras) y es subcadena
         del surface_form (no hallucination del LLM)

Diseño deliberadamente simple por simplicidad/coste:
    - Embed solo el string del concepto, no focal/headers/aliases
    - Cache es JSON simple en wiki/_meta/semantic_recovery_cache.json
    - Invalidación: si top-K de un discarded cambia (nueva page entra al
      top-K vía cosine), cache_key cambia → re-evaluación automática
    - Sólo high-confidence se aplica; medium/low se reportan

Coste esperado: ~3-4M tokens primer pase (one-time), ~100k por run
posterior (con cache caliente). Ver docs/SEMANTIC_RECOVERY_NOTES.md.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

# Reusos del scan_mentions_ledger (helpers ya testeados de extracción/apply)
_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _REPO / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))
from scan_mentions_ledger import (  # type: ignore  # noqa: E402
    _apply_findings_as_citations,
    _build_page_lexicon,
    _enrich_findings_with_timestamps,
    _normalize_for_match,
    _resolve_video_paths,
    ALIASES_BLOCK_RE,
    FRONTMATTER_RE,
)

WIKI_ROOT = _REPO / "wiki"
EXTRACTION_RUNS = WIKI_ROOT / "_meta" / "extraction_runs"
CACHE_PATH = WIKI_ROOT / "_meta" / "semantic_recovery_cache.json"

# Reason codes que SÍ son candidatos a recovery (resto = scope-out o ya capturados)
RECOVERABLE_REASONS = frozenset({
    "passing_mention",
    "established_concept_used_as_example",
    "recommended_reference",
    "internal_framework_reference",
    "promotion_threshold_not_met",
    "out_of_scope_figure",
})

# Archivos del aggregator que NO son per-video JSONs
_AGGREGATOR_FILENAMES = (
    "state",
    "pending_",
    "promote_",
    "thesis_",
    "discard_",
    "recommended_",
    "aggregation_",
    "blocks_filtered",
    "_",  # cualquier prefijo audit
)


@dataclass
class DiscardedEntry:
    video_id: str
    surface_form: str
    reason_code: str
    reason_detail: str = ""
    quote_evidence: str = ""
    timestamp_seconds: Optional[int] = None

    @property
    def cache_key(self) -> str:
        """Hash insensible a variantes triviales del surface_form."""
        norm = _normalize_for_match(self.surface_form)
        return hashlib.sha1(f"{norm}|{self.reason_code}".encode()).hexdigest()[:16]


# Filtro minimalista para alias enrichment. La decisión semántica
# (¿qué parte del surface_form es el nombre canónico?) la toma el LLM judge
# devolviendo `alias_candidate`. Aquí solo validamos sanidad numérica del
# candidate para evitar hallucinations groseras o glosas largas.
ALIAS_MAX_CHARS = 60
ALIAS_MAX_WORDS = 7


def _is_concept_like(s: str) -> bool:
    """True si el string tiene longitud razonable de nombre canónico.
    No mira contenido — la decisión semántica vive en el LLM judge."""
    s = s.strip()
    if not s:
        return False
    return len(s) <= ALIAS_MAX_CHARS and len(s.split()) <= ALIAS_MAX_WORDS


def _alias_in_surface_form(alias_candidate: str, surface_form: str) -> bool:
    """True si alias_candidate aparece literalmente en surface_form con word
    boundaries (anti-hallucination del LLM). Insensible a case y diacríticos."""
    norm_alias = _normalize_for_match(alias_candidate)
    norm_sf = _normalize_for_match(surface_form)
    if not norm_alias:
        return False
    # word boundary match: re.escape + \b
    return bool(re.search(rf"\b{re.escape(norm_alias)}\b", norm_sf))


@dataclass
class JudgeDecision:
    match_page_id: Optional[str]
    confidence: str  # high|medium|low
    rationale: str
    analyzed_at: str
    candidates_signature: str
    # Alias candidate (extraído por el LLM del surface_form, limpio) y si ya
    # existe en canonical_name/aliases de la matched page. Persistidos en
    # cache para que el alias enrichment en runs futuros funcione vía cache
    # hit sin tener que reinvocar al LLM.
    alias_candidate: Optional[str] = None
    alias_exists: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "JudgeDecision":
        return cls(**d)


def _collect_eligible_discarded(extraction_runs: Path = EXTRACTION_RUNS) -> list[DiscardedEntry]:
    """Escanea JSONs históricos, filtra por reason_code recoverable, dedup por
    (surface_form normalizado, reason_code).

    Si el mismo surface_form aparece en varios vídeos, mantiene el primer
    encuentro (suficiente para que el LLM judge decida una vez).
    """
    seen: dict[str, DiscardedEntry] = {}
    for jpath in extraction_runs.glob("*/*.json"):
        name = jpath.name
        if name.startswith(_AGGREGATOR_FILENAMES):
            continue
        vid = jpath.stem
        if len(vid) != 11:
            continue
        try:
            doc = json.loads(jpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for entry in doc.get("discarded", []) or []:
            reason = entry.get("reason_code", "")
            if reason not in RECOVERABLE_REASONS:
                continue
            sf = (entry.get("surface_form") or "").strip()
            if not sf:
                continue
            # Filtro previo MUY laxo: solo descarta lo claramente inviable.
            # El gate estricto concept-like se aplica más tarde, solo al cristalizar
            # el alias — la citation se materializa siempre que haya match high.
            if len(sf) > 120 or len(sf.split()) > 15:
                continue
            de = DiscardedEntry(
                video_id=vid,
                surface_form=sf,
                reason_code=reason,
                reason_detail=entry.get("reason_detail", "") or "",
                quote_evidence=entry.get("quote_evidence", "") or "",
                timestamp_seconds=entry.get("timestamp_seconds"),
            )
            seen.setdefault(de.cache_key, de)
    return list(seen.values())


def _embed_strings(strings: list[str]) -> np.ndarray:
    """Embed BGE-M3 sobre strings cortos. Vectores L2-normalizados (BGE-M3 default).
    Devuelve (N, D)."""
    from ariadna.embeddings import DenseEmbedder
    embedder = DenseEmbedder()
    return embedder.embed(strings, batch_size=64)


def _compute_top_k(
    discarded_vecs: np.ndarray,
    page_vecs: np.ndarray,
    k: int = 5,
) -> tuple[np.ndarray, np.ndarray]:
    """Cosine top-K. Asume vectores L2-normalizados (producto interno = cosine).

    Devuelve (top_idx, sim_matrix). top_idx shape (N_discarded, k); sim_matrix
    completa para debug/threshold.
    """
    sim = discarded_vecs @ page_vecs.T
    top_idx = np.argsort(-sim, axis=1)[:, :k]
    return top_idx, sim


def _candidates_signature(candidate_page_ids: list[str]) -> str:
    """Hash de la lista ORDENADA de candidates. Si top-K cambia (e.g., nueva
    page entra al top-K), el hash cambia → cache miss → re-evaluación."""
    return hashlib.sha1("|".join(candidate_page_ids).encode()).hexdigest()[:16]


def _load_cache() -> dict[str, dict]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


_JUDGE_PROMPT_TEMPLATE = """Eres un evaluador semántico. Recibes una MENCIÓN DESCARTADA del corpus YouTube de Proxy y 5 PÁGINAS WIKI CANDIDATAS (con sus aliases ya declarados). Determina si la mención se refiere semánticamente a alguna de ellas y extrae el concepto limpio si aplica.

## Mención descartada

surface_form: {sf!r}
reason_code: {reason_code}
reason_detail: {reason_detail!r}
quote_evidence: {quote!r}

## Candidatas (top-5 por similitud coseno con surface_form)

{candidates_block}

## Tu tarea

**1) Decide match.** ¿La mención `surface_form` se refiere semánticamente a alguna candidata?
- Sinónimos ("mito del sol" ≈ "mito solar"), variantes morfológicas, registros distintos: SÍ matchea
- Co-ocurrencia temática sola NO matchea ("psicología" NO matchea jung-carl-gustav)

**2) Extrae alias_candidate.** Si hay match, identifica EL CONCEPTO LIMPIO dentro del surface_form. **DEBE SER UNA SUBCADENA LITERAL DEL surface_form** (puedes elegir mayúsculas/minúsculas pero no cambiar palabras ni morfología). El corpus es la fuente — no normalices ni reformules.

Ejemplos:
- surface_form="Narrativas políticas y sofisma estético" → alias_candidate="sofisma estético" ✓ (subcadena)
- surface_form="mito solar" → alias_candidate="mito solar" ✓
- surface_form="endofobia (herida narcisista del progresista)" → alias_candidate="endofobia" ✓
- surface_form="Realismo cognitivo invocado como tesis filosófica" → alias_candidate="Realismo cognitivo" ✓
- surface_form="mitos solares" → alias_candidate="mitos solares" ✓ (NO "mito solar" — eso es reformulación, prohibido)
- surface_form="autismo como bioanomalía" → alias_candidate=null (ninguna subcadena limpia funciona como nombre)

Reglas para alias_candidate:
- Subcadena LITERAL del surface_form (case insensitive permitido, morfología NO)
- Concepto puro: sin verbos conjugados, sin glosas, sin conectores explicativos
- Máximo 60 caracteres y 7 palabras
- Si no hay match, o no se puede extraer subcadena que funcione como nombre canónico, devuelve null

**3) Decide alias_exists.** ¿El alias_candidate ya está declarado en la page matched (como canonical_name o en aliases)? Compara case-insensitive y tolerando diacríticos.

## Output (JSON ÚNICO sin texto adicional)

{{
  "match_page_id": "<page_id o null>",
  "confidence": "high" | "medium" | "low",
  "rationale": "<una frase>",
  "alias_candidate": "<concepto limpio o null>",
  "alias_exists": true | false
}}

Reglas de confidence:
- "high" + match: equivalencia semántica clara, sin ambigüedad
- "medium" + match: probable pero con ambigüedad contextual
- "low" + match: match débil, probablemente ruido
- match_page_id=null: ninguna candidata matchea
"""


_JSON_OUTPUT_RE = re.compile(
    r'\{[^{}]*"match_page_id"[^{}]*\}', re.DOTALL
)


def _llm_judge(
    discarded: DiscardedEntry,
    candidates: list[dict],
    timeout_s: int = 120,
) -> JudgeDecision:
    """Invoca `claude -p` sub-agente para decidir si el discarded matchea alguno
    de los candidates. Output JSON estructurado. Si falla, devuelve no-match low.
    """
    candidates_block = "\n".join(
        f"  {i + 1}. page_id={c['page_id']}, canonical_name={c['canonical_name']!r}, "
        f"page_type={c['page_type']}, aliases={c.get('aliases', [])!r}"
        for i, c in enumerate(candidates)
    )
    prompt = _JUDGE_PROMPT_TEMPLATE.format(
        sf=discarded.surface_form,
        reason_code=discarded.reason_code,
        reason_detail=discarded.reason_detail or "(none)",
        quote=discarded.quote_evidence or "(none)",
        candidates_block=candidates_block,
    )
    candidates_sig = _candidates_signature([c["page_id"] for c in candidates])
    now = datetime.now(timezone.utc).isoformat()

    try:
        proc = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--output-format", "json",
                "--dangerously-skip-permissions",
                "--max-turns", "1",
                "--model", "claude-sonnet-4-6",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude -p failed rc={proc.returncode}: {proc.stderr[:300]}")
        # claude -p --output-format json devuelve una LISTA de mensajes stream
        # (system init, assistant, rate_limit_event, result). El mensaje con
        # type='result' lleva el campo 'result' con el texto final.
        text = proc.stdout
        try:
            wrapper = json.loads(proc.stdout)
            if isinstance(wrapper, list):
                # buscar el mensaje result; fallback a último assistant
                for msg in reversed(wrapper):
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("type") == "result" and msg.get("result"):
                        text = msg["result"]
                        break
                else:
                    # No 'result' encontrado, intentar último 'assistant'
                    for msg in reversed(wrapper):
                        if isinstance(msg, dict) and msg.get("type") == "assistant":
                            content = msg.get("message", {}).get("content") or []
                            for block in content if isinstance(content, list) else []:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text = block.get("text", text)
                                    break
                            break
            elif isinstance(wrapper, dict):
                text = wrapper.get("result") or proc.stdout
        except json.JSONDecodeError:
            text = proc.stdout
        m = _JSON_OUTPUT_RE.search(text)
        if not m:
            raise ValueError(f"no JSON found in output (first 200 chars): {text[:200]}")
        parsed = json.loads(m.group(0))
    except Exception as exc:
        return JudgeDecision(
            match_page_id=None,
            confidence="low",
            rationale=f"LLM error: {type(exc).__name__}: {exc}",
            analyzed_at=now,
            candidates_signature=candidates_sig,
        )

    match_pid = parsed.get("match_page_id")
    if match_pid in ("null", "None", ""):
        match_pid = None
    conf = parsed.get("confidence", "low")
    if conf not in ("high", "medium", "low"):
        conf = "low"
    alias_cand = parsed.get("alias_candidate")
    if alias_cand in ("null", "None", "", None):
        alias_cand = None
    elif isinstance(alias_cand, str):
        alias_cand = alias_cand.strip() or None
    alias_exists = bool(parsed.get("alias_exists", False))
    return JudgeDecision(
        match_page_id=match_pid,
        confidence=conf,
        rationale=parsed.get("rationale", ""),
        analyzed_at=now,
        candidates_signature=candidates_sig,
        alias_candidate=alias_cand,
        alias_exists=alias_exists,
    )


def _add_alias_to_page(page_path: Path, new_alias: str) -> bool:
    """Añade new_alias al frontmatter.aliases si no duplica (case+diacritics insensitive).

    Returns True si se modificó el archivo, False si ya existía o no se pudo añadir.
    """
    text = page_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return False
    fm = m.group(1)

    am = ALIASES_BLOCK_RE.search(fm)
    existing: list[str] = []
    if am:
        raw = am.group(1)
        for line in raw.splitlines():
            cleaned = line.strip().lstrip("-").strip().strip('"').strip("'").strip()
            if cleaned:
                existing.append(cleaned)

    new_norm = _normalize_for_match(new_alias)
    if any(_normalize_for_match(e) == new_norm for e in existing):
        return False

    new_aliases = existing + [new_alias]
    new_block = "aliases:\n" + "\n".join(f"- {a}" for a in new_aliases) + "\n"

    if am:
        # Replace existing aliases block (incluye newline final)
        new_fm = fm[:am.start()] + new_block.rstrip("\n") + "\n" + fm[am.end():]
    else:
        # Insertar tras canonical_name si existe; sino al final del fm
        cn_m = re.search(r"^canonical_name:\s*[^\n]+\n", fm, re.MULTILINE)
        if cn_m:
            insert_at = cn_m.end()
            new_fm = fm[:insert_at] + new_block + fm[insert_at:]
        else:
            new_fm = fm.rstrip() + "\n" + new_block

    new_text = text.replace(m.group(0), f"---\n{new_fm}\n---\n", 1)
    page_path.write_text(new_text, encoding="utf-8")
    return True


def run_semantic_recovery(
    corpus_root: Path,
    apply: bool = False,
    top_k: int = 5,
    min_cosine: float = 0.50,
) -> dict:
    """Pipeline completo. Devuelve stats dict.

    apply=False: solo reporta, no toca filesystem (excepto cache).
    apply=True: materializa citations + añade aliases para matches high.

    min_cosine: si el mejor candidato tiene cosine < threshold, no se invoca
    el LLM judge (claramente fuera de rango). Ahorro de cost.
    """
    print("=== Semantic Recovery — pasada 2 (LLM judge sobre top-K cosine) ===", file=sys.stderr)

    discarded = _collect_eligible_discarded()
    print(f"  Discarded eligibles (post-filter): {len(discarded)}", file=sys.stderr)

    page_lexicon = _build_page_lexicon(WIKI_ROOT)
    page_ids = list(page_lexicon.keys())
    page_canonicals = [page_lexicon[pid]["canonical_name"] for pid in page_ids]
    print(f"  Pages en wiki: {len(page_ids)}", file=sys.stderr)

    if not discarded or not page_ids:
        print("  Nada que procesar.", file=sys.stderr)
        return {"discarded_eligible": len(discarded), "pages": len(page_ids)}

    print("  Calculando embeddings (in-memory)...", file=sys.stderr)
    page_vecs = _embed_strings(page_canonicals)
    discarded_strings = [d.surface_form for d in discarded]
    discarded_vecs = _embed_strings(discarded_strings)

    top_idx, sim = _compute_top_k(discarded_vecs, page_vecs, k=top_k)

    cache = _load_cache()
    cache_hits = 0
    llm_calls = 0
    skipped_low_cosine = 0
    decisions: list[tuple[DiscardedEntry, JudgeDecision]] = []

    for i, d in enumerate(discarded):
        candidate_idx = top_idx[i].tolist()
        candidate_ids = [page_ids[j] for j in candidate_idx]
        top_score = float(sim[i, candidate_idx[0]])

        if top_score < min_cosine:
            skipped_low_cosine += 1
            continue

        candidates_sig = _candidates_signature(candidate_ids)
        cache_key = f"{d.cache_key}:{candidates_sig}"

        if cache_key in cache:
            cache_hits += 1
            decisions.append((d, JudgeDecision.from_dict(cache[cache_key])))
            continue

        candidates = [
            {
                "page_id": pid,
                "canonical_name": page_lexicon[pid]["canonical_name"],
                "page_type": page_lexicon[pid]["page_type"],
                "aliases": page_lexicon[pid].get("aliases", []),
            }
            for pid in candidate_ids
        ]
        decision = _llm_judge(d, candidates)
        cache[cache_key] = decision.to_dict()
        llm_calls += 1
        decisions.append((d, decision))

        if llm_calls % 10 == 0:
            _save_cache(cache)
            print(f"    progress: {llm_calls} LLM calls (cache_hits={cache_hits})", file=sys.stderr)

    _save_cache(cache)

    matches_high = [(d, dec) for d, dec in decisions if dec.match_page_id and dec.confidence == "high"]
    matches_medium = [(d, dec) for d, dec in decisions if dec.match_page_id and dec.confidence == "medium"]
    matches_low = [(d, dec) for d, dec in decisions if dec.match_page_id and dec.confidence == "low"]
    no_matches = [(d, dec) for d, dec in decisions if not dec.match_page_id]

    print(f"\n  Total decisions: {len(decisions)} (cache={cache_hits}, llm={llm_calls}, skipped_low_cosine={skipped_low_cosine})", file=sys.stderr)
    print(f"  matches high:    {len(matches_high)}", file=sys.stderr)
    print(f"  matches medium:  {len(matches_medium)}", file=sys.stderr)
    print(f"  matches low:     {len(matches_low)}", file=sys.stderr)
    print(f"  no_matches:      {len(no_matches)}", file=sys.stderr)

    stats = {
        "discarded_eligible": len(discarded),
        "pages": len(page_ids),
        "cache_hits": cache_hits,
        "llm_calls": llm_calls,
        "skipped_low_cosine": skipped_low_cosine,
        "matches_high": len(matches_high),
        "matches_medium": len(matches_medium),
        "matches_low": len(matches_low),
        "no_matches": len(no_matches),
        "citations_added": 0,
        "aliases_added": 0,
        "aliases_skipped_non_concept": 0,
    }

    # Audit report sample (top matches high con rationale, para revisión humana)
    print("\n  Sample matches high (top 5):", file=sys.stderr)
    for d, dec in matches_high[:5]:
        print(f"    [{dec.confidence}] {d.surface_form!r} → {dec.match_page_id}", file=sys.stderr)
        print(f"      rationale: {dec.rationale[:120]}", file=sys.stderr)

    if not apply:
        print("\n  [dry-run] no aplicado. Para aplicar: --apply", file=sys.stderr)
        return stats

    print(f"\n  Aplicando {len(matches_high)} matches high...", file=sys.stderr)
    video_paths = _resolve_video_paths(corpus_root)

    # Agrupar matches por page_id
    by_page: dict[str, list[dict]] = defaultdict(list)
    alias_candidates_by_page: dict[str, set[str]] = defaultdict(set)
    for d, dec in matches_high:
        pid = dec.match_page_id
        if pid not in page_lexicon:
            continue
        v = video_paths.get(d.video_id)
        if v is None:
            continue
        finding = {
            "video_id": d.video_id,
            "video_title": v.video_title,
            "surface_form": d.surface_form,
            "timestamp_seconds": d.timestamp_seconds,
            "quote_evidence": d.quote_evidence,
        }
        by_page[pid].append(finding)
        # Recolectar alias_candidate sólo si:
        #   - LLM lo extrajo (no null)
        #   - LLM dice que no existe ya en la page
        #   - pasa validación numérica (longitud/palabras)
        #   - aparece literalmente como word-match en el surface_form
        #     (anti-hallucination — el corpus es la fuente)
        if dec.alias_candidate and not dec.alias_exists:
            if (
                _is_concept_like(dec.alias_candidate)
                and _alias_in_surface_form(dec.alias_candidate, d.surface_form)
            ):
                alias_candidates_by_page[pid].add(dec.alias_candidate)
            else:
                stats["aliases_skipped_non_concept"] += 1

    for pid, findings in by_page.items():
        page_info = page_lexicon[pid]
        enriched = _enrich_findings_with_timestamps(findings, video_paths)
        apply_stats = _apply_findings_as_citations(pid, page_info, enriched)
        stats["citations_added"] += apply_stats.get("added", 0)

        for alias in alias_candidates_by_page[pid]:
            if _add_alias_to_page(page_info["path"], alias):
                stats["aliases_added"] += 1

    print(f"  citations added:               {stats['citations_added']}", file=sys.stderr)
    print(f"  aliases added:                 {stats['aliases_added']}", file=sys.stderr)
    print(f"  aliases skipped (validation):  {stats['aliases_skipped_non_concept']}", file=sys.stderr)
    return stats
