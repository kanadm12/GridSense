# PROMPT 23E — Database Test Stability

Status: **Windows SQLite native stability BLOCKED. Stabilisation gate NOT complete.**

## 0. Final closure status (current round)

- **Restricted PostgreSQL 16 (`gs_it_23e`, no superuser bypass).** Full backend suite on the adopted 158-pin lock: 389 passed, 0 skipped, exit 0 (`python:3.11.16-slim`, `--require-hashes`, `-rs`). Includes the migration-to-head test.
- **Linux CI runtime.** Supported verification configuration. Without PostgreSQL, the earlier clean-copy run gave 331 passed and 24 expected PostgreSQL skips.
- **Windows SQLite.** Native access violation remains BLOCKED and explicitly unsupported. Excluded from release acceptance. Not reopened, and not claimed fixed. PostgreSQL coverage is not claimed to be equivalent to the Windows SQLite path.
- **Regression detection on Linux.** SQLite-related regressions remain detectable by the Linux suite, which runs without PostgreSQL, and by the PostgreSQL integration suite.

## 1. Summary

| Area | Result |
|---|---|
| Per-request DDL in `get_db()` | FIXED: `Base.metadata.create_all` removed; schema is managed only by Alembic. |
| Windows SQLite native access violation | BLOCKED: still reproduces in the corrected source (see §3). Not fixed. |
| PostgreSQL integration suite | PASS: 19/19 (12 integration tests + 7 fixture-guard tests). Linux and repeated runs not yet done. |
| Full SQLite backend pytest (Windows) | 267 passed, but process exit 1 from a native fault traceback in teardown. Not a clean pass. |
| Backend Ruff (`ruff check .`, and CI gate `ruff check app tests`) | PASS (CI gate passes; full-tree format drift in 60 files is non-gating and not changed). |
| Mobile lint / typecheck / Expo Doctor | PASS (lint exit 0, `tsc --noEmit` exit 0, 20/20 Expo Doctor checks). |
| npm production audit | PASS: 0 vulnerabilities. |
| npm full audit | 14 moderate, 0 high/critical (development tooling; not yet remediated). |
| CI hardening | PARTIAL: top-level `permissions: contents: read` added; `security-scan` job has `security-events: write`. Trivy is still `@master`; actions still use major tags; `safety check ... || true` still non-gating. |
| Hosted GitHub Actions | NOT VERIFIED. No hosted run occurred. |

## 2. Changes made in this phase

1. [backend/app/database.py](/C:/Users/Kanad/Desktop/PROJECTS/GridSense/backend/app/database.py): `get_db()` no longer calls `create_all`. The session is closed in `finally`.
2. [backend/tests/test_database_lifecycle.py](/C:/Users/Kanad/Desktop/PROJECTS/GridSense/backend/tests/test_database_lifecycle.py) (new, 2 tests): `get_db` issues no DDL and releases its connection after close and after an exception.
3. [backend/tests/test_scheduling_contract.py](/C:/Users/Kanad/Desktop/PROJECTS/GridSense/backend/tests/test_scheduling_contract.py): teardown asserts zero checked-out connections before `drop_all`; the engine is disposed in `finally`.
4. PostgreSQL integration profile, [backend/tests/integration/](/C:/Users/Kanad/Desktop/PROJECTS/GridSense/backend/tests/integration):
   - `conftest.py`: explicit opt-in via `GRIDSENSE_INTEGRATION_DATABASE_URL`; URL must be `postgresql*` and the database name must contain `test` and not be `gridsense` or `gridsense_test_prod`; one session-scoped schema `gs_it_<hex>` migrated with `alembic upgrade head`; dropped with `CASCADE` at the end. `pg_db` now asserts `current_schema()` equals the test schema before truncating, and truncates schema-qualified tables only.
   - `test_auth_and_meters.py` (5), `test_upload_journey.py` (2), `test_tariffs_billing.py` (5, new), `test_fixture_guards.py` (7, new: refuses non-disposable names and non-PostgreSQL drivers, accepts the disposable name, and skips when unset). No test connects to a database for the guard checks.
5. Ruff: 11 import-order fixes applied (`ruff check --fix --select I001`, behaviour-preserving) plus manual E501 wraps in `alembic/versions/c9d0e1f2a3b4_add_immutable_tariff_revisions.py`, `scripts/staging_smoke.py` and the new integration files. No logic changed.
6. [.github/workflows/ci.yml](/C:/Users/Kanad/Desktop/PROJECTS/GridSense/.github/workflows/ci.yml): top-level `permissions: contents: read`; `security-scan` job adds `security-events: write`.

## 3. Native-fault experiments (Windows, SQLite, `--capture=fd`, Python 3.11.9, SQLAlchemy 2.0.52, pytest 9.1.1)

Collection fingerprint `4c0adbaf…` was identical across the corrected arm's runs. The baseline run fingerprint is recorded in [PROMPT23D_FULL_SUITE_COMPARISON.md](/C:/Users/Kanad/Desktop/PROJECTS/GridSense/backend/docs/stage1/PROMPT23D_FULL_SUITE_COMPARISON.md).

| Arm | Runs | Native diagnostic runs | Harness exit | Notes |
|---|---|---|---|---|
| Baseline (unmodified source) | 5 (this phase) | 4 of 5 | pytest 0; harness 1 when diagnostic present | Matches the 23D finding. |
| Corrected (`create_all` removed, checked-out assertion) | 5 | 2 of 5 (runs 3, 4: 3 and 2 access-violation lines) | 0, 0, 1, 1, 0 | Fingerprint identical; all pytest exits 0. |
| Full suite, un-harnessed `pytest tests --ignore=tests/integration` | 1 | Yes (traceback) | 1 | 267 passed; native fault in `test_vertical_slice.py` client-fixture teardown `drop_all`. |

Interpretation:
- The corrected arm had fewer diagnostics (2/5 vs 4/5). With n=5 per arm this difference is not statistically meaningful and is not evidence of a causal fix.
- The un-harnessed full-suite run shows the same signature (fatal exception during `Base.metadata.drop_all` teardown) in a different module, so teardown `drop_all` remains a suspect. The `drop_all` teardown pattern is the common factor.
- **Conclusion: no verified causal repair. Windows SQLite native stability is BLOCKED.** The per-request DDL removal is retained because it is independently justified (production schema is owned by Alembic) and covered by a regression test, but it is not claimed as the native-fault fix.

## 4. PostgreSQL integration results

- Container: `gridsense-test-pg16-prompt23e` (PostgreSQL 16, `127.0.0.1:55432`, database `gridsense_test`), left running. Credentials come from the container environment and are not written to the repo.
- Result: `19 passed` (run after all edits). Earlier run with the same 12 tests: `12 passed`.
- Coverage: register/login, duplicate and wrong-password rejection, meter ownership isolation, unauthenticated rejection, NEM12 upload import with owner-only usage, owner-scoped confirmed tariff revisions, billing reconciliation (48 × 0.5 kWh at 30 c plus 100 c supply, AEDT), exclusion of quality-V and unknown-direction intervals (partial status, no full bill), no estimate without a confirmed tariff, and 403 for non-owner billing/recommendations.
- Not yet covered (gaps, not claimed as equivalent to SQLite): scheduling preview on PostgreSQL; tariff POST 422 without `confirmed=true`; recommendations evidence content; MILP/greedy/preferred scheduling; NEM12 unverified-clock exclusion (the PostgreSQL round trip returns timezone-aware timestamps, so the naive branch is not exercised).
- Not yet done: repeated runs on Windows and Linux (only one Windows pass each for the current file set), PostgreSQL migration upgrade/downgrade/re-upgrade, Redis/RQ checks.

## 5. Environment changes

- `psycopg2-binary==2.9.12` was installed into the global Python 3.11 during Prompt 23E's first turn. It must be recorded as an environment change. No further global installs were made.
- The developer database `backend/gridsense.db` SHA256 `4B027DA4…B73BD2B0` is unchanged.
- Temporary harness outputs under `%TEMP%\gs_23e*` were removed.

## 6. Open issues (exact)

1. Windows SQLite native access violation: BLOCKED. Reproduces in baseline (4/5) and corrected (2/5) arms, and in an un-harnessed full-suite run during `drop_all` teardown.
2. `alembic/versions/0001_initial_schema.py` still calls `create_all`. Recorded risk; not changed in this phase.
3. Scheduling 403 vs 404 for another user's tariff (existence disclosure): open product decision.
4. Sample NEM12 yields `total_kwh == 0` by design (unknown direction and unverified clock are excluded). Whether it should produce billable usage is a product decision; tests were not changed to force it.
5. CI: Trivy `@master` unpinned; actions use major tags, not SHAs; `safety check` remains non-gating; hosted run NOT VERIFIED.
6. npm full audit: 14 moderate advisories, development-only; not yet mitigated or documented per advisory.
7. Not done in this phase: Linux PostgreSQL and SQLite repeated runs; Redis/RQ checks; PostgreSQL migration up/down/up; clean-copy source verification; manifest reconciliation (61 vs 56 untracked discrepancy); updates to `ENGINEERING_DEFECT_REGISTER.md`, `BASELINE_VERIFICATION.md`, `DEVELOPMENT_STATUS.md` and `STAGE1_SOURCE_CHECKPOINT_PLAN.md`.

## 7. Decision

- Windows SQLite stability: **BLOCKED**.
- PostgreSQL integration profile: **PARTIAL** (19/19 locally on Windows; cross-platform and repeated runs outstanding).
- Release engineering: **PARTIAL** (Ruff, mobile checks, production audit PASS; CI hardening partial; hosted CI NOT VERIFIED).
- Overall stabilisation gate: **NOT COMPLETE**. Prompt 24 should not begin until the native fault has a verified causal repair or a documented containment decision is approved.

## Final status update (Prompt 23E completion pass)

Evidence lives under `files/prompt23e/` (restricted-pg, hang-investigation). Git state: HEAD `d789f98`; nothing staged, committed, reset, or deleted.

### P1 Restricted PostgreSQL isolation: PASS
- Disposable container `gridsense-it-pg16-23e` (PostgreSQL 16.13, 127.0.0.1:55433, no host volume). Role `gs_it_23e` is NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOBYPASSRLS. Database `gridsense_test_23e`. Admin-owned guard schema `unrelated_guard_23e`.
- Denial probes confirm the role cannot create tables in foreign schemas or `public`, create roles, or become superuser.
- Superuser skip removed from `test_isolation_probe.py`. The conftest refuses superusers unless `GRIDSENSE_INTEGRATION_ALLOW_SUPERUSER=1`, which is unset for acceptance.
- Restricted-role runs: 35 passed, 0 skipped, exit 0 in each of 3 runs before the lint fix and 3 runs after it (`restricted-pg/run-*.txt`, `post-change-run-*.txt`).
- The existing developer container `gridsense-test-pg16-prompt23e` (port 55432) and its databases were not touched.

### P2 Windows full-suite hang: NOT REPRODUCED (historical evidence retained)
- Five bounded runs with `faulthandler_timeout=90`: full-1 (exit 0, collected 268, before the matrix test was added), full-2 (exit 0, collected 275), full-3 (exit 0 but native diagnostic detected), module-only-1 and module-only-2 (exit 0, 21 IDs each). None hung. Runs took 12–80 s.
- The hang in `test_synthetic_tou_demo_uses_cheaper_start_and_reports_real_tradeoff` is not reproduced and its cause remains unexplained. Hypotheses: HiGHS MILP not honouring the 5 s limit, a held checked-out SQLite connection, or `drop_all` file-lock contention. None are confirmed.

### P3 Cross-platform checks
- PostgreSQL integration, Linux (`python:3.11-slim`, Python 3.11.18, `requirements-dev.lock`): 35 collected, 35 passed, exit 0 against the restricted role.
- PostgreSQL integration, Windows: 35 passed (restricted role).
- SQLite non-integration suite, Linux container: 275 passed, exit 0.
- SQLite non-integration suite, Windows, direct pytest from a clean copy of the kept source set: 275 passed, exit 0 (`gs_clean_23e` copy, removed afterwards).
- Linux results are not evidence that Windows SQLite is fixed.

### P4 NEM12 source-time eligibility: FIXED
- Defect: an aware timestamp with a `None` or unverified source-time basis was normalised and billable. Only an explicit unsupported basis was rejected.
- Correction: `interval_bounds_utc` in `backend/app/services/interval_quality.py` returns None unless `source_time_basis` is in `NORMALIZABLE_SOURCE_TIME_BASES`, for both aware and naive timestamps.
- Regression: `test_source_time_basis_matrix_for_aware_and_naive_timestamps` (7 cases) in `backend/tests/test_interval_quality.py` covers UTC aware and naive (eligible), `None` aware and naive, unverified NEM12 aware and naive, and unverified fixed UTC+10 aware (ineligible).
- Targeted run (interval, billing, usage analyzer, NEM12 parser): 85 passed.
- Deliberate tightening: legacy rows with a `None` basis and aware timestamps may now be excluded from billing. Their basis is nullable in `app/models/reading.py`. Unknown-direction readings are not reclassified as consumption.

### P5 CI and security
- pip-audit gate (`--require-hashes`, locked `requirements-dev.lock`): **FAILS** with 85 known vulnerabilities in 15 packages. CI would be red. This is BLOCKED pending a dependency decision. Affected packages include aiohttp, certifi, chromadb, dnspython, ecdsa, filelock, httpx2, langgraph-sdk, multidict, oauthlib, opentelemetry-api, pillow, pyasn1, python-jose (PYSEC-2026-4298; direct dependency, used in `app/services/auth.py`), and urllib3. Many fixes are major-version bumps. No upgrade has been made.
- Workflow: 23 `uses:` references, all SHA-pinned. Top-level `permissions: contents: read`. Deploy jobs are gated to `develop`/`main` pushes and use environments, so pull-request runs cannot reach deploy secrets.
- npm audit: full = 14 moderate, 0 high or critical; production (`--omit=dev`) = 0. All 14 trace to the dev-only ESLint toolchain (`eslint`, `@eslint/*`, `@typescript-eslint/*`, `eslint-config-expo`, `eslint-plugin-*`, `minimatch` ReDoS). Accepted residual risk: development tooling only. Fix path is a breaking ESLint major upgrade.
- Mobile: lint, typecheck, expo-doctor 20/20, web export: all exit 0.
- Hosted GitHub Actions: NOT VERIFIED. No hosted run has been executed.

### P6 Migrations, Redis, backend lint
- Alembic on disposable DB `gridsense_migrate_23e`: upgrade head, downgrade base, upgrade head all exit 0. Head `d1e2f3a4b5c6`. DB dropped afterwards.
- Redis 7.4.8 PONG on 6381. RQ job `operator.add(2,3)` in a SimpleWorker burst returned 5.
- `ruff check app tests`: pass.

### P7 Source manifest and secret scan
- `git status` lists 829 entries: 114 modified, 715 untracked.
- Kept source set: 188 untracked and modified paths, plus tracked files, giving 316 files in a clean copy with nothing missing.
- Excluded: Graphify output (about 459 paths, including `backend/graphify-out/` and `backend/docs/demo/graphify-out/`), legacy `backend/file*` artifacts (5 entries, Windows-invalid names including U+F03A characters), SQLite and PostgreSQL data, `.env` secrets (only `backend/.env.example` is tracked), caches, virtual environments, and `node_modules`. `files/prompt23e/` is retained as evidence, not source.
- Secret-pattern scan over the kept set: no real credentials. Matches were test placeholders only (`hashed_password`, `testpassword123`, a masked DSN in `test_fixture_guards.py`).

### Windows SQLite native fault: BLOCKED
- Recurred in full-3 (`native_diagnostic_detected: True`, "Windows fatal exception: access violation" in SQLAlchemy `engine/default.py` `do_execute`, line 952), with exit code 0. The harness exit code cannot be trusted alone.
- The clean-copy direct pytest run (275 passed, exit 0) did not show the fault. It is intermittent and not reproducibly fixed.
- No containment has been verified as equivalent. A proposed containment would be fully isolated PostgreSQL integration for Windows development, with locked Linux SQLite in CI. It requires approval.

### Final gate summary
| Gate | Result |
|---|---|
| P1 Restricted PG isolation | PASS |
| P2 Hang | NOT REPRODUCED (historical evidence kept) |
| P3 Cross-platform | PASS (PG 35/35 both platforms; SQLite 275 Linux and clean-copy Windows) |
| P4 NEM12 source-time | FIXED (targeted 85 passed) |
| P5 CI / pip-audit | BLOCKED (85 vulnerabilities, 15 packages, gate red) |
| npm audit | ACCEPTED RESIDUAL RISK (14 moderate, dev-only) |
| Windows SQLite native fault | BLOCKED |
| Hosted CI | NOT VERIFIED |
| Overall | **PARTIAL / BLOCKED**. Prompt 24 must not begin. |

## Security-remediation pass (Prompt 23E-Security)

- Restricted PostgreSQL integration with the adopted lock: Windows 35 passed, Linux 35 passed (`files/prompt23e-security/`). Role `gs_it_23e`; superuser bypass not used.
- Migrations: Alembic upgrade head, downgrade base, upgrade head all exit 0 in a disposable schema, then dropped.
- Windows SQLite native harness, 4 runs: run 1, 3 and 4 clean; **run 2 reported a native access violation** (harness exit 1, pytest said 320 passed). Status remains BLOCKED.
- Hang: not reproduced in this pass. Historical evidence retained.
- Details and per-advisory decisions: [PROMPT23E_SECURITY_REMEDIATION.md](/C:/Users/Kanad/Desktop/PROJECTS/GridSense/backend/docs/stage1/PROMPT23E_SECURITY_REMEDIATION.md).

## Prompt 23E-Security final sign-off (Task A–D)

- Restricted PostgreSQL on the clean copy: 355 passed, 0 skipped (`gs_it_23e`, no superuser bypass). Without PostgreSQL: 331 passed, 24 skipped. Ruff passed.
- Windows SQLite native fault: BLOCKED. It is explicitly unsupported and excluded from release gates (see security doc Section 11).
- Hosted CI: NOT VERIFIED.
- Superseded: the 275-test SQLite counts and the 320/24 counts in this file are older runs. The current counts are above.
- Overall: **PARTIAL**. Prompt 24 must not begin.
