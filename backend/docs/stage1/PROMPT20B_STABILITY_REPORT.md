# Prompt 20B — SQLite native diagnostics and test stability

**Assessment: PARTIAL — stability is not established.**\
**Run date:** 1 November 2026\
**Repository revision:** `d789f9814da9955db1c63ced921a95379dd08495`

## Executive result

The reported Windows access violation was reproduced during the scheduling
contract module's fixture teardown. Before the test-fixture change, two of
three consecutive captured module runs printed native access-violation
diagnostics while still reporting all 19 tests passed. The reported frames
included SQLAlchemy schema-drop traversal and SQLAlchemy result materialization.

The original fixture used an in-memory SQLite database with `StaticPool` and
`check_same_thread=False`. Its setup `Session` remained open while TestClient
request sessions ran on application worker threads. `StaticPool` can hand the
same underlying DBAPI connection to these sessions. This is an unsafe test
isolation pattern and a plausible contributing cause, but it is **not a
confirmed root cause**.

The fixture now uses a per-test temporary SQLite file and normal per-connection
pooling. The scheduling module then passed three repeated captured runs, one
uncaptured run, and all ten database-backed tests run individually without
diagnostics. Three post-change full-suite runs all passed 261 tests, but two
of those three runs printed native access-violation diagnostics. One of the
two diagnostic runs printed two separate native traces. Therefore the change
is a targeted isolation mitigation, not a verified resolution. No dependency
versions were changed.

**Prompt 21 readiness:** Do not call the repository's backend test baseline
stable or use it as a clean Stage 1 stability gate yet. Prompt 21 work may
proceed only if the residual diagnostic is tracked as an explicit blocker and
not treated as harmless. Before claiming stability, identify the remaining
native failure source and obtain repeated full-suite runs with no diagnostic,
or document an independently verified containment.

## Baseline and repository state

- `HEAD`: `d789f9814da9955db1c63ced921a95379dd08495`.
- The worktree was already dirty with Prompt 17–20 implementation and
  documentation changes. These were preserved; no reset, checkout, commit, or
  push was performed.
- `git diff --cached --name-only` was empty at inspection. No credentials,
  local database, virtual environment, cache, or graph artifact was staged.
- pytest databases created for the modified scheduling fixture are disposable
  files under pytest's `tmp_path`; they are not application or user databases.
  The 30 retained scheduling database files from the three latest pytest
  sessions were removed after verification; pytest's parent temp directories
  were left intact.
- The task's proposed staging list is at the end of this report. Nothing has
  been staged.

### Environment recorded

| Component | Version / detail |
|---|---|
| OS | Windows 10 build `10.0.26200` (64-bit) |
| Python | CPython `3.11.9`, MSC v.1938 AMD64 |
| SQLite runtime | `3.45.1` |
| Python sqlite module | stdlib extension, module version `2.6.0` |
| SQLite threading | `sqlite3.threadsafety == 3`; compile options include `THREADSAFE=1` and `MUTEX_W32` |
| SQLAlchemy | `2.0.52` |
| pytest | `9.1.1` |
| greenlet | `3.5.5` |
| aiosqlite | Not installed |
| `PYTHONFAULTHANDLER` / `PYTHONMALLOC` | Unset |

These are the interpreter and packages from `.venv311`; the SQLite library is
the runtime linked to that Python installation. The SQLAlchemy SQLite tests
here are synchronous; aiosqlite is not in this execution path.

## Reproduction results

All commands below were run from `backend/` with
`..\\.venv311\\Scripts\\python.exe`.

| Run | Command / mode | Result |
|---|---|---|
| Collection | `-m pytest --collect-only -q tests\\test_scheduling_contract.py` | 19 tests collected. |
| Before fixture change, module | `-m pytest tests\\test_scheduling_contract.py -q` | 19 passed, 6 warnings; no diagnostic in this run. |
| Before fixture change, module without pytest capture | `-m pytest -s -q tests\\test_scheduling_contract.py` | 19 passed, 6 warnings; no diagnostic in this run. |
| Before fixture change, individual repeated API test | `test_scheduling_fixture_validates_and_openapi_exposes_v1`, three separate processes | 3/3 passed, no diagnostic. |
| Before fixture change, bounded module repetitions | The captured module command, three consecutive processes | 2/3 runs printed a Windows native access-violation diagnostic; all three runs still reported 19 passed, 6 warnings. |
| After fixture change, bounded module repetitions | Same captured module command, three consecutive processes | 3/3 runs: 19 passed, 6 warnings; no diagnostic. |
| After fixture change, module without capture | `-m pytest -s -q tests\\test_scheduling_contract.py` | 19 passed, 6 warnings; no diagnostic. |
| After fixture change, individual DB-backed tests | Each of the 10 tests using `scheduling_api`, in a separate process | 10/10 passed; no diagnostic. |
| After fixture change, focused integration run without capture | `-m pytest -s -q tests\\test_scheduling_contract.py tests\\test_vertical_slice.py tests\\test_migrations.py` | 23 passed, 10 warnings; no diagnostic. |
| After fixture change, bounded full-suite repetitions | `-m pytest -q`, three separate processes | 3/3 runs: 261 passed, 12 warnings. Durations 58.44 s, 49.53 s, and 66.63 s. Native diagnostics in 2/3 runs; the third run was clean. One diagnostic run printed two native stack traces. |

### Native stack evidence

Before the fixture change, the repeated module run produced two different
representative stack locations:

1. SQLAlchemy `ddl.visit_table` / `visit_metadata` →
   `Base.metadata.drop_all()` → `tests/test_scheduling_contract.py` fixture
   teardown. All 19 tests passed.
2. SQLAlchemy `engine/result.py::_allrows` while pytest continued. All 19
   tests passed.

After the fixture change, the full-suite traces still implicated SQLAlchemy
schema teardown. One trace was:

```text
Windows fatal exception: access violation
sqlalchemy.engine.default.do_execute
sqlalchemy.engine.base._exec_single_context / exec_driver_sql
sqlalchemy.dialects.sqlite.base._get_table_pragma / has_table
sqlalchemy.sql.ddl._can_drop_table / visit_metadata
sqlalchemy.sql.schema.MetaData.drop_all
backend/tests/test_scheduling_contract.py fixture teardown
```

The observed phase is fixture teardown during `Base.metadata.drop_all()`;
SQLAlchemy is introspecting SQLite schema state via a PRAGMA. The full-suite
test processes exited successfully and reported all tests passed, but two of
three full-suite runs still had native diagnostics. A second trace in one run
was in SQLAlchemy result processor setup (`type_api._cached_result_processor`
and `engine.default.get_result_processor`). The diagnostics remain failure
signals and are not classified as harmless.

`sqlite3.threadsafety == 3` and `THREADSAFE=1` show that this Python SQLite
build uses serialized threading support. They do not prove that SQLAlchemy
sessions sharing one checked-out connection through `StaticPool` are safe.
Conversely, the full-suite diagnostic after replacing that pattern shows that
the sharing pattern alone does not explain all observed occurrences.

## Change and root-cause assessment

### Implemented mitigation

Changed only the `scheduling_api` test fixture in
[`test_scheduling_contract.py`](../../tests/test_scheduling_contract.py):

- Replaced the shared in-memory `StaticPool` engine with a per-test SQLite
  database file under pytest's `tmp_path`.
- Removed `check_same_thread=False`; TestClient request sessions obtain normal
  pooled connections rather than reusing the fixture's single DBAPI connection.
- Retained explicit fixture cleanup order: restore dependency overrides, close
  the setup session, drop test tables, and dispose the engine.

This removes a concrete cross-session/cross-thread connection-sharing hazard
from the targeted fixture. It improved isolated repeatability in the bounded
sample, but did not eliminate the full-suite diagnostic.

### Root cause

**Unresolved.** Evidence supports the fixture's former `StaticPool` sharing as
a credible contributing defect, but does not support claiming it was the
complete root cause. The remaining diagnostic could involve state from earlier
tests, a separate native-library interaction, or another lifecycle issue; none
has been isolated. These are hypotheses only.

No Python, SQLite, SQLAlchemy, greenlet, or pytest upgrades were attempted.
There was no evidence justifying a dependency change or broad database
infrastructure rewrite.

### Containment until resolved

- Keep all test SQLite databases disposable and isolated; do not point tests
  at developer, demo, staging, or production databases.
- Keep the scheduling test fixture on file-backed per-test SQLite connections.
- Treat any `Windows fatal exception: access violation` as a failed stability
  signal even when pytest exits 0.
- Preserve stdout/stderr and the native stack from affected runs.
- Do not suppress faulthandler output or mark the diagnostic as expected.
- Do not certify Prompt 21's baseline until full-suite repetition is clean or
  the remaining native fault has an independently verified containment.

## Verification after the fixture change

| Check | Command | Result |
|---|---|---|
| Scheduling contract module, captured | `..\\.venv311\\Scripts\\python.exe -m pytest -q tests\\test_scheduling_contract.py` repeated 3 times | **PASS — 19 passed on each run; no diagnostic.** |
| Scheduling contract module, uncaptured | `..\\.venv311\\Scripts\\python.exe -m pytest -s -q tests\\test_scheduling_contract.py` | **PASS — 19 passed; no diagnostic.** |
| Scheduling, vertical-slice and migrations integration | `..\\.venv311\\Scripts\\python.exe -m pytest -s -q tests\\test_scheduling_contract.py tests\\test_vertical_slice.py tests\\test_migrations.py` | **PASS — 23 passed, 10 warnings; no diagnostic.** |
| Full backend suite | `..\\.venv311\\Scripts\\python.exe -m pytest -q`, three separate runs | **TESTS PASS / STABILITY FAIL — 261 passed, 12 warnings on all runs; 58.44 s, 49.53 s, and 66.63 s. Native diagnostics in 2/3 runs; one run was clean.** |
| Ruff | `..\\.venv311\\Scripts\\python.exe -m ruff check tests\\test_scheduling_contract.py` | **PASS.** |
| Mobile TypeScript | `npx tsc --noEmit` from `mobile/` | **PASS.** |
| Migration compatibility | Included in focused integration run; no migration was added | **PASS for covered migration tests; PostgreSQL service was not rerun.** |

The full backend run is therefore not marked as a clean stability pass.

## Change inventory and proposed staging list

### Changes made for Prompt 20B

1. Modified [`test_scheduling_contract.py`](../../tests/test_scheduling_contract.py)
   to use isolated file-backed test databases rather than cross-thread
   `StaticPool` reuse.
2. Added this report.
3. Updated the Prompt 20B record in
   [`BASELINE_VERIFICATION.md`](../../../BASELINE_VERIFICATION.md).

No application behavior, schema, migration, tariff logic, recommendation
logic, or external provider configuration was changed.

### Proposed clean staging list — not staged

- `backend/tests/test_scheduling_contract.py`
- `backend/docs/stage1/PROMPT20B_STABILITY_REPORT.md`
- `BASELINE_VERIFICATION.md` — **stage only the new Prompt 20B section**. This
  file already contains earlier dirty Prompt 17–20 material; do not stage the
  entire file without reviewing and preserving those changes.

`git diff --cached --name-only` was empty when the baseline was recorded. Do
not stage `.env` files, local databases, `.venv*`, pytest caches, generated
Graphify outputs, or the pre-existing unrelated worktree changes. No commit or
push is authorized.
