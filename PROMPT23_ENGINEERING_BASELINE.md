# Prompt 23 — Engineering Baseline and Prompt 24 Readiness

- **Review date:** 1 November 2026
- **Repository:** `kanadm12/GridSense`
- **Branch / HEAD:** `main` / `d789f9814da9955db1c63ced921a95379dd08495`
- **Overall assessment:** **PARTIAL**
- **Windows native SQLite stability:** **BLOCKED**
- **Full repository Ruff gate:** **FAIL**

## Executive decision

Prompt 23 improved source recoverability and reproducibility without adding
energy features, providers, credentials, forecasts, or optimizers. The
checkpoint inventory, universal hash-pinned Python development lock, mobile
ESLint setup, migration portability fix, CI workflow checks, and worker-health
regressions are now documented and exercised.

The project is **not stable**: all three latest Windows full-suite runs passed
their Python assertions, but the unsuppressed native SQLite access-violation
diagnostic appeared in two of the three runs. Linux passed its latest full
run, but that does not resolve a Windows-specific native failure. The
repository-wide Ruff command still reports 174 findings and is used by the
backend CI lint job, so that job is expected to fail until the lint debt is
addressed.

No repository files were staged, committed, pushed, reset, or deleted.
Developer databases and local configuration were preserved; only
task-scoped disposable validation artifacts were removed after use.

## 1. Source and Git baseline

The inventory snapshot recorded:

| Item | Observed state |
|---|---|
| Branch and HEAD | `main`, `d789f9814da9955db1c63ced921a95379dd08495` |
| Tracked modified paths | 70 |
| Untracked paths | 653 |
| Staged paths | 0 |
| Untracked Graphify-generated files | 601 |
| Untracked backend-root `file*` test artifacts | 5 |
| Untracked implementation, fixtures, and docs | 47 |

The 47 source paths include the four untracked Alembic migrations, AER
reference data, external-data/evidence/eligibility services, Stage 1
acceptance evidence, versioned fixtures, and `backend/tests/test_health.py`.
The exact preserved paths, exclusions, full migration chain, import wiring,
and proposed review groupings are listed in
[STAGE1_SOURCE_CHECKPOINT_PLAN.md](STAGE1_SOURCE_CHECKPOINT_PLAN.md).

Ignore-rule review confirmed that local `.env`, databases, Python
environments, caches, `node_modules`, and build outputs are excluded. Expo's
`mobile/expo-env.d.ts` exclusion is generated and intentional. The AER JSON
catalog, new migrations, tests, fixtures, and Stage 1 reports are not
accidentally ignored. Credential review found no confirmed real credential
in the proposed source paths; no credential values are recorded here.

`alembic history --verbose` reports one continuous chain from
`0001_initial_schema` through `d1e2f3a4b5c6` (head). The four new migration
files are present and required. Active import/wiring checks confirmed the
context router, interval-quality services, baseline-eligibility service,
calculation evidence, AER reference-data service, weather service, schemas,
and models are connected to the active application. The full Prompt 17
acceptance report remains absent; the available Prompt 17 record is the
migration-compatibility report.

## 2. Reproducible runtime baseline

| Component | Windows | Linux comparison / services |
|---|---|---|
| OS / runtime | Windows x64 | Linux x86_64 in `gridsense-api:latest` |
| Python | CPython 3.11.9 | CPython 3.11.16 |
| SQLite | 3.45.1; Python sqlite module 2.6.0 | 3.46.1 |
| SQLAlchemy | 2.0.52 | 2.0.52 |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 | 9.1.1 / 1.4.0 |
| greenlet | 3.5.5 | 3.5.5 |
| Ruff | 0.16.3 | 0.16.3 from the lock |
| PostgreSQL / Redis | Not used for the Windows native-fault runs | PostgreSQL 16 and Redis 7 disposable services |
| Node / npm | Node 22.20.0 / npm 11.6.2 | CI pins Node 22.20.0 |

`backend/requirements-dev.lock` is a universal Python 3.11 lock with package
hashes (160 resolved package records; 4,292 lines). It was synced into a clean
Windows venv and installed in Linux with
`pip install --require-hashes -r requirements-dev.lock`. `pytest-cov` is now
declared as a development dependency, matching the CI coverage command.

Reproducible commands from the repository root:

```powershell
Push-Location backend
& ..\.venv311\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
& ..\.venv311\Scripts\python.exe -m pytest -q --capture=fd
& ..\.venv311\Scripts\python.exe -m ruff check app tests
Pop-Location

Push-Location mobile
npm ci
npm run lint
npm run typecheck
npm run export:web
Pop-Location
```

Tests were run on disposable source copies and disposable databases/services,
not on developer/demo data. A first Linux collection attempt omitted the
test-only `DEBUG` and `SECRET_KEY` environment required by `Settings` and
stopped at collection. The corrected run supplied those CI test values; the
successful result below is from that corrected run.

## 3. Windows SQLite native-fault investigation

### Latest repeated full-suite evidence

Three independent Windows processes ran from a disposable backend source copy
using the locked environment and `pytest -q --capture=fd`:

| Run | Result | Native diagnostic |
|---|---|---|
| 1 | 265 passed, 12 warnings, exit 0, 105.09 s | No |
| 2 | 265 passed, 12 warnings, exit 0, 125.33 s | **Yes** |
| 3 | 265 passed, 12 warnings, exit 0, 113.28 s | **Yes** |

The native diagnostics were detected in captured output before temporary logs
were cleaned up. A passing pytest summary or exit code does not override them.
**The Windows stability gate remains blocked.**

### Existing evidence and bounded A/B result

The Prompt 20B/20C reports trace earlier native stacks through SQLAlchemy
SQLite execution/result handling and schema inspection during fixture
teardown. They document the former `StaticPool`/shared-connection risk in a
scheduling fixture and its switch to per-test file-backed SQLite with normal
pooling. The full-suite diagnostic persisted after that mitigation. No
single deterministic test or root cause was identified.

A bounded database-heavy set of 58 tests was compared under pytest capture
modes. One `--capture=fd` run emitted a diagnostic; `--capture=sys` and `-s`
runs did not. This supports a **capture/timing interaction hypothesis** for
the native failure, but it does not prove that capture causes the fault or
identify the unsafe connection lifecycle. The different outcomes are
intermittent evidence, not containment. No diagnostic suppression, dependency
upgrade, or speculative SQLite fixture change was made for Prompt 23.

### Stability classification

**BLOCKED.** The next investigation must preserve native output, vary one
meaningful factor at a time, and reproduce/contain the fault on Windows.
Linux success is a separate platform gate and cannot be reported as a Windows
resolution.

## 4. Test, lint, migration, and mobile results

| Gate | Result | Evidence / limitation |
|---|---|---|
| Focused worker-health and migration tests | **PASS** | `tests/test_health.py tests/test_migrations.py`: 4 passed, 8 warnings, 8.28 s on the final rerun. |
| Focused Ruff for worker-health change | **PASS** | `ruff check app/api/health.py tests/test_health.py`. |
| Windows full backend suite | **BLOCKED for stability** | Each of three runs had 265 passing tests and 12 warnings; native diagnostic in 2/3 runs. |
| Linux full backend suite | **PASS for this environment** | Fresh venv, hash-locked install, disposable copy: 265 passed, 13 warnings, 116.69 s; no native diagnostic; command exit 0. |
| Full backend Ruff | **FAIL** | `ruff check app tests`: 174 findings (75 W293, 41 E501, 25 F401, 22 I001, 3 F841, 3 N806, 3 W291, 2 E712). 122 are marked fixable. |
| PostgreSQL migrations | **PASS** | PostgreSQL 16 upgrade to head, downgrade to base, and re-upgrade to `d1e2f3a4b5c6` passed. |
| CI workflow syntax | **PASS for parsing only** | PyYAML parsed `.github/workflows/ci.yml` and found nine jobs. Hosted GitHub Actions was not run. |
| Clean mobile dependency sync | **PASS** | `npm ci` in a disposable copy succeeded. The non-silent install reported 967 packages added, 968 audited, and 64 npm vulnerabilities: 2 low, 43 moderate, 18 high, 1 critical. No audit fix was applied. |
| Mobile ESLint | **PASS with warnings** | ESLint 9.39.1 / Expo flat config: 0 errors, 18 warnings. npm warns that ESLint 9.39.1 is no longer supported. |
| Mobile TypeScript | **PASS** | `npx tsc --noEmit` in the clean copy. |
| Expo web export | **PASS** | Clean-copy export bundled 1,075 modules; web entry bundle about 2.38 MB. |
| Updated Markdown links | **PASS** | Local links in `STAGE1_SOURCE_CHECKPOINT_PLAN.md`, `PROMPT23_ENGINEERING_BASELINE.md`, `BASELINE_VERIFICATION.md`, and `DEVELOPMENT_STATUS.md` resolve. |
| `git diff --check` | **PASS** | No whitespace errors; Git emitted existing LF-to-CRLF normalization warnings for several tracked files. |

The full Ruff failure is material: the existing `backend-lint` workflow runs
`ruff check app tests`, so that CI job is currently expected to fail. The
focused changed-file Ruff gate passes; no broad formatting cleanup or blanket
lint suppression was applied. The mobile manifest still has a Jest `test`
script without Jest installed and no mobile test suite was found; this is not
claimed as a passing mobile unit-test gate.

## 5. Operational smoke and justified source fix

The disposable PostgreSQL-backed operational smoke from this Prompt 23
segment passed API liveness/readiness, registration/login, cross-user meter
denial, explicitly classified synthetic usage, unknown-direction exclusion,
confirmed-versus-illustrative tariff separation, and deterministic synthetic
scheduling. It originally failed only at worker health, exposing two
source-level incompatibilities:

1. `/health/worker` imported `get_redis_conn` from `app.worker`, where that
   symbol does not exist. The established helper is
   `app.tasks.get_redis_conn`.
2. With locked RQ 2.11, `Queue` has no `.workers` attribute. Worker discovery
   must use `Worker.all(connection=redis, queue=queue)`.

The health route now uses the existing task connection helper and RQ's worker
registry. It returns 503 `worker:not_running` when Redis is reachable but no
worker is registered, instead of reporting a healthy worker state with a
zero count. Redis connection failures still return 503 `worker:unreachable`.
Regression tests cover a reachable worker/queue, no worker, and Redis
unavailable.

Operational verification after the fix:

- TestClient `GET /health/worker`, with the auth dependency overridden to a
  test user, against disposable Redis 7 and a real RQ 2.11 worker returned
  HTTP 200 with `workers: 1`, `jobs_queued: 0`, and `jobs_failed: 0`. This
  validates the route and worker query, not production authentication.
  redis-py emitted a debug-level unsupported `CLIENT MAINT_NOTIFICATIONS`
  message against Redis 7; it did not affect the successful response.
- With Redis live and no worker, the health function returned HTTP 503 with
  `{"status":"unavailable","worker":"not_running","workers":0}`.
- The Redis-unreachable regression returns HTTP 503 with
  `{"status":"unavailable","worker":"unreachable"}`.

These are disposable service checks, not production deployment validation.
No AEMO, AER, Open-Meteo, AI, SMTP, or Home Assistant credentials were
configured. The unknown-direction NEM12 fixture remains excluded from
eligible measured usage.

## 6. PASS / PARTIAL / BLOCKED / FAIL assessment

| Requirement | Status | Evidence, exact condition, and next action |
|---|---|---|
| Preserve and inventory the Prompt 17–22 source baseline | **PASS** | Exact modified/untracked source and exclusion list is in the checkpoint plan. No files staged or discarded. Review untracked source paths before any future staging. |
| Reproducible Python and mobile dependency installation | **PASS** | Hash-locked Python install passed in clean Windows and Linux environments; clean mobile `npm ci` passed. Keep the lock files synchronized when manifests change. |
| Alembic chain and PostgreSQL migration cycle | **PASS** | One complete chain; PostgreSQL 16 upgrade/downgrade/re-upgrade passed. Retain the portability correction and rerun the cycle for later migration edits. |
| Linux full backend regression | **PASS** | 265 passed, 13 warnings, no native diagnostic in the disposable locked environment. Continue as an independent Linux gate. |
| Windows backend assertions | **PASS** | 265 tests passed in each of 3 runs. This is separate from native stability. |
| Windows native SQLite stability | **BLOCKED** | Diagnostic observed in 2/3 full runs. No proven root cause or satisfactory containment. Continue controlled native investigation; do not call the repository stable. |
| Repository-wide backend Ruff | **FAIL** | 174 findings, and the CI lint job invokes the failing full check. Fix the lint debt in scoped reviewed changes or agree an explicit incremental gate; do not silently suppress it. |
| Mobile lint, TypeScript, and web export | **PASS** | Clean-copy checks pass; ESLint has 18 warnings, and npm reports 64 dependency advisories. Review advisories and warnings in a separately scoped dependency/security task. |
| Worker availability and failure reporting | **PASS** | Unit tests plus real Redis/RQ/TestClient checks distinguish an active worker, no worker, and Redis unreachable. |
| Hosted CI execution | **PARTIAL** | Workflow YAML parses and its commands are locally reproducible, but GitHub Actions was not run. Its full Ruff step is known to fail at the present baseline. |
| Production readiness | **BLOCKED** | No production deployment exercise, real-household semantic validation, confirmed customer tariff validation, verified measured scheduling baseline, or provider/legal credentials. A synthetic demo is not field validation. |

## 7. Prompt 24 readiness

**PARTIAL — ready for a bounded engineering-remediation prompt, not a feature
or production-readiness claim.** Prompt 24 should prioritize:

1. Continue Windows SQLite fault isolation with preserved native diagnostics
   and controlled A/B variables. If the root cause cannot be established,
   keep Windows explicitly blocked and rely on a separately verified Linux
   gate without calling the Windows suite stable.
2. Resolve the 174 Ruff findings in reviewed, scoped batches so the existing
   backend CI lint job can pass; retain the focused Ruff check for changed
   files during the cleanup.
3. Execute the actual hosted CI workflow after its lint gate is green and
   retain platform-specific logs.
4. Review the source checkpoint plan and obtain approval before staging or
   committing anything.

Stage 1 remains suitable only for controlled, explicitly synthetic/advisory
demonstrations under the existing limitations. It is not suitable for
real-household financial decisions or production deployment.
