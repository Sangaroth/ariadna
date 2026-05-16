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

## Chunk 2: SQLite global setup

> Crea `data/ariadna.db` con el schema multi-tenant completo (spec sección 4.1), en WAL mode, e migra el contenido actual de `data/wiki.db` mediante `ATTACH DATABASE` con INSERTs explícitos por tabla (spec sección 8.1 pasos 9-11). Inserta la fila `proxy` en `projects` antes que el resto (FK constraint). Termina con verificación de conteos.
>
> Importante: NO borra `data/wiki.db` en este chunk. El borrado se hace al final de la migración global cuando todo el resto del plan ha pasado, no aquí. En este chunk `data/wiki.db` queda intacto y coexiste con `data/ariadna.db`.

### Task 2.1: `scripts/init_ariadna_db.py` — crear schema + WAL

**Files:**
- Create: `scripts/init_ariadna_db.py`
- Test: `scripts/test_init_ariadna_db.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_init_ariadna_db.py
"""Verifica que init_ariadna_db crea schema completo, WAL mode, e índices."""
import sqlite3
import subprocess
from pathlib import Path


EXPECTED_TABLES = {
    "projects", "research_queue", "pages", "aliases", "relations",
    "body_wikilinks", "citations", "relation_types_canonical",
}
EXPECTED_INDEXES = {
    "idx_queue_status_type", "idx_queue_project", "idx_queue_dedup",
    "idx_pages_project", "idx_pages_type",
    "idx_aliases_alias",
    "idx_relations_to", "idx_relations_type",
    "idx_body_wikilinks_target",
    "idx_citations_source",
    "idx_reltypes_type",
}


def test_init_creates_schema_and_wal(tmp_path):
    db = tmp_path / "ariadna.db"
    result = subprocess.run(
        [".venv/bin/python", "scripts/init_ariadna_db.py", "--db", str(db)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"script failed: {result.stderr}"
    assert db.exists()

    conn = sqlite3.connect(str(db))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert EXPECTED_TABLES.issubset(tables), f"missing tables: {EXPECTED_TABLES - tables}"

    indexes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()}
    assert EXPECTED_INDEXES.issubset(indexes), f"missing indexes: {EXPECTED_INDEXES - indexes}"

    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal", f"journal_mode is {mode!r}, expected wal"

    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    # foreign_keys es conexión-local; el test verifica que el schema se puede
    # crear sin error con FK on (pragma se setea al runtime por el server/scripts).
    conn.close()


def test_init_is_idempotent(tmp_path):
    """Re-ejecutar el script no debe fallar ni duplicar schema."""
    db = tmp_path / "ariadna.db"
    for _ in range(2):
        result = subprocess.run(
            [".venv/bin/python", "scripts/init_ariadna_db.py", "--db", str(db)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"script failed: {result.stderr}"

    conn = sqlite3.connect(str(db))
    n_tables = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='projects'"
    ).fetchone()[0]
    assert n_tables == 1
    conn.close()


def test_init_unique_index_queue_dedup_partial(tmp_path):
    """El UNIQUE INDEX idx_queue_dedup debe ser partial (WHERE status IN pending/processing).
    Verificable insertando dos filas con misma (project, url) en estados terminales — no debe fallar.
    """
    db = tmp_path / "ariadna.db"
    subprocess.run(
        [".venv/bin/python", "scripts/init_ariadna_db.py", "--db", str(db)],
        check=True, capture_output=True, timeout=30,
    )
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys = OFF")  # bypass FK para este test atómico
    conn.execute(
        "INSERT INTO research_queue(request_id, project_id, source_url, source_type, status, created_at) "
        "VALUES ('r1', 'proxy', 'https://x', 'web', 'done', '2026-05-16T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO research_queue(request_id, project_id, source_url, source_type, status, created_at) "
        "VALUES ('r2', 'proxy', 'https://x', 'web', 'done', '2026-05-16T00:00:01+00:00')"
    )
    conn.commit()
    # Dos pending de la misma (project, url) SÍ debe fallar
    conn.execute(
        "INSERT INTO research_queue(request_id, project_id, source_url, source_type, status, created_at) "
        "VALUES ('r3', 'proxy', 'https://y', 'web', 'pending', '2026-05-16T00:00:02+00:00')"
    )
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO research_queue(request_id, project_id, source_url, source_type, status, created_at) "
            "VALUES ('r4', 'proxy', 'https://y', 'web', 'pending', '2026-05-16T00:00:03+00:00')"
        )
        conn.commit()
        raise AssertionError("expected UNIQUE constraint failure on duplicate pending")
    except sqlite3.IntegrityError:
        pass
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest scripts/test_init_ariadna_db.py -v
# Expected: FAIL — "No such file or directory: scripts/init_ariadna_db.py"
```

- [ ] **Step 3: Implement `scripts/init_ariadna_db.py`**

```python
#!/usr/bin/env python3
"""Crea data/ariadna.db con el schema multi-tenant completo (spec sección 4.1)
y activa journal_mode=WAL. Idempotente: re-ejecutar sobre una DB existente
es no-op (todas las CREATE TABLE/INDEX usan IF NOT EXISTS).

NO inserta filas — solo schema. El bootstrap del proyecto 'proxy' y la migración
de contenido desde data/wiki.db viven en scripts/migrate_wiki_db_to_global.py.

Uso:
    python scripts/init_ariadna_db.py                       # crea data/ariadna.db
    python scripts/init_ariadna_db.py --db /tmp/test.db     # override path (tests)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    project_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    created_at      TEXT NOT NULL,
    archived_at     TEXT,
    config_version  TEXT NOT NULL DEFAULT '1.0'
);

CREATE TABLE IF NOT EXISTS research_queue (
    request_id        TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL REFERENCES projects(project_id),
    source_url        TEXT NOT NULL,
    source_type       TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    priority          INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    picked_up_at      TEXT,
    completed_at      TEXT,
    assigned_worker   TEXT,
    retry_count       INTEGER NOT NULL DEFAULT 0,
    error_msg         TEXT,
    notes             TEXT,
    metadata          TEXT
);
CREATE INDEX IF NOT EXISTS idx_queue_status_type ON research_queue(status, source_type);
CREATE INDEX IF NOT EXISTS idx_queue_project ON research_queue(project_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_queue_dedup
    ON research_queue(project_id, source_url)
    WHERE status IN ('pending', 'processing');

CREATE TABLE IF NOT EXISTS pages (
    page_id        TEXT NOT NULL,
    project_id     TEXT NOT NULL REFERENCES projects(project_id),
    page_type      TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    domain_primary TEXT,
    file_path      TEXT NOT NULL,
    last_compiled  TEXT,
    sources_count  INTEGER,
    review_status  TEXT,
    body_md        TEXT NOT NULL,
    indexed_at     TEXT NOT NULL,
    PRIMARY KEY (project_id, page_id)
);
CREATE INDEX IF NOT EXISTS idx_pages_project ON pages(project_id);
CREATE INDEX IF NOT EXISTS idx_pages_type ON pages(project_id, page_type);

CREATE TABLE IF NOT EXISTS aliases (
    project_id  TEXT NOT NULL,
    page_id     TEXT NOT NULL,
    alias       TEXT NOT NULL,
    PRIMARY KEY (project_id, page_id, alias),
    FOREIGN KEY (project_id, page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_aliases_alias ON aliases(alias);

CREATE TABLE IF NOT EXISTS relations (
    project_id    TEXT NOT NULL,
    from_page_id  TEXT NOT NULL,
    type          TEXT NOT NULL,
    to_page_id    TEXT NOT NULL,
    note          TEXT,
    weight        TEXT,
    PRIMARY KEY (project_id, from_page_id, type, to_page_id),
    FOREIGN KEY (project_id, from_page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
    -- Intencional: NO hay FK sobre (project_id, to_page_id). Las relations pueden
    -- apuntar a páginas todavía NO compiladas: ese es el mecanismo que usa el
    -- validador para señalar "wikilinks rotos = candidatos a próximo batch".
);
CREATE INDEX IF NOT EXISTS idx_relations_to   ON relations(project_id, to_page_id);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(type);

CREATE TABLE IF NOT EXISTS body_wikilinks (
    project_id      TEXT NOT NULL,
    page_id         TEXT NOT NULL,
    target_page_id  TEXT NOT NULL,
    PRIMARY KEY (project_id, page_id, target_page_id),
    FOREIGN KEY (project_id, page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_body_wikilinks_target ON body_wikilinks(project_id, target_page_id);

CREATE TABLE IF NOT EXISTS citations (
    project_id        TEXT NOT NULL,
    page_id           TEXT NOT NULL,
    source_id         TEXT NOT NULL,
    timestamp_seconds INTEGER NOT NULL DEFAULT 0,
    title             TEXT,
    url               TEXT NOT NULL,
    PRIMARY KEY (project_id, page_id, source_id, timestamp_seconds),
    FOREIGN KEY (project_id, page_id) REFERENCES pages(project_id, page_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_citations_source ON citations(source_id);

CREATE TABLE IF NOT EXISTS relation_types_canonical (
    project_id      TEXT,
    type            TEXT NOT NULL,
    description     TEXT,
    inverse         TEXT,
    from_types_csv  TEXT,
    to_types_csv    TEXT,
    PRIMARY KEY (project_id, type)
);
CREATE INDEX IF NOT EXISTS idx_reltypes_type ON relation_types_canonical(type);
"""


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        # WAL primero (persistente en la DB, no en la conexión).
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if mode.lower() != "wal":
            raise RuntimeError(f"failed to set WAL mode (got {mode!r})")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
    print(f"ariadna.db initialized at {db_path} (WAL mode, schema v1.0)")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=Path("data/ariadna.db"))
    args = p.parse_args()
    init_db(args.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest scripts/test_init_ariadna_db.py -v
# Expected: 3 passed
```

- [ ] **Step 5: Commit**

```bash
git add scripts/init_ariadna_db.py scripts/test_init_ariadna_db.py
git commit -m "feat(migration): init_ariadna_db crea schema multi-tenant + WAL

Schema completo de spec sección 4.1 (8 tablas + índices) idempotente.
WAL mode persistido en la DB. NO inserta datos (eso vive en migrate_wiki_db_to_global).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 2.2: `scripts/migrate_wiki_db_to_global.py` — copiar contenido vía ATTACH

> Copia el contenido de `data/wiki.db` a `data/ariadna.db` mapeando cada tabla a su nueva forma (añade columna `project_id='proxy'`, renombra `citations.video_id` → `citations.source_id`). NO migra `relation_types_canonical` (se rellena en startup del MCP server desde el JSON, fuente de verdad). NO borra `data/wiki.db` (el borrado vive en chunk 9 cuando todo el plan ha pasado).

**Files:**
- Create: `scripts/migrate_wiki_db_to_global.py`
- Test: `scripts/test_migrate_wiki_db_to_global.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_migrate_wiki_db_to_global.py
"""Verifica que migrate_wiki_db_to_global.py copia todas las tablas correctamente
con project_id='proxy', renombra video_id → source_id en citations, y termina
con conteos coincidentes."""
import sqlite3
import subprocess
from pathlib import Path


def _create_old_wiki_db(path: Path) -> None:
    """Recrea un wiki.db con schema antiguo (sin project_id) y datos sintéticos
    de prueba: 2 páginas, 2 aliases, 2 relations, 2 wikilinks, 3 citations."""
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE pages (
            page_id TEXT PRIMARY KEY, page_type TEXT NOT NULL, canonical_name TEXT NOT NULL,
            domain_primary TEXT, file_path TEXT NOT NULL, last_compiled TEXT,
            sources_count INTEGER, review_status TEXT, body_md TEXT NOT NULL,
            indexed_at TEXT NOT NULL
        );
        CREATE TABLE aliases (page_id TEXT, alias TEXT, PRIMARY KEY (page_id, alias));
        CREATE TABLE relations (
            from_page_id TEXT, type TEXT, to_page_id TEXT, note TEXT, weight TEXT,
            PRIMARY KEY (from_page_id, type, to_page_id)
        );
        CREATE TABLE body_wikilinks (
            page_id TEXT, target_page_id TEXT, PRIMARY KEY (page_id, target_page_id)
        );
        CREATE TABLE citations (
            page_id TEXT, video_id TEXT, timestamp_seconds INTEGER DEFAULT 0,
            title TEXT, url TEXT NOT NULL,
            PRIMARY KEY (page_id, video_id, timestamp_seconds)
        );
        CREATE TABLE relation_types_canonical (
            type TEXT PRIMARY KEY, description TEXT, inverse TEXT,
            from_types_csv TEXT, to_types_csv TEXT
        );
        INSERT INTO pages VALUES
            ('shadow', 'concept', 'Sombra', 'jung', 'concepts/shadow.md',
             '2026-05-16T00:00:00+00:00', 5, 'reviewed', '# Sombra',
             '2026-05-16T01:00:00+00:00'),
            ('jung', 'author', 'Carl Jung', 'jung', 'authors/jung.md',
             '2026-05-16T00:00:00+00:00', 3, 'draft', '# Jung',
             '2026-05-16T01:00:01+00:00');
        INSERT INTO aliases VALUES ('shadow', 'sombra'), ('jung', 'C. Jung');
        INSERT INTO relations VALUES
            ('shadow', 'developed_by', 'jung', NULL, NULL),
            ('jung', 'developed', 'shadow', NULL, NULL);
        INSERT INTO body_wikilinks VALUES ('shadow', 'jung'), ('jung', 'shadow');
        INSERT INTO citations VALUES
            ('shadow', 'video_a', 120, 'Sombra ep 1', 'https://yt/a?t=120'),
            ('shadow', 'video_a', 300, 'Sombra ep 1', 'https://yt/a?t=300'),
            ('jung',   'video_b', 0,   'Bio Jung',    'https://yt/b');
    """)
    conn.commit()
    conn.close()


def test_migrate_copies_all_tables(tmp_path):
    old = tmp_path / "wiki.db"
    new = tmp_path / "ariadna.db"
    _create_old_wiki_db(old)
    # Init new schema first
    subprocess.run(
        [".venv/bin/python", "scripts/init_ariadna_db.py", "--db", str(new)],
        check=True, capture_output=True, timeout=30,
    )
    # Migrate
    result = subprocess.run(
        [".venv/bin/python", "scripts/migrate_wiki_db_to_global.py",
         "--source", str(old), "--target", str(new), "--project-id", "proxy"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"migrate failed: {result.stderr}"

    conn = sqlite3.connect(str(new))
    # projects row exists for 'proxy'
    rows = conn.execute("SELECT project_id, name FROM projects").fetchall()
    assert rows == [("proxy", "Proxy YouTube corpus")], rows
    # pages
    n_pages = conn.execute("SELECT COUNT(*) FROM pages WHERE project_id='proxy'").fetchone()[0]
    assert n_pages == 2
    # aliases (project_id added)
    rows = conn.execute(
        "SELECT project_id, page_id, alias FROM aliases ORDER BY page_id, alias"
    ).fetchall()
    assert rows == [("proxy", "jung", "C. Jung"), ("proxy", "shadow", "sombra")]
    # relations
    n_rel = conn.execute("SELECT COUNT(*) FROM relations WHERE project_id='proxy'").fetchone()[0]
    assert n_rel == 2
    # body_wikilinks
    n_wl = conn.execute("SELECT COUNT(*) FROM body_wikilinks WHERE project_id='proxy'").fetchone()[0]
    assert n_wl == 2
    # citations: video_id → source_id (verifica columna)
    rows = conn.execute(
        "SELECT project_id, page_id, source_id, timestamp_seconds FROM citations "
        "ORDER BY page_id, source_id, timestamp_seconds"
    ).fetchall()
    assert rows == [
        ("proxy", "jung",   "video_b", 0),
        ("proxy", "shadow", "video_a", 120),
        ("proxy", "shadow", "video_a", 300),
    ]
    # relation_types_canonical: NO se migra (queda vacío; lo rellena startup MCP)
    n_rt = conn.execute("SELECT COUNT(*) FROM relation_types_canonical").fetchone()[0]
    assert n_rt == 0
    conn.close()


def test_migrate_uses_min_indexed_at_for_created_at(tmp_path):
    """created_at del proyecto proxy debe ser MIN(indexed_at) de pages."""
    old = tmp_path / "wiki.db"
    new = tmp_path / "ariadna.db"
    _create_old_wiki_db(old)
    subprocess.run(
        [".venv/bin/python", "scripts/init_ariadna_db.py", "--db", str(new)],
        check=True, capture_output=True, timeout=30,
    )
    subprocess.run(
        [".venv/bin/python", "scripts/migrate_wiki_db_to_global.py",
         "--source", str(old), "--target", str(new), "--project-id", "proxy"],
        check=True, capture_output=True, timeout=30,
    )
    conn = sqlite3.connect(str(new))
    created_at = conn.execute(
        "SELECT created_at FROM projects WHERE project_id='proxy'"
    ).fetchone()[0]
    # MIN(indexed_at) en la fixture es 2026-05-16T01:00:00+00:00
    assert created_at == "2026-05-16T01:00:00+00:00", created_at
    conn.close()


def test_migrate_is_idempotent_via_fail_fast(tmp_path):
    """Re-ejecutar la migración sobre un target que ya tiene la fila proxy
    debe fallar con mensaje claro (no doble-INSERT silencioso)."""
    old = tmp_path / "wiki.db"
    new = tmp_path / "ariadna.db"
    _create_old_wiki_db(old)
    subprocess.run(
        [".venv/bin/python", "scripts/init_ariadna_db.py", "--db", str(new)],
        check=True, capture_output=True, timeout=30,
    )
    subprocess.run(
        [".venv/bin/python", "scripts/migrate_wiki_db_to_global.py",
         "--source", str(old), "--target", str(new), "--project-id", "proxy"],
        check=True, capture_output=True, timeout=30,
    )
    # Second run: target tiene 'proxy' ya
    result = subprocess.run(
        [".venv/bin/python", "scripts/migrate_wiki_db_to_global.py",
         "--source", str(old), "--target", str(new), "--project-id", "proxy"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "already exists" in result.stderr.lower() or "already exists" in result.stdout.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest scripts/test_migrate_wiki_db_to_global.py -v
# Expected: FAIL — "No such file or directory: scripts/migrate_wiki_db_to_global.py"
```

- [ ] **Step 3: Implement `scripts/migrate_wiki_db_to_global.py`**

```python
#!/usr/bin/env python3
"""Migra el contenido de data/wiki.db a data/ariadna.db, taggeando todas las filas
con project_id='proxy' (o el slug pasado por --project-id). Mapea citations.video_id
→ citations.source_id (rename de columna).

Asume:
- target (ariadna.db) ya tiene el schema multi-tenant aplicado (corre init_ariadna_db.py antes).
- source (wiki.db) tiene el schema antiguo (pages/aliases/relations/body_wikilinks/citations).
- target NO tiene aún la fila para project_id pasado (fail-fast si ya existe).

NO copia relation_types_canonical: se rellena en startup del MCP server desde
wiki/_meta/relation_types_core.json (fuente de verdad — ver spec sección 7.3).

NO borra data/wiki.db. El borrado del wiki.db legacy vive en Chunk 9 (post-verificación
final). Hasta ese momento ambos archivos coexisten; los scripts existentes siguen
leyendo wiki.db sin romperse.

Uso:
    python scripts/migrate_wiki_db_to_global.py \
        --source data/wiki.db --target data/ariadna.db --project-id proxy
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DEFAULT_NAME = "Proxy YouTube corpus"
PROJECT_DEFAULT_DESC = (
    "Canal YouTube de Proxy: análisis arquetípico, mitología, psicología junguiana"
)


def migrate(source: Path, target: Path, project_id: str) -> dict[str, int]:
    if not source.exists():
        raise SystemExit(f"source DB not found: {source}")
    if not target.exists():
        raise SystemExit(
            f"target DB not found: {target} "
            f"(run scripts/init_ariadna_db.py first)"
        )

    conn = sqlite3.connect(str(target))
    conn.execute("PRAGMA foreign_keys = ON")

    # Fail-fast si project_id ya existe (no queremos doble-INSERT silencioso).
    existing = conn.execute(
        "SELECT project_id FROM projects WHERE project_id=?", (project_id,)
    ).fetchone()
    if existing is not None:
        conn.close()
        raise SystemExit(
            f"project_id={project_id!r} already exists in target {target}; "
            f"refusing to re-migrate. Delete the row manually if you really want to redo."
        )

    # ATTACH source
    conn.execute(f"ATTACH DATABASE '{source}' AS old")

    # 1) Leer MIN(indexed_at) de pages para created_at del proyecto.
    min_idx = conn.execute("SELECT MIN(indexed_at) FROM old.pages").fetchone()[0]
    created_at = min_idx or datetime.now(timezone.utc).isoformat()

    # 2) INSERT proyecto (PRIMERO, las FKs lo exigen)
    conn.execute(
        "INSERT INTO projects(project_id, name, description, created_at) "
        "VALUES (?, ?, ?, ?)",
        (project_id, PROJECT_DEFAULT_NAME, PROJECT_DEFAULT_DESC, created_at),
    )

    counts: dict[str, int] = {}

    # 3) pages (project_id como primera columna)
    conn.execute(
        f"""
        INSERT INTO pages (project_id, page_id, page_type, canonical_name, domain_primary,
                           file_path, last_compiled, sources_count, review_status,
                           body_md, indexed_at)
        SELECT '{project_id}', page_id, page_type, canonical_name, domain_primary,
               file_path, last_compiled, sources_count, review_status,
               body_md, indexed_at
        FROM old.pages
        """
    )
    counts["pages"] = conn.total_changes

    # 4) aliases
    n_before = conn.total_changes
    conn.execute(
        f"INSERT INTO aliases (project_id, page_id, alias) "
        f"SELECT '{project_id}', page_id, alias FROM old.aliases"
    )
    counts["aliases"] = conn.total_changes - n_before

    # 5) relations
    n_before = conn.total_changes
    conn.execute(
        f"INSERT INTO relations (project_id, from_page_id, type, to_page_id, note, weight) "
        f"SELECT '{project_id}', from_page_id, type, to_page_id, note, weight "
        f"FROM old.relations"
    )
    counts["relations"] = conn.total_changes - n_before

    # 6) body_wikilinks
    n_before = conn.total_changes
    conn.execute(
        f"INSERT INTO body_wikilinks (project_id, page_id, target_page_id) "
        f"SELECT '{project_id}', page_id, target_page_id FROM old.body_wikilinks"
    )
    counts["body_wikilinks"] = conn.total_changes - n_before

    # 7) citations (video_id → source_id rename)
    n_before = conn.total_changes
    conn.execute(
        f"INSERT INTO citations (project_id, page_id, source_id, timestamp_seconds, title, url) "
        f"SELECT '{project_id}', page_id, video_id, timestamp_seconds, title, url "
        f"FROM old.citations"
    )
    counts["citations"] = conn.total_changes - n_before

    conn.commit()
    conn.execute("DETACH DATABASE old")
    conn.close()

    return counts


def verify_counts(source: Path, target: Path, project_id: str) -> dict[str, tuple[int, int]]:
    """Devuelve {table: (source_count, target_count_for_project)}.
    target_count debe coincidir con source_count para cada tabla migrada.
    """
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    tgt = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    out = {}
    for tbl in ("pages", "aliases", "relations", "body_wikilinks", "citations"):
        n_src = src.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        n_tgt = tgt.execute(
            f"SELECT COUNT(*) FROM {tbl} WHERE project_id=?", (project_id,)
        ).fetchone()[0]
        out[tbl] = (n_src, n_tgt)
    src.close()
    tgt.close()
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=Path("data/wiki.db"))
    p.add_argument("--target", type=Path, default=Path("data/ariadna.db"))
    p.add_argument("--project-id", default="proxy")
    p.add_argument("--verify-only", action="store_true",
                   help="Solo verificar conteos sin migrar (post-migración)")
    args = p.parse_args()

    if not args.verify_only:
        counts = migrate(args.source, args.target, args.project_id)
        print(f"migrated rows: {counts}")

    diff = verify_counts(args.source, args.target, args.project_id)
    all_match = True
    for tbl, (n_src, n_tgt) in diff.items():
        marker = "✓" if n_src == n_tgt else "✗"
        print(f"  {marker} {tbl}: source={n_src}, target={n_tgt}")
        if n_src != n_tgt:
            all_match = False
    return 0 if all_match else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest scripts/test_migrate_wiki_db_to_global.py -v
# Expected: 3 passed
```

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_wiki_db_to_global.py scripts/test_migrate_wiki_db_to_global.py
git commit -m "feat(migration): migrate_wiki_db_to_global vía ATTACH + INSERTs explícitos

Copia pages/aliases/relations/body_wikilinks/citations de wiki.db a ariadna.db
con project_id='proxy' añadido y video_id→source_id renombrado. Fail-fast si
el proyecto ya existe en target. relation_types_canonical NO se migra (lo
rellena startup MCP desde JSON).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 2.3: Ejecutar migración real y verificar conteos contra `data/wiki.db`

> Ejecutar los dos scripts contra la BBDD real y comprobar que los conteos coinciden. `data/wiki.db` no se toca; ambos archivos coexisten hasta Chunk 9.

- [ ] **Step 1: Capturar conteos pre-migración**

```bash
.venv/bin/python -c "
import sqlite3, json
c = sqlite3.connect('file:data/wiki.db?mode=ro', uri=True)
counts = {t: c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
          for t in ['pages','aliases','relations','body_wikilinks','citations']}
counts['min_indexed_at'] = c.execute('SELECT MIN(indexed_at) FROM pages').fetchone()[0]
print(json.dumps(counts, indent=2))
" | tee /tmp/wiki_db_baseline_counts.json
# Expected: {pages: ~206, aliases: ~1006, relations: ~1294, body_wikilinks: ~1611, citations: ~4066, ...}
# (conteos reales en el momento de migrar pueden divergir levemente si hubo extracción)
```

- [ ] **Step 2: Crear `data/ariadna.db` con schema**

```bash
.venv/bin/python scripts/init_ariadna_db.py --db data/ariadna.db
# Expected stdout: "ariadna.db initialized at data/ariadna.db (WAL mode, schema v1.0)"
ls -la data/ariadna.db data/ariadna.db-wal 2>/dev/null || true
```

- [ ] **Step 3: Migrar contenido**

```bash
.venv/bin/python scripts/migrate_wiki_db_to_global.py \
    --source data/wiki.db --target data/ariadna.db --project-id proxy
# Expected stdout:
#   migrated rows: {'pages': 206, 'aliases': 1006, 'relations': 1294, ...}
#   ✓ pages: source=206, target=206
#   ✓ aliases: source=1006, target=1006
#   ✓ relations: source=1294, target=1294
#   ✓ body_wikilinks: source=1611, target=1611
#   ✓ citations: source=4066, target=4066
```

- [ ] **Step 4: Verificar conteos via SQL directo**

```bash
.venv/bin/python -c "
import sqlite3
c = sqlite3.connect('file:data/ariadna.db?mode=ro', uri=True)
print('projects:', c.execute('SELECT project_id, name, created_at FROM projects').fetchall())
print('journal_mode:', c.execute('PRAGMA journal_mode').fetchone()[0])
for t in ['pages','aliases','relations','body_wikilinks','citations']:
    n = c.execute(f'SELECT COUNT(*) FROM {t} WHERE project_id=\"proxy\"').fetchone()[0]
    print(f'{t}.proxy:', n)
n_total = c.execute('SELECT COUNT(*) FROM relation_types_canonical').fetchone()[0]
assert n_total == 0, f'relation_types_canonical should be empty, got {n_total}'
print('relation_types_canonical: empty (poblado en startup MCP) ✓')
"
# Expected: projects=[(proxy, 'Proxy YouTube corpus', '...')], journal_mode=wal,
# conteos = los de baseline, relation_types_canonical empty.
```

- [ ] **Step 5: Añadir `data/ariadna.db*` a `.gitignore` y commit del cambio**

`data/wiki.db` está gitignorado (artefacto local reconstruible). `data/ariadna.db`
es del mismo tipo: derivado de `projects/<slug>/wiki/` vía `build_wiki_db.py`,
no fuente de verdad. Por simetría se gitignora también; nunca se versiona el
binario SQLite.

```bash
# Verificar que ariadna.db NO está accidentalmente tracked:
git ls-files data/ariadna.db && echo "STOP: tracked" || echo "ok: untracked"

# Añadir las entradas al .gitignore (junto a las de wiki.db):
cat >> .gitignore <<'EOF'

# ariadna.db es derivado de projects/<slug>/wiki/ (build_wiki_db.py)
data/ariadna.db
data/ariadna.db-journal
data/ariadna.db-wal
data/ariadna.db-shm
EOF

git add .gitignore
git commit -m "chore(migration): gitignore data/ariadna.db* (artefacto local derivado)

ariadna.db lo reconstruye build_wiki_db.py desde projects/<slug>/wiki/, igual
que wiki.db. No es fuente de verdad: gitignorado por simetría.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Notas:
- Si los conteos divergen entre `wiki.db` y `ariadna.db.proxy`: abortar, hacer `rm data/ariadna.db data/ariadna.db-wal data/ariadna.db-shm` y diagnosticar antes de re-ejecutar.
- `data/ariadna.db` no se commitea jamás. Si vuelves a empezar la migración desde cero, simplemente borra el archivo local y re-ejecuta init + migrate.

---
