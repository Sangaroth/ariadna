#!/usr/bin/env python3
"""Indexa las páginas wiki en la misma colección Qdrant que los chunks raw.

Estrategia: 1 vector por página, focal al concepto. El texto que se embebe es:

    canonical_name
    aliases: ...
    dominio: ...
    {primer párrafo de la primera sección H2}
    conceptos relacionados: ...

Razones (ver docs/CORPUS_COVERAGE_STRATEGY.md y diálogo de pivote):
- Embedding del cuerpo entero produce vectores difusos (manifestaciones,
  lagunas y fuentes diluyen la identidad del concepto)
- Embedding focal captura "qué es X" sin ruido. Un solo vector basta para
  validar el modo híbrido en queries reales antes de invertir en mayor
  granularidad
- Si una sección secundaria (ej. "ánima sola" dentro de anima-archetype)
  no aparece en queries esperadas, iteramos a vectores por sección con
  embedding_role='section'

El indexador es idempotente: borra todos los puntos con source_type='wiki_page'
antes de reinsertar.

Uso:
    python scripts/index_wiki_to_qdrant.py
    python scripts/index_wiki_to_qdrant.py --dry-run
    python scripts/index_wiki_to_qdrant.py --wiki-dir /path/to/wiki

IMPORTANTE: Qdrant embedded usa lock por proceso. Para usar este script con el
servidor MCP corriendo simultáneamente FALLA. Pasos: parar server (pkill -f
'ariadna.mcp_server'), ejecutar este script, reiniciar server.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ariadna.config import COLLECTION_NAME  # noqa: E402
from ariadna.embeddings import DenseEmbedder  # noqa: E402
from ariadna.storage import CorpusStore  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ariadna.wiki_index")

WIKI_DIR_DEFAULT = REPO / "wiki"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([a-z0-9][a-z0-9_-]*)(?:\|[^\]]+)?\]\]")
H1_RE = re.compile(r"^# (.+)$", re.MULTILINE)
H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
QUOTE_LINE_RE = re.compile(r"^>", re.MULTILINE)


@dataclass
class WikiPage:
    page_id: str
    page_type: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    domain: list[str] = field(default_factory=list)
    domain_primary: str | None = None
    related_concepts: list[str] = field(default_factory=list)
    related_authors: list[str] = field(default_factory=list)
    related_works: list[str] = field(default_factory=list)
    file_path: str = ""
    body: str = ""
    first_section_text: str = ""

    def embed_text(self) -> str:
        """Texto focal que se vectoriza. Captura la identidad del concepto sin diluir."""
        parts = [self.canonical_name]
        if self.aliases:
            parts.append(f"aliases: {', '.join(self.aliases)}")
        if self.domain_primary:
            parts.append(f"dominio: {self.domain_primary}")
        if self.first_section_text:
            parts.append(self.first_section_text)
        related_all = self.related_concepts + self.related_authors + self.related_works
        if related_all:
            parts.append(f"conceptos relacionados: {', '.join(related_all)}")
        return "\n\n".join(parts)

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_type": "wiki_page",
            "embedding_role": "concept",
            "page_id": self.page_id,
            "page_type": self.page_type,
            "canonical_name": self.canonical_name,
            "aliases": self.aliases,
            "domain": self.domain,
            "domain_primary": self.domain_primary,
            "related_concepts": self.related_concepts,
            "related_authors": self.related_authors,
            "related_works": self.related_works,
            "file_path": self.file_path,
            "embedded_text": self.embed_text(),
            "body": self.body,
        }


def _parse_yaml_list(fm_text: str, key: str) -> list[str]:
    """Extrae una lista YAML simple del tipo:
        key:
          - valor1
          - valor2
    Quita comillas y, si los valores son wikilinks, extrae el page_id.
    """
    pattern = rf"^{re.escape(key)}:\s*\n((?:\s*-\s*[^\n]+\n)+)"
    m = re.search(pattern, fm_text, re.MULTILINE)
    if not m:
        return []
    items: list[str] = []
    for line in m.group(1).splitlines():
        v = line.strip().lstrip("-").strip().strip('"').strip("'")
        if not v:
            continue
        wl = WIKILINK_RE.match(v)
        if wl:
            items.append(wl.group(1))
        else:
            items.append(v)
    return items


def _parse_scalar(fm_text: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*([^\n]+)$", fm_text, re.MULTILINE)
    if not m:
        return None
    val = m.group(1).strip().strip('"').strip("'")
    if val.lower() == "null" or val == "":
        return None
    return val


def _extract_first_section(body: str) -> str:
    """Devuelve el contenido de la primera sección H2 (## ...) hasta el siguiente H2 o EOF.

    Limpia las líneas blockquote (>) y de cita arrow (→) para reducir ruido del embedding.
    """
    h2_iter = list(H2_RE.finditer(body))
    if not h2_iter:
        return ""
    first = h2_iter[0]
    end = h2_iter[1].start() if len(h2_iter) > 1 else len(body)
    section_body = body[first.end():end].strip()

    cleaned: list[str] = []
    for line in section_body.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if stripped.startswith(">"):
            continue
        if stripped.startswith("→"):
            continue
        cleaned.append(stripped)
    text = "\n".join(cleaned).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > 1500:
        text = text[:1500].rsplit(" ", 1)[0] + "..."
    return text


def parse_wiki_file(md_path: Path, repo_root: Path) -> WikiPage | None:
    text = md_path.read_text(encoding="utf-8")
    fm = FRONTMATTER_RE.match(text)
    if not fm:
        log.warning("  · skip (no frontmatter): %s", md_path.relative_to(repo_root))
        return None
    fm_text = fm.group(1)
    body = text[fm.end():]

    page_id = _parse_scalar(fm_text, "page_id")
    page_type = _parse_scalar(fm_text, "page_type")
    canonical_name = _parse_scalar(fm_text, "canonical_name")
    if not page_id or not page_type or not canonical_name:
        log.warning("  · skip (incomplete frontmatter): %s", md_path.relative_to(repo_root))
        return None

    return WikiPage(
        page_id=page_id,
        page_type=page_type,
        canonical_name=canonical_name,
        aliases=_parse_yaml_list(fm_text, "aliases"),
        domain=_parse_yaml_list(fm_text, "domain"),
        domain_primary=_parse_scalar(fm_text, "domain_primary"),
        related_concepts=_parse_yaml_list(fm_text, "related_concepts"),
        related_authors=_parse_yaml_list(fm_text, "related_authors"),
        related_works=_parse_yaml_list(fm_text, "related_works"),
        file_path=str(md_path.relative_to(repo_root)),
        body=body.strip(),
        first_section_text=_extract_first_section(body),
    )


def page_id_int(page_id: str) -> int:
    """ID entero estable a partir del page_id. Distinto del namespace de chunks raw
    (chunks raw usan video_id+timestamp). Prefijamos 'wiki:' para asegurar unicidad."""
    return int(hashlib.sha256(f"wiki:{page_id}".encode()).hexdigest()[:15], 16)


def collect_pages(wiki_dir: Path, repo_root: Path) -> list[WikiPage]:
    pages: list[WikiPage] = []
    for md in sorted(wiki_dir.rglob("*.md")):
        if md.name == "README.md":
            continue
        page = parse_wiki_file(md, repo_root)
        if page:
            pages.append(page)
    return pages


def index_wiki(
    wiki_dir: Path,
    repo_root: Path,
    dry_run: bool = False,
) -> None:
    log.info("Wiki dir: %s", wiki_dir)
    pages = collect_pages(wiki_dir, repo_root)
    log.info("Páginas encontradas: %d", len(pages))
    if not pages:
        log.warning("Nada que indexar.")
        return

    for p in pages:
        log.info(
            "  • %s (%s, %s) — embed_text=%d chars",
            p.page_id,
            p.page_type,
            p.domain_primary or "?",
            len(p.embed_text()),
        )

    if dry_run:
        log.info("Dry-run: no se indexa. Mostrando muestra de embed_text:")
        log.info("\n%s", pages[0].embed_text())
        return

    log.info("Cargando embedder BGE-M3...")
    embedder = DenseEmbedder()

    log.info("Calculando %d embeddings...", len(pages))
    texts = [p.embed_text() for p in pages]
    vectors = embedder.embed(texts, batch_size=16)
    log.info("Vectores listos: shape=%s", vectors.shape)

    store = CorpusStore(vector_dim=vectors.shape[1])
    store.ensure_collection(recreate=False)

    n_deleted = store.delete_by_filter({"source_type": "wiki_page"})
    if n_deleted > 0:
        log.info("Borrados %d wiki_pages antiguos (idempotencia)", n_deleted)

    ids = [page_id_int(p.page_id) for p in pages]
    payloads = [p.to_payload() for p in pages]
    store.upsert_batch(ids, vectors, payloads)
    log.info("Insertados %d wiki_pages. Total en colección: %d", len(pages), store.count())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Indexa páginas wiki en Qdrant (1 vector focal por página)."
    )
    parser.add_argument(
        "--wiki-dir",
        type=Path,
        default=WIKI_DIR_DEFAULT,
        help=f"Ruta a wiki/ (default: {WIKI_DIR_DEFAULT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo parsea y muestra qué se indexaría",
    )
    args = parser.parse_args()

    if not args.wiki_dir.exists():
        log.error("Wiki dir no existe: %s", args.wiki_dir)
        return 1

    index_wiki(wiki_dir=args.wiki_dir, repo_root=REPO, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
