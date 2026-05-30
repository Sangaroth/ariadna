#!/usr/bin/env python3
"""Verifica criterios de éxito Fase 2 (MCP tools nuevas de cola + cross-project).
Ver spec sección 9.

Asume MCP server vivo — tests vía protocolo MCP HTTP. El puerto por defecto de
config.py es 8080 (run_server.sh lo override a 8765); ajustar MCP_URL si procede.

Los stubs se rellenan tras implementar las tools (Fase 5 del plan universal).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ARIADNA_DB = Path("data/ariadna.db")
MCP_URL = "http://127.0.0.1:8080/mcp"


class CheckResult:
    def __init__(self, name: str, passed: bool, details: str = ""):
        self.name = name
        self.passed = passed
        self.details = details


# Cada uno de los checks de la spec sección 9 Fase 2 será una función aquí.
# Se rellenan en la fase de verificación de las tools.

def check_create_project_basic() -> CheckResult: raise NotImplementedError
def check_create_project_duplicate() -> CheckResult: raise NotImplementedError
def check_create_project_invalid_slug() -> CheckResult: raise NotImplementedError
def check_create_project_incompatible_options() -> CheckResult: raise NotImplementedError
def check_create_project_seed_from_templates() -> CheckResult: raise NotImplementedError
def check_create_project_inherit_from() -> CheckResult: raise NotImplementedError
def check_add_youtube_url() -> CheckResult: raise NotImplementedError
def check_add_arxiv_url() -> CheckResult: raise NotImplementedError
def check_add_pdf_url() -> CheckResult: raise NotImplementedError
def check_add_web_url() -> CheckResult: raise NotImplementedError
def check_add_unknown_url() -> CheckResult: raise NotImplementedError
def check_add_duplicate() -> CheckResult: raise NotImplementedError
def check_add_explicit_source_type_respected() -> CheckResult: raise NotImplementedError
def check_list_queue_filtered() -> CheckResult: raise NotImplementedError
def check_list_queue_cross_all() -> CheckResult: raise NotImplementedError
def check_list_queue_invalid_status() -> CheckResult: raise NotImplementedError
def check_cancel_pending() -> CheckResult: raise NotImplementedError
def check_cancel_already_cancelled() -> CheckResult: raise NotImplementedError
def check_cancel_not_found() -> CheckResult: raise NotImplementedError
def check_list_projects_counts() -> CheckResult: raise NotImplementedError
def check_obsolete_tools_removed() -> CheckResult: raise NotImplementedError
# Cross-project queries (parámetro project: str | list[str] | None)
def check_search_project_list() -> CheckResult: raise NotImplementedError
def check_search_project_provenance() -> CheckResult: raise NotImplementedError


CHECKS = [
    check_create_project_basic,
    check_create_project_duplicate,
    check_create_project_invalid_slug,
    check_create_project_incompatible_options,
    check_create_project_seed_from_templates,
    check_create_project_inherit_from,
    check_add_youtube_url,
    check_add_arxiv_url,
    check_add_pdf_url,
    check_add_web_url,
    check_add_unknown_url,
    check_add_duplicate,
    check_add_explicit_source_type_respected,
    check_list_queue_filtered,
    check_list_queue_cross_all,
    check_list_queue_invalid_status,
    check_cancel_pending,
    check_cancel_already_cancelled,
    check_cancel_not_found,
    check_list_projects_counts,
    check_obsolete_tools_removed,
    check_search_project_list,
    check_search_project_provenance,
]


def main() -> int:
    print(f"Verifying Phase 2 — {len(CHECKS)} checks\n")
    results = []
    for check in CHECKS:
        try:
            r = check()
        except NotImplementedError:
            r = CheckResult(check.__name__, False, "NOT IMPLEMENTED")
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
