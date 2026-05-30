#!/usr/bin/env python3
"""Verifica criterios de éxito Fase 1 (migración multi-tenancy + modelo universal).
Ver spec sección 9 y el plan de modelo universal (docs/.../plans).

Exit 0 si todos los checks pasan; exit 1 con detalle si alguno falla.

Los stubs se rellenan en la fase de verificación final, una vez los paths
post-migración y el schema de data/ariadna.db son definitivos.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

BASELINE_PATH = Path("data/baseline_pre_migration.json")
ARIADNA_DB = Path("data/ariadna.db")


class CheckResult:
    def __init__(self, name: str, passed: bool, details: str = ""):
        self.name = name
        self.passed = passed
        self.details = details


# --- Equivalencia funcional (red de seguridad: Proxy responde idéntico) ------

def check_functional_equivalence() -> CheckResult:
    """Re-ejecuta las 10 queries canónicas (mismo MCP) y compara contra baseline.
    Como la migración usa set_payload in-place (sin re-embed), el conjunto de
    raw_chunk_ids (youtube_url) por query debe ser idéntico y los scores deben
    coincidir dentro de ±0.01; ningún mode_recommended debe cambiar de lane.
    """
    raise NotImplementedError("filled in final verification")


def check_filter_by_project() -> CheckResult:
    """search_corpus(query, project='proxy') == search_corpus(query). Todos los puntos son proxy."""
    raise NotImplementedError("filled in final verification")


def check_nonexistent_project() -> CheckResult:
    """search_corpus(query, project='nope') devuelve PROJECT_NOT_FOUND."""
    raise NotImplementedError("filled in final verification")


def check_get_wiki_page_equiv() -> CheckResult:
    """get_wiki_page con/sin project devuelve mismo body_md."""
    raise NotImplementedError("filled in final verification")


def check_test_hybrid_passes() -> CheckResult:
    """scripts/test_hybrid.py exit 0 (checks verde)."""
    raise NotImplementedError("filled in final verification")


# --- Integridad del schema unificado ----------------------------------------

def check_sqlite_counts() -> CheckResult:
    """projects table tiene 1 fila (proxy); pages count >= baseline (pre-migración wiki.db)."""
    raise NotImplementedError("filled in final verification")


def check_qdrant_all_tagged() -> CheckResult:
    """Todos los puntos Qdrant tienen project_id en payload."""
    raise NotImplementedError("filled in final verification")


def check_global_resources() -> CheckResult:
    """wiki/_meta/relation_types_core.json existe con 30 tipos; 4 *_default.* existen."""
    raise NotImplementedError("filled in final verification")


def check_run_can_resume() -> CheckResult:
    """extract_themes --resume pilot_sonnet_20260509 --project=proxy --dry-run exit 0."""
    raise NotImplementedError("filled in final verification")


def check_build_wiki_db_scoped() -> CheckResult:
    """build_wiki_db.py --project=proxy completes <5s, produces same relation count as baseline."""
    raise NotImplementedError("filled in final verification")


def check_validator() -> CheckResult:
    """validate_wiki_relations.py --project=proxy exit 0."""
    raise NotImplementedError("filled in final verification")


# --- Modelo universal de referencias (TAXONOMY completo) ---------------------

def check_sources_populated() -> CheckResult:
    """Tabla `sources` poblada: 1 fila youtube_video por vídeo de Proxy (~288);
    `source_projects` mapea cada una a project_id='proxy'."""
    raise NotImplementedError("filled in final verification")


def check_authors_populated() -> CheckResult:
    """Tabla `authors` (per-project) poblada desde frontmatter de wiki/authors/;
    author_sources con role subject_of derivado de citations."""
    raise NotImplementedError("filled in final verification")


def check_domains_assigned() -> CheckResult:
    """Ningún raw chunk queda sin `domain_primary` OpenAlex; las 5 categorías
    legacy se mapearon (determinista + herencia wiki). page_domains poblado."""
    raise NotImplementedError("filled in final verification")


def check_citations_generalized() -> CheckResult:
    """citations migrada a (source_id, position, position_url, cite_markdown);
    los source_id youtube:<id> resuelven contra `sources`."""
    raise NotImplementedError("filled in final verification")


def check_cross_project_isolation() -> CheckResult:
    """search_corpus(project=['proxy']) no devuelve nada de otros proyectos;
    project como list[str] funciona (filtro OR-of); cada hit lleva su project_id."""
    raise NotImplementedError("filled in final verification")


CHECKS = [
    check_functional_equivalence,
    check_filter_by_project,
    check_nonexistent_project,
    check_get_wiki_page_equiv,
    check_test_hybrid_passes,
    check_sqlite_counts,
    check_qdrant_all_tagged,
    check_global_resources,
    check_run_can_resume,
    check_build_wiki_db_scoped,
    check_validator,
    check_sources_populated,
    check_authors_populated,
    check_domains_assigned,
    check_citations_generalized,
    check_cross_project_isolation,
]


def main() -> int:
    print(f"Verifying Phase 1 — {len(CHECKS)} checks\n")
    results: list[CheckResult] = []
    for check in CHECKS:
        try:
            r = check()
        except NotImplementedError as e:
            r = CheckResult(check.__name__, False, f"NOT IMPLEMENTED: {e}")
        except Exception as e:  # noqa: BLE001
            r = CheckResult(check.__name__, False, f"EXCEPTION: {e}")
        marker = "✓" if r.passed else "✗"
        print(f"  {marker} {r.name}{': ' + r.details if r.details else ''}")
        results.append(r)
    failed = [r for r in results if not r.passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
