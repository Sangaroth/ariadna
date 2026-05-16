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

## Chunk 3: Filesystem refactor

> Refactor estructural del filesystem para mover el corpus Proxy a `projects/proxy/`, dejando `wiki/_meta/` como home de los recursos globales (defaults editables + `relation_types_core.json`). Casi todo son `git mv`: poco código nuevo, mucha cirugía de paths. NO modifica `scripts/extract_video_themes.py` ni ningún path hardcoded en Python (eso es Chunk 4); aquí solo se mueven archivos y se crean placeholders.
>
> **Pre-condición:** Chunk 2 completado (`data/ariadna.db` existe con el contenido migrado). El refactor de filesystem no toca SQLite ni Qdrant.
>
> **Por qué no es TDD:** la mayoría de las tasks son `git mv` cuyo "test" es la verificación post-hoc del filesystem. Para esas tasks se usa el patrón "ejecutar comando → verificar resultado con check explícito → commit". La task 3.5 (extracción de prompts a markdown) SÍ tiene test: byte-equality con el constante Python original.

### Task 3.1: Mover el contenido wiki Proxy a `projects/proxy/wiki/`

**Files:**
- Move: `wiki/concepts/`     → `projects/proxy/wiki/concepts/`
- Move: `wiki/authors/`      → `projects/proxy/wiki/authors/`
- Move: `wiki/entities/`     → `projects/proxy/wiki/entities/`
- Move: `wiki/synthesis/`    → `projects/proxy/wiki/synthesis/`
- Move: `wiki/README.md`     → `projects/proxy/wiki/README.md`

- [ ] **Step 1: Crear el directorio destino**

```bash
mkdir -p projects/proxy/wiki
ls -la projects/proxy/wiki/
# Expected: empty dir
```

- [ ] **Step 2: Mover los 4 subdirs y el README**

```bash
git mv wiki/concepts  projects/proxy/wiki/concepts
git mv wiki/authors   projects/proxy/wiki/authors
git mv wiki/entities  projects/proxy/wiki/entities
git mv wiki/synthesis projects/proxy/wiki/synthesis
git mv wiki/README.md projects/proxy/wiki/README.md
```

- [ ] **Step 3: Verificar resultado**

```bash
# Nuevo layout: 4 subdirs + README en projects/proxy/wiki/
ls projects/proxy/wiki/
# Expected: README.md authors concepts entities synthesis

# Old paths gone:
[ ! -d wiki/concepts ] && [ ! -d wiki/authors ] && [ ! -d wiki/entities ] && [ ! -d wiki/synthesis ] \
    && echo "ok: old paths gone" || echo "FAIL: old paths still exist"

# Conteo de páginas conservado:
find projects/proxy/wiki -name '*.md' | wc -l
# Expected: igual a `find wiki/{concepts,authors,entities,synthesis} -name '*.md' | wc -l` antes
# Para Proxy: ~183-220 archivos.

# Git ve los movimientos como renames (no como delete+add):
git status --short | head -20
# Expected: lines starting with "R " (renames). Si aparece "D " seguido de "??" es que git
# no detectó el rename — re-ejecutar con git mv explícito archivo a archivo.
```

- [ ] **Step 4: Notas sobre artefactos no contemplados**

- `wiki/Sin nombre/`: directorio vacío untracked (residuo Obsidian). NO mover; opcionalmente `rmdir 'wiki/Sin nombre'` si vacío para limpieza, pero no bloqueante.
- Cualquier otro archivo suelto en `wiki/` raíz (excepto `wiki/_meta/`) que aparezca en `git status`: revisar caso por caso. Esperado: ninguno tras el `git mv`.

- [ ] **Step 5: Commit**

```bash
git add -A projects/proxy/wiki/
git status --short  # last check antes de commit
git commit -m "refactor(projects): mover contenido wiki Proxy a projects/proxy/wiki/

git mv de concepts/ authors/ entities/ synthesis/ + README.md.
Los .md son la fuente de verdad; SQLite se reconstruye con build_wiki_db.py
(Chunk 4 aplicará el flag --project para hacerlo project-aware).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 3.2: Mover los `_meta/` editoriales de Proxy a `projects/proxy/_meta/`

> Mueve los archivos editoriales específicos de Proxy a su nuevo home. **Deja en `wiki/_meta/` solo** `relation_types.json` (que se renombra en Task 3.3) y los `*_default.*` que se crean en Task 3.4.

**Files:**
- Move: `wiki/_meta/scope.md`                 → `projects/proxy/_meta/scope.md`
- Move: `wiki/_meta/topic_filters.json`       → `projects/proxy/_meta/topic_filters.json`
- Move: `wiki/_meta/canonical_whitelist.json` → `projects/proxy/_meta/canonical_whitelist.json`
- Move: `wiki/_meta/extraction_runs/`         → `projects/proxy/_meta/extraction_runs/`
- Move: `wiki/_meta/INDEX.md`                 → `projects/proxy/_meta/INDEX.md`
- Move: `wiki/_meta/legacy/`                  → `projects/proxy/_meta/legacy/`

- [ ] **Step 1: Crear el directorio destino**

```bash
mkdir -p projects/proxy/_meta
```

- [ ] **Step 2: Mover archivos editoriales y carpetas históricas Proxy**

```bash
git mv wiki/_meta/scope.md                 projects/proxy/_meta/scope.md
git mv wiki/_meta/topic_filters.json       projects/proxy/_meta/topic_filters.json
git mv wiki/_meta/canonical_whitelist.json projects/proxy/_meta/canonical_whitelist.json
git mv wiki/_meta/INDEX.md                 projects/proxy/_meta/INDEX.md
git mv wiki/_meta/extraction_runs          projects/proxy/_meta/extraction_runs
git mv wiki/_meta/legacy                   projects/proxy/_meta/legacy
```

Nota: `extraction_runs/` puede pesar > 100 MB (cientos de JSONs per-video). `git mv` lo mueve como renames; el commit resultante es metadata, no se duplica el contenido. Si git detecta esos archivos como delete+add y el repo se hace grande, abortar y verificar `.gitignore` (algunos runs antiguos podrían ya estar gitignorados — en cuyo caso `git mv` solo mueve los tracked).

- [ ] **Step 3: Verificar resultado**

```bash
ls projects/proxy/_meta/
# Expected: INDEX.md canonical_whitelist.json extraction_runs legacy scope.md topic_filters.json

# wiki/_meta/ ahora debería contener únicamente relation_types.json (se renombra en Task 3.3):
ls wiki/_meta/
# Expected: relation_types.json   ← y nada más
# (después de Task 3.4 también estarán los *_default.*)

git status --short | grep '_meta' | head -20
# Expected: renames "R " desde wiki/_meta/* hacia projects/proxy/_meta/*
```

- [ ] **Step 4: Commit**

```bash
git add -A projects/proxy/_meta/ wiki/_meta/
git commit -m "refactor(projects): mover _meta editoriales Proxy a projects/proxy/_meta/

scope.md, topic_filters.json, canonical_whitelist.json, INDEX.md,
extraction_runs/ y legacy/ son específicos de Proxy y viven bajo el proyecto.
wiki/_meta/ pasa a contener solo recursos globales (relation_types_core.json
+ defaults editables).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 3.3: Promover `relation_types.json` a `relation_types_core.json`

> El archivo actual `wiki/_meta/relation_types.json` contiene los 30 tipos de relación canónicos universales. Tras la migración, esos tipos pasan a ser el **core global** (no específico de Proxy). Se renombra para clarificar su rol.

**Files:**
- Rename: `wiki/_meta/relation_types.json` → `wiki/_meta/relation_types_core.json`

- [ ] **Step 1: Verificar el contenido actual**

```bash
.venv/bin/python -c "
import json
d = json.load(open('wiki/_meta/relation_types.json'))
print('types count:', len(d['types']))
print('top-level keys:', list(d.keys()))
"
# Expected: types count: 30, keys: ['version', 'schema_version', 'last_updated', 'description', 'types', 'fields_per_relation', 'policy_notes']
```

- [ ] **Step 2: Rename via git**

```bash
git mv wiki/_meta/relation_types.json wiki/_meta/relation_types_core.json
```

- [ ] **Step 3: Verificar que el JSON sigue siendo válido**

```bash
.venv/bin/python -c "
import json
d = json.load(open('wiki/_meta/relation_types_core.json'))
assert len(d['types']) == 30, f'expected 30 types, got {len(d[\"types\"])}'
print('ok: 30 types preserved')
"
```

- [ ] **Step 4: Commit**

```bash
git add wiki/_meta/relation_types_core.json
git commit -m "refactor(projects): rename relation_types.json → relation_types_core.json

Los 30 tipos son el core global (no Proxy-específicos). El nuevo nombre lo
hace explícito; cada proyecto podrá añadir extensions en
projects/<slug>/_meta/relation_types_ext.json (placeholder se crea en Task 3.6).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 3.4: Crear `wiki/_meta/*_default.*` placeholders

> Los archivos `*_default.*` son los recursos editoriales globales por defecto que aplican a cualquier proyecto sin override (spec sección 5.1). Contenido inicial: plantillas genéricas, **NO** copia del estado Proxy actual (porque Proxy ya tiene sus propios overrides en `projects/proxy/_meta/`, así que el default debe ser un punto de partida genuinamente genérico).

**Files:**
- Create: `wiki/_meta/scope_default.md`
- Create: `wiki/_meta/topic_filters_default.json`
- Create: `wiki/_meta/canonical_whitelist_default.json`
- Create: `wiki/_meta/subagent_prompt_default.md`

- [ ] **Step 1: Crear `wiki/_meta/scope_default.md`** (plantilla genérica editable)

```markdown
<!-- wiki/_meta/scope_default.md -->
# Scope editorial — plantilla por defecto

> **Plantilla genérica para proyectos nuevos.** Cuando crees un proyecto con
> `create_project(seed_from_templates=True)`, una copia de este archivo aparece
> en `projects/<slug>/_meta/scope.md` lista para editar y divergir.

## 1. Qué entra como conocimiento

(Define aquí los criterios editoriales: dominio del proyecto, tipo de contenido
que SÍ merece página wiki, granularidad de los conceptos.)

## 2. Qué se descarta como ruido

(Criterios de exclusión: temas off-topic, formatos sin estructura,
contenido efímero, etc.)

## 3. Vocabulario canónico

(Lista de términos del dominio con su forma preferida y aliases conocidos.
Ejemplo:
- **arquetipo** (preferido) — alias: archetype, archetipo
- **individuación** (preferido, con tilde)
)

## 4. Página vs no-página

(Bullets sobre qué tipo de menciones merecen página propia vs solo cita.)

## 5. Tipos de página activos

(Lista de page_type aceptados en este proyecto: concept | author | entity_work
| entity_institution | synthesis | ...)
```

- [ ] **Step 2: Crear `wiki/_meta/topic_filters_default.json`** (regex universal de descarte)

```json
{
  "version": "1.0",
  "description": "Filtros de descarte universales aplicables a cualquier proyecto. Override per-proyecto en projects/<slug>/_meta/topic_filters.json.",
  "drop_patterns": [
    {"regex": "^\\s*$", "reason": "empty content"},
    {"regex": "(?i)spam|publicidad|promo code", "reason": "promotional noise"}
  ],
  "keep_patterns": []
}
```

- [ ] **Step 3: Crear `wiki/_meta/canonical_whitelist_default.json`** (vacío)

```json
{
  "version": "1.0",
  "description": "Whitelist de términos canónicos. Override per-proyecto en projects/<slug>/_meta/canonical_whitelist.json.",
  "terms": []
}
```

- [ ] **Step 4: Crear `wiki/_meta/subagent_prompt_default.md`** (prompt base genérico)

```markdown
---
kind: concept_author_entity_work
applies_to: any project without override
---

# Sub-agent system prompt — plantilla por defecto

Eres un constructor focalizado de páginas wiki.

CONTEXTO: Trabajas para un proyecto multi-tenant; el scope editorial específico
del proyecto vive en `projects/<slug>/_meta/scope.md`. La plantilla aquí
captura los invariantes globales válidos para cualquier dominio.

TU ÚNICA TAREA: dado UN candidato aprobado (entidad + metadata + cita evidence)
+ un fragmento del summary de la fuente donde aparece, devuelves la página
markdown completa (frontmatter YAML + body markdown) lista para insertar en el wiki.

NO tomas decisiones de scope. NO descartas. NO sugieres otras páginas.
NO juzgas si merece ser página — alguien ya lo decidió. Tú solo CONSTRUYES.

Conforme al schema y vocabulario del proyecto, produces un JSON estricto con
dos campos: `frontmatter` (object) y `body_markdown` (string). Sin preámbulo,
sin epílogo, sin code fences. Primer carácter '{', último '}'.

Reglas duras:
1. `frontmatter.relations[]` con AL MENOS 2 entradas tipadas (usa los tipos en
   `wiki/_meta/relation_types_core.json` + extensiones del proyecto en
   `projects/<slug>/_meta/relation_types_ext.json`).
2. `frontmatter.aliases[]` con variantes razonables del surface_form.
3. `body_markdown` empieza con `# {canonical_name}`, contiene ≥3 secciones H2,
   citas en formato literal con enlace a la fuente, wikilinks `[[page-id]]` a
   otras páginas existentes.
4. Sección `## Lagunas` al final con bullets de gaps declarados o `(sin lagunas
   declaradas todavía)`.
5. Citas LITERALES del summary recibido (substring exacto). Sin paráfrasis.
6. Respeta el vocabulario canónico del proyecto — ver `scope.md` §3.
```

- [ ] **Step 5: Verificar que los 4 archivos existen y son válidos**

```bash
ls wiki/_meta/
# Expected: 4 archivos *_default.* + relation_types_core.json
# = canonical_whitelist_default.json relation_types_core.json scope_default.md
#   subagent_prompt_default.md topic_filters_default.json

# Validar JSON syntax:
.venv/bin/python -c "
import json
for f in ['topic_filters_default.json', 'canonical_whitelist_default.json']:
    json.load(open(f'wiki/_meta/{f}'))
    print(f'ok: wiki/_meta/{f}')
"
```

- [ ] **Step 6: Commit**

```bash
git add wiki/_meta/scope_default.md wiki/_meta/topic_filters_default.json \
        wiki/_meta/canonical_whitelist_default.json wiki/_meta/subagent_prompt_default.md
git commit -m "feat(projects): plantillas globales editables wiki/_meta/*_default.*

4 archivos default editables (scope, topic_filters, canonical_whitelist,
subagent_prompt) usados por proyectos sin override propio. Editar el default
propaga a todos los proyectos no-overriding.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 3.5: Extraer prompts del sub-agente a `projects/proxy/_meta/subagent_prompt.md`

> Los prompts `SUBAGENT_SYSTEM_PROMPT` y `SUBAGENT_SYNTHESIS_SYSTEM_PROMPT` viven hoy hard-coded como constantes en `scripts/extract_video_themes.py`. Esta task los **copia** a un archivo markdown que se convierte en la fuente de verdad. El refactor de `scripts/extract_video_themes.py` para leer del archivo en vez de las constantes inline vive en Chunk 4 Task 4.3 (path updates). En este chunk, las constantes Python quedan intactas — el archivo markdown se crea como espejo byte-equivalente, listo para que Chunk 4 elimine las constantes.
>
> **Por qué no se hace todo en un chunk:** mantener cada chunk al menos parcialmente reversible. Si chunk 4 falla, las constantes Python siguen siendo la fuente y el archivo markdown se queda como artefacto inocuo.

**Files:**
- Create: `projects/proxy/_meta/subagent_prompt.md`
- Test: `scripts/test_subagent_prompt_extraction.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_subagent_prompt_extraction.py
"""Verifica que projects/proxy/_meta/subagent_prompt.md contiene literalmente
el texto de las constantes SUBAGENT_SYSTEM_PROMPT y SUBAGENT_SYNTHESIS_SYSTEM_PROMPT
declaradas en scripts/extract_video_themes.py.

Anti-drift: durante Chunk 3 el archivo md espeja las constantes. En Chunk 4 las
constantes serán reemplazadas por lecturas del md; este test asegura que la
fuente de verdad del refactor está intacta.
"""
from pathlib import Path
import re
import sys


def _load_constant(src: str, name: str) -> str:
    """Extrae el contenido entre triple-quotes de una constante TOP-LEVEL del archivo.
    Espera el patrón `NAME = \"\"\"...\"\"\"` (multilinea)."""
    pattern = rf"^{re.escape(name)}\s*=\s*\"\"\"(.*?)\"\"\""
    m = re.search(pattern, src, re.MULTILINE | re.DOTALL)
    assert m, f"constante {name} no encontrada en el source"
    return m.group(1)


def test_subagent_prompts_md_mirrors_python_constants():
    py_src = Path("scripts/extract_video_themes.py").read_text()
    base_prompt = _load_constant(py_src, "SUBAGENT_SYSTEM_PROMPT")
    synth_prompt = _load_constant(py_src, "SUBAGENT_SYNTHESIS_SYSTEM_PROMPT")

    md_path = Path("projects/proxy/_meta/subagent_prompt.md")
    assert md_path.exists(), f"missing: {md_path}"
    md_text = md_path.read_text()

    # El md debe tener dos secciones, una con kind concept/author/entity_work
    # y otra con kind synthesis. Cada sección encierra el prompt entre marcadores
    # explícitos para que un parser pueda dividirlas sin ambigüedad.
    assert "<!-- BEGIN PROMPT concept_author_entity_work -->" in md_text
    assert "<!-- END PROMPT concept_author_entity_work -->" in md_text
    assert "<!-- BEGIN PROMPT synthesis -->" in md_text
    assert "<!-- END PROMPT synthesis -->" in md_text

    def _between(text: str, kind: str) -> str:
        start_marker = f"<!-- BEGIN PROMPT {kind} -->\n"
        end_marker = f"\n<!-- END PROMPT {kind} -->"
        i = text.index(start_marker) + len(start_marker)
        j = text.index(end_marker, i)
        return text[i:j]

    md_base = _between(md_text, "concept_author_entity_work")
    md_synth = _between(md_text, "synthesis")

    # Equality byte-a-byte (tras strip de whitespace exterior — los markdown markers
    # no permiten exactitud absoluta pero el contenido interno sí debe coincidir).
    assert md_base.strip() == base_prompt.strip(), \
        f"concept_author_entity_work prompt drift"
    assert md_synth.strip() == synth_prompt.strip(), \
        f"synthesis prompt drift"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest scripts/test_subagent_prompt_extraction.py -v
# Expected: FAIL — missing projects/proxy/_meta/subagent_prompt.md
```

- [ ] **Step 3: Crear `projects/proxy/_meta/subagent_prompt.md`** con ambos prompts

> Copia literal de las constantes desde `scripts/extract_video_themes.py:953-976` (SUBAGENT_SYSTEM_PROMPT) y `:1226-1257` (SUBAGENT_SYNTHESIS_SYSTEM_PROMPT). Los markers `<!-- BEGIN/END PROMPT <kind> -->` permiten al parser de Chunk 4 separarlos. **Texto entre markers debe coincidir byte-a-byte con la constante Python tras `.strip()`** (el test lo verifica).
>
> **Método recomendado (primary): el script Python al final de este Step.** Lee directamente las constantes con regex y serializa al markdown sin riesgo de drift por escape/whitespace. El método heredoc que aparece debajo es **referencia visual del shape** del archivo, no se ejecuta — el test del Step 4 fallará si lo intentas y hay drift de un solo carácter.

```bash
# ━━━━━━━━ Referencia visual del shape — NO EJECUTAR (usar Python copier abajo) ━━━━━━━━

cat > projects/proxy/_meta/subagent_prompt.md <<'EOF'
---
project: proxy
source_of_truth: this file (Chunk 4 elimina las constantes inline en extract_video_themes.py)
kinds:
  - concept_author_entity_work
  - synthesis
---

# Sub-agent system prompts — Proxy

Override per-proyecto del prompt del sub-agente que construye páginas wiki.
Dos kinds: `concept_author_entity_work` (default para concepts/authors/entities)
y `synthesis` (para tesis monográficas auto-promovidas).

<!-- BEGIN PROMPT concept_author_entity_work -->
Eres un constructor focalizado de páginas wiki para Ariadna.

CONTEXTO: Ariadna es un wiki markdown sobre el corpus YouTube del canal Proxy
(análisis arquetípico, mitología comparada, psicología junguiana, crítica cultural).

TU ÚNICA TAREA: dado UN candidato aprobado (entidad + metadata + cita evidence) + un
fragmento del summary del vídeo donde aparece, devuelves la página markdown completa
(frontmatter YAML + body markdown) lista para insertar en el wiki.

NO tomas decisiones de scope. NO descartas. NO sugieres otras páginas.
NO juzgas si merece ser página — alguien ya lo decidió. Tú solo CONSTRUYES.

Conforme al schema y vocabulario que se te entregan, produces un JSON estricto con
dos campos: `frontmatter` (object) y `body_markdown` (string). Sin preámbulo,
sin epílogo, sin code fences. Primer carácter '{', último '}'.

Reglas duras:
1. `frontmatter.relations[]` con AL MENOS 2 entradas tipadas (usa relation_types.json).
2. `frontmatter.aliases[]` con variantes razonables del surface_form (con/sin diacríticos, abreviadas, etc.) — al menos 1 entrada si hay variación.
3. `body_markdown` empieza con `# {canonical_name}`, contiene ≥3 secciones H2, citas en formato `> "texto literal del summary"\n→ [Título (mm:ss)](https://youtu.be/ID?t=SECS)`, wikilinks `[[page-id]]` para referenciar otras páginas existentes o de este batch.
4. Sección `## Lagunas` al final con bullets de gaps declarados o `(sin lagunas declaradas todavía)`.
5. Citas LITERALES del summary recibido (substring exacto). Sin paráfrasis ni traducción.
6. Respeta vocabulario del canal (égersis, mito polar, mitología propia/impropia, etc.) — ver scope.md §5.
<!-- END PROMPT concept_author_entity_work -->

<!-- BEGIN PROMPT synthesis -->
Eres un constructor focalizado de páginas synthesis para Ariadna.

CONTEXTO: Ariadna documenta el canal Proxy. Las páginas `synthesis` con
`synthesis_subtype: author_thesis` capturan TESIS ORIGINALES articuladas por el speaker
en vídeos monográficos sostenidos. NO son explicaciones de conceptos académicos
estándar (eso son `concept`); son el marco PROPIO del canal.

TU ÚNICA TAREA: dado UN thesis_candidate auto-promovido (cumple gate de scope.md §2.4.1)
+ contexto del summary del vídeo monográfico, devuelves la página markdown completa
(frontmatter YAML + body markdown) que articula la tesis con sus piezas internas.

NO tomas decisiones de scope. La promoción ya pasó el gate automático.
NO descartas piezas. Cada elemento de framework_internal_structure es contenido valioso.

Conforme al schema, produces JSON estricto con `frontmatter` y `body_markdown`.
Sin preámbulo, sin code fences. Primer carácter '{', último '}'.

Reglas duras:
1. `frontmatter.page_type: "synthesis"` y `frontmatter.synthesis_subtype: "author_thesis"`.
2. `frontmatter.auto_promoted_synthesis: true` (marca de auditoría — esta página se promovió sin firma humana porque el gate cumplió).
3. `frontmatter.relations[]` con AL MENOS 2 entradas tipadas hacia páginas existentes que la tesis toca o critica.
4. `frontmatter.aliases[]` con variantes razonables del thesis_title.
5. `body_markdown` empieza con `# {thesis_title}` y contiene:
   - `## Tesis nuclear` (1-2 párrafos articulando lo que el speaker propone)
   - `## Estructura del marco` con sub-bullets para CADA pieza de framework_internal_structure (no omitas piezas)
   - `## Citas del vídeo` con los speaker_authorship_marks como `> "literal"\n→ [Título (mm:ss)](URL)`
   - `## Páginas conectadas` con wikilinks `[[page-id]]` a `related_existing_pages`
   - `## Lagunas` al final
   - `## Status auto-promoción` con disclaimer: "Esta página se ha auto-promovido al cumplir el gate de scope.md §2.4.1 (minutes_sustained, signal_marks, framework pieces). Queda abierta a revisión humana — campo `auto_promoted_synthesis: true` en frontmatter es la marca de auditoría."
6. Citas LITERALES del summary recibido (substring exacto).
7. Respeta vocabulario del canal (égersis, mito polar, mitología propia/impropia, diagrama de Proxy, etc.) — ver scope.md §5.
<!-- END PROMPT synthesis -->
EOF
```

**Método primario (a ejecutar): Python copia las constantes sin tocar el texto.** Usa este script — el test del Step 4 lo verifica:

```bash
.venv/bin/python <<'PYEOF'
import re
from pathlib import Path

src = Path("scripts/extract_video_themes.py").read_text()

def grab(name):
    m = re.search(rf'^{name}\s*=\s*"""(.*?)"""', src, re.MULTILINE | re.DOTALL)
    assert m, name
    return m.group(1).strip()

base = grab("SUBAGENT_SYSTEM_PROMPT")
synth = grab("SUBAGENT_SYNTHESIS_SYSTEM_PROMPT")

header = """---
project: proxy
source_of_truth: this file (Chunk 4 elimina las constantes inline en extract_video_themes.py)
kinds:
  - concept_author_entity_work
  - synthesis
---

# Sub-agent system prompts — Proxy

Override per-proyecto del prompt del sub-agente que construye páginas wiki.
Dos kinds: `concept_author_entity_work` (default para concepts/authors/entities)
y `synthesis` (para tesis monográficas auto-promovidas).

<!-- BEGIN PROMPT concept_author_entity_work -->
"""

out = (
    header
    + base
    + "\n<!-- END PROMPT concept_author_entity_work -->\n\n"
    + "<!-- BEGIN PROMPT synthesis -->\n"
    + synth
    + "\n<!-- END PROMPT synthesis -->\n"
)

Path("projects/proxy/_meta/subagent_prompt.md").write_text(out)
print("written:", len(out), "chars")
PYEOF
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest scripts/test_subagent_prompt_extraction.py -v
# Expected: PASS
```

- [ ] **Step 5: Commit**

```bash
git add projects/proxy/_meta/subagent_prompt.md scripts/test_subagent_prompt_extraction.py
git commit -m "feat(projects): extraer subagent prompts a projects/proxy/_meta/subagent_prompt.md

Espeja byte-a-byte las constantes SUBAGENT_SYSTEM_PROMPT y
SUBAGENT_SYNTHESIS_SYSTEM_PROMPT de scripts/extract_video_themes.py.
Chunk 4 eliminará las constantes Python y leerá del md. Test de drift
incluido (scripts/test_subagent_prompt_extraction.py).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 3.6: Crear placeholders en `projects/proxy/_meta/`

> Crea los dos placeholders mínimos que un proyecto debe tener: `relation_types_ext.json` (vacío, sin extensiones) y `INDEX.md` (referencia básica al proyecto, ya existe pero falta confirmar).
>
> Nota: `INDEX.md` ya se movió en Task 3.2 desde `wiki/_meta/INDEX.md`. Esta task solo añade `relation_types_ext.json` y verifica que `INDEX.md` está presente.

**Files:**
- Create: `projects/proxy/_meta/relation_types_ext.json`

- [ ] **Step 1: Crear `projects/proxy/_meta/relation_types_ext.json`** vacío

```bash
cat > projects/proxy/_meta/relation_types_ext.json <<'EOF'
{
  "version": "1.0",
  "schema_version": "1.0.0",
  "description": "Extensiones de relation_types específicas de Proxy. Cualquier tipo aquí extiende relation_types_core.json. Colisión con un tipo core es error: el server falla en startup.",
  "types": []
}
EOF
```

- [ ] **Step 2: Validar JSON y verificar INDEX.md presente**

```bash
.venv/bin/python -c "
import json
d = json.load(open('projects/proxy/_meta/relation_types_ext.json'))
assert d['types'] == []
print('ok: relation_types_ext.json válido (sin extensiones)')
"

[ -f projects/proxy/_meta/INDEX.md ] && echo "ok: INDEX.md presente" || echo "FAIL: INDEX.md ausente"
```

- [ ] **Step 3: Verificar layout final del proyecto Proxy**

```bash
find projects/proxy -maxdepth 3 -type d
# Expected:
# projects/proxy
# projects/proxy/_meta
# projects/proxy/_meta/extraction_runs
# projects/proxy/_meta/legacy
# projects/proxy/wiki
# projects/proxy/wiki/authors
# projects/proxy/wiki/concepts
# projects/proxy/wiki/entities
# projects/proxy/wiki/synthesis

ls projects/proxy/_meta/
# Expected: INDEX.md canonical_whitelist.json extraction_runs legacy
#           relation_types_ext.json scope.md subagent_prompt.md topic_filters.json
```

- [ ] **Step 4: Verificar layout final de `wiki/_meta/`**

```bash
ls wiki/_meta/
# Expected (después de chunks 3.2-3.4):
#   canonical_whitelist_default.json
#   relation_types_core.json
#   scope_default.md
#   subagent_prompt_default.md
#   topic_filters_default.json
```

- [ ] **Step 5: Commit**

```bash
git add projects/proxy/_meta/relation_types_ext.json
git commit -m "feat(projects): proxy relation_types_ext.json placeholder (sin extensiones)

Proxy no necesita extensions por ahora — los 30 tipos core cubren su grafo.
El archivo existe para que ProjectConfig (Chunk 4) lo encuentre y reload
relation_types lo procese (vacío = no-op).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 4: ProjectConfig module + path updates

> Crea el módulo `ariadna/project_config.py` que resuelve recursos editoriales (scope, topic_filters, canonical_whitelist, subagent_prompt, relation_types core+ext) aplicando el patrón default→override (spec sección 7.1-7.2). Después actualiza los paths hardcoded en los 7 archivos Python afectados para que apunten al nuevo layout multi-project: `data/wiki.db` → `data/ariadna.db`, `wiki/` → `projects/<slug>/wiki/`, `wiki/_meta/extraction_runs/` → `projects/<slug>/_meta/extraction_runs/`, y `citations.video_id` → `citations.source_id`. Los scripts CLI ganan `--project` flag.
>
> **Pre-condición:** Chunks 2-3 completados. `data/ariadna.db` existe con contenido `proxy`; el filesystem ya está en `projects/proxy/{_meta,wiki}/`; los defaults globales están en `wiki/_meta/*_default.*`.
>
> **Out of scope:** wiring del parámetro `project` en las tools MCP (eso vive en Chunk 8); registro de `reload_relation_types` en el startup del MCP server (Chunk 8). En este chunk la función `reload_relation_types` se escribe pero no se invoca en ningún hook todavía.

### Task 4.1: Crear `ariadna/project_config.py`

> Módulo nuevo con `ProjectConfig` (resuelve recursos per-proyecto vía default→override fallback) y `reload_relation_types()` (rellena la tabla `relation_types_canonical` en SQLite desde core JSON + ext JSON por proyecto, transacción atómica). Stateless: lee filesystem en cada acceso (archivos pequeños).

**Files:**
- Create: `ariadna/project_config.py`
- Test: `tests/test_project_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_project_config.py
"""Tests para ProjectConfig: resolución default→override + reload de relation_types."""
import json
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Construye un mini repo con la estructura wiki/_meta/ + projects/proxy/_meta/."""
    (tmp_path / "wiki" / "_meta").mkdir(parents=True)
    (tmp_path / "projects" / "proxy" / "_meta").mkdir(parents=True)
    (tmp_path / "projects" / "proxy" / "wiki").mkdir()

    # defaults globales
    (tmp_path / "wiki" / "_meta" / "scope_default.md").write_text("# default scope\n")
    (tmp_path / "wiki" / "_meta" / "topic_filters_default.json").write_text(
        json.dumps({"version": "1.0", "drop_patterns": []})
    )
    (tmp_path / "wiki" / "_meta" / "canonical_whitelist_default.json").write_text(
        json.dumps({"terms": []})
    )
    (tmp_path / "wiki" / "_meta" / "subagent_prompt_default.md").write_text(
        "# default subagent prompt\n"
    )
    # core relation_types con shape de dict (tal como hoy)
    (tmp_path / "wiki" / "_meta" / "relation_types_core.json").write_text(json.dumps({
        "version": "2.0.0",
        "types": {
            "developed_by": {"description": "x dev by y", "from": ["concept"], "to": ["author"], "inverse": "developed"},
            "developed":    {"description": "x dev",      "from": ["author"], "to": ["concept"], "inverse": "developed_by"},
        }
    }))

    # override Proxy: scope + subagent_prompt + ext vacío
    (tmp_path / "projects" / "proxy" / "_meta" / "scope.md").write_text("# proxy scope\n")
    (tmp_path / "projects" / "proxy" / "_meta" / "subagent_prompt.md").write_text(
        "<!-- BEGIN PROMPT concept_author_entity_work -->\nproxy prompt body\n<!-- END PROMPT concept_author_entity_work -->\n"
        "<!-- BEGIN PROMPT synthesis -->\nproxy synthesis body\n<!-- END PROMPT synthesis -->\n"
    )
    (tmp_path / "projects" / "proxy" / "_meta" / "relation_types_ext.json").write_text(
        json.dumps({"types": {}})  # dict shape (consistente con core); _normalize_types_block acepta ambos
    )
    # SQLite con projects + relation_types_canonical
    db = tmp_path / "data" / "ariadna.db"
    db.parent.mkdir()
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE projects(project_id TEXT PRIMARY KEY, name TEXT NOT NULL,
            description TEXT, created_at TEXT NOT NULL, archived_at TEXT,
            config_version TEXT NOT NULL DEFAULT '1.0');
        CREATE TABLE relation_types_canonical(
            project_id TEXT, type TEXT NOT NULL,
            description TEXT, inverse TEXT,
            from_types_csv TEXT, to_types_csv TEXT,
            PRIMARY KEY (project_id, type));
        INSERT INTO projects(project_id, name, created_at)
            VALUES ('proxy', 'Proxy', '2026-05-16T00:00:00+00:00');
    """)
    conn.commit()
    conn.close()
    return tmp_path


def test_for_project_falls_back_to_default(fake_repo, monkeypatch):
    monkeypatch.chdir(fake_repo)
    from ariadna.project_config import ProjectConfig

    cfg = ProjectConfig.for_project("proxy")
    # scope: override existe → usa el de Proxy
    assert cfg.scope_text() == "# proxy scope\n"
    # topic_filters: no hay override → cae al default
    assert cfg.topic_filters() == {"version": "1.0", "drop_patterns": []}
    # canonical_whitelist: no hay override → default
    assert cfg.canonical_whitelist() == {"terms": []}
    # subagent_prompt: hay override → carga del archivo Proxy y devuelve dict por kind
    prompts = cfg.subagent_prompts()
    assert "concept_author_entity_work" in prompts
    assert "synthesis" in prompts
    assert "proxy prompt body" in prompts["concept_author_entity_work"]


def test_for_project_raises_if_unknown(fake_repo, monkeypatch):
    monkeypatch.chdir(fake_repo)
    from ariadna.project_config import ProjectConfig, ProjectNotFoundError

    with pytest.raises(ProjectNotFoundError):
        ProjectConfig.for_project("does-not-exist")


def test_wiki_root_and_extraction_runs_paths(fake_repo, monkeypatch):
    monkeypatch.chdir(fake_repo)
    from ariadna.project_config import ProjectConfig

    cfg = ProjectConfig.for_project("proxy")
    assert cfg.wiki_root() == (fake_repo / "projects" / "proxy" / "wiki").resolve()
    assert cfg.extraction_runs_dir() == (fake_repo / "projects" / "proxy" / "_meta" / "extraction_runs").resolve()


def test_reload_relation_types_inserts_core_and_ext(fake_repo, monkeypatch):
    monkeypatch.chdir(fake_repo)
    from ariadna.project_config import reload_relation_types

    conn = sqlite3.connect(str(fake_repo / "data" / "ariadna.db"))
    reload_relation_types(conn)
    rows = conn.execute(
        "SELECT project_id, type FROM relation_types_canonical ORDER BY project_id, type"
    ).fetchall()
    # core es project_id NULL; ext de proxy no añade nada porque está vacío
    assert rows == [(None, "developed"), (None, "developed_by")]
    conn.close()


def test_reload_relation_types_rejects_ext_colliding_with_core(fake_repo, monkeypatch):
    monkeypatch.chdir(fake_repo)
    from ariadna.project_config import reload_relation_types, ConfigError

    # Forzar colisión: ext declara un tipo "developed" (que es core)
    (fake_repo / "projects" / "proxy" / "_meta" / "relation_types_ext.json").write_text(
        json.dumps({"types": {"developed": {"description": "...", "inverse": "x", "from": [], "to": []}}})
    )
    conn = sqlite3.connect(str(fake_repo / "data" / "ariadna.db"))
    with pytest.raises(ConfigError, match="developed"):
        reload_relation_types(conn)
    # La tabla queda con el estado previo (vacío en este caso, no parcial)
    n = conn.execute("SELECT COUNT(*) FROM relation_types_canonical").fetchone()[0]
    assert n == 0
    conn.close()


def test_reload_relation_types_rejects_malformed_ext_json(fake_repo, monkeypatch):
    """Spec sección 7.3: JSON inválido en ext_path debe fallar loudly y rollback intacto."""
    monkeypatch.chdir(fake_repo)
    from ariadna.project_config import reload_relation_types

    (fake_repo / "projects" / "proxy" / "_meta" / "relation_types_ext.json").write_text(
        "{ this is not json"
    )
    conn = sqlite3.connect(str(fake_repo / "data" / "ariadna.db"))
    with pytest.raises(json.JSONDecodeError):
        reload_relation_types(conn)
    # Tabla queda intacta — rollback automático
    n = conn.execute("SELECT COUNT(*) FROM relation_types_canonical").fetchone()[0]
    assert n == 0
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_project_config.py -v
# Expected: collection error o ModuleNotFoundError (ariadna.project_config no existe)
```

- [ ] **Step 3: Implement `ariadna/project_config.py`**

```python
"""ProjectConfig — resolución de recursos editoriales per-proyecto.

Aplica el patrón default→override de spec sección 7.1-7.2:
- defaults globales viven en `wiki/_meta/*_default.*` (plantillas editables).
- overrides per-proyecto viven en `projects/<slug>/_meta/<name>.*` (sin sufijo).

Stateless: cada llamada lee filesystem (archivos pequeños, < 10 ms).

También expone `reload_relation_types(conn)` que rellena la tabla
`relation_types_canonical` en SQLite desde `wiki/_meta/relation_types_core.json` +
las `projects/<slug>/_meta/relation_types_ext.json` de cada proyecto activo,
en una transacción atómica (spec sección 7.3).
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parent.parent
WIKI_META = REPO / "wiki" / "_meta"


class ProjectNotFoundError(LookupError):
    """Lanzado por ProjectConfig.for_project cuando el slug no está en SQLite."""


class ConfigError(RuntimeError):
    """Configuración editorial inválida (colisión core↔ext, etc)."""


@dataclass(frozen=True)
class ProjectConfig:
    project_id: str

    @staticmethod
    def for_project(project_id: str, db_path: Path | None = None) -> "ProjectConfig":
        """Valida que el slug existe en la tabla projects de ariadna.db."""
        db = db_path or (REPO / "data" / "ariadna.db")
        if not db.exists():
            raise ProjectNotFoundError(
                f"ariadna.db not found at {db}; run scripts/init_ariadna_db.py first"
            )
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT project_id FROM projects WHERE project_id=?", (project_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise ProjectNotFoundError(f"unknown project_id: {project_id!r}")
        return ProjectConfig(project_id=project_id)

    # --- paths --------------------------------------------------------------

    @property
    def _meta_dir(self) -> Path:
        return (REPO / "projects" / self.project_id / "_meta").resolve()

    def wiki_root(self) -> Path:
        return (REPO / "projects" / self.project_id / "wiki").resolve()

    def extraction_runs_dir(self) -> Path:
        return (self._meta_dir / "extraction_runs").resolve()

    def _resolve(self, name: str) -> Path:
        """Resuelve nombre relativo aplicando default→override fallback.
        Ej: 'scope.md' → projects/<pid>/_meta/scope.md si existe, si no
        wiki/_meta/scope_default.md. Si ninguno existe, ConfigError.
        """
        local = self._meta_dir / name
        if local.exists():
            return local
        stem, _, ext = name.rpartition(".")
        fallback = WIKI_META / f"{stem}_default.{ext}"
        if not fallback.exists():
            raise ConfigError(
                f"missing editorial resource {name!r} for project {self.project_id!r}: "
                f"no override at {local}, no default at {fallback}"
            )
        return fallback

    # --- accessors ----------------------------------------------------------

    def scope_text(self) -> str:
        return self._resolve("scope.md").read_text()

    def topic_filters(self) -> dict:
        return json.loads(self._resolve("topic_filters.json").read_text())

    def canonical_whitelist(self) -> dict:
        return json.loads(self._resolve("canonical_whitelist.json").read_text())

    def subagent_prompts(self) -> dict[str, str]:
        """Lee `subagent_prompt.md` (o default) y devuelve {kind: prompt_text}.
        El archivo separa kinds con `<!-- BEGIN/END PROMPT <kind> -->`.
        Default file: una sola sección kind=concept_author_entity_work.
        """
        text = self._resolve("subagent_prompt.md").read_text()
        return _parse_prompt_sections(text)

    def relation_types_ext(self) -> dict:
        """Devuelve {types: {name: {...}}} o {types: {}} si no hay ext."""
        path = self._meta_dir / "relation_types_ext.json"
        if not path.exists():
            return {"types": {}}
        return json.loads(path.read_text())


_PROMPT_RE = re.compile(
    r"<!--\s*BEGIN PROMPT (\S+)\s*-->\n?(.*?)\n?<!--\s*END PROMPT \1\s*-->",
    re.DOTALL,
)
_YAML_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def _parse_prompt_sections(text: str) -> dict[str, str]:
    """Extrae bloques con markers <!-- BEGIN/END PROMPT <kind> -->.
    Si no hay markers, strip de YAML frontmatter inicial y devuelve
    {'concept_author_entity_work': text.strip()} (compat con el default
    plano que tiene frontmatter pero un solo cuerpo).
    """
    matches = _PROMPT_RE.findall(text)
    if not matches:
        body = _YAML_FRONTMATTER_RE.sub("", text, count=1)
        return {"concept_author_entity_work": body.strip()}
    return {kind: body.strip() for kind, body in matches}


# --- relation types reload ---------------------------------------------------

def _normalize_types_block(block: Any) -> Iterable[tuple[str, dict]]:
    """Soporta dos shapes del campo `types`:
       - dict {name: {description, inverse, from, to}}  ← shape actual
       - list [{type, description, ...}]                ← shape spec section 7.3 pseudocode
    Devuelve siempre tuplas (type_name, attrs_dict).
    """
    if isinstance(block, dict):
        for name, attrs in block.items():
            yield name, attrs
    elif isinstance(block, list):
        for t in block:
            yield t["type"], t
    else:
        raise ConfigError(f"relation_types.types has unexpected shape: {type(block).__name__}")


def reload_relation_types(conn: sqlite3.Connection) -> None:
    """Rellena `relation_types_canonical` en SQLite con:
       - core de `wiki/_meta/relation_types_core.json` (project_id=NULL)
       - ext de cada `projects/<slug>/_meta/relation_types_ext.json` (project_id=slug)
    En transacción atómica: cualquier excepción rollback completo, la tabla
    queda con su estado anterior intacto. Si un ext declara un tipo que ya
    existe en core, levanta ConfigError. Si el JSON está malformado, propaga
    `json.JSONDecodeError` (rollback aplica igual).
    """
    core_path = WIKI_META / "relation_types_core.json"
    core_doc = json.loads(core_path.read_text())
    core_types = dict(_normalize_types_block(core_doc.get("types", {})))
    core_names = set(core_types)

    with conn:  # implicit BEGIN ... COMMIT/ROLLBACK
        conn.execute("DELETE FROM relation_types_canonical")
        for name, attrs in core_types.items():
            conn.execute(
                "INSERT INTO relation_types_canonical(project_id, type, description, "
                "inverse, from_types_csv, to_types_csv) VALUES (NULL, ?, ?, ?, ?, ?)",
                (
                    name,
                    attrs.get("description"),
                    attrs.get("inverse"),
                    ",".join(attrs.get("from", [])),
                    ",".join(attrs.get("to", [])),
                ),
            )
        project_ids = [
            r[0] for r in conn.execute(
                "SELECT project_id FROM projects WHERE archived_at IS NULL"
            ).fetchall()
        ]
        for pid in project_ids:
            ext_path = REPO / "projects" / pid / "_meta" / "relation_types_ext.json"
            if not ext_path.exists():
                continue
            ext_doc = json.loads(ext_path.read_text())  # may raise JSONDecodeError → rollback
            for name, attrs in _normalize_types_block(ext_doc.get("types", {})):
                if name in core_names:
                    raise ConfigError(
                        f"Project {pid!r} ext declares type {name!r} that collides with core. "
                        f"Rename or remove."
                    )
                conn.execute(
                    "INSERT INTO relation_types_canonical(project_id, type, description, "
                    "inverse, from_types_csv, to_types_csv) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        pid, name,
                        attrs.get("description"),
                        attrs.get("inverse"),
                        ",".join(attrs.get("from", [])),
                        ",".join(attrs.get("to", [])),
                    ),
                )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_project_config.py -v
# Expected: 6 passed
```

- [ ] **Step 5: Commit**

```bash
git add ariadna/project_config.py tests/test_project_config.py
git commit -m "feat(projects): ProjectConfig + reload_relation_types

Resuelve scope/topic_filters/canonical_whitelist/subagent_prompts vía
default→override fallback. reload_relation_types rellena
relation_types_canonical en transacción atómica desde core JSON +
extensions por proyecto, con detección de colisiones core↔ext.

Soporta ambos shapes del campo 'types' (dict y list) para compat con el
shape actual y el pseudocode del spec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4.2: Actualizar `ariadna/search.py` — `wiki.db` → `ariadna.db` + `video_id` → `source_id`

> El Searcher hoy abre `data/wiki.db` y ejecuta queries con `citations.video_id`. Tras Chunk 2, el contenido vive en `data/ariadna.db` con columnas renombradas. Cambios mínimos: path constant + 2 columnas en SQL. No se añade filtro `project_id` todavía — esto se hace en Chunk 8 (cuando MCP tools acepten `project` param). En este chunk el Searcher queda multi-tenant-aware pero sin scoping, que es semánticamente equivalente al estado pre-migración (solo existe 'proxy').

**Files:**
- Modify: `ariadna/search.py:18-21` (constant rename)
- Modify: `ariadna/search.py:97-120` (constructor + `_open_*`)
- Modify: `ariadna/search.py:329-411` (citations queries — `video_id` → `source_id`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_search_uses_ariadna_db.py
"""Verifica que Searcher abre data/ariadna.db (no wiki.db) y consulta
citations con la nueva columna source_id."""
import sqlite3
from pathlib import Path

import pytest


def test_searcher_constant_points_to_ariadna_db():
    from ariadna import search
    assert search.ARIADNA_DB_PATH.name == "ariadna.db"
    # legacy alias kept temporarily? — NO, eliminar
    assert not hasattr(search, "WIKI_DB_PATH"), \
        "WIKI_DB_PATH debe haberse retirado; el código usa ARIADNA_DB_PATH"


def test_searcher_citations_query_uses_source_id_column(tmp_path, monkeypatch):
    """Smoke: con un ariadna.db mínimo, _lookup_wiki_via_citations no falla."""
    db = tmp_path / "ariadna.db"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE projects(project_id TEXT PRIMARY KEY, name TEXT, created_at TEXT NOT NULL);
        CREATE TABLE pages(project_id TEXT, page_id TEXT, page_type TEXT NOT NULL,
            canonical_name TEXT NOT NULL, domain_primary TEXT, file_path TEXT NOT NULL,
            last_compiled TEXT, sources_count INTEGER, review_status TEXT,
            body_md TEXT NOT NULL, indexed_at TEXT NOT NULL,
            PRIMARY KEY (project_id, page_id));
        CREATE TABLE aliases(project_id TEXT, page_id TEXT, alias TEXT,
            PRIMARY KEY (project_id, page_id, alias));
        CREATE TABLE relations(project_id TEXT, from_page_id TEXT, type TEXT,
            to_page_id TEXT, note TEXT, weight TEXT,
            PRIMARY KEY (project_id, from_page_id, type, to_page_id));
        CREATE TABLE citations(project_id TEXT, page_id TEXT, source_id TEXT NOT NULL,
            timestamp_seconds INTEGER NOT NULL DEFAULT 0, title TEXT, url TEXT NOT NULL,
            PRIMARY KEY (project_id, page_id, source_id, timestamp_seconds));
        INSERT INTO projects VALUES ('proxy', 'Proxy', '2026-05-16T00:00:00+00:00');
        INSERT INTO pages VALUES ('proxy', 'shadow', 'concept', 'Sombra', 'jung',
            'concepts/shadow.md', NULL, 1, 'reviewed', '# Sombra',
            '2026-05-16T00:00:00+00:00');
        INSERT INTO citations VALUES ('proxy', 'shadow', 'vid_a', 120, 'Sombra', 'https://x');
    """)
    conn.commit()
    conn.close()

    from ariadna.search import Searcher
    s = Searcher.__new__(Searcher)  # no full init
    s.wiki_db_path = db  # legacy attr name retained for minimal diff (renombre interno)
    hits = s._lookup_wiki_via_citations([
        {"video_id": "vid_a", "timestamp_seconds": 120, "dense_score": 0.9, "score": 0.9,
         "video_title": "Sombra"}
    ])
    assert "shadow" in hits
    assert hits["shadow"][0]["match_strength"] == "exact"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_search_uses_ariadna_db.py -v
# Expected: AssertionError "ARIADNA_DB_PATH no existe" o similar
```

- [ ] **Step 3: Apply edits to `ariadna/search.py`**

Cambios concretos:

1. **Línea 18-21**: renombrar la constante. Reemplaza:
   ```python
   WIKI_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "wiki.db"
   ```
   por:
   ```python
   ARIADNA_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ariadna.db"
   ```

2. **Línea 102, 107, 108, 112**: parámetro y atributo. Reemplaza el `wiki_db_path` (constructor + asignación) por **misma** firma — `wiki_db_path` se mantiene como **nombre interno** del atributo para minimizar churn pero apunta a ariadna.db. Cambio:
   ```python
   def __init__(self, ..., wiki_db_path: Path | None = None) -> None:
       ...
       self.wiki_db_path = wiki_db_path or ARIADNA_DB_PATH
       if not self.wiki_db_path.exists():
           log.warning(
               "ariadna.db no existe en %s — lookup indirecto vía citations desactivado. "
               "Ejecuta `python scripts/init_ariadna_db.py && python scripts/build_wiki_db.py --project=proxy`.",
               self.wiki_db_path,
           )
   ```

3. **Línea 116 (docstring)**: cambia "Abre conexión read-only a wiki.db" → "Abre conexión read-only a ariadna.db".

4. **3 queries SQL** que usan `citations.video_id`:
   - `ariadna/search.py:348`: `WHERE video_id = ? AND timestamp_seconds = ?`
   - `ariadna/search.py:386`: `SELECT DISTINCT page_id FROM citations WHERE video_id = ?`
   - `ariadna/search.py:437`: `WHERE video_id = ? AND timestamp_seconds = ?`

   Renombrar la columna en las 3:
   ```python
   # antes
   "WHERE video_id = ? AND timestamp_seconds = ?"
   # después
   "WHERE source_id = ? AND timestamp_seconds = ?"
   ```
   Los parámetros bind siguen llamándose `video_id` en el código Python (es el field name del chunk Qdrant, que no cambia) — solo cambia el nombre de columna SQL.

5. **Línea 175 (docstring)**: actualizar referencia "data/wiki.db:citations" → "data/ariadna.db:citations".

6. **Líneas 308-309 y 540 (docstrings)**: idem.

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_search_uses_ariadna_db.py -v
# Expected: 2 passed
```

- [ ] **Step 5: Commit**

```bash
git add ariadna/search.py tests/test_search_uses_ariadna_db.py
git commit -m "refactor(search): Searcher lee data/ariadna.db con columna source_id

WIKI_DB_PATH → ARIADNA_DB_PATH; SQL citations.video_id → citations.source_id.
Sin filtro project_id todavía (Chunk 8 wireará el param en la tool MCP);
multi-tenant sin scoping es semánticamente equivalente al pre-migración
porque solo existe 'proxy'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4.3: `scripts/build_wiki_db.py` — flag `--project` y target `ariadna.db`

> El builder hoy escanea `wiki/` global y escribe a `data/wiki.db`. Cambios: acepta `--project=<slug>` (requerido), resuelve `wiki_root` vía `ProjectConfig`, escribe a `data/ariadna.db`, taggea cada fila con `project_id=<slug>`. **Modo:** UPSERT (`INSERT OR REPLACE` con PK compuesta `(project_id, page_id)`) para que builds repetidos sean idempotentes sin truncar otras proyectos.

**Files:**
- Modify: `scripts/build_wiki_db.py:47-49` (constants), `:253` (DELETE→DELETE scoped), CLI argparse, SQL templates.

- [ ] **Step 1: Write the failing test**

```python
# scripts/test_build_wiki_db_project_aware.py
"""Verifica que build_wiki_db.py --project=proxy escribe en ariadna.db
con project_id correctamente y NO toca filas de otros proyectos."""
import shutil
import sqlite3
import subprocess
from pathlib import Path


def test_build_wiki_db_scoped_to_project(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    # Estructura mínima de un proyecto Proxy
    (repo / "projects" / "proxy" / "wiki" / "concepts").mkdir(parents=True)
    (repo / "projects" / "proxy" / "_meta").mkdir(parents=True)
    (repo / "projects" / "proxy" / "wiki" / "concepts" / "shadow.md").write_text(
        "---\npage_id: shadow\npage_type: concept\ncanonical_name: Sombra\n"
        "domain_primary: jung\nrelations:\n  - type: developed_by\n    to: jung\n"
        "aliases:\n  - sombra\n---\n# Sombra\nLa [[jung]] desarrolló este concepto.\n"
    )
    (repo / "wiki" / "_meta").mkdir(parents=True)
    shutil.copy("wiki/_meta/relation_types_core.json", repo / "wiki" / "_meta" / "relation_types_core.json")
    (repo / "data").mkdir()

    # init schema + proyecto
    subprocess.run(
        [".venv/bin/python",
         str(Path("scripts/init_ariadna_db.py").resolve()),
         "--db", str(repo / "data" / "ariadna.db")],
        check=True, capture_output=True, timeout=30,
    )
    conn = sqlite3.connect(str(repo / "data" / "ariadna.db"))
    conn.execute("INSERT INTO projects(project_id, name, created_at) "
                 "VALUES ('proxy', 'Proxy', '2026-05-16T00:00:00+00:00')")
    # Crear OTRO proyecto con una page sintética para verificar aislamiento
    conn.execute("INSERT INTO projects(project_id, name, created_at) "
                 "VALUES ('other', 'Other', '2026-05-16T00:00:00+00:00')")
    conn.execute("INSERT INTO pages(project_id, page_id, page_type, canonical_name, "
                 "file_path, body_md, indexed_at) "
                 "VALUES ('other', 'foo', 'concept', 'Foo', 'concepts/foo.md', '# Foo',"
                 "'2026-05-16T00:00:00+00:00')")
    conn.commit()
    conn.close()

    monkeypatch.chdir(repo)
    result = subprocess.run(
        [".venv/bin/python",
         str(Path("scripts/build_wiki_db.py").resolve()),
         "--project", "proxy"],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"build failed: {result.stderr}"

    conn = sqlite3.connect(str(repo / "data" / "ariadna.db"))
    n_proxy = conn.execute("SELECT COUNT(*) FROM pages WHERE project_id='proxy'").fetchone()[0]
    assert n_proxy == 1
    # 'other' no se ha tocado:
    n_other = conn.execute("SELECT COUNT(*) FROM pages WHERE project_id='other'").fetchone()[0]
    assert n_other == 1
    # FK constraint: relations[0].from_page_id apunta a 'shadow'
    rels = conn.execute("SELECT type, to_page_id FROM relations WHERE project_id='proxy'").fetchall()
    assert ("developed_by", "jung") in rels
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest scripts/test_build_wiki_db_project_aware.py -v
# Expected: FAIL — script doesn't have --project flag
```

- [ ] **Step 3: Apply edits to `scripts/build_wiki_db.py`**

Cambios:

1. **Líneas 47-49** (constants): reemplazar
   ```python
   WIKI_DIR = REPO / "wiki"
   DB_PATH = REPO / "data" / "wiki.db"
   RELATION_TYPES_PATH = WIKI_DIR / "_meta" / "relation_types.json"
   ```
   por
   ```python
   # Resueltos al parsear --project (ver main()):
   PROJECT_ID: str = ""           # set by main()
   WIKI_DIR: Path | None = None   # set by main()
   DB_PATH = REPO / "data" / "ariadna.db"
   RELATION_TYPES_CORE_PATH = REPO / "wiki" / "_meta" / "relation_types_core.json"
   ```

2. **Schema CREATE TABLE** (en el `executescript` del build): **eliminar todo el bloque CREATE TABLE**. Las tablas ya existen en `ariadna.db` (creadas por `init_ariadna_db.py`). El script ahora solo INSERTea (no crea schema).

3. **DELETE statements antes del rebuild** (línea ~253):
   ```python
   # antes (borra todas las filas de las tablas, single-tenant):
   for tbl in ("citations", "body_wikilinks", "relations", "aliases", "pages"):
       conn.execute(f"DELETE FROM {tbl}")

   # después (borra solo las filas de este proyecto):
   for tbl in ("citations", "body_wikilinks", "relations", "aliases", "pages"):
       conn.execute(f"DELETE FROM {tbl} WHERE project_id=?", (PROJECT_ID,))
   ```
   (Las FK ON DELETE CASCADE no aplican porque pages no se borra primero — el orden inverso de citation→body_wikilinks→relations→aliases→pages respeta dependencias.)

4. **Cada INSERT** debe taggear `project_id`:
   ```python
   # ejemplo pages:
   conn.execute(
       "INSERT INTO pages(project_id, page_id, page_type, canonical_name, domain_primary, "
       "file_path, last_compiled, sources_count, review_status, body_md, indexed_at) "
       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
       (PROJECT_ID, page_id, page_type, ...),
   )
   ```
   Y `citations`: la columna se llama ahora `source_id`, no `video_id`:
   ```python
   conn.execute(
       "INSERT INTO citations(project_id, page_id, source_id, timestamp_seconds, title, url) "
       "VALUES (?, ?, ?, ?, ?, ?)",
       (PROJECT_ID, page_id, video_id, ts, title, url),
   )
   ```

5. **argparse** (en `main()`): añadir
   ```python
   parser.add_argument("--project", required=True,
                       help="Project slug (e.g. 'proxy'). Read from projects table at startup.")
   ```
   y al inicio de main:
   ```python
   global PROJECT_ID, WIKI_DIR
   from ariadna.project_config import ProjectConfig
   cfg = ProjectConfig.for_project(args.project)
   PROJECT_ID = args.project
   WIKI_DIR = cfg.wiki_root()
   ```

6. **Queries de drift/broken/citations en el CLI `--query`** (`scripts/build_wiki_db.py` líneas ~290-360 en las funciones `q_drift()`, `q_broken()`, `q_citations()`, `q_backlinks()`, `q_stats()`):
   - Cualquier SQL que diga `citations.video_id` → `citations.source_id`.
   - Cada query SELECT debe filtrar por proyecto: añadir `WHERE project_id = ?` con el slug actual como bind param. Smoke `python scripts/build_wiki_db.py --project=proxy --query=stats` debe devolver los mismos counts pre-migración.

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest scripts/test_build_wiki_db_project_aware.py -v
# Expected: PASS
```

- [ ] **Step 5: Commit**

```bash
git add scripts/build_wiki_db.py scripts/test_build_wiki_db_project_aware.py
git commit -m "feat(build_wiki_db): flag --project, target ariadna.db, scoped UPSERT

Script lee projects/<slug>/wiki/, escribe a data/ariadna.db con
project_id=<slug> en cada fila. Otros proyectos no se tocan. Schema lo
crea init_ariadna_db.py (este script ya no CREATE TABLE).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4.4: `scripts/index_wiki_to_qdrant.py` — per-project + `project_id` payload

> El indexador hoy escanea `wiki/**` y escribe puntos con payload sin `project_id`. Cambios: aceptar `--project=<slug>`, usar `ProjectConfig.wiki_root()`, añadir `project_id` al payload de cada wiki_page indexada. Idempotencia per-proyecto: el delete previo (`delete_by_filter source_type=wiki_page`) se restringe a `AND project_id=<slug>`.

**Files:**
- Modify: `scripts/index_wiki_to_qdrant.py:61` (constant default), CLI, `index_wiki()`, `delete_by_filter` call.

- [ ] **Step 1: Write the failing test** (unit, sin Qdrant real)

```python
# scripts/test_index_wiki_to_qdrant_payload.py
"""Verifica que el payload generado para un wiki page incluye project_id.
Mock del CorpusStore: la task no requiere Qdrant vivo."""
from pathlib import Path
from unittest.mock import MagicMock


def test_wiki_payload_has_project_id(tmp_path, monkeypatch):
    # Mini wiki: 1 .md
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "shadow.md").write_text(
        "---\npage_id: shadow\npage_type: concept\ncanonical_name: Sombra\n"
        "domain_primary: jung\n---\n# Sombra\n"
    )

    from scripts import index_wiki_to_qdrant as m
    pages = m.collect_pages(wiki, tmp_path)
    assert len(pages) == 1
    payload = m.page_to_payload(pages[0], project_id="proxy")  # nuevo helper

    assert payload["project_id"] == "proxy"
    assert payload["source_type"] == "wiki_page"
    assert payload["page_id"] == "shadow"
```

> Si `page_to_payload` no existe como helper aislado en el script actual, extraer la construcción del payload a una función nombrada `page_to_payload(page, *, project_id: str) -> dict` durante la edición (Step 2) — esto facilita el test sin levantar Qdrant.

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest scripts/test_index_wiki_to_qdrant_payload.py -v
# Expected: AttributeError (page_to_payload no existe) o KeyError (project_id no en payload).
```

- [ ] **Step 3: Apply edits**

1. Renombrar `WIKI_DIR_DEFAULT` → eliminado; en su lugar resolver wiki_root vía `ProjectConfig.for_project(args.project).wiki_root()`.

2. **argparse**: añadir
   ```python
   parser.add_argument("--project", required=True, help="Project slug")
   parser.add_argument("--wiki-dir", type=Path, default=None,
                       help="Override wiki dir (default: ProjectConfig(project).wiki_root())")
   ```
   y en main:
   ```python
   from ariadna.project_config import ProjectConfig
   cfg = ProjectConfig.for_project(args.project)
   wiki_dir = args.wiki_dir or cfg.wiki_root()
   ```

3. **Payload**: extraer la construcción del payload a un helper que envuelva `WikiPage.to_payload()` añadiendo `project_id`. Evita re-listar campos y posible divergencia:
   ```python
   def page_to_payload(page: "WikiPage", *, project_id: str) -> dict:
       payload = page.to_payload()       # método existente en WikiPage
       payload["project_id"] = project_id
       return payload
   ```
   El call site dentro de `index_wiki(...)` (línea ~287 del script) cambia de `p.to_payload()` a `page_to_payload(p, project_id=args.project)`.

4. **Delete previo (idempotencia)**: cambiar
   ```python
   n_deleted = store.delete_by_filter({"source_type": "wiki_page"})
   ```
   por
   ```python
   n_deleted = store.delete_by_filter({"source_type": "wiki_page", "project_id": args.project})
   ```
   `CorpusStore.delete_by_filter` ya acepta dict de filtros y los une con AND (ver `ariadna/storage.py:175-189`); no requiere cambio de firma.

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest scripts/test_index_wiki_to_qdrant_payload.py -v
# Expected: 1 passed
```

- [ ] **Step 5: Verificar smoke con dry-run**

```bash
.venv/bin/python scripts/index_wiki_to_qdrant.py --project proxy --dry-run
# Expected: log "Wiki dir: .../projects/proxy/wiki", N pages enumeradas,
# no errores. Sin --dry-run NO ejecutar en este task — el run real va en Chunk 9.
```

- [ ] **Step 6: Commit**

```bash
git add scripts/index_wiki_to_qdrant.py scripts/test_index_wiki_to_qdrant_payload.py
git commit -m "feat(index_wiki): flag --project, payload project_id, delete scoped

Indexador taggea cada wiki_page con project_id en payload Qdrant. El
delete idempotente previo al rebuild se restringe a (source_type=wiki_page,
project_id=<slug>) para no tocar puntos de otros proyectos.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4.5: `scripts/extract_video_themes.py` — RUNS_DIR per-proyecto + cargar prompts del .md

> Hoy el script asume `wiki/_meta/extraction_runs/` y tiene los prompts hard-coded como constantes. Cambios:
> - `RUNS_DIR = META / "extraction_runs"` → resuelto vía `ProjectConfig.for_project(args.project).extraction_runs_dir()`.
> - `WIKI = REPO / "wiki"` → `cfg.wiki_root()`.
> - `SUBAGENT_SYSTEM_PROMPT` y `SUBAGENT_SYNTHESIS_SYSTEM_PROMPT` constantes → leídos en runtime con `cfg.subagent_prompts()`. Las constantes se eliminan del Python.
> - Acepta `--project` en CLI (default 'proxy' para no romper invocaciones pre-existentes durante la migración).

**Files:**
- Modify: `scripts/extract_video_themes.py` líneas 66-69, 953-976, 1187, 1226-1257, 1407, CLI argparse.
- Update: `scripts/test_subagent_prompt_extraction.py` (Chunk 3) — tras eliminar las constantes Python, el test debe **borrarse o re-orientarse** (ver Step 4 abajo).

- [ ] **Step 1: Apply edits**

1. **Constants block (líneas 66-69)**: reemplazar
   ```python
   WIKI = REPO / "wiki"
   META = WIKI / "_meta"
   RUNS_DIR = META / "extraction_runs"
   ```
   por placeholders que se rellenan en main():
   ```python
   # Resueltos al parsear --project (ver main()):
   PROJECT_ID: str = ""
   WIKI: Path | None = None
   META: Path | None = None
   RUNS_DIR: Path | None = None
   SUBAGENT_SYSTEM_PROMPT: str = ""
   SUBAGENT_SYNTHESIS_SYSTEM_PROMPT: str = ""
   ```

2. **Eliminar las dos constantes inline** (líneas 953-976 y 1226-1257). Se cargan dinámicamente en main():
   ```python
   def _load_project_runtime(project_id: str) -> None:
       global PROJECT_ID, WIKI, META, RUNS_DIR, SUBAGENT_SYSTEM_PROMPT, SUBAGENT_SYNTHESIS_SYSTEM_PROMPT
       from ariadna.project_config import ProjectConfig
       cfg = ProjectConfig.for_project(project_id)
       PROJECT_ID = project_id
       WIKI = cfg.wiki_root()
       META = (WIKI.parent / "_meta")
       RUNS_DIR = cfg.extraction_runs_dir()
       prompts = cfg.subagent_prompts()
       SUBAGENT_SYSTEM_PROMPT = prompts["concept_author_entity_work"]
       if "synthesis" in prompts:
           SUBAGENT_SYNTHESIS_SYSTEM_PROMPT = prompts["synthesis"]
       else:
           # Default global no incluye synthesis section. Aviso explícito porque la
           # tarea de auto-promoción de tesis usaría el concept prompt — semánticamente
           # incorrecto. Crear projects/<slug>/_meta/subagent_prompt.md con la sección
           # synthesis antes de habilitar thesis_candidate gate en este proyecto.
           print(
               f"WARN: project {project_id!r} has no 'synthesis' subagent prompt; "
               f"falling back to concept_author_entity_work. Add a synthesis section "
               f"to projects/{project_id}/_meta/subagent_prompt.md to silence this warning.",
               file=sys.stderr,
           )
           SUBAGENT_SYNTHESIS_SYSTEM_PROMPT = SUBAGENT_SYSTEM_PROMPT
   ```

3. **CLI argparse**: añadir
   ```python
   parser.add_argument("--project", default="proxy",
                       help="Project slug (default proxy durante migración)")
   ```
   y al inicio de main, **antes** de cualquier acceso a WIKI/META/RUNS_DIR:
   ```python
   _load_project_runtime(args.project)
   ```

4. Las referencias a `SUBAGENT_SYSTEM_PROMPT` y `SUBAGENT_SYNTHESIS_SYSTEM_PROMPT` en las líneas 1187 y 1407 (los call-sites de `invoke_claude`) ya funcionan porque `_load_project_runtime` las setea como globales antes del primer uso. No requieren cambios.

- [ ] **Step 2: Verificar que el script importa sin errores**

```bash
.venv/bin/python -c "import scripts.extract_video_themes as m; print('ok')"
# Expected: ok
.venv/bin/python scripts/extract_video_themes.py --help | head -10
# Expected: muestra --project en el output del help
```

- [ ] **Step 3: Actualizar/eliminar el test de drift de Chunk 3**

El test `scripts/test_subagent_prompt_extraction.py` espera que las constantes Python existan. Tras esta task, ya NO existen — el .md es la fuente de verdad. **Borrar** el test:

```bash
git rm scripts/test_subagent_prompt_extraction.py
```

Y añadir un test ligero que valide que `cfg.subagent_prompts()` devuelve ambos kinds para Proxy:

```python
# tests/test_subagent_prompts_loaded.py
"""Tras Chunk 4, los prompts viven en projects/proxy/_meta/subagent_prompt.md
y se cargan vía ProjectConfig. Requiere data/ariadna.db con proyecto 'proxy'
(creado en Chunk 2)."""
from pathlib import Path
import pytest

REQUIRES_DB = Path("data/ariadna.db")

@pytest.mark.skipif(not REQUIRES_DB.exists(),
                    reason="data/ariadna.db ausente; correr Chunk 2 primero")
def test_proxy_subagent_prompts_loaded():
    from ariadna.project_config import ProjectConfig
    cfg = ProjectConfig.for_project("proxy")
    prompts = cfg.subagent_prompts()
    assert "concept_author_entity_work" in prompts
    assert "synthesis" in prompts
    # Frases únicas de cada prompt (anti-drift contra cambios silenciosos):
    assert "constructor focalizado" in prompts["concept_author_entity_work"]
    assert "auto_promoted_synthesis" in prompts["synthesis"]
    assert "thesis_candidate" in prompts["synthesis"]
```

- [ ] **Step 4: Run pytest**

```bash
.venv/bin/python -m pytest tests/test_subagent_prompts_loaded.py -v
# Expected: 1 passed (asume cwd = repo root y data/ariadna.db existe con 'proxy')
```

- [ ] **Step 5: Commit**

```bash
git add scripts/extract_video_themes.py tests/test_subagent_prompts_loaded.py
git rm scripts/test_subagent_prompt_extraction.py
git commit -m "refactor(extract_video_themes): runtime resolution + prompts del .md

WIKI/META/RUNS_DIR/SUBAGENT_*_PROMPT son ahora globales que main() rellena
desde ProjectConfig.for_project(args.project). Las dos constantes inline
desaparecen del .py — única fuente de verdad: projects/<slug>/_meta/subagent_prompt.md.
Test de drift de Chunk 3 se sustituye por test de carga.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4.6: `ariadna/policy_filters.py` + `ariadna/build_index.py` — aceptar `project_id`

> `build_policy_filter_map` acepta un `extraction_runs_dir` arbitrario; basta con que el caller le pase el path correcto. `ariadna/build_index.py` tiene un default global `DEFAULT_EXTRACTION_RUNS` que apunta a la ruta vieja. **Nota:** la función pública del módulo se llama `build(...)` (no `build_index`); ver `ariadna/build_index.py:40`. Cambios:
> - `policy_filters.build_policy_filter_map`: añadir parámetro opcional `project_id` para incluirlo en el log/contexto (no afecta lógica).
> - `build_index.DEFAULT_EXTRACTION_RUNS`: eliminar el global; la función `build()` requiere ahora `project_id` y deriva el path con `ProjectConfig`.
> - Auditoría de callers: `grep -rn "from ariadna.build_index\|ariadna.build_index.build" ariadna/ scripts/` — único caller es `main()` del propio módulo (CLI). El `build_index(client, model)` de `scripts/run_eval_pilot.py:64` es una función local no relacionada (no importa de `ariadna.build_index`).

**Files:**
- Modify: `ariadna/policy_filters.py:24-30`
- Modify: `ariadna/build_index.py:25` (eliminar DEFAULT_EXTRACTION_RUNS), `:40-46` (signature de `build()`), `:61` (call site de `build_policy_filter_map`), `:106-112` (payload construction)

- [ ] **Step 1: Apply edits**

`ariadna/policy_filters.py`:
```python
def build_policy_filter_map(
    extraction_runs_dir: Path,
    project_id: str | None = None,  # ← nuevo, solo para logging
) -> dict[tuple[str, int], dict]:
    """..."""
    if project_id:
        log.info("policy_filter_map scope: project=%s, dir=%s", project_id, extraction_runs_dir)
    # resto sin cambios
```

`ariadna/build_index.py` (función pública: `build()`, no `build_index`):
```python
# Eliminar línea 25:
# DEFAULT_EXTRACTION_RUNS = Path(__file__).resolve().parent.parent / "wiki" / "_meta" / "extraction_runs"

# build() signature (líneas 40-46):
def build(
    corpus_path: Path,
    project_id: str,                  # ← nuevo, requerido (insertar como 2º param)
    recreate: bool = False,
    batch_size: int = 64,
    dry_run: bool = False,
    extraction_runs_dir: Path | None = None,
) -> None:
    from ariadna.project_config import ProjectConfig
    cfg = ProjectConfig.for_project(project_id)
    extraction_runs_dir = extraction_runs_dir or cfg.extraction_runs_dir()
    policy_map = build_policy_filter_map(extraction_runs_dir, project_id=project_id)
    # resto sin cambios hasta el loop de payloads.
```

**Payload (línea 108)**: añadir `project_id` al dict de payload:
```python
for c in batch_chunks:
    payload = c.to_payload()
    payload["project_id"] = project_id     # ← nuevo
    pf = policy_map.get((c.video_id, c.timestamp_seconds))
    if pf is not None:
        payload["policy_filter"] = pf
    payloads.append(payload)
```

**CLI `main()` (línea 121+)**: añadir `--project` al argparse y pasarlo a `build(...)`. Default `proxy` para no romper invocaciones existentes durante la migración.

- [ ] **Step 2: Verificar que `build` importa con la nueva firma**

```bash
.venv/bin/python -c "from ariadna.build_index import build; import inspect; print(list(inspect.signature(build).parameters))"
# Expected: incluye 'project_id' en la lista
```

- [ ] **Step 3: Commit**

```bash
git add ariadna/policy_filters.py ariadna/build_index.py
git commit -m "refactor(build_index): build() requiere project_id; sin defaults globales

policy_filters.build_policy_filter_map gana param project_id (solo logging).
build() (la función pública del módulo) resuelve extraction_runs_dir vía
ProjectConfig si no se pasa, y añade project_id al payload de cada chunk.
DEFAULT_EXTRACTION_RUNS hardcoded eliminado.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 4.7: `scripts/validate_wiki_relations.py` — flag `--project`

> Validador hoy escanea `wiki/**/*.md` directamente. Cambios: aceptar `--project`, escanear `projects/<slug>/wiki/**/*.md` vía `ProjectConfig.wiki_root()`. No requiere DB cambios (lee solo filesystem + frontmatter).

**Files:**
- Modify: `scripts/validate_wiki_relations.py:33-35`, CLI.

- [ ] **Step 1: Apply edits**

```python
# Eliminar líneas 34-35 (constants top-level):
# WIKI = REPO / "wiki"
# META = WIKI / "_meta"

# Convertir a placeholders top-level que main() rellena (mismo patrón que extract_video_themes.py):
WIKI: Path | None = None
META: Path | None = None

# argparse:
parser.add_argument("--project", required=True, help="Project slug to validate")

# Al inicio de main(), antes de cualquier uso de WIKI/META:
def main() -> int:
    args = parser.parse_args()
    global WIKI, META
    from ariadna.project_config import ProjectConfig
    cfg = ProjectConfig.for_project(args.project)
    WIKI = cfg.wiki_root()
    META = WIKI.parent / "_meta"
    # ... resto sin cambios; helpers que referencian WIKI globalmente siguen funcionando.
```

**Patrón único elegido: globales rellenadas por main()**, no paso de argumento. Coincide con la forma en que `scripts/extract_video_themes.py` (Task 4.5) resuelve sus paths — mantiene la consistencia entre los dos scripts grandes del módulo.

- [ ] **Step 2: Smoke test**

```bash
.venv/bin/python scripts/validate_wiki_relations.py --project proxy --help | head -5
# Expected: --project flag visible
.venv/bin/python scripts/validate_wiki_relations.py --project proxy
# Expected: exit 0 (mismos warnings que pre-migración, ningún error nuevo).
# Si introduces errors, abortar y diagnosticar — algo está mal con el path.
```

- [ ] **Step 3: Commit**

```bash
git add scripts/validate_wiki_relations.py
git commit -m "feat(validate_wiki_relations): flag --project + scan projects/<slug>/wiki

Validador es project-aware. exit 0 contra projects/proxy/wiki/ confirma que
el grafo migrado es idéntico (mismos wikilinks rotos identificados como
candidates a próximo batch).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 5: Qdrant backfill `project_id`

> Hasta ahora `data/qdrant/` tiene ~6442 puntos con payload SIN `project_id`. Esta task escribe un script idempotente (`scripts/migrate_qdrant_project_id.py`) que recorre la colección **seleccionando** puntos sin la key (filtro `must=[IsEmpty(project_id)]`) y les añade `project_id: 'proxy'` vía `client.set_payload`. Resume-safe por construcción: una vez taggeado un punto, el mismo filtro lo excluye en la siguiente iteración del scroll, así que re-ejecutar el script continúa donde se cortó. La **verificación** al final usa el dual: count con `must=[IsEmpty(project_id)]` debe ser 0 (equivalente a `must_not=[IsEmpty]` cubriendo el universo, ver spec sección 10 riesgo 6).
>
> Solo se invoca `set_payload`; no se tocan IDs ni vectores. Los `chunk_id_int` del baseline (Chunk 1) siguen siendo válidos para la verificación funcional post-migración (spec sección 8.1 paso 12 nota "Estabilidad de Qdrant IDs").
>
> **Pre-condición:** Chunks 2-4 completados. **Importante**: durante este chunk el MCP server y cualquier worker que escriba a Qdrant deben estar parados (pre-flight check 1 ya cubre esto a nivel de plan; en este chunk se reverifica explícitamente).
>
> **Scope:** solo el backfill del payload. La verificación end-to-end del Phase 1 (count post-backfill, igualdad funcional con baseline) vive en Chunk 9.

### Task 5.1: `scripts/migrate_qdrant_project_id.py` — backfill batched + resume-safe

**Files:**
- Create: `scripts/migrate_qdrant_project_id.py`
- Test: `scripts/test_migrate_qdrant_project_id.py`

- [ ] **Step 1: Write the failing test** (mock client, sin Qdrant real)

```python
# scripts/test_migrate_qdrant_project_id.py
"""Verifica la lógica de paginación + set_payload sobre un cliente Qdrant fake.
NO levanta Qdrant real (eso vive en el smoke al final del chunk)."""
from unittest.mock import MagicMock, call

import pytest


def _make_fake_client(initial_pts_without_pid, ids_per_batch=2):
    """Cliente fake que devuelve `initial_pts_without_pid` puntos sin project_id
    en batches de `ids_per_batch`, y se 'vacía' una vez set_payload ha sido
    invocado sobre todos ellos."""
    client = MagicMock()
    state = {"pending": list(initial_pts_without_pid)}

    def fake_scroll(collection_name, scroll_filter, limit, **kw):
        batch = state["pending"][:limit]
        next_offset = state["pending"][limit] if len(state["pending"]) > limit else None
        # devolvemos (points, offset) — points son objetos con .id
        pts = [MagicMock(id=pid) for pid in batch]
        return pts, next_offset

    def fake_set_payload(collection_name, payload, points, **kw):
        # remueve los ids tageados de pending
        ids_set = set(points)
        state["pending"] = [p for p in state["pending"] if p not in ids_set]

    def fake_count(collection_name, count_filter=None, exact=True):
        # Si filtro must_not IsEmpty(project_id), devuelve los pending
        # (suficiente para el test del verify-only mode):
        r = MagicMock()
        r.count = len(state["pending"]) if count_filter else len(initial_pts_without_pid)
        return r

    client.scroll = fake_scroll
    client.set_payload = fake_set_payload
    client.count = fake_count
    return client, state


def test_backfill_tags_all_points_idempotent(monkeypatch):
    from scripts import migrate_qdrant_project_id as m

    client, state = _make_fake_client([1001, 1002, 1003, 1004, 1005])
    # primera pasada
    n1 = m.backfill(client, collection="ariadna_corpus", project_id="proxy",
                    batch_size=2)
    assert n1 == 5
    assert state["pending"] == []
    # segunda pasada (idempotente: pending vacío → 0)
    n2 = m.backfill(client, collection="ariadna_corpus", project_id="proxy",
                    batch_size=2)
    assert n2 == 0


def test_count_pending_uses_isempty_filter():
    """count_pending debe invocar client.count con un Filter must=IsEmpty(project_id)."""
    from scripts import migrate_qdrant_project_id as m

    client = MagicMock()
    client.count.return_value = MagicMock(count=42)
    n = m.count_pending(client, collection="ariadna_corpus")
    assert n == 42
    # El call_args[1]['count_filter'] debe ser un Filter con must=[IsEmptyCondition(...)]
    call_kwargs = client.count.call_args.kwargs
    assert call_kwargs["exact"] is True
    flt = call_kwargs["count_filter"]
    assert flt.must is not None and len(flt.must) == 1
    # IsEmptyCondition tiene un attr `is_empty.key`
    cond = flt.must[0]
    assert getattr(cond.is_empty, "key", None) == "project_id"


def test_backfill_resumes_on_partial(monkeypatch):
    """Simula que el primer call de scroll devuelve menos del total
    (e.g. proceso killeado a mitad). La siguiente invocación recoge el resto."""
    from scripts import migrate_qdrant_project_id as m

    client, state = _make_fake_client([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    # batch_size 3 — los primeros 3 se tagean, simulamos kill después de set_payload
    # → segunda invocación de backfill ve 7 pending y termina:
    n1 = m.backfill(client, collection="ariadna_corpus", project_id="proxy",
                    batch_size=3, max_batches=1)
    assert n1 == 3
    assert len(state["pending"]) == 7

    n2 = m.backfill(client, collection="ariadna_corpus", project_id="proxy",
                    batch_size=3)
    assert n2 == 7
    assert state["pending"] == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest scripts/test_migrate_qdrant_project_id.py -v
# Expected: ModuleNotFoundError (scripts.migrate_qdrant_project_id no existe)
```

- [ ] **Step 3: Implement `scripts/migrate_qdrant_project_id.py`**

```python
#!/usr/bin/env python3
"""Backfill de `project_id` en payload Qdrant.

Itera sobre todos los puntos de la colección filtrando los que NO tienen
`project_id` (vía IsEmptyCondition) y los taggea con el slug pasado por
`--project-id` (default 'proxy'). Resume-safe: re-ejecutar continúa donde
se cortó. Idempotente: una segunda corrida sobre colección ya taggeada es
no-op (0 puntos procesados).

Uso:
    python scripts/migrate_qdrant_project_id.py
    python scripts/migrate_qdrant_project_id.py --project-id proxy --batch-size 500
    python scripts/migrate_qdrant_project_id.py --verify-only     # solo conteo, no escribe
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Filter,
    IsEmptyCondition,
    PayloadField,
)

from ariadna.config import QDRANT_PATH, COLLECTION_NAME  # ajustar a los nombres reales en ariadna/config.py


def _without_project_filter() -> Filter:
    """Filter para puntos cuyo payload NO tiene la key 'project_id'."""
    return Filter(
        must=[IsEmptyCondition(is_empty=PayloadField(key="project_id"))],
    )


def count_pending(client: Any, collection: str) -> int:
    """Cuenta cuántos puntos quedan sin project_id."""
    return client.count(
        collection_name=collection,
        count_filter=_without_project_filter(),
        exact=True,
    ).count


def backfill(
    client: Any,
    collection: str,
    project_id: str,
    batch_size: int = 500,
    max_batches: int | None = None,
) -> int:
    """Recorre la colección en batches y taggea cada batch con set_payload.

    Devuelve el número total de puntos taggeados en esta invocación.
    `max_batches=N` corta tras N batches (útil para tests/limit en runs grandes).
    """
    total = 0
    batch_idx = 0
    while True:
        if max_batches is not None and batch_idx >= max_batches:
            return total
        pts, _next = client.scroll(
            collection_name=collection,
            scroll_filter=_without_project_filter(),
            limit=batch_size,
            with_payload=False,
            with_vectors=False,
        )
        if not pts:
            return total
        ids = [p.id for p in pts]
        client.set_payload(
            collection_name=collection,
            payload={"project_id": project_id},
            points=ids,
        )
        total += len(ids)
        batch_idx += 1
        # log progresivo cada N batches
        if batch_idx % 10 == 0:
            print(f"  batch {batch_idx}: total taggeados = {total}", flush=True)
    # unreachable, ruff: el while True termina vía return arriba


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project-id", default="proxy")
    p.add_argument("--collection", default=COLLECTION_NAME)
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument("--verify-only", action="store_true",
                   help="Solo cuenta puntos sin project_id; no escribe.")
    p.add_argument("--max-batches", type=int, default=None,
                   help="Corta tras N batches (test/resume).")
    args = p.parse_args()

    client = QdrantClient(path=str(QDRANT_PATH))

    pending = count_pending(client, args.collection)
    print(f"pending (sin project_id): {pending}")
    if args.verify_only:
        return 0 if pending == 0 else 1

    if pending == 0:
        print("ok: nothing to backfill")
        return 0

    print(f"backfilling {pending} points to project_id={args.project_id!r}...")
    t0 = time.time()
    n = backfill(client, args.collection, args.project_id,
                 batch_size=args.batch_size, max_batches=args.max_batches)
    elapsed = time.time() - t0
    print(f"done: tagged {n} points in {elapsed:.1f}s")

    # Verificación final
    final = count_pending(client, args.collection)
    if final == 0:
        print("ok: 0 points without project_id")
        return 0
    print(f"WARN: {final} points still without project_id; re-run to continue", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

> Verificar al implementar: `ariadna/config.py` exporta los nombres usados (`QDRANT_PATH`, `COLLECTION_NAME`). Si los nombres difieren, ajustar el import (el patrón es local a este script — no introducir nuevas exports en `config.py`).

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest scripts/test_migrate_qdrant_project_id.py -v
# Expected: 3 passed
```

- [ ] **Step 5: Commit (todavía sin ejecutar contra Qdrant real)**

```bash
git add scripts/migrate_qdrant_project_id.py scripts/test_migrate_qdrant_project_id.py
git commit -m "feat(migration): script backfill Qdrant project_id idempotente

Recorre la colección filtrando IsEmpty(project_id) y aplica set_payload
batched. Resume-safe por construcción: re-ejecutar continúa por los
puntos pendientes. --verify-only sin escritura. Test con cliente fake.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 5.2: Ejecutar el backfill contra Qdrant real

> Pre-flight: el MCP server y extract_video_themes deben estar parados (la pre-flight check del plan los cubre, pero re-verificamos aquí). Tras la ejecución, count de puntos sin `project_id` debe ser 0.

- [ ] **Step 1: Verificar pre-condiciones**

```bash
pgrep -af "ariadna.mcp_server" && echo "STOP: server activo" || echo "ok: server parado"
pgrep -af "scripts/extract_video_themes" && echo "STOP: run activo" || echo "ok: sin run"
# Ambos deben dar "ok"
```

- [ ] **Step 2: Snapshot pre-backfill**

```bash
.venv/bin/python scripts/migrate_qdrant_project_id.py --verify-only
# Expected: "pending (sin project_id): ~6442" (puntos totales pre-migración).
```

- [ ] **Step 3: Ejecutar el backfill**

```bash
.venv/bin/python scripts/migrate_qdrant_project_id.py --project-id proxy
# Expected: "pending (sin project_id): 6442" → "tagged 6442 points in <Xs>" → "ok: 0 points without project_id"
# Tiempo estimado: ~minuto-y-pico (batches de 500 sobre embedded Qdrant local).
```

- [ ] **Step 4: Verificación post-backfill**

```bash
# count total no cambia (no se añaden ni quitan puntos):
.venv/bin/python -c "
from qdrant_client import QdrantClient
from ariadna.config import QDRANT_PATH, COLLECTION_NAME
c = QdrantClient(path=str(QDRANT_PATH))
print('total points:', c.count(collection_name=COLLECTION_NAME).count)
"
# Expected: igual al baseline (typ ~6442).

# Y todos tienen project_id:
.venv/bin/python scripts/migrate_qdrant_project_id.py --verify-only
# Expected: "pending (sin project_id): 0"; exit 0.

# Spot-check: scrolling con must={project_id=proxy} debe devolver todos los puntos:
.venv/bin/python -c "
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
from ariadna.config import QDRANT_PATH, COLLECTION_NAME
c = QdrantClient(path=str(QDRANT_PATH))
n = c.count(collection_name=COLLECTION_NAME,
            count_filter=Filter(must=[FieldCondition(key='project_id', match=MatchValue(value='proxy'))])).count
print('proxy points:', n)
"
# Expected: igual al total (typ ~6442).
```

- [ ] **Step 5: Commit** (registro del estado de la ejecución; el backfill no produce archivos versionables, solo cambia el estado interno de `data/qdrant/` que está gitignorado, así que el commit es un marker simbólico — opcional)

```bash
# Solo si quieres dejar una marca git del paso de migración ejecutado:
git commit --allow-empty -m "chore(migration): backfill Qdrant project_id ejecutado

~6442 puntos taggeados con project_id='proxy'. Idempotente: re-ejecutar
no cambia nada. data/qdrant/ es gitignorado; este commit es marker
simbólico de la ejecución.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Si decides no marcar el step en git, sigue al siguiente chunk; el smoke de verificación final está en Chunk 9.

---

## Chunk 6: Tools MCP write nuevas

> Implementa la lógica de las tres tools de escritura del MCP server (spec sección 6.1): `create_project`, `add_to_research_queue` y `cancel_request`. El módulo `ariadna/mcp_tools_write.py` aísla la validación + I/O en funciones `*_impl(conn, ...)` que reciben la conexión SQLite por inyección — testables sin levantar el server. **El wiring con `@mcp.tool` en `ariadna/mcp_server.py` se difiere a Chunk 8** (junto con las tools modificadas + el cleanup de las retiradas, para un solo cambio coherente en el server). No procesa la cola — solo añade ítems (los workers son scope futuro).
>
> **Nota sobre slugs en spec:** el regex de spec 6.5 (`^[a-z][a-z0-9-]{1,40}[a-z0-9]$`) prohíbe underscores. Los ejemplos de spec sec 9 fase 2 (`test_e`, `test_combo`, ...) son inconsistentes con su propio regex — los tests de este chunk usan kebab-case (`test-e`, `test-combo`, ...) para respetar el regex. Spec necesita un fix retrospectivo en sus ejemplos.
>
> **Pre-condición:** Chunks 2-5 completados (SQLite + projects layout + Qdrant taggeado). `ProjectConfig` disponible para validación.

### Task 6.1: Helpers de validación + auto-detección

> Funciones puras testables: `validate_slug`, `detect_source_type`, `_seed_meta_files`, `_inherit_meta_files`. Sin estado, sin DB.

**Files:**
- Create: `ariadna/mcp_tools_write.py`
- Test: `tests/test_mcp_tools_write_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mcp_tools_write_helpers.py
"""Helpers puros usados por las tools de escritura."""
import pytest


@pytest.mark.parametrize("slug, ok", [
    ("proxy", True),
    ("tesis-doctorado", True),
    ("a1b2c3", True),
    ("raspberry-gadget", True),
    ("Proxy", False),         # uppercase
    ("test_underscore", False),  # underscore not allowed
    ("test e", False),         # space
    ("-leading", False),
    ("trailing-", False),
    ("a", False),               # too short (regex {1,40} on body → len ≥ 3)
    ("ab", False),              # still too short
    ("abc", True),              # len 3 ok
    ("123abc", False),          # starts with digit
    ("test--double", True),     # double hyphen ok (regex no forbids)
    ("", False),
])
def test_validate_slug(slug, ok):
    from ariadna.mcp_tools_write import validate_slug
    if ok:
        assert validate_slug(slug) is None, f"slug {slug!r} should be valid"
    else:
        err = validate_slug(slug)
        assert err is not None and err["code"] == "SLUG_INVALID"


@pytest.mark.parametrize("url, expected", [
    ("https://youtube.com/watch?v=abc", "youtube"),
    ("https://youtu.be/abc", "youtube"),
    ("https://arxiv.org/abs/2301.00001", "paper"),
    ("https://doi.org/10.1234/foo", "paper"),
    ("https://example.com/paper.pdf", "pdf"),
    ("https://example.com/paper.PDF", "pdf"),
    ("https://example.com/", "web"),
    ("not-a-url", "unknown"),
    ("", "unknown"),
])
def test_detect_source_type(url, expected):
    from ariadna.mcp_tools_write import detect_source_type
    assert detect_source_type(url) == expected
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_mcp_tools_write_helpers.py -v
# Expected: ModuleNotFoundError
```

- [ ] **Step 3: Implement `ariadna/mcp_tools_write.py`** (helpers — el resto se añade en tasks siguientes)

```python
"""Lógica de las tools MCP write: create_project, add_to_research_queue, cancel_request.

Separado de mcp_server.py para tests unitarios: el módulo expone funciones puras
+ funciones que reciben una `sqlite3.Connection` (inyectable en tests sin levantar
el server).
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
WIKI_META = REPO / "wiki" / "_meta"
PROJECTS_ROOT = REPO / "projects"

SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}[a-z0-9]$")
VALID_SOURCE_TYPES = {"youtube", "paper", "web", "pdf", "unknown"}


# --- validación pura ---------------------------------------------------------

def validate_slug(slug: str) -> dict | None:
    if not slug or not SLUG_RE.fullmatch(slug):
        return {
            "error": (
                f"slug {slug!r} no es válido. Regex requerida: "
                r"^[a-z][a-z0-9-]{1,40}[a-z0-9]$"
            ),
            "code": "SLUG_INVALID",
        }
    return None


def detect_source_type(url: str) -> str:
    if not url:
        return "unknown"
    u = url.strip()
    if "youtube.com/watch" in u or "youtu.be/" in u:
        return "youtube"
    if "arxiv.org/" in u or "doi.org/" in u:
        return "paper"
    if u.lower().endswith(".pdf"):
        return "pdf"
    if u.startswith("http://") or u.startswith("https://"):
        return "web"
    return "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_mcp_tools_write_helpers.py -v
# Expected: ~25 passed (combinación de parametrize)
```

- [ ] **Step 5: Commit**

```bash
git add ariadna/mcp_tools_write.py tests/test_mcp_tools_write_helpers.py
git commit -m "feat(mcp): helpers de validación y auto-detección para tools write

validate_slug (regex spec sección 6.5) + detect_source_type (spec 6.6).
Funciones puras testables que las tools create_project y
add_to_research_queue invocarán. Sin DB, sin estado.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 6.2: `create_project` — crear estructura mínima + opciones seed/inherit

> Crea el directorio `projects/<slug>/{_meta,wiki/{concepts,authors,entities/{works,institutions},synthesis}}/` con `.gitkeep` en cada subdir wiki vacío + `relation_types_ext.json` (`{"types": {}}`), `INDEX.md` placeholder, `extraction_runs/` dir. Si `seed_from_templates=True`: copia `wiki/_meta/*_default.*` a `projects/<slug>/_meta/<name>.<ext>`. Si `inherit_from=<other_slug>`: copia los archivos editoriales del proyecto padre. Ambas opciones son **mutuamente excluyentes** (INCOMPATIBLE_OPTIONS).

**Files:**
- Modify: `ariadna/mcp_tools_write.py` (añadir `create_project_impl`)
- Test: `tests/test_create_project.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_create_project.py
"""create_project_impl: crea estructura mínima + opciones seed/inherit."""
import json
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    # Mínima estructura: wiki/_meta/*_default.* y projects/proxy/_meta/* (padre potencial)
    (tmp_path / "wiki" / "_meta").mkdir(parents=True)
    (tmp_path / "wiki" / "_meta" / "scope_default.md").write_text("# default scope\n")
    (tmp_path / "wiki" / "_meta" / "topic_filters_default.json").write_text("{}")
    (tmp_path / "wiki" / "_meta" / "canonical_whitelist_default.json").write_text("{}")
    (tmp_path / "wiki" / "_meta" / "subagent_prompt_default.md").write_text("default prompt")

    (tmp_path / "projects" / "proxy" / "_meta").mkdir(parents=True)
    (tmp_path / "projects" / "proxy" / "_meta" / "scope.md").write_text("# proxy scope\n")
    (tmp_path / "projects" / "proxy" / "_meta" / "topic_filters.json").write_text("{}")
    (tmp_path / "projects" / "proxy" / "_meta" / "canonical_whitelist.json").write_text("{}")
    (tmp_path / "projects" / "proxy" / "_meta" / "subagent_prompt.md").write_text("proxy prompt")

    db = tmp_path / "data" / "ariadna.db"
    db.parent.mkdir()
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE projects(project_id TEXT PRIMARY KEY, name TEXT NOT NULL,
            description TEXT, created_at TEXT NOT NULL, archived_at TEXT,
            config_version TEXT NOT NULL DEFAULT '1.0');
        INSERT INTO projects(project_id, name, created_at)
            VALUES ('proxy', 'Proxy', '2026-05-16T00:00:00+00:00');
    """)
    conn.commit()
    conn.close()
    monkeypatch.chdir(tmp_path)
    # Monkeypatch REPO en el módulo
    import ariadna.mcp_tools_write as m
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "WIKI_META", tmp_path / "wiki" / "_meta")
    monkeypatch.setattr(m, "PROJECTS_ROOT", tmp_path / "projects")
    return tmp_path


def _open(repo: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(repo / "data" / "ariadna.db"))


def test_create_project_basic(fake_repo):
    from ariadna.mcp_tools_write import create_project_impl
    conn = _open(fake_repo)
    out = create_project_impl(conn, slug="test-e", name="Test E", description="desc")
    conn.close()

    assert out["project_id"] == "test-e"
    # paths_created lista las rutas relativas creadas — verificar shape + miembros clave
    pc = out["paths_created"]
    assert isinstance(pc, list) and len(pc) >= 6  # 5 wiki subdirs + _meta
    assert "projects/test-e/wiki/concepts" in pc
    assert "projects/test-e/wiki/entities/works" in pc
    assert "projects/test-e/_meta" in pc
    # Estructura wiki + meta con .gitkeep en subdirs vacíos:
    base = fake_repo / "projects" / "test-e"
    for sub in ["wiki/concepts", "wiki/authors", "wiki/entities/works",
                "wiki/entities/institutions", "wiki/synthesis", "_meta/extraction_runs"]:
        assert (base / sub).is_dir()
    for sub in ["wiki/concepts", "wiki/authors", "wiki/entities/works",
                "wiki/entities/institutions", "wiki/synthesis"]:
        assert (base / sub / ".gitkeep").is_file()
    assert (base / "_meta" / "relation_types_ext.json").is_file()
    rext = json.loads((base / "_meta" / "relation_types_ext.json").read_text())
    # Shape spec sec 5.3: types como lista vacía. Metadata extra (version/schema_version/description)
    # se preserva para consistencia con el placeholder de Proxy (Chunk 3 Task 3.6).
    assert rext["types"] == []
    assert rext["version"] == "1.0"
    assert (base / "_meta" / "INDEX.md").is_file()
    # SQLite tiene la fila:
    conn = _open(fake_repo)
    row = conn.execute("SELECT name, description FROM projects WHERE project_id='test-e'").fetchone()
    conn.close()
    assert row == ("Test E", "desc")


def test_create_project_duplicate_slug(fake_repo):
    from ariadna.mcp_tools_write import create_project_impl
    conn = _open(fake_repo)
    out = create_project_impl(conn, slug="proxy", name="Dupe")
    conn.close()
    assert out.get("code") == "SLUG_DUPLICATE"


def test_create_project_invalid_slug(fake_repo):
    from ariadna.mcp_tools_write import create_project_impl
    conn = _open(fake_repo)
    out = create_project_impl(conn, slug="Bad_Slug", name="X")
    conn.close()
    assert out["code"] == "SLUG_INVALID"


def test_create_project_incompatible_options(fake_repo):
    from ariadna.mcp_tools_write import create_project_impl
    conn = _open(fake_repo)
    out = create_project_impl(conn, slug="test-combo", name="X",
                              seed_from_templates=True, inherit_from="proxy")
    conn.close()
    assert out["code"] == "INCOMPATIBLE_OPTIONS"
    # No state created:
    assert not (fake_repo / "projects" / "test-combo").exists()


def test_create_project_seed_from_templates(fake_repo):
    from ariadna.mcp_tools_write import create_project_impl
    conn = _open(fake_repo)
    out = create_project_impl(conn, slug="test-templates", name="X",
                              seed_from_templates=True)
    conn.close()
    base = fake_repo / "projects" / "test-templates" / "_meta"
    assert (base / "scope.md").read_text() == "# default scope\n"
    assert (base / "topic_filters.json").read_text() == "{}"
    assert (base / "subagent_prompt.md").read_text() == "default prompt"


def test_create_project_inherit_from(fake_repo):
    from ariadna.mcp_tools_write import create_project_impl
    conn = _open(fake_repo)
    out = create_project_impl(conn, slug="test-inherit", name="X", inherit_from="proxy")
    conn.close()
    base = fake_repo / "projects" / "test-inherit" / "_meta"
    assert (base / "scope.md").read_text() == "# proxy scope\n"
    assert (base / "subagent_prompt.md").read_text() == "proxy prompt"


def test_create_project_inherit_from_not_found(fake_repo):
    from ariadna.mcp_tools_write import create_project_impl
    conn = _open(fake_repo)
    out = create_project_impl(conn, slug="test-z", name="X", inherit_from="does-not-exist")
    conn.close()
    assert out["code"] == "INHERIT_FROM_NOT_FOUND"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_create_project.py -v
# Expected: AttributeError create_project_impl
```

- [ ] **Step 3: Implement `create_project_impl` in `ariadna/mcp_tools_write.py`**

```python
WIKI_SUBDIRS = [
    "concepts", "authors",
    "entities/works", "entities/institutions",
    "synthesis",
]
META_OVERRIDABLES = [
    ("scope_default.md", "scope.md"),
    ("topic_filters_default.json", "topic_filters.json"),
    ("canonical_whitelist_default.json", "canonical_whitelist.json"),
    ("subagent_prompt_default.md", "subagent_prompt.md"),
]


def create_project_impl(
    conn: sqlite3.Connection,
    slug: str,
    name: str,
    description: str = "",
    seed_from_templates: bool = False,
    inherit_from: str | None = None,
) -> dict:
    # 1. validaciones
    if seed_from_templates and inherit_from:
        return {
            "error": "seed_from_templates y inherit_from son mutuamente excluyentes",
            "code": "INCOMPATIBLE_OPTIONS",
        }
    err = validate_slug(slug)
    if err:
        return err
    # 2. duplicado
    if conn.execute("SELECT 1 FROM projects WHERE project_id=?", (slug,)).fetchone():
        return {"error": f"project_id {slug!r} already exists", "code": "SLUG_DUPLICATE"}
    # 3. inherit_from check
    if inherit_from is not None:
        if not conn.execute(
            "SELECT 1 FROM projects WHERE project_id=?", (inherit_from,)
        ).fetchone():
            return {
                "error": f"inherit_from {inherit_from!r} does not exist",
                "code": "INHERIT_FROM_NOT_FOUND",
            }

    base = PROJECTS_ROOT / slug
    paths_created: list[str] = []

    def _rel(p: Path) -> str:
        # POSIX-style relative path desde REPO (independiente del OS)
        return p.relative_to(REPO).as_posix()

    # 4. estructura wiki/<subdirs> con .gitkeep
    for sub in WIKI_SUBDIRS:
        p = base / "wiki" / sub
        p.mkdir(parents=True, exist_ok=False)
        (p / ".gitkeep").write_text("")
        paths_created.append(_rel(p))

    # 5. _meta
    meta = base / "_meta"
    meta.mkdir(parents=True)
    (meta / "extraction_runs").mkdir()
    paths_created.append(_rel(meta))

    # 6. relation_types_ext.json + INDEX.md
    # Shape spec sec 5.3: {"types": []}. Metadata extra (version/schema_version/description)
    # se incluye para consistencia con projects/proxy/_meta/relation_types_ext.json
    # creado en Chunk 3 Task 3.6 — el módulo project_config._normalize_types_block
    # acepta tanto list como dict, así que ambos shapes funcionan.
    (meta / "relation_types_ext.json").write_text(json.dumps({
        "version": "1.0",
        "schema_version": "1.0.0",
        "description": (
            f"Extensiones de relation_types específicas de {slug}. Cualquier tipo aquí "
            f"extiende relation_types_core.json. Colisión con un tipo core es error: "
            f"el server falla en startup."
        ),
        "types": [],
    }, indent=2) + "\n")
    (meta / "INDEX.md").write_text(f"# {name}\n\n{description}\n")

    # 7. seed_from_templates: copia los defaults
    if seed_from_templates:
        for src_name, dst_name in META_OVERRIDABLES:
            src = WIKI_META / src_name
            if src.exists():
                shutil.copy2(src, meta / dst_name)

    # 8. inherit_from: copia los overrides del padre
    if inherit_from:
        parent_meta = PROJECTS_ROOT / inherit_from / "_meta"
        for _, dst_name in META_OVERRIDABLES:
            src = parent_meta / dst_name
            if src.exists():
                shutil.copy2(src, meta / dst_name)
        # También relation_types_ext del padre si existe
        parent_ext = parent_meta / "relation_types_ext.json"
        if parent_ext.exists():
            shutil.copy2(parent_ext, meta / "relation_types_ext.json")

    # 9. INSERT en SQLite
    conn.execute(
        "INSERT INTO projects(project_id, name, description, created_at) "
        "VALUES (?, ?, ?, ?)",
        (slug, name, description, _now_iso()),
    )
    conn.commit()

    return {
        "project_id": slug,
        "paths_created": paths_created,
        "message": f"project {slug!r} created ({len(paths_created)} paths)",
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_create_project.py -v
# Expected: 7 passed
```

- [ ] **Step 5: Commit**

```bash
git add ariadna/mcp_tools_write.py tests/test_create_project.py
git commit -m "feat(mcp): create_project_impl + tests

Crea projects/<slug>/{wiki,_meta}/ con .gitkeep en subdirs vacíos +
INDEX.md, relation_types_ext.json. Opciones seed_from_templates e
inherit_from son mutuamente excluyentes (INCOMPATIBLE_OPTIONS). FSM
de errores: SLUG_INVALID, SLUG_DUPLICATE, INHERIT_FROM_NOT_FOUND.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 6.3: `add_to_research_queue` — idempotencia via UNIQUE INDEX

> Inserta una fila en `research_queue` con auto-detección de `source_type`. Si el caller pasa `source_type` explícito, lo respeta sin warning (spec sección 6.6 precedencia). Idempotencia: misma `(project_id, source_url)` en estado `pending|processing` devuelve el `request_id` existente con `was_duplicate=True`.

**Files:**
- Modify: `ariadna/mcp_tools_write.py` (añadir `add_to_research_queue_impl`)
- Test: `tests/test_add_to_research_queue.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_add_to_research_queue.py
"""add_to_research_queue_impl: detect_source_type + idempotencia."""
import sqlite3
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def db_with_proxy(tmp_path):
    db = tmp_path / "ariadna.db"
    # init schema:
    # Resolución de paths anclada al repo root via __file__ (test no depende de cwd):
    repo_root = Path(__file__).resolve().parent.parent
    subprocess.run(
        [str(repo_root / ".venv/bin/python"),
         str(repo_root / "scripts/init_ariadna_db.py"),
         "--db", str(db)],
        check=True, capture_output=True, timeout=30,
    )
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO projects(project_id, name, created_at) "
                 "VALUES ('proxy', 'Proxy', '2026-05-16T00:00:00+00:00')")
    conn.commit()
    return conn


def test_add_youtube_url_auto_detect(db_with_proxy):
    from ariadna.mcp_tools_write import add_to_research_queue_impl
    out = add_to_research_queue_impl(
        db_with_proxy, project="proxy", source_url="https://youtu.be/abc"
    )
    assert out["detected_source_type"] == "youtube"
    assert out["status"] == "pending"
    assert out["was_duplicate"] is False
    assert "request_id" in out and len(out["request_id"]) > 10


def test_add_arxiv_paper(db_with_proxy):
    from ariadna.mcp_tools_write import add_to_research_queue_impl
    out = add_to_research_queue_impl(
        db_with_proxy, project="proxy",
        source_url="https://arxiv.org/abs/2301.00001",
    )
    assert out["detected_source_type"] == "paper"


def test_add_duplicate_returns_same_request_id(db_with_proxy):
    from ariadna.mcp_tools_write import add_to_research_queue_impl
    out1 = add_to_research_queue_impl(
        db_with_proxy, project="proxy", source_url="https://example.com/x"
    )
    out2 = add_to_research_queue_impl(
        db_with_proxy, project="proxy", source_url="https://example.com/x"
    )
    assert out2["was_duplicate"] is True
    assert out2["request_id"] == out1["request_id"]


def test_add_explicit_source_type_overrides_detector(db_with_proxy):
    from ariadna.mcp_tools_write import add_to_research_queue_impl
    out = add_to_research_queue_impl(
        db_with_proxy, project="proxy",
        source_url="https://example.com/",
        source_type="youtube",   # detector diría web; caller manda
    )
    assert out["detected_source_type"] == "youtube"
    # Confirmar en SQLite:
    src = db_with_proxy.execute(
        "SELECT source_type FROM research_queue WHERE request_id=?",
        (out["request_id"],),
    ).fetchone()[0]
    assert src == "youtube"


def test_add_unknown_project(db_with_proxy):
    from ariadna.mcp_tools_write import add_to_research_queue_impl
    out = add_to_research_queue_impl(
        db_with_proxy, project="ghost", source_url="https://x.com"
    )
    assert out["code"] == "PROJECT_NOT_FOUND"


def test_add_invalid_source_type_explicit(db_with_proxy):
    from ariadna.mcp_tools_write import add_to_research_queue_impl
    out = add_to_research_queue_impl(
        db_with_proxy, project="proxy", source_url="https://x.com",
        source_type="malware",
    )
    assert out["code"] == "INVALID_SOURCE_TYPE"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_add_to_research_queue.py -v
# Expected: AttributeError add_to_research_queue_impl
```

- [ ] **Step 3: Implement `add_to_research_queue_impl`**

```python
def add_to_research_queue_impl(
    conn: sqlite3.Connection,
    project: str,
    source_url: str,
    source_type: str | None = None,
    notes: str = "",
    priority: int = 0,
) -> dict:
    # 1. project existe
    if not conn.execute("SELECT 1 FROM projects WHERE project_id=?", (project,)).fetchone():
        return {"error": f"project {project!r} not found", "code": "PROJECT_NOT_FOUND"}

    # 2. source_url no vacía
    if not source_url or not source_url.strip():
        return {"error": "source_url empty", "code": "INVALID_URL"}

    # 3. source_type: precedencia caller > detector
    detected = source_type or detect_source_type(source_url)
    if detected not in VALID_SOURCE_TYPES:
        return {
            "error": f"source_type {detected!r} not in {sorted(VALID_SOURCE_TYPES)}",
            "code": "INVALID_SOURCE_TYPE",
        }

    # 4. idempotencia: existe una fila pending/processing con misma (project, url)?
    existing = conn.execute(
        "SELECT request_id, status FROM research_queue "
        "WHERE project_id=? AND source_url=? AND status IN ('pending','processing')",
        (project, source_url),
    ).fetchone()
    if existing:
        return {
            "request_id": existing[0],
            "detected_source_type": detected,
            "status": existing[1],
            "was_duplicate": True,
            "message": "url already in queue for this project",
        }

    # 5. INSERT
    request_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO research_queue("
        "request_id, project_id, source_url, source_type, status, priority, "
        "created_at, notes) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)",
        (request_id, project, source_url, detected, priority, _now_iso(), notes),
    )
    conn.commit()
    return {
        "request_id": request_id,
        "detected_source_type": detected,
        "status": "pending",
        "was_duplicate": False,
        "message": f"added to queue (project={project!r}, type={detected!r})",
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_add_to_research_queue.py -v
# Expected: 6 passed
```

- [ ] **Step 5: Commit**

```bash
git add ariadna/mcp_tools_write.py tests/test_add_to_research_queue.py
git commit -m "feat(mcp): add_to_research_queue_impl con detect + idempotencia

source_type auto-detect (youtube/paper/web/pdf/unknown) o respeta caller.
Idempotencia: misma (project, url) en pending/processing devuelve el
request_id existente con was_duplicate=True (UNIQUE INDEX en SQLite
respalda la garantía aunque la query también la implementa explicit).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 6.4: `cancel_request` — FSM rules

> FSM (spec sección 4.2.1): `pending→cancelled` OK, `failed→cancelled` OK, `processing→cancelled` no-op, `done|cancelled` no-op idempotente.

**Files:**
- Modify: `ariadna/mcp_tools_write.py` (añadir `cancel_request_impl`)
- Test: `tests/test_cancel_request.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cancel_request.py
"""cancel_request_impl: respeta FSM transitions spec sec 4.2.1."""
import sqlite3
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def db_with_items(tmp_path):
    db = tmp_path / "ariadna.db"
    # Resolución de paths anclada al repo root via __file__ (test no depende de cwd):
    repo_root = Path(__file__).resolve().parent.parent
    subprocess.run(
        [str(repo_root / ".venv/bin/python"),
         str(repo_root / "scripts/init_ariadna_db.py"),
         "--db", str(db)],
        check=True, capture_output=True, timeout=30,
    )
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO projects(project_id, name, created_at) "
                 "VALUES ('proxy', 'Proxy', '2026-05-16T00:00:00+00:00')")
    for rid, status in [
        ("r-pending",    "pending"),
        ("r-processing", "processing"),
        ("r-done",       "done"),
        ("r-failed",     "failed"),
        ("r-cancelled",  "cancelled"),
    ]:
        conn.execute(
            "INSERT INTO research_queue(request_id, project_id, source_url, "
            "source_type, status, created_at) "
            "VALUES (?, 'proxy', ?, 'web', ?, '2026-05-16T00:00:00+00:00')",
            (rid, f"https://x/{rid}", status),
        )
    conn.commit()
    return conn


def test_cancel_pending_ok(db_with_items):
    from ariadna.mcp_tools_write import cancel_request_impl
    out = cancel_request_impl(db_with_items, request_id="r-pending", reason="user changed mind")
    assert out["previous_status"] == "pending"
    assert out["current_status"] == "cancelled"
    # SQLite refleja:
    row = db_with_items.execute(
        "SELECT status, completed_at, error_msg FROM research_queue WHERE request_id='r-pending'"
    ).fetchone()
    assert row[0] == "cancelled"
    assert row[1] is not None  # completed_at se setea
    assert "user changed mind" in (row[2] or "")


def test_cancel_failed_ok(db_with_items):
    from ariadna.mcp_tools_write import cancel_request_impl
    out = cancel_request_impl(db_with_items, request_id="r-failed", reason="abandoned")
    assert out["previous_status"] == "failed"
    assert out["current_status"] == "cancelled"


def test_cancel_processing_no_op(db_with_items):
    from ariadna.mcp_tools_write import cancel_request_impl
    out = cancel_request_impl(db_with_items, request_id="r-processing")
    assert out["previous_status"] == "processing"
    assert out["current_status"] == "processing"  # NO-OP
    assert "cannot cancel" in out["message"].lower()


def test_cancel_done_idempotent_noop(db_with_items):
    from ariadna.mcp_tools_write import cancel_request_impl
    out = cancel_request_impl(db_with_items, request_id="r-done")
    assert out["previous_status"] == "done"
    assert out["current_status"] == "done"


def test_cancel_cancelled_idempotent_noop(db_with_items):
    from ariadna.mcp_tools_write import cancel_request_impl
    out = cancel_request_impl(db_with_items, request_id="r-cancelled")
    assert out["previous_status"] == "cancelled"
    assert out["current_status"] == "cancelled"


def test_cancel_not_found(db_with_items):
    from ariadna.mcp_tools_write import cancel_request_impl
    out = cancel_request_impl(db_with_items, request_id="r-nonexistent")
    assert out["code"] == "REQUEST_NOT_FOUND"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_cancel_request.py -v
# Expected: AttributeError cancel_request_impl
```

- [ ] **Step 3: Implement `cancel_request_impl`**

```python
def cancel_request_impl(
    conn: sqlite3.Connection,
    request_id: str,
    reason: str = "",
) -> dict:
    row = conn.execute(
        "SELECT status FROM research_queue WHERE request_id=?", (request_id,)
    ).fetchone()
    if row is None:
        return {"error": f"request_id {request_id!r} not found", "code": "REQUEST_NOT_FOUND"}
    prev = row[0]
    if prev == "processing":
        return {
            "request_id": request_id,
            "previous_status": "processing",
            "current_status": "processing",
            "message": "cannot cancel item currently being processed; "
                       "let it finish or fail naturally",
        }
    if prev in ("done", "cancelled"):
        return {
            "request_id": request_id,
            "previous_status": prev,
            "current_status": prev,
            "message": f"already terminal ({prev}); no-op",
        }
    # pending o failed → cancelled
    err_msg = f"cancelled by user: {reason}" if reason else "cancelled by user"
    conn.execute(
        "UPDATE research_queue SET status='cancelled', completed_at=?, error_msg=? "
        "WHERE request_id=?",
        (_now_iso(), err_msg, request_id),
    )
    conn.commit()
    return {
        "request_id": request_id,
        "previous_status": prev,
        "current_status": "cancelled",
        "message": f"cancelled ({prev} → cancelled)",
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_cancel_request.py -v
# Expected: 6 passed
```

- [ ] **Step 5: Commit**

```bash
git add ariadna/mcp_tools_write.py tests/test_cancel_request.py
git commit -m "feat(mcp): cancel_request_impl respeta FSM spec sec 4.2.1

pending→cancelled OK, failed→cancelled OK (saca del retry pool),
processing→cancelled NO-OP (no se cancela mid-process), done/cancelled
idempotente. error_msg registra 'cancelled by user: <reason>'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 7: Tools MCP read nuevas

> Implementa las dos tools read (spec sección 6.2): `list_projects` (conteos derivados en vivo, sin caching) y `list_research_queue` (filtros project/status/source_type/limit). Lógica en `ariadna/mcp_tools_read.py`, paralela al patrón de Chunk 6. Wiring `@mcp.tool` se difiere a Chunk 8.
>
> **Pre-condición:** Chunks 2-6 completados. SQLite tiene tabla `projects` poblada y `research_queue` lista para queries.

### Task 7.1: `list_projects` — conteos derivados en vivo

> Conteos `n_pages`, `n_chunks`, `n_queue_pending`. **`n_pages`** desde `SELECT COUNT(*) FROM pages WHERE project_id=?`. **`n_queue_pending`** desde `research_queue` con status='pending'. **`n_chunks`** desde Qdrant (`client.count(filter=project_id=X)`). El acceso a Qdrant se inyecta como callback para tests sin levantar Qdrant.

**Files:**
- Create: `ariadna/mcp_tools_read.py`
- Test: `tests/test_list_projects.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_list_projects.py
"""list_projects_impl: conteos derivados, include_archived filter."""
import sqlite3
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def db_with_two_projects(tmp_path):
    db = tmp_path / "ariadna.db"
    repo_root = Path(__file__).resolve().parent.parent
    subprocess.run(
        [str(repo_root / ".venv/bin/python"),
         str(repo_root / "scripts/init_ariadna_db.py"),
         "--db", str(db)],
        check=True, capture_output=True, timeout=30,
    )
    conn = sqlite3.connect(str(db))
    # 1 activo, 1 archivado
    conn.execute("INSERT INTO projects(project_id, name, description, created_at) "
                 "VALUES ('proxy', 'Proxy', 'desc', '2026-05-16T00:00:00+00:00')")
    conn.execute("INSERT INTO projects(project_id, name, created_at, archived_at) "
                 "VALUES ('old-proj', 'Old', '2025-01-01T00:00:00+00:00', '2026-05-01T00:00:00+00:00')")
    # 2 pages en proxy, 1 en old-proj
    for pid, page_id, name in [("proxy", "shadow", "Sombra"),
                                ("proxy", "anima", "Anima"),
                                ("old-proj", "x", "X")]:
        conn.execute(
            "INSERT INTO pages(project_id, page_id, page_type, canonical_name, "
            "file_path, body_md, indexed_at) VALUES (?, ?, 'concept', ?, ?, '# x',"
            "'2026-05-16T00:00:00+00:00')",
            (pid, page_id, name, f"concepts/{page_id}.md"),
        )
    # 3 items pending en proxy, 1 done (no contado), 1 pending en old-proj
    for rid, project, status in [
        ("r1", "proxy", "pending"), ("r2", "proxy", "pending"), ("r3", "proxy", "pending"),
        ("r4", "proxy", "done"),
        ("r5", "old-proj", "pending"),
    ]:
        conn.execute(
            "INSERT INTO research_queue(request_id, project_id, source_url, "
            "source_type, status, created_at) VALUES (?, ?, ?, 'web', ?, '2026-05-16T00:00:00+00:00')",
            (rid, project, f"https://x/{rid}", status),
        )
    conn.commit()
    return conn


def _fake_chunk_counter(counts_by_project):
    """Devuelve una función count_chunks_fn(project_id) → int."""
    def fn(project_id: str) -> int:
        return counts_by_project.get(project_id, 0)
    return fn


def test_list_projects_default_excludes_archived(db_with_two_projects):
    from ariadna.mcp_tools_read import list_projects_impl
    out = list_projects_impl(
        db_with_two_projects, include_archived=False,
        count_chunks_fn=_fake_chunk_counter({"proxy": 6259, "old-proj": 0}),
    )
    assert "projects" in out
    pids = [p["project_id"] for p in out["projects"]]
    assert pids == ["proxy"]   # old-proj filtrado
    proxy = out["projects"][0]
    assert proxy["name"] == "Proxy"
    assert proxy["description"] == "desc"
    assert proxy["n_pages"] == 2
    assert proxy["n_chunks"] == 6259
    assert proxy["n_queue_pending"] == 3
    assert proxy["archived_at"] is None


def test_list_projects_include_archived(db_with_two_projects):
    from ariadna.mcp_tools_read import list_projects_impl
    out = list_projects_impl(
        db_with_two_projects, include_archived=True,
        count_chunks_fn=_fake_chunk_counter({"proxy": 6259, "old-proj": 100}),
    )
    pids = sorted(p["project_id"] for p in out["projects"])
    assert pids == ["old-proj", "proxy"]
    old = next(p for p in out["projects"] if p["project_id"] == "old-proj")
    assert old["archived_at"] is not None
    assert old["n_pages"] == 1
    assert old["n_chunks"] == 100
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_list_projects.py -v
# Expected: ModuleNotFoundError ariadna.mcp_tools_read
```

- [ ] **Step 3: Implement `ariadna/mcp_tools_read.py`**

```python
"""Tools MCP read: list_projects, list_research_queue.

Funciones *_impl que reciben conexión SQLite + callbacks inyectables (e.g.
contador de chunks Qdrant). El wiring `@mcp.tool` vive en mcp_server.py (Chunk 8).
"""
from __future__ import annotations

import sqlite3
from typing import Any, Callable


def list_projects_impl(
    conn: sqlite3.Connection,
    include_archived: bool = False,
    count_chunks_fn: Callable[[str], int] | None = None,
) -> dict[str, Any]:
    """Lista proyectos con conteos derivados en vivo.

    `count_chunks_fn(project_id) -> int` es inyectado por el caller (mcp_server.py
    pasa un wrapper sobre QdrantClient.count). En tests puedes pasar una lambda
    o un fake.
    """
    if count_chunks_fn is None:
        count_chunks_fn = lambda pid: 0  # noqa: E731 — fallback explícito

    where = "" if include_archived else "WHERE archived_at IS NULL"
    rows = conn.execute(
        f"SELECT project_id, name, description, created_at, archived_at "
        f"FROM projects {where} ORDER BY created_at ASC"
    ).fetchall()

    projects: list[dict[str, Any]] = []
    for pid, name, description, created_at, archived_at in rows:
        n_pages = conn.execute(
            "SELECT COUNT(*) FROM pages WHERE project_id=?", (pid,)
        ).fetchone()[0]
        n_queue_pending = conn.execute(
            "SELECT COUNT(*) FROM research_queue WHERE project_id=? AND status='pending'",
            (pid,),
        ).fetchone()[0]
        n_chunks = count_chunks_fn(pid)
        projects.append({
            "project_id": pid,
            "name": name,
            "description": description,
            "created_at": created_at,
            "archived_at": archived_at,
            "n_pages": n_pages,
            "n_chunks": n_chunks,
            "n_queue_pending": n_queue_pending,
        })

    return {"projects": projects, "include_archived": include_archived}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_list_projects.py -v
# Expected: 2 passed
```

- [ ] **Step 5: Commit**

```bash
git add ariadna/mcp_tools_read.py tests/test_list_projects.py
git commit -m "feat(mcp): list_projects_impl con conteos derivados en vivo

n_pages/n_queue_pending desde SQLite; n_chunks vía callback inyectable
(mcp_server.py wrapperá QdrantClient.count en Chunk 8). include_archived
filtra projects.archived_at IS NULL por default. Sin caching: conteos
on-demand (queries baratas, archivos pequeños).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 7.2: `list_research_queue` — filtros + límite

> Filtros opcionales: `project`, `status` (acepta 'all' para no filtrar), `source_type`. `limit` controla el page. Devuelve además `total_matching` (conteo sin límite) y `filters_applied`.

**Files:**
- Modify: `ariadna/mcp_tools_read.py` (añadir `list_research_queue_impl`)
- Test: `tests/test_list_research_queue.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_list_research_queue.py
"""list_research_queue_impl: filtros project/status/source_type + limit."""
import sqlite3
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def db_with_queue(tmp_path):
    db = tmp_path / "ariadna.db"
    repo_root = Path(__file__).resolve().parent.parent
    subprocess.run(
        [str(repo_root / ".venv/bin/python"),
         str(repo_root / "scripts/init_ariadna_db.py"),
         "--db", str(db)],
        check=True, capture_output=True, timeout=30,
    )
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO projects(project_id, name, created_at) "
                 "VALUES ('proxy', 'Proxy', '2026-05-16T00:00:00+00:00')")
    conn.execute("INSERT INTO projects(project_id, name, created_at) "
                 "VALUES ('tesis', 'Tesis', '2026-05-16T00:00:00+00:00')")
    items = [
        ("r1", "proxy", "https://yt/a", "youtube",  "pending"),
        ("r2", "proxy", "https://yt/b", "youtube",  "pending"),
        ("r3", "proxy", "https://x.com/p1.pdf", "pdf", "pending"),
        ("r4", "proxy", "https://yt/c", "youtube",  "done"),
        ("r5", "tesis", "https://arxiv/p", "paper", "pending"),
        ("r6", "tesis", "https://arxiv/q", "paper", "cancelled"),
    ]
    for rid, project, url, stype, status in items:
        conn.execute(
            "INSERT INTO research_queue(request_id, project_id, source_url, "
            "source_type, status, created_at) VALUES (?, ?, ?, ?, ?, '2026-05-16T00:00:00+00:00')",
            (rid, project, url, stype, status),
        )
    conn.commit()
    return conn


def test_list_queue_filter_project_and_status(db_with_queue):
    from ariadna.mcp_tools_read import list_research_queue_impl
    out = list_research_queue_impl(db_with_queue, project="proxy", status="pending")
    rids = sorted(item["request_id"] for item in out["items"])
    assert rids == ["r1", "r2", "r3"]
    assert out["total_matching"] == 3
    assert out["filters_applied"] == {"project": "proxy", "status": "pending",
                                       "source_type": None, "limit": 50}


def test_list_queue_filter_source_type(db_with_queue):
    from ariadna.mcp_tools_read import list_research_queue_impl
    out = list_research_queue_impl(db_with_queue, project="proxy",
                                    status="pending", source_type="youtube")
    rids = sorted(item["request_id"] for item in out["items"])
    assert rids == ["r1", "r2"]
    assert out["total_matching"] == 2


def test_list_queue_status_all_cross_all_projects(db_with_queue):
    from ariadna.mcp_tools_read import list_research_queue_impl
    out = list_research_queue_impl(db_with_queue, project=None, status="all")
    assert out["total_matching"] == 6
    assert len(out["items"]) == 6


def test_list_queue_invalid_status_returns_error(db_with_queue):
    from ariadna.mcp_tools_read import list_research_queue_impl
    out = list_research_queue_impl(db_with_queue, status="weird")
    assert out["code"] == "INVALID_STATUS"


def test_list_queue_invalid_source_type_returns_error(db_with_queue):
    from ariadna.mcp_tools_read import list_research_queue_impl
    out = list_research_queue_impl(db_with_queue, source_type="exotic")
    assert out["code"] == "INVALID_SOURCE_TYPE"


def test_list_queue_limit_caps_items_but_not_total(db_with_queue):
    from ariadna.mcp_tools_read import list_research_queue_impl
    out = list_research_queue_impl(db_with_queue, status="all", limit=2)
    assert len(out["items"]) == 2
    assert out["total_matching"] == 6  # sin truncar
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_list_research_queue.py -v
# Expected: AttributeError list_research_queue_impl
```

- [ ] **Step 3: Implement `list_research_queue_impl`**

```python
VALID_STATUSES_FOR_QUERY = {"pending", "processing", "done", "failed", "cancelled", "all"}
VALID_SOURCE_TYPES_FOR_QUERY = {"youtube", "paper", "web", "pdf", "unknown"}

QUEUE_COLUMNS = [
    "request_id", "project_id", "source_url", "source_type", "status",
    "priority", "created_at", "picked_up_at", "completed_at",
    "assigned_worker", "retry_count", "error_msg", "notes",
]


def list_research_queue_impl(
    conn: sqlite3.Connection,
    project: str | None = None,
    status: str = "pending",
    source_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    if status not in VALID_STATUSES_FOR_QUERY:
        return {
            "error": f"status {status!r} not in {sorted(VALID_STATUSES_FOR_QUERY)}",
            "code": "INVALID_STATUS",
        }
    if source_type is not None and source_type not in VALID_SOURCE_TYPES_FOR_QUERY:
        return {
            "error": f"source_type {source_type!r} not in {sorted(VALID_SOURCE_TYPES_FOR_QUERY)}",
            "code": "INVALID_SOURCE_TYPE",
        }
    if limit <= 0:
        return {"error": "limit must be positive", "code": "INVALID_LIMIT"}

    clauses: list[str] = []
    params: list[Any] = []
    if project is not None:
        clauses.append("project_id = ?")
        params.append(project)
    if status != "all":
        clauses.append("status = ?")
        params.append(status)
    if source_type is not None:
        clauses.append("source_type = ?")
        params.append(source_type)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    # total_matching ANTES de aplicar limit
    total = conn.execute(
        f"SELECT COUNT(*) FROM research_queue{where}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT {', '.join(QUEUE_COLUMNS)} FROM research_queue{where} "
        f"ORDER BY priority DESC, created_at ASC LIMIT ?",
        params + [limit],
    ).fetchall()
    items = [dict(zip(QUEUE_COLUMNS, row)) for row in rows]

    return {
        "items": items,
        "total_matching": total,
        "filters_applied": {
            "project": project, "status": status,
            "source_type": source_type, "limit": limit,
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_list_research_queue.py -v
# Expected: 6 passed
```

- [ ] **Step 5: Commit**

```bash
git add ariadna/mcp_tools_read.py tests/test_list_research_queue.py
git commit -m "feat(mcp): list_research_queue_impl con filtros + limit

project/status/source_type opcionales. status='all' devuelve cualquier
estado. total_matching pre-limit + filters_applied en respuesta para que
el agente sepa el efecto de su llamada. Order priority DESC, created_at ASC.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 8: Tools MCP modificadas + cleanup

> El último chunk de cambios a producción: modifica `search_corpus` y `get_wiki_page` para aceptar `project`, elimina las tools YouTube-específicas obsoletas (`get_video_summary`, `list_videos`), wire de las 5 tools nuevas escritas en Chunks 6-7, y registra el startup hook `reload_relation_types`. Tras este chunk el server expone el contrato MCP final de Fase 2.
>
> **Pre-condición:** Chunks 2-7 completados. `ProjectConfig`, `mcp_tools_write`, `mcp_tools_read` listos. Tests de los _impl pasando.

### Task 8.1: `search_corpus` — añadir parámetro `project` + `projects_seen` en metadata

> El parámetro acepta `str` (filter a un proyecto), `list[str]` (OR-of, ver spec sección 4.2), o `None` (cross-all, default). El Searcher tiene que construir el `Filter` Qdrant dinámicamente y propagar `projects_seen` (set de project_ids vistos en los resultados) en `retrieval_metadata`.

**Files:**
- Modify: `ariadna/search.py` — añadir parámetro `project` a `search_hybrid()` + payload filter + post-process
- Modify: `ariadna/mcp_server.py:93-114` — añadir parámetro y propagación
- Test: `tests/test_search_corpus_project_filter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_search_corpus_project_filter.py
"""search_hybrid acepta project: str | list[str] | None y devuelve
projects_seen en retrieval_metadata."""
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_searcher_search_hybrid_signature_accepts_project():
    from ariadna.search import Searcher
    import inspect
    sig = inspect.signature(Searcher.search_hybrid)
    assert "project" in sig.parameters
    p = sig.parameters["project"]
    assert p.default is None


def test_searcher_builds_qdrant_filter_with_project_str():
    """Verifica que pasando project='proxy' se construye un Filter con
    must=[FieldCondition(project_id=proxy)]."""
    from ariadna.search import _build_project_filter
    flt = _build_project_filter("proxy")
    assert flt is not None
    assert len(flt.must) == 1
    cond = flt.must[0]
    assert cond.key == "project_id"
    assert cond.match.value == "proxy"


def test_searcher_builds_qdrant_filter_with_project_list():
    from ariadna.search import _build_project_filter
    flt = _build_project_filter(["proxy", "tesis"])
    # OR-of: must=[Filter(should=[...])]
    assert flt is not None
    inner = flt.must[0]
    assert len(inner.should) == 2
    assert {c.match.value for c in inner.should} == {"proxy", "tesis"}


def test_searcher_returns_none_filter_when_project_none():
    from ariadna.search import _build_project_filter
    assert _build_project_filter(None) is None


def test_projects_seen_collected_from_results():
    """Tras un hybrid search, retrieval_metadata.projects_seen es la unión
    de project_id de raw_chunks ∪ wiki_pages."""
    from ariadna.search import _collect_projects_seen
    raw_chunks = [{"project_id": "proxy"}, {"project_id": "tesis"}]
    wiki_pages = [{"project_id": "proxy"}]
    seen = _collect_projects_seen(raw_chunks, wiki_pages)
    assert seen == ["proxy", "tesis"]   # sorted
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_search_corpus_project_filter.py -v
# Expected: ImportError (_build_project_filter / _collect_projects_seen no existen)
```

- [ ] **Step 3: Apply edits to `ariadna/search.py`**

1. **Imports**: añadir `FieldCondition`, `Filter`, `MatchValue` si no están ya.

2. **Helpers nuevos** (top-level del módulo):
   ```python
   def _build_project_filter(project: str | list[str] | None) -> Filter | None:
       """Spec 4.2: str → must, list → must=[Filter(should=...)], None → no filter."""
       if project is None:
           return None
       if isinstance(project, str):
           return Filter(must=[FieldCondition(key="project_id",
                                              match=MatchValue(value=project))])
       if isinstance(project, list) and project:
           return Filter(must=[Filter(should=[
               FieldCondition(key="project_id", match=MatchValue(value=p))
               for p in project
           ])])
       return None  # list vacía → equivalente a None

   def _collect_projects_seen(raw_chunks: list[dict], wiki_pages: list[dict]) -> list[str]:
       seen: set[str] = set()
       for it in raw_chunks:
           if it.get("project_id"):
               seen.add(it["project_id"])
       for it in wiki_pages:
           if it.get("project_id"):
               seen.add(it["project_id"])
       return sorted(seen)
   ```

3. **`Searcher.search_hybrid` signature**: añadir `project: str | list[str] | None = None` como nuevo kwarg.

4. **Aplicar el filtro Qdrant**: el método `self.store.search(query_vec, top_k=..., filters={...})` tiene que aceptar el filtro de proyecto. Hay dos rutas:
   - (a) Extender `CorpusStore.search` para que acepte un `must_filter: Filter | None` adicional combinable con los demás filtros.
   - (b) Construir el filtro en `search_hybrid` con un mini-helper y pasarlo al call de scroll/search via filter combinator.

   **Opción (a) es más limpia.** En `ariadna/storage.py:search()` (línea ~ donde construye `must=[...]`):
   ```python
   def search(self, query_vec, top_k, filters=None, must_not_filters=None,
              exclude_field_present=None, extra_must_filter: Filter | None = None):
       ...
       qdrant_filter = Filter(must=must, ...)
       if extra_must_filter is not None:
           # merge: añade los must del extra al must existente
           qdrant_filter.must = list(qdrant_filter.must or []) + list(extra_must_filter.must or [])
       ...
   ```

   En `search_hybrid()`:
   ```python
   project_filter = _build_project_filter(project)
   raw_results_dense = self.store.search(
       query_vec, top_k=prefetch_k, filters=raw_filters,
       must_not_filters={"source_type": "wiki_page"},
       exclude_field_present=exclude_pf,
       extra_must_filter=project_filter,
   )
   wiki_results = self.store.search(
       query_vec, top_k=top_k_wiki,
       filters={"source_type": "wiki_page"},
       extra_must_filter=project_filter,
   )
   ```

5. **`retrieval_metadata.projects_seen`**: en la construcción del dict de retorno de `search_hybrid`, después de tener `raw_chunks` y `wiki_pages` finales:
   ```python
   meta["projects_seen"] = _collect_projects_seen(raw_chunks, wiki_pages)
   ```

- [ ] **Step 4: Apply edits to `ariadna/mcp_server.py`** (tool `search_corpus`)

```python
@mcp.tool(name="search_corpus", description=...)
def search_corpus(
    query: str,
    top_k: int = 5,
    top_k_wiki: int = 2,
    project: str | list[str] | None = None,    # ← nuevo
    category: str | None = None,
    playlist: str | None = None,
    include_filtered: bool = False,
) -> dict[str, Any]:
    """..."""
    # Validar project si se pasó: existe en SQLite?
    if project is not None:
        from ariadna.project_config import ProjectConfig, ProjectNotFoundError
        slugs = [project] if isinstance(project, str) else list(project)
        for s in slugs:
            try:
                ProjectConfig.for_project(s)
            except ProjectNotFoundError:
                return {"error": f"project {s!r} not found", "code": "PROJECT_NOT_FOUND"}

    searcher = get_searcher()
    return searcher.search_hybrid(
        query, top_k_raw=top_k, top_k_wiki=top_k_wiki,
        project=project,
        category=category, playlist=playlist,
        include_filtered=include_filtered,
    )
```

Y actualizar la `description` del tool (string) para mencionar el nuevo parámetro `project`.

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/test_search_corpus_project_filter.py -v
# Expected: 5 passed
```

- [ ] **Step 6: Commit**

```bash
git add ariadna/search.py ariadna/storage.py ariadna/mcp_server.py tests/test_search_corpus_project_filter.py
git commit -m "feat(mcp): search_corpus acepta project + projects_seen en metadata

Searcher.search_hybrid gana param project: str|list[str]|None (cross-all,
único, o OR-of). CorpusStore.search acepta extra_must_filter para combinar
con los filtros existentes. retrieval_metadata.projects_seen lista los
project_ids vistos en raw_chunks ∪ wiki_pages. mcp_server valida que el
slug existe antes de delegar (PROJECT_NOT_FOUND).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 8.2: `get_wiki_page` — `project` + tiebreak `indexed_at` ASC + `projects_with_this_id`

> Spec sección 6.3: `project=None` busca cross-all; si `page_id` aparece en varios proyectos, desempata por `indexed_at` ASC (el más antiguo gana) y devuelve `metadata.projects_with_this_id`. `project='proxy'` solo busca en Proxy (error si no existe).

**Files:**
- Modify: `ariadna/mcp_server.py:129-143` (tool body)
- Test: `tests/test_get_wiki_page_project.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_get_wiki_page_project.py
"""get_wiki_page acepta project; cross-all desempata por indexed_at ASC."""
import sqlite3
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def db_with_two_pages_same_id(tmp_path):
    db = tmp_path / "ariadna.db"
    repo_root = Path(__file__).resolve().parent.parent
    subprocess.run(
        [str(repo_root / ".venv/bin/python"),
         str(repo_root / "scripts/init_ariadna_db.py"),
         "--db", str(db)],
        check=True, capture_output=True, timeout=30,
    )
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO projects(project_id, name, created_at) "
                 "VALUES ('proxy', 'Proxy', '2026-05-16T00:00:00+00:00')")
    conn.execute("INSERT INTO projects(project_id, name, created_at) "
                 "VALUES ('tesis', 'Tesis', '2026-05-16T00:00:00+00:00')")
    # Misma page_id 'shadow' en ambos proyectos. proxy es más viejo:
    conn.execute(
        "INSERT INTO pages(project_id, page_id, page_type, canonical_name, "
        "file_path, body_md, indexed_at) VALUES "
        "('proxy', 'shadow', 'concept', 'Sombra Jung', 'concepts/shadow.md', "
        "'# Sombra Jung\\nbody from proxy', '2026-05-16T01:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO pages(project_id, page_id, page_type, canonical_name, "
        "file_path, body_md, indexed_at) VALUES "
        "('tesis', 'shadow', 'concept', 'Sombra tesis', 'concepts/shadow.md', "
        "'# Sombra tesis\\nbody from tesis', '2026-05-16T02:00:00+00:00')"
    )
    conn.commit()
    return db


def test_get_wiki_page_with_explicit_project(db_with_two_pages_same_id):
    from ariadna.mcp_tools_read import get_wiki_page_impl
    out = get_wiki_page_impl(db_with_two_pages_same_id, page_id="shadow", project="tesis")
    assert out["page_id"] == "shadow"
    assert out["project_id"] == "tesis"
    assert "body from tesis" in out["body_md"]


def test_get_wiki_page_cross_all_picks_oldest(db_with_two_pages_same_id):
    from ariadna.mcp_tools_read import get_wiki_page_impl
    out = get_wiki_page_impl(db_with_two_pages_same_id, page_id="shadow", project=None)
    # proxy es más viejo (01:00 vs 02:00) → gana
    assert out["project_id"] == "proxy"
    assert "body from proxy" in out["body_md"]
    assert out["projects_with_this_id"] == ["proxy", "tesis"]


def test_get_wiki_page_not_found(db_with_two_pages_same_id):
    from ariadna.mcp_tools_read import get_wiki_page_impl
    out = get_wiki_page_impl(db_with_two_pages_same_id, page_id="ghost", project=None)
    assert out["code"] == "WIKI_PAGE_NOT_FOUND"


def test_get_wiki_page_existing_project_missing_page(db_with_two_pages_same_id):
    """project existe pero la page no está en ese proyecto."""
    from ariadna.mcp_tools_read import get_wiki_page_impl
    out = get_wiki_page_impl(db_with_two_pages_same_id, page_id="ghost", project="proxy")
    assert out["code"] == "WIKI_PAGE_NOT_FOUND"


def test_get_wiki_page_project_not_found(db_with_two_pages_same_id):
    from ariadna.mcp_tools_read import get_wiki_page_impl
    out = get_wiki_page_impl(db_with_two_pages_same_id, page_id="shadow",
                             project="does-not-exist")
    assert out["code"] == "PROJECT_NOT_FOUND"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_get_wiki_page_project.py -v
# Expected: AttributeError get_wiki_page_impl
```

- [ ] **Step 3: Implement `get_wiki_page_impl` in `ariadna/mcp_tools_read.py`** y wirearla en mcp_server.py

```python
# ariadna/mcp_tools_read.py
def get_wiki_page_impl(
    db_path: "Path",
    page_id: str,
    project: str | None = None,
) -> dict[str, Any]:
    """Lee una página wiki desde ariadna.db. project=None: cross-all,
    desempate por indexed_at ASC (más antiguo gana). Devuelve además
    projects_with_this_id si la page aparece en varios proyectos."""
    import sqlite3 as _sql
    conn = _sql.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        # Validar project si se pasó
        if project is not None:
            if not conn.execute(
                "SELECT 1 FROM projects WHERE project_id=?", (project,)
            ).fetchone():
                return {"error": f"project {project!r} not found",
                        "code": "PROJECT_NOT_FOUND"}
            row = conn.execute(
                "SELECT project_id, page_id, page_type, canonical_name, "
                "domain_primary, file_path, body_md, indexed_at "
                "FROM pages WHERE project_id=? AND page_id=?",
                (project, page_id),
            ).fetchone()
            if row is None:
                return {
                    "error": f"page {page_id!r} not found in project {project!r}",
                    "code": "WIKI_PAGE_NOT_FOUND",
                }
            pid, page, ptype, cname, dom, fpath, body, idx = row
            return {
                "project_id": pid, "page_id": page, "page_type": ptype,
                "canonical_name": cname, "domain_primary": dom,
                "file_path": fpath, "body_md": body, "indexed_at": idx,
                "projects_with_this_id": [pid],
            }

        # Cross-all: enumera matches ordenados por indexed_at ASC
        rows = conn.execute(
            "SELECT project_id, page_id, page_type, canonical_name, domain_primary, "
            "file_path, body_md, indexed_at FROM pages WHERE page_id=? "
            "ORDER BY indexed_at ASC",
            (page_id,),
        ).fetchall()
        if not rows:
            return {
                "error": f"page {page_id!r} not found in any project",
                "code": "WIKI_PAGE_NOT_FOUND",
            }
        first = rows[0]
        all_projects = [r[0] for r in rows]
        pid, page, ptype, cname, dom, fpath, body, idx = first
        return {
            "project_id": pid, "page_id": page, "page_type": ptype,
            "canonical_name": cname, "domain_primary": dom,
            "file_path": fpath, "body_md": body, "indexed_at": idx,
            "projects_with_this_id": all_projects,
        }
    finally:
        conn.close()
```

Y en `ariadna/mcp_server.py`, reemplazar el cuerpo de `get_wiki_page`:

```python
ARIADNA_DB = PROJECT_ROOT / "data" / "ariadna.db"

@mcp.tool(name="get_wiki_page", description=...)
def get_wiki_page(
    page_id: str,
    project: str | None = None,
) -> dict[str, Any]:
    from ariadna.mcp_tools_read import get_wiki_page_impl
    return get_wiki_page_impl(ARIADNA_DB, page_id=page_id, project=project)
```

Actualizar la `description` del tool para mencionar el parámetro `project` y el comportamiento de tiebreak.

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python -m pytest tests/test_get_wiki_page_project.py -v
# Expected: 5 passed
```

- [ ] **Step 5: Commit**

```bash
git add ariadna/mcp_tools_read.py ariadna/mcp_server.py tests/test_get_wiki_page_project.py
git commit -m "feat(mcp): get_wiki_page acepta project; cross-all desempata indexed_at ASC

project=str: filtro estricto, WIKI_PAGE_NOT_FOUND si no existe en ese proyecto.
project=None: busca cross-all, devuelve el más antiguo por indexed_at ASC y
mete projects_with_this_id con la lista ordenada de todos los matches para
que el agente pueda pedir explícitamente cada uno.

Tool migra de filesystem.rglob a SQLite ariadna.db.pages — más rápido y
project-aware.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 8.3: Eliminar `get_video_summary` + `list_videos` + `CorpusStore.list_videos`

> Spec sección 6.4: tools YouTube-específicas obsoletas. Casos de uso ya cubiertos por `search_corpus` (drill-down via filter) y `list_research_queue`.

**Files:**
- Modify: `ariadna/mcp_server.py:146-204` (eliminar dos tools completas)
- Modify: `ariadna/storage.py:226-273` (eliminar `list_videos`)

- [ ] **Step 1: Verificar que no hay callers fuera del MCP**

```bash
# Antes de borrar, asegurar que nadie más usa list_videos:
grep -rn "list_videos\|get_video_summary" --include="*.py" \
    ariadna/ scripts/ tests/ | grep -v "test_" | grep -v "#" || echo "ok: no callers"
# Expected: solo referencias en ariadna/mcp_server.py y ariadna/storage.py (los que se borran)
```

- [ ] **Step 2: Borrar las dos tools de `ariadna/mcp_server.py`**

Eliminar el bloque completo de líneas 146-204 (`@mcp.tool(name="get_video_summary")` y `@mcp.tool(name="list_videos")` + sus funciones). El resto del archivo permanece.

- [ ] **Step 3: Borrar `CorpusStore.list_videos` de `ariadna/storage.py`**

Eliminar el método `list_videos` (líneas 226-273). Verificar que no quedan imports innecesarios tras el borrado.

- [ ] **Step 4: Smoke test del server arrancando**

```bash
# Server arranca sin errores (no import circular, no referencias rotas):
.venv/bin/python -c "from ariadna.mcp_server import mcp; print('tools:', [t.name for t in mcp._tool_manager.list_tools()])" 2>&1 | head -20
# Expected: lista sin 'get_video_summary' ni 'list_videos' (pero con 'search_corpus', 'get_wiki_page',
# y las nuevas que se wirean en Task 8.4).
```

- [ ] **Step 5: Commit**

```bash
git add ariadna/mcp_server.py ariadna/storage.py
git commit -m "refactor(mcp): retirar get_video_summary y list_videos (YouTube-específicas)

Casos de uso cubiertos por search_corpus (drill-down via filter video_id=X)
y list_research_queue (qué se ha procesado). YAGNI: si reaparece demanda,
spec separada propone get_source_summary / list_sources agnósticas al tipo.

CorpusStore.list_videos también eliminado de storage.py (sin callers tras
borrar la tool).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 8.4: Wire de las 5 tools nuevas en `mcp_server.py`

> Decora con `@mcp.tool` las funciones `*_impl` escritas en Chunks 6-7. La conexión SQLite se obtiene fresh por tool call (single-writer Phase 1; multi-writer requires future work).

**Files:**
- Modify: `ariadna/mcp_server.py` (añadir 5 @mcp.tool blocks)

- [ ] **Step 1: Apply edits**

Añadir al final de `mcp_server.py` (antes de `# Entry point`):

```python
# ---------------------------------------------------------------------------
# Write tools (project + research queue)
# ---------------------------------------------------------------------------

def _open_db_rw() -> sqlite3.Connection:
    """Conexión RW a ariadna.db. WAL mode habilita lectores concurrentes."""
    conn = sqlite3.connect(str(ARIADNA_DB))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@mcp.tool(
    name="create_project",
    description=(
        "Crea un proyecto nuevo (slug kebab-case, name, description). "
        "seed_from_templates=True copia los defaults globales a projects/<slug>/_meta/. "
        "inherit_from='<slug>' copia los overrides de otro proyecto. "
        "seed_from_templates e inherit_from son mutuamente excluyentes."
    ),
)
def create_project(
    slug: str, name: str, description: str = "",
    seed_from_templates: bool = False, inherit_from: str | None = None,
) -> dict[str, Any]:
    from ariadna.mcp_tools_write import create_project_impl
    conn = _open_db_rw()
    try:
        return create_project_impl(conn, slug=slug, name=name, description=description,
                                    seed_from_templates=seed_from_templates,
                                    inherit_from=inherit_from)
    finally:
        conn.close()


@mcp.tool(
    name="add_to_research_queue",
    description=(
        "Añade una URL a la cola de investigación de un proyecto. "
        "source_type se auto-detecta de la URL (youtube/paper/web/pdf) si no se pasa. "
        "Idempotente: misma (project, url) pending/processing devuelve el request_id existente."
    ),
)
def add_to_research_queue(
    project: str, source_url: str, source_type: str | None = None,
    notes: str = "", priority: int = 0,
) -> dict[str, Any]:
    from ariadna.mcp_tools_write import add_to_research_queue_impl
    conn = _open_db_rw()
    try:
        return add_to_research_queue_impl(
            conn, project=project, source_url=source_url,
            source_type=source_type, notes=notes, priority=priority,
        )
    finally:
        conn.close()


@mcp.tool(
    name="cancel_request",
    description=(
        "Cancela un request de la cola. pending/failed → cancelled OK. "
        "processing → NO-OP (deja al worker terminar). done/cancelled → no-op idempotente."
    ),
)
def cancel_request(request_id: str, reason: str = "") -> dict[str, Any]:
    from ariadna.mcp_tools_write import cancel_request_impl
    conn = _open_db_rw()
    try:
        return cancel_request_impl(conn, request_id=request_id, reason=reason)
    finally:
        conn.close()


@mcp.tool(
    name="list_projects",
    description=(
        "Lista proyectos con sus conteos derivados (n_pages, n_chunks, n_queue_pending). "
        "include_archived=True incluye archived; default solo activos."
    ),
)
def list_projects(include_archived: bool = False) -> dict[str, Any]:
    from ariadna.mcp_tools_read import list_projects_impl
    from ariadna.storage import CorpusStore
    from qdrant_client.http.models import Filter, FieldCondition, MatchValue
    # CorpusStore() directo (no get_searcher) — esta tool no necesita el embedder,
    # solo el QdrantClient. Evita pagar warmup BGE-M3 multi-second en la primera
    # llamada a list_projects desde el agente.
    store = CorpusStore()

    def _count_chunks(pid: str) -> int:
        return store.client.count(
            collection_name=store.collection_name,
            count_filter=Filter(must=[FieldCondition(
                key="project_id", match=MatchValue(value=pid),
            )]),
            exact=True,
        ).count

    conn = sqlite3.connect(f"file:{ARIADNA_DB}?mode=ro", uri=True)
    try:
        return list_projects_impl(conn, include_archived=include_archived,
                                   count_chunks_fn=_count_chunks)
    finally:
        conn.close()


@mcp.tool(
    name="list_research_queue",
    description=(
        "Lista items de la cola con filtros project/status/source_type. "
        "status='all' devuelve cualquier estado. limit cap (default 50). "
        "Devuelve total_matching pre-limit + filters_applied."
    ),
)
def list_research_queue(
    project: str | None = None, status: str = "pending",
    source_type: str | None = None, limit: int = 50,
) -> dict[str, Any]:
    from ariadna.mcp_tools_read import list_research_queue_impl
    conn = sqlite3.connect(f"file:{ARIADNA_DB}?mode=ro", uri=True)
    try:
        return list_research_queue_impl(conn, project=project, status=status,
                                         source_type=source_type, limit=limit)
    finally:
        conn.close()
```

Y al inicio del archivo, asegurar imports `import sqlite3` y la constante `ARIADNA_DB`.

- [ ] **Step 2: Smoke test — tools registradas**

```bash
.venv/bin/python -c "
from ariadna.mcp_server import mcp
tools = sorted(t.name for t in mcp._tool_manager.list_tools())
print(tools)
"
# Expected:
# ['add_to_research_queue', 'cancel_request', 'create_project', 'get_wiki_page',
#  'list_projects', 'list_research_queue', 'search_corpus']
# (sin get_video_summary ni list_videos)
```

- [ ] **Step 3: Commit**

```bash
git add ariadna/mcp_server.py
git commit -m "feat(mcp): wire 5 tools nuevas (create_project, add/cancel queue, list_*)

Cada tool obtiene conexión SQLite fresh por call (RW para writes, RO para
reads). list_projects construye count_chunks_fn como wrapper sobre
QdrantClient.count filtrando por project_id.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Task 8.5: Startup hook `reload_relation_types`

> Spec sección 7.3: al iniciar el server, cargar core JSON + ext de cada proyecto activo en `relation_types_canonical`. Falla loudly si hay colisión o JSON malformado.

**Files:**
- Modify: `ariadna/mcp_server.py:main()` o init temprano

- [ ] **Step 1: Apply edits**

En `main()` (o un `_warmup()` antes de `mcp.run()`):

```python
def main() -> int:
    parser = argparse.ArgumentParser(...)
    # ... resto del parser ...
    args = parser.parse_args()

    # Startup hook: relation_types
    from ariadna.project_config import reload_relation_types
    log.info("Loading relation_types_canonical from JSON sources...")
    conn = sqlite3.connect(str(ARIADNA_DB))
    try:
        reload_relation_types(conn)
        n = conn.execute("SELECT COUNT(*) FROM relation_types_canonical").fetchone()[0]
        log.info("relation_types_canonical poblado: %d filas", n)
    finally:
        conn.close()

    if args.warm:
        log.info("Precarga de searcher solicitada (--warm)...")
        _ = get_searcher()

    mcp.run(transport="streamable-http")
    return 0
```

- [ ] **Step 2: Smoke test arranque**

```bash
# Lanzar el server brevemente para confirmar que el startup hook no rompe:
timeout 5 .venv/bin/python -m ariadna.mcp_server --port 18765 2>&1 | head -20 || true
# Expected: log "relation_types_canonical poblado: 30 filas" (los 30 tipos core).
# Si rompe con ConfigError, hay colisión core↔ext que arreglar antes de seguir.
```

- [ ] **Step 3: Commit**

```bash
git add ariadna/mcp_server.py
git commit -m "feat(mcp): startup hook reload_relation_types

Al arrancar el server, repuebla relation_types_canonical desde
wiki/_meta/relation_types_core.json + cada projects/<slug>/_meta/
relation_types_ext.json en transacción atómica. Falla loudly si hay
colisión core↔ext o JSON malformado — la deuda editorial bloquea
arranque.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---
