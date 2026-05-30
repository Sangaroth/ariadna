"""Orquesta blob → summary.md usando run_claude + validate_summary.

generate_paper_summary: PDF bytes → índice temático con markers [p.NN]. El worker
(F7) lo invoca cuando un item `paper` no trae sumario (no-bypass).
"""

from __future__ import annotations

import logging

from ariadna.summarize.pdf_extract import extract_pages, pdf_to_summary_input
from ariadna.summarize.prompts import SUMMARY_PROMPT_PAPER_ES, validate_summary
from ariadna.summarize.run_claude import run_claude as _run_claude

log = logging.getLogger(__name__)


class SummarizationError(RuntimeError):
    """El summarizer no produjo un sumario válido."""


def generate_summary(
    source_input: str,
    title: str,
    prompt_template: str,
    n_units: int,
    *,
    model: str | None = None,
    run_claude_fn=_run_claude,
    validate=True,
    **validate_kwargs,
) -> str:
    """Núcleo agnóstico: formatea el prompt, llama al LLM y valida.

    `source_input` = texto de la fuente con marcas de posición; `n_units` = nº de
    páginas/segmentos (para el prompt). Lanza SummarizationError si falla.
    """
    prompt = prompt_template.format(title=title, n_pages=n_units, text=source_input)
    out = run_claude_fn(prompt, model=model)
    if not out:
        raise SummarizationError("run_claude no devolvió contenido")
    if validate:
        issues = validate_summary(out, **validate_kwargs)
        if issues:
            raise SummarizationError(f"sumario inválido: {issues}")
    return out


def generate_paper_summary(
    pdf: bytes,
    title: str,
    *,
    model: str | None = None,
    run_claude_fn=_run_claude,
) -> str:
    """PDF (bytes) → summary.md con markers [p.NN]. Lanza SummarizationError si falla."""
    pages = extract_pages(pdf)
    if not pages:
        raise SummarizationError("PDF sin páginas extraíbles")
    source_input = pdf_to_summary_input(pages)
    return generate_summary(
        source_input, title, SUMMARY_PROMPT_PAPER_ES, n_units=len(pages),
        model=model, run_claude_fn=run_claude_fn,
        max_ordinal=len(pages),  # ninguna página citada puede exceder el total
    )
