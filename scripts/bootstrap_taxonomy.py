#!/usr/bin/env python3
"""
Bootstrap de la taxonomía canónica desde OpenAlex Topics.

Descarga el catálogo completo de Topics de OpenAlex (~4500 entradas
jerarquizadas con IDs estables) y lo persiste en
`data/vocabulary/domains_full.json`.

Uso:
    python scripts/bootstrap_taxonomy.py
    python scripts/bootstrap_taxonomy.py --output data/vocabulary/domains_full.json
    python scripts/bootstrap_taxonomy.py --resume         # reanuda si falló a mitad

Tras la descarga, el siguiente paso (manual) es curar
`data/vocabulary/domains.json` con las ~80-100 topics que aplican al
corpus. Ese subconjunto curado es la lista activa que el extractor de
wiki / chunks usa como vocabulario controlado.

Referencias:
- API: https://docs.openalex.org/api-entities/topics
- Esquema: https://docs.openalex.org/api-entities/topics/topic-object
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OPENALEX_TOPICS_URL = "https://api.openalex.org/topics"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "vocabulary" / "domains_full.json"
PER_PAGE = 200  # max permitido por OpenAlex
RATE_LIMIT_SLEEP = 0.5  # cortesía con la API gratuita


def fetch_page(page: int, mailto: str | None = None) -> dict[str, Any]:
    """Descarga una página de topics de OpenAlex.

    OpenAlex pide opcionalmente un email en query string (`mailto=`)
    para ofrecer mejor rate limit y contactar si tu uso es problemático.
    No es obligatorio.
    """
    params = {"per-page": PER_PAGE, "page": page}
    if mailto:
        params["mailto"] = mailto
    url = f"{OPENALEX_TOPICS_URL}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "ariadna-bootstrap/1.0"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_all(output: Path, mailto: str | None, resume: bool) -> list[dict[str, Any]]:
    output.parent.mkdir(parents=True, exist_ok=True)

    already: list[dict[str, Any]] = []
    start_page = 1

    if resume and output.exists():
        already = json.loads(output.read_text(encoding="utf-8"))
        print(f"Resume: {len(already)} topics ya descargados.")
        # Asume páginas completas. Si la última estaba a medias, redescarga esa.
        start_page = (len(already) // PER_PAGE) + 1
        already = already[: (start_page - 1) * PER_PAGE]
        print(f"Reanudando desde página {start_page}.")

    all_topics = list(already)
    page = start_page
    while True:
        try:
            data = fetch_page(page, mailto=mailto)
        except Exception as exc:
            print(f"ERROR en página {page}: {exc}", file=sys.stderr)
            print(f"Guardado parcial en {output} ({len(all_topics)} topics). Reintenta con --resume.", file=sys.stderr)
            output.write_text(json.dumps(all_topics, ensure_ascii=False, indent=2), encoding="utf-8")
            sys.exit(2)

        results = data.get("results", [])
        if not results:
            break

        all_topics.extend(results)
        print(f"  Página {page}: {len(results)} topics  (acumulado: {len(all_topics)})")

        # Persistir cada página por si se interrumpe
        output.write_text(json.dumps(all_topics, ensure_ascii=False, indent=2), encoding="utf-8")

        meta = data.get("meta", {})
        total_count = meta.get("count")
        if total_count and len(all_topics) >= total_count:
            break

        page += 1
        time.sleep(RATE_LIMIT_SLEEP)

    return all_topics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path de salida JSON (default: data/vocabulary/domains_full.json)")
    parser.add_argument("--mailto", type=str, default=None, help="Email para identificarse a OpenAlex (mejor rate limit). Opcional.")
    parser.add_argument("--resume", action="store_true", help="Reanuda descarga si fichero parcial existe")
    args = parser.parse_args()

    print(f"Descargando OpenAlex Topics → {args.output}")
    if args.mailto:
        print(f"Identificándose como mailto={args.mailto}")
    else:
        print("Sin --mailto: usando rate limit anónimo (más restrictivo)")

    topics = download_all(args.output, mailto=args.mailto, resume=args.resume)

    print()
    print(f"OK. Descargados {len(topics)} topics.")
    print(f"Guardado en: {args.output}")
    print()
    print("PRÓXIMOS PASOS (manuales):")
    print("  1. Inspecciona el JSON descargado")
    print("  2. Filtra a las ~80-100 topics relevantes para tu corpus")
    print("  3. Guárdalas en data/vocabulary/domains.json (lista activa)")
    print("  4. Añade extensiones proxy.contemporary.* para conceptos no académicos")
    print("  5. Esa lista es la fuente de verdad para el campo 'domain' del schema")
    print()
    print("Ver docs/TAXONOMY_PROPOSAL.md §4.5 y docs/WIKI_GENERATION.md para detalle.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
