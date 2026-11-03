# Prompt 20C — native SQLite access-violation investigation

**Stability verdict: PARTIAL — native fault unresolved.**\
**Run date:** 1 November 2026\
**Starting revision:** `d789f9814da9955db1c63ced921a95379dd08495`

## Executive finding

The Windows access violation remains intermittent. The Prompt 20B
file-backed/per-test scheduling fixture is an appropriate isolation
improvement, but it does not prevent the full-suite diagnostic. I could not
isolate a single test or a deterministic test ordering as the cause.

On Windows, three separate full-suite processes each reported **261 passed,
12 warnings**. Two of those runs printed native access-violation diagnostics;
one did not. The traces were reported in SQLAlchemy SQLite schema inspection
during scheduling fixture teardown and SQLAlchemy result-processor code. A
test count and process exit code of zero do not make those runs stable.

An anomaly-detector-plus-scheduling module pair reproduced intermittently in
both test orders, but reducing it to the full anomaly module plus one
scheduling API test produced no diagnostic in ten runs. One group of other
SQLite-heavy modules also emitted diagnostics once. These observations show
intermittency, not cause.

The Linux comparison (same SQLAlchemy, greenlet and pytest versions, but newer
Python patch version and SQLite runtime) passed both the focused reproducer
group and the full suite without native diagnostics. This makes a
Windows/runtime-specific interaction plausible, but a single Linux run and
the different Python/SQLite builds do not prove that.

**No new source fix is supported by this evidence.** The Prompt 20B
file-backed scheduling fixture remains in the worktree. No dependencies were
upgraded, no database migrations or application changes were made, and no
commit or push occurred.

## Repository and data safety baseline

- Starting `HEAD`: `d789f9814da9955db1c63ced921a95379dd08495`.
- The worktree was already dirty from Prompt 17–20B. Existing changes were
  preserved.
- The index was empty: `git diff --cached --name-only` returned no paths.
- A staged-path check found no `.env`, local database, virtual environment,
  cache, or Graphify output.
- No developer/demo database, credential, deployment service, or external
  provider configuration was accessed or changed.
- Linux runs used disposable `docker run --rm` containers. No Docker
  containers were running before those runs. Docker wrote no test database
  onto the mounted source tree.
- Temporary scheduling SQLite test databases and task-specific diagnostic
  logs from Prompt 20B/C runs were removed. Pytest parent temporary
  directories were left intact.
- No files were staged, committed, reset, or pushed.

## Environment versions

| Component | Windows primary environment | Linux comparison |
|---|---|---|
| OS | Windows 10 build `10.0.26200`, x64 | Linux x86_64 in existing local `gridsense-api:latest` image |
| Python | CPython 3.11.9, MSC v.1938 AMD64 | CPython 3.11.16, GCC 14.2 |
| SQLite runtime | 3.45.1 | 3.46.1 |
| Python sqlite module | 2.6.0 | Standard library module |
| SQLAlchemy | 2.0.52 | 2.0.52 |
| greenlet | 3.5.5 | 3.5.5 |
| pytest | 9.1.1 | 9.1.1 |
| pytest-asyncio | 1.4.0 | 1.4.0 |
| SQLite threading report | `threadsafety=3`; compile options `THREADSAFE=1`, `MUTEX_W32` | Not separately recorded |
| `PYTHONFAULTHANDLER` / `PYTHONMALLOC` | Unset | Container defaults |

The Linux image already contained the backend runtime dependencies. Pytest and
pytest-asyncio were installed inside each disposable container invocation;
the host environment and project manifests were not changed. This is not a
fresh full dependency resolution from `pyproject.toml`.

## Fixture and connection lifecycle audit

The audit searched backend tests for `create_engine`, `Base.metadata` schema
operations, SQLite pool/thread options, `TestClient`, and dependency
overrides. This table records the observed patterns; it does not imply each
one causes the native diagnostic.

| Test file(s) | Engine / pool pattern | Session/schema cleanup | Client and override lifecycle |
|---|---|---|---|
| `tests/conftest.py` | Per-fixture `sqlite:///:memory:`; default SQLite pool | Closes session; no explicit `drop_all()` or `dispose()` | Generic session fixture; no TestClient override. |
| `test_anomaly_detector.py`, `test_billing.py`, `test_forecasting.py`, `test_usage_analyzer.py` | Module-global `sqlite:///:memory:`; `check_same_thread=False`; default pool | Per-test `create_all`; closes session then `drop_all`; no explicit engine disposal | No TestClient fixture in these modules. |
| `test_notification_service.py` | Fixture-local `sqlite:///:memory:`; `check_same_thread=False` | Closes session then `drop_all`; engine is not explicitly disposed | No FastAPI TestClient. |
| `test_auth.py`, `test_insights_endpoints.py`, `test_ml.py`, `test_password_reset.py` | Module-global shared-cache in-memory SQLite URI; `check_same_thread=False`, `uri=True` | `create_all` and `drop_all`; engine generally remains undisposed | API modules use TestClient. Some clear global dependency overrides instead of restoring the prior map. |
| `test_upload.py`, `test_rate_limits.py`, `test_vertical_slice.py` | Module-global `sqlite://` plus `StaticPool`, `check_same_thread=False` | `create_all` and `drop_all`; no explicit engine disposal | TestClient APIs use worker threads. `test_rate_limits.py` restores prior overrides; upload/vertical-slice teardown clears overrides. |
| `test_scheduling_contract.py` | Per-test temporary file-backed SQLite; normal pooling; default thread checking | Closes setup session, drops schema, disposes engine after TestClient exits | Restores prior dependency overrides. This is the Prompt 20B isolation change. |
| `test_external_data.py` | Database obtained from `test_db` in `conftest.py` | Cleanup inherited from `conftest.py` | Saves/restores dependency overrides around TestClient. |
| `test_demo_seed.py`, `test_migrations.py` | Disposable file-backed SQLite files | Explicit engine disposal in cleanup paths | No persistent application database. |

The audit found lifecycle-hardening opportunities: several global test
engines are not explicitly disposed; some TestClient fixtures clear overrides
instead of restoring prior values; multiple API fixtures use
`StaticPool`/`check_same_thread=False`. None is by itself confirmed as the
fault source. In particular, changing the scheduling fixture removed its
shared single-connection hazard, but full-suite diagnostics persisted.

## Reproduction and test-order experiments

Commands were run from `backend/` with
`..\\.venv311\\Scripts\\python.exe`, except where marked Docker/Linux.

| Experiment | Repetitions | Result |
|---|---:|---|
| Scheduling module alone before Prompt 20B fixture change | 3 captured | 2/3 emitted diagnostics; each reported 19 passing tests. |
| Scheduling module alone after file-backed fixture change | 3 captured + 1 uncaptured | 4/4 had 19 passing tests and no diagnostic. |
| Ten DB-backed scheduling tests, individually, after fixture change | 10 | All passed; no diagnostic. |
| Scheduling + vertical-slice + migrations, uncaptured | 1 | 23 passed; no diagnostic. |
| Anomaly module then scheduling module | 3 | One run printed native diagnostics; all three runs passed. |
| Scheduling module then anomaly module | 3 | One run printed native diagnostics; all three runs passed. |
| Anomaly module then one scheduling API smoke test | 5 | 0/5 diagnostics. |
| One scheduling API smoke test then anomaly module | 5 | 0/5 diagnostics. |
| Each of three anomaly test classes/subgroups then scheduling | 3 different groups | No diagnostic in these individual runs. |
| `test_upload`, `test_rate_limits`, `test_vertical_slice` then scheduling | 3 | 0/3 diagnostics. |
| Scheduling then those StaticPool modules | 3 | 1/3 emitted diagnostics; all tests passed. |
| `test_auth`, `test_insights_endpoints`, `test_ml` then scheduling | 1 | No diagnostic. |
| Billing + anomaly + forecasting + usage-analyzer modules then scheduling | 1 | Native diagnostic mentions in the scheduling fixture path; 66 tests passed. |
| Full Windows suite after Prompt 20B fixture change | 3 independent processes | 3/3: 261 passed, 12 warnings. Durations 58.44 s, 49.53 s, 66.63 s. Diagnostics in 2/3 runs; one run clean. |
| Full Windows suite without capture (`-s`) | 2 independent processes | 2/2: 261 passed, 12 warnings; no diagnostic. |
| Full Windows suite with Python-stream capture (`--capture=sys`) | 1 process | 261 passed, 12 warnings; no diagnostic. |
| Anomaly + scheduling focused group in Linux container | 1 | 24 passed, 7 warnings; no diagnostic. |
| Full backend suite in Linux container | 1 | 261 passed, 13 warnings; no native diagnostic. |

The Windows native traces observed in prior runs included:

```text
Windows fatal exception: access violation
sqlalchemy.engine.default.do_execute / engine.base.exec_driver_sql
sqlalchemy.dialects.sqlite.base._get_table_pragma / has_table
sqlalchemy.sql.ddl._can_drop_table / visit_metadata
sqlalchemy.sql.schema.MetaData.drop_all
tests/test_scheduling_contract.py fixture teardown
```

Other traces were observed in SQLAlchemy result construction and result
processor setup. The repeat experiments do not establish that the teardown
call is the origin; it may be where earlier invalid native state is next used.

### Minimal reproducer status

**No reliable minimal reproducer was isolated.** The smallest intermittently
reproducing combination observed was the complete anomaly-detector module
paired with the scheduling module (24 tests total), but it was clean in four
of six runs and showed the diagnostic in either module ordering. Reducing the
scheduling side to one API smoke test yielded ten clean attempts. No individual
anomaly class followed by scheduling reproduced in its one-run check.

Therefore the evidence does not justify attributing the issue to the anomaly
module, the scheduling module, a specific fixture, `StaticPool`, a specific
SQLite connection, or one test order.

### Pytest capture-mode signal

The three Windows default-capture full-suite runs had diagnostics in 2/3
processes. Two full runs with capture disabled (`-s`) and one using
`--capture=sys` had no diagnostic. This is a preliminary association with
pytest's default file-descriptor capture, not a causal finding: the samples
are small, the fault is intermittent, and the native stack still points into
SQLAlchemy/SQLite calls. More controlled repetitions of `--capture=fd`,
`--capture=sys`, and `-s` are required before treating capture mode as a
trigger or containment.

## Root-cause assessment and containment

**Root cause: unresolved.** The evidence is consistent with a
Windows-native-library/runtime issue, a sporadic SQLite connection/lifetime
interaction, or a pytest file-descriptor-capture interaction, but none is
verified. Windows used Python 3.11.9 and SQLite 3.45.1; Linux used Python
3.11.16 and SQLite 3.46.1. The Linux success does not distinguish those
variables, and one clean Linux run does not establish a stable Linux baseline.

No dependency upgrades or broad fixture rewrites were attempted. The Prompt
20B file-backed scheduling fixture remains as a local mitigation because it
removes the original StaticPool sharing hazard and its isolated module runs
were clean. Do not mask the message, convert it to an expected warning, or
use pytest's exit status as stability evidence.

Until isolated:

1. Keep test databases disposable and never point them at developer, demo,
   staging, or production databases.
2. Record full stdout/stderr and the native stack for any occurrence.
3. Treat any native access-violation diagnostic as a stability failure even
   if pytest reports all tests passed and exits zero.
4. Require a clean repeated full-suite Windows run, or an independently
   verified containment, before declaring the baseline stable.
5. If testing possible lifecycle fixes, change one fixture at a time and
   require repeatable A/B evidence; do not broadly alter all test engines.

## Verification commands and status

| Check | Command | Result |
|---|---|---|
| Windows affected module | `..\\.venv311\\Scripts\\python.exe -m pytest -q tests\\test_scheduling_contract.py` | **PASS for test assertions; isolated repetitions clean after Prompt 20B change.** |
| Windows full suite | `..\\.venv311\\Scripts\\python.exe -m pytest -q` | **Tests PASS / stability FAIL — 261 passed, 12 warnings on all 3 runs; native diagnostics in 2/3.** |
| Windows capture comparison | `pytest -s -q` twice; `pytest --capture=sys -q` once | **261 passed on all; no diagnostic in these 3 runs. Preliminary capture-mode correlation only.** |
| Linux focused reproducer | Disposable `gridsense-api:latest` container; `python -m pytest -q tests/test_anomaly_detector.py tests/test_scheduling_contract.py` | **PASS — 24 passed, no diagnostic in one run.** |
| Linux full suite | Same image, `python -m pytest -q` | **PASS — 261 passed, 13 warnings; no native diagnostic in one run.** |
| Ruff | `..\\.venv311\\Scripts\\python.exe -m ruff check tests\\test_scheduling_contract.py` | **PASS.** |
| Mobile TypeScript | `npx tsc --noEmit` from `mobile/` | **PASS.** |
| Integration/migrations | `pytest -s -q tests\\test_scheduling_contract.py tests\\test_vertical_slice.py tests\\test_migrations.py` | **PASS — 23 passed; no native diagnostic.** No new migration was added. |
| Whitespace | `git diff --check` | **PASS.** |

### Explicit verdict

- **Reproduced:** YES, intermittently on Windows.
- **Deterministic minimal reproducer:** NO.
- **Root cause confirmed:** NO.
- **Candidate code fix independently verified:** NO. The existing Prompt 20B
  scheduling-fixture isolation is retained, but residual diagnostics remain.
- **Stability:** **PARTIAL / unresolved**.
- **Prompt 21 readiness:** **BLOCKED for claiming a clean/stable backend test
  baseline.** Feature work must not relabel or suppress this issue.

## Change inventory and proposed staging list

Prompt 20C adds this report and updates the Prompt 20C section of
[`BASELINE_VERIFICATION.md`](../../../BASELINE_VERIFICATION.md). No source
change was made because causal evidence was insufficient. The existing
Prompt 20B change in [`test_scheduling_contract.py`](../../tests/test_scheduling_contract.py)
is still dirty and predates this investigation.

**Proposed staging list only; nothing is staged:**

- `backend/docs/stage1/PROMPT20C_NATIVE_FAULT_REPORT.md`
- `BASELINE_VERIFICATION.md` — stage only the new Prompt 20C section after
  reviewing the pre-existing Prompt 17–20B changes in the same file.
- Do not add `test_scheduling_contract.py` as a Prompt 20C change; it is the
  retained Prompt 20B mitigation and should be staged only if that earlier
  task's change is separately approved.

Exclude credentials, local databases, `.venv*`, pytest caches, generated
Graphify output, and all unrelated pre-existing modifications. No commit or
push is authorized.
