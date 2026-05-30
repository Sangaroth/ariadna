"""Adquisición de fuentes externas (PDFs de papers) tras una interfaz conmutable.

Decisión MVP (plan §F): el worker no enlaza una librería de scraping; lanza
`claude -p` con el MCP `paper-search` (`download_paper`, `get_paper_by_doi`) y parsea
una respuesta JSON mínima. `PaperAcquirer` es la interfaz; `ClaudePaperAcquirer` la
implementación CLI; `MockPaperAcquirer` para tests. Migrar a librería directa = otra
implementación de la interfaz, sin tocar el worker.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ariadna.summarize.run_claude import run_claude as _run_claude

log = logging.getLogger(__name__)

# Orden de fallback de plataformas para descargar por DOI (scihub primero, arxiv después).
DEFAULT_PLATFORMS = ["scihub", "arxiv"]


@dataclass
class AcquiredPaper:
    path: Path           # PDF descargado en disco
    platform: str        # de dónde salió
    doi: str


class PaperAcquirer(Protocol):
    def metadata(self, doi: str) -> dict: ...
    def download(self, doi: str, dest_dir: Path, platforms: list[str] | None = None) -> AcquiredPaper: ...


def _extract_json(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise ValueError("respuesta sin JSON")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("JSON no balanceado")


class ClaudePaperAcquirer:
    """Adquiere papers lanzando `claude -p` con el MCP paper-search.

    Best-effort: la robustez real se valida en F8 (depende de scihub/arxiv + config
    MCP del CLI). Cada método pide a Claude que use las tools y responda SOLO un JSON.
    """

    def __init__(self, allowed_tools: str = "mcp__paper-search__*", model: str | None = None,
                 run_claude_fn=_run_claude):
        self.allowed_tools = allowed_tools
        self.model = model
        self._run = run_claude_fn

    def _ask_json(self, instruction: str) -> dict:
        # run_claude no expone --allowedTools; lo embebemos en el prompt y confiamos en
        # la config MCP heredada del CLI. (F8: si hace falta, ampliar run_claude con flags.)
        out = self._run(instruction, model=self.model)
        if not out:
            raise RuntimeError("claude -p sin respuesta (¿paper-search MCP disponible?)")
        return _extract_json(out)

    def metadata(self, doi: str) -> dict:
        instr = (
            f"Usa la tool mcp__paper-search__get_paper_by_doi con doi='{doi}' platform='all'. "
            "Responde SOLO un objeto JSON con los campos que encuentres: "
            '{"title": "...", "authors": "...", "year": 0, "journal": "...", "abstract": "..."}'
        )
        try:
            return self._ask_json(instr)
        except Exception as e:  # noqa: BLE001
            log.warning("metadata(%s) falló: %s", doi, e)
            return {}

    def download(self, doi: str, dest_dir: Path, platforms: list[str] | None = None) -> AcquiredPaper:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        plats = platforms or DEFAULT_PLATFORMS
        instr = (
            f"Descarga el PDF del paper con DOI '{doi}'. Usa la tool "
            f"mcp__paper-search__download_paper con paperId='{doi}', savePath='{dest_dir}', "
            f"probando platform en este orden hasta que una funcione: {plats}. "
            'Cuando lo tengas, responde SOLO un JSON: '
            '{"path": "<ruta absoluta del PDF guardado>", "platform": "<plataforma>"} '
            'o {"error": "no se pudo descargar"}.'
        )
        data = self._ask_json(instr)
        if data.get("error") or not data.get("path"):
            raise RuntimeError(f"download fallido para {doi}: {data.get('error', 'sin path')}")
        path = Path(data["path"])
        if not path.exists():
            # A veces el modelo reporta un nombre relativo: localiza un PDF nuevo en dest_dir.
            cands = sorted(dest_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not cands:
                raise RuntimeError(f"PDF no encontrado tras download de {doi} (reportado: {path})")
            path = cands[0]
        return AcquiredPaper(path=path, platform=data.get("platform", "?"), doi=doi)


class MockPaperAcquirer:
    """Acquirer de test: escribe un PDF fijo y devuelve metadata estática."""

    def __init__(self, pdf_bytes: bytes, meta: dict | None = None):
        self.pdf_bytes = pdf_bytes
        self.meta = meta or {"title": "Mock Paper"}

    def metadata(self, doi: str) -> dict:
        return dict(self.meta)

    def download(self, doi: str, dest_dir: Path, platforms: list[str] | None = None) -> AcquiredPaper:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.-]", "_", doi)
        path = dest_dir / f"{safe}.pdf"
        path.write_bytes(self.pdf_bytes)
        return AcquiredPaper(path=path, platform="mock", doi=doi)
