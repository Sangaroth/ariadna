"""Summarizer nativo de Ariadna: convierte una fuente sin sumario (paper PDF, web…)
en un summary.md con markers de posición, listo para extract_themes.

Diseño (plan §D): porta el PATRÓN de ProxySummaries (run_claude vía `claude -p`,
prompt + validate_summary), NO el repo. El summarizer es por-fuente; el paso es
SALTABLE en el worker cuando la fuente ya trae sumario (bypass bring-your-own-summary,
p.ej. ProxySummaries para el canal proxy). YouTube-nativo queda como seam diferido.

    from ariadna.summarize import generate_paper_summary
    summary_md = generate_paper_summary(pdf_bytes, title="...")
"""

from __future__ import annotations

from ariadna.summarize.generate import generate_paper_summary, generate_summary
from ariadna.summarize.pdf_extract import extract_pages, pdf_to_summary_input
from ariadna.summarize.prompts import SUMMARY_PROMPT_PAPER_ES, validate_summary
from ariadna.summarize.run_claude import run_claude

__all__ = [
    "generate_paper_summary",
    "generate_summary",
    "extract_pages",
    "pdf_to_summary_input",
    "SUMMARY_PROMPT_PAPER_ES",
    "validate_summary",
    "run_claude",
]
