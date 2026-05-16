# Multi-project Ariadna + research queue — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrar Ariadna de single-tenant (corpus Proxy implícito) a multi-tenant (Project como unidad atómica con scope + wiki + cola), añadir cola SQLite de ingesta y las tools MCP para gestionarla — sin workers todavía.

**Architecture:** Single Qdrant collection con `project_id` en payload; una sola SQLite `data/ariadna.db` con todo el estado relacional; filesystem `projects/<slug>/{_meta,wiki}/` separado por proyecto; recursos editoriales globales (`wiki/_meta/*_default.*`) con override per-proyecto opcional. MCP gana tools write para crear proyectos y añadir items a cola; **no procesa** la cola (workers son scope de specs futuras).

**Tech Stack:** Python 3.13, SQLite (WAL mode), Qdrant embedded, FastMCP, BGE-M3 (sin cambios), pyyaml.

**Spec:** [docs/superpowers/specs/2026-05-16-multi-project-and-research-queue-design.md](../specs/2026-05-16-multi-project-and-research-queue-design.md)

---

## Pre-flight check (executed before Chunk 1)

Antes de tocar nada, verificar el entorno está listo. Estos checks se ejecutan **a mano** una vez al inicio; no son tasks del plan.

```bash
# 1. Sesión de extracción parada — la migración no puede convivir con el run
pgrep -af "scripts/extract_video_themes" && echo "STOP: hay run activo" || echo "ok: sin run"
# Si hay run activo: esperar a que cierre su sesión actual o killearlo limpiamente
# (los JSONs per-video escritos no se pierden; --resume continuará después)

# 2. MCP server parado — el indexador y la migración cogen lock Qdrant
pgrep -af "ariadna.mcp_server" && echo "STOP: server activo" || echo "ok: server parado"
pkill -f "ariadna.mcp_server" 2>/dev/null
ss -tlnp 2>/dev/null | grep 8765 && echo "STOP: puerto ocupado" || echo "ok: puerto libre"

# 3. Working tree git limpio
git status --short
# Si hay cambios sin commitear: decidir caso por caso (commit o stash)

# 4. Branch dedicada para esta migración (push se hace tras el primer commit del Chunk 1)
git checkout -b feat/multi-project-migration

# 5. Backup defensivo de wiki/ (no versionado; está en .gitignore tras la migración)
cp -r wiki/ wiki.backup.$(date +%Y%m%d_%H%M%S)/

# 6. Verificar que data/wiki.db existe y es válido
.venv/bin/python -c "import sqlite3; c=sqlite3.connect('data/wiki.db'); print(c.execute('SELECT COUNT(*) FROM pages').fetchone())"

# 7. Sanity: source_type es consultable en payload Qdrant (asumido por baseline capture)
.venv/bin/python -c "
from ariadna.storage import CorpusStore
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
s = CorpusStore()
n = s.client.count(collection_name=s.collection_name, count_filter=Filter(must=[FieldCondition(key='source_type', match=MatchValue(value='wiki_page'))])).count
print(f'wiki_pages with source_type tag: {n}')
# Expected: > 0 (al menos 183 tras reindex previo). Si 0, los wiki_pages no tienen source_type tag
# y baseline capture devolverá total_wiki_pages_qdrant=0.
"
```

Solo cuando los 6 checks pasan, continúa con Chunk 1.

---

## Chunk 1: Pre-migration tooling

> Scripts auxiliares que se necesitan ANTES de tocar el filesystem: captura del baseline pre-migración (para comparación funcional post-migración) + esqueletos de los scripts de verificación que se llenan en chunks posteriores.

### Task 1.1: Crear `scripts/capture_baseline.py`

**Files:**
- Create: `scripts/capture_baseline.py`
- Test: `scripts/test_capture_baseline.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_capture_baseline.py
"""Smoke test: capture_baseline produce un JSON con shape esperado."""
import json
import subprocess
from pathlib import Path

def test_capture_baseline_runs_and_produces_json(tmp_path):
    """Ejecuta el script y verifica que el JSON resultante tiene la estructura esperada."""
    out_file = tmp_path / "baseline.json"
    result = subprocess.run(
        [".venv/bin/python", "scripts/capture_baseline.py", "--out", str(out_file)],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"script failed: {result.stderr}"
    assert out_file.exists()

    data = json.loads(out_file.read_text())
    assert "queries" in data
    assert "captured_at" in data
    assert "total_chunks_qdrant" in data
    assert "total_wiki_pages_qdrant" in data
    assert len(data["queries"]) == 10  # 10 queries canónicas
    for q in data["queries"]:
        assert "query" in q
        assert "raw_chunk_ids" in q  # lista de chunk_id_int
        assert "wiki_page_ids" in q
        assert "raw_top_score" in q
        assert "wiki_top_score" in q
        assert "mode_recommended" in q
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest scripts/test_capture_baseline.py -v
# Expected: FAIL — "No such file or directory: scripts/capture_baseline.py"
```

- [ ] **Step 3: Implement `scripts/capture_baseline.py`**

```python
#!/usr/bin/env python3
"""Captura el estado funcional pre-migración: ejecuta N queries canónicas
contra el corpus actual y serializa los resultados a un JSON. Permite
comparación determinista post-migración para verificar que el sistema sigue
funcionando idénticamente desde la perspectiva del agente.

Ver spec sección 9 — Fase 1 verification criteria.

Uso:
    python scripts/capture_baseline.py --out data/baseline_pre_migration.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# 10 queries que cubren los tres lanes (wiki_dominant, balanced, raw_with_warning)
# y los 5 pilares editoriales de Proxy. Si la migración no preserva resultados
# en estas queries, algo se rompió.
CANONICAL_QUERIES: list[str] = [
    "sombra junguiana",
    "mito polar",
    "Tolkien",
    "hieros gamos",
    "anima archetype",
    "consumismo crítica",
    "individuation jung",
    "Pinocho análisis arquetípico",
    "viaje del héroe",
    "psicología cognitiva",
]


def capture(out_path: Path) -> None:
    from ariadna.search import Searcher
    from ariadna.storage import CorpusStore

    store = CorpusStore()
    searcher = Searcher()

    total_chunks = store.client.count(collection_name=store.collection_name).count
    # Aproximación: wiki_pages son los que tienen source_type='wiki_page'
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue
    wiki_count = store.client.count(
        collection_name=store.collection_name,
        count_filter=Filter(must=[FieldCondition(key="source_type", match=MatchValue(value="wiki_page"))]),
    ).count

    queries_data = []
    for q in CANONICAL_QUERIES:
        result = searcher.search_hybrid(q, top_k_raw=5, top_k_wiki=2)
        raw_chunks = result.get("raw_chunks", [])
        wiki_pages = result.get("wiki_pages", [])
        meta = result.get("retrieval_metadata", {})

        queries_data.append({
            "query": q,
            "raw_chunk_ids": [c.get("chunk_id") if isinstance(c, dict) else c.chunk_id
                              for c in raw_chunks if c],
            "wiki_page_ids": [w.get("page_id") if isinstance(w, dict) else w.page_id
                              for w in wiki_pages if w],
            "raw_top_score": float(raw_chunks[0]["score"] if raw_chunks and isinstance(raw_chunks[0], dict)
                                   else (raw_chunks[0].score if raw_chunks else 0.0)),
            "wiki_top_score": float(wiki_pages[0]["score"] if wiki_pages and isinstance(wiki_pages[0], dict)
                                    else (wiki_pages[0].score if wiki_pages else 0.0)),
            "mode_recommended": meta.get("mode_recommended"),
        })

    baseline = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "total_chunks_qdrant": total_chunks,
        "total_wiki_pages_qdrant": wiki_count,
        "queries": queries_data,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2))
    print(f"baseline written: {out_path} ({total_chunks} total chunks, {len(queries_data)} queries)")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("data/baseline_pre_migration.json"))
    args = p.parse_args()
    capture(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest scripts/test_capture_baseline.py -v
# Expected: PASS
```

- [ ] **Step 5: Execute the baseline capture (this generates the file we'll diff against later)**

```bash
.venv/bin/python scripts/capture_baseline.py --out data/baseline_pre_migration.json
# Expected stdout: "baseline written: data/baseline_pre_migration.json (~6442 total chunks, 10 queries)"
# Nota: el conteo exacto depende del momento de ejecución (run de extracción
# puede haber añadido pages). Ronda 6259 raw + 183-220 wiki ≈ 6442-6479.
```

Verify:
```bash
ls -la data/baseline_pre_migration.json
.venv/bin/python -c "import json; d=json.load(open('data/baseline_pre_migration.json')); print(f'queries: {len(d[\"queries\"])}, chunks: {d[\"total_chunks_qdrant\"]}')"
# Expected: queries: 10, chunks: ~6442 (rango aceptable ±100)
```

- [ ] **Step 6: Commit**

```bash
git add scripts/capture_baseline.py scripts/test_capture_baseline.py data/baseline_pre_migration.json
git commit -m "feat(migration): script + baseline capture pre-migración

10 queries canónicas cubriendo los 3 lanes y 5 pilares. Permite diff
funcional determinista post-migración.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 1.2: Skeleton `scripts/verify_phase1.py`

> Verificador post-migración Fase 1. Stub ahora, se completa en Chunk 9 con las assertions reales una vez que conocemos los paths finales. **NO se ejecuta en CI desde este chunk** — solo se commitea el esqueleto.

**Files:**
- Create: `scripts/verify_phase1.py`

- [ ] **Step 1: Create skeleton with all check function signatures**

```python
#!/usr/bin/env python3
"""Verifica criterios de éxito Fase 1 (multi-tenancy migration).
Ver spec sección 9.

Exit 0 si todos los checks pasan; exit 1 con detalle si alguno falla.
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


def check_functional_equivalence() -> CheckResult:
    """Re-ejecuta las 10 queries canónicas y compara contra baseline.
    Tolerancia ±0.01 en cosine scores; mismo set de chunk_ids en top-5.
    """
    # Implementado en Chunk 9
    raise NotImplementedError("filled in Chunk 9 task 9.1")


def check_filter_by_project() -> CheckResult:
    """search_corpus(query, project='proxy') == search_corpus(query). Todos los puntos son proxy."""
    raise NotImplementedError("filled in Chunk 9 task 9.1")


def check_nonexistent_project() -> CheckResult:
    """search_corpus(query, project='nope') devuelve PROJECT_NOT_FOUND."""
    raise NotImplementedError("filled in Chunk 9 task 9.1")


def check_get_wiki_page_equiv() -> CheckResult:
    """get_wiki_page con/sin project devuelve mismo body_md."""
    raise NotImplementedError("filled in Chunk 9 task 9.1")


def check_test_hybrid_passes() -> CheckResult:
    """scripts/test_hybrid.py exit 0 (5/5 checks verde)."""
    raise NotImplementedError("filled in Chunk 9 task 9.1")


def check_sqlite_counts() -> CheckResult:
    """projects table tiene 1 fila (proxy); pages count >= baseline."""
    raise NotImplementedError("filled in Chunk 9 task 9.1")


def check_qdrant_all_tagged() -> CheckResult:
    """Todos los puntos Qdrant tienen project_id en payload."""
    raise NotImplementedError("filled in Chunk 9 task 9.1")


def check_global_resources() -> CheckResult:
    """wiki/_meta/relation_types_core.json existe con 30 tipos; 4 *_default.* existen."""
    raise NotImplementedError("filled in Chunk 9 task 9.1")


def check_run_can_resume() -> CheckResult:
    """extract_video_themes --resume pilot_sonnet_20260509 --project=proxy --dry-run exit 0."""
    raise NotImplementedError("filled in Chunk 9 task 9.1")


def check_build_wiki_db_scoped() -> CheckResult:
    """build_wiki_db.py --project=proxy completes <5s, produces same relation count as baseline."""
    raise NotImplementedError("filled in Chunk 9 task 9.1")


def check_validator() -> CheckResult:
    """validate_wiki_relations.py --project=proxy exit 0."""
    raise NotImplementedError("filled in Chunk 9 task 9.1")


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
]


def main() -> int:
    print(f"Verifying Phase 1 — {len(CHECKS)} checks\n")
    results: list[CheckResult] = []
    for check in CHECKS:
        try:
            r = check()
        except NotImplementedError as e:
            r = CheckResult(check.__name__, False, f"NOT IMPLEMENTED: {e}")
        except Exception as e:
            r = CheckResult(check.__name__, False, f"EXCEPTION: {e}")
        marker = "✓" if r.passed else "✗"
        print(f"  {marker} {r.name}{': ' + r.details if r.details else ''}")
        results.append(r)
    failed = [r for r in results if not r.passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify script imports and runs (even with NotImplementedError stubs)**

```bash
.venv/bin/python scripts/verify_phase1.py
# Expected exit: 1
# Expected output: 11 lines starting "✗ check_<name>: NOT IMPLEMENTED: filled in Chunk 9 task 9.1"
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_phase1.py
git commit -m "feat(migration): scaffold verify_phase1 con todos los checks como stubs

Stubs serán completados en Chunk 9 con assertions reales una vez los
paths post-migración son conocidos.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 1.3: Skeleton `scripts/verify_phase2.py`

> Verificador Fase 2 (tools MCP de cola). Stub ahora, completado tras chunks 6-8. **NO se ejecuta en CI desde este chunk** — solo se commitea el esqueleto.

**Files:**
- Create: `scripts/verify_phase2.py`

- [ ] **Step 1: Create skeleton**

```python
#!/usr/bin/env python3
"""Verifica criterios de éxito Fase 2 (MCP tools nuevas de cola).
Ver spec sección 9.

Asume MCP server vivo en localhost:8765 — tests via HTTP MCP protocol.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ARIADNA_DB = Path("data/ariadna.db")
MCP_URL = "http://127.0.0.1:8765/mcp"


class CheckResult:
    def __init__(self, name: str, passed: bool, details: str = ""):
        self.name = name
        self.passed = passed
        self.details = details


# Cada uno de los checks de la spec sección 9 Fase 2 será una función aquí.
# Se rellenan en Chunk 9 task 9.2.

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
]


def main() -> int:
    print(f"Verifying Phase 2 — {len(CHECKS)} checks\n")
    results = []
    for check in CHECKS:
        try:
            r = check()
        except NotImplementedError:
            r = CheckResult(check.__name__, False, "NOT IMPLEMENTED")
        except Exception as e:
            r = CheckResult(check.__name__, False, f"EXCEPTION: {e}")
        marker = "✓" if r.passed else "✗"
        print(f"  {marker} {r.name}{': ' + r.details if r.details else ''}")
        results.append(r)
    failed = [r for r in results if not r.passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify it runs**

```bash
.venv/bin/python scripts/verify_phase2.py
# Expected exit: 1
# Expected: 21 lines starting "✗ check_<name>: NOT IMPLEMENTED"
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_phase2.py
git commit -m "feat(migration): scaffold verify_phase2 con stubs de los 21 checks

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---
