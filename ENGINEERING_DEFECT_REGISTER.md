# GridSense Engineering Defect Register — Prompt 23A/23B/23C/23D

- **Review date:** 2 November 2026
- **Repository:** `kanadm12/GridSense`
- **Branch / HEAD:** `main` / `d789f9814da9955db1c63ced921a95379dd08495`

**Overall disposition:** PARTIAL — Prompt 24 must not begin.

## Prompt 23E-Security closure entries (current round)

| ID | Status | Evidence |
|---|---|---|
| D23E-SEC-GATE | VERIFIED: release gate rejects PROPOSED, unapproved, expired, mis-scoped and placeholder entries. Unknown findings fail. | `backend/tests/test_security_gate.py` (34 passed) |
| D23E-SEC-CHROMA | PROPOSED RISK ACCEPTANCE (4 advisories, owner pending, review 2026-12-31). Gate remains red on 9 unaccepted findings. | `backend/security/risk-acceptances.json`; gate exit 1 |
| D23E-SEC-TRIVY | VERIFIED: Trivy recognises 158/158 pins from the staged, SHA256-checked lock copy. | Trivy 0.66.0 JSON and SARIF |
| D23E-SEC-GITLEAKS | VERIFIED: exit 0 on the clean copy with fingerprint-scoped `.gitleaksignore` (10 synthetic JWT fixtures). Negative controls exit 1. | `.gitleaksignore`, `.gitleaks.toml` |
| D23E-CI-ACTIONLINT | VERIFIED: actionlint 1.7.7 with ShellCheck exit 0 after four corrections. | `.github/workflows/ci.yml` |
| D23E-HOSTED-CI | NOT VERIFIED: no hosted run. | None |
| D23E-WIN-SQLITE | BLOCKED: explicitly unsupported. Not reopened. | Section 0 of this register |
| D23E-MANIFEST-678-681 | NOT VERIFIED: no trustworthy earlier snapshot. | Current manifest: 321 included / 706 excluded |

## Historical defect entries

This register records Prompt 23A defects and Prompt 23B/23C/23D evidence and
dispositions. `VERIFIED` means the corrective behavior was exercised by the
named regression check; it does not imply production readiness.

## Defects

### D23A-001 — Backend Ruff debt

- **Severity:** Medium
- **Affected files/environment:** `backend/app/**`, `backend/tests/**`;
  Windows CPython 3.11.9, Ruff 0.16.3.
- **Reproduction:** From `backend/`, run
  `..\.venv311\Scripts\python.exe -m ruff check app tests`.
- **Observed:** Prompt 23 recorded 174 findings across application and test
  files. After targeted autofixes and manual review, the same full command
  exits 0.
- **Expected:** The repository's configured backend lint gate exits 0 without
  disabling rules or adding blanket `noqa` directives.
- **Root cause:** Accumulated formatting, import-order, unused-symbol, and
  correctness-style debt. No runtime failure was attributed to these findings.
- **Corrective action:** Apply formatter/autofix-supported changes and
  explicitly review the behavior-sensitive fixes.
- **Regression test:** Full backend Ruff command; full backend pytest suite.
- **Closure evidence:** `ruff check app tests` reports `All checks passed!`;
  focused four-module regression run passed 23 tests; full Windows and Linux
  suites each reported 265 passing tests. The Windows native diagnostic is
  tracked separately as D23A-002.
- **Status:** VERIFIED.

### D23A-002 — Intermittent Windows SQLite native access violation

- **Severity:** High
- **Affected files/environment:** Backend SQLite tests and SQLAlchemy
  lifecycle; Windows x64 CPython 3.11.9 / SQLite 3.45.1 and isolated CPython
  3.11.15 / SQLite 3.50.4; SQLAlchemy 2.0.52, pytest 9.1.1, greenlet 3.5.5.
- **Reproduction:** From `backend/`, run the child-process harness, for
  example:
  `..\.venv311\Scripts\python.exe scripts\run_native_pytest.py --output-dir <disposable-output-dir> --capture fd`.
- **Observed:** Seven full Windows processes used the identical 270-node test
  collection fingerprint. All reported 265 passed and 12 warnings with exit
  code 0; four processes nevertheless emitted six unsuppressed native
  access-violation diagnostics. The diagnostics occurred under `fd`, `sys`,
  and no capture. The newer isolated Python 3.11.15 / SQLite 3.50.4 pair also
  emitted two diagnostics. The harness recorded the then-running pytest node
  ID and retained complete stdout/stderr. These IDs and SQLAlchemy frames are
  correlation evidence, not proof of the corrupting operation or cause.
  Prompt 23C added opt-in lifecycle instrumentation and ran controlled
  25-node A/B selections. The module-global-to-fixture-scoped engine arm
  produced no native diagnostic in three baseline and three treatment runs.
  A separate expired-ORM-user thread-ownership hazard was found in the
  scheduling test fixture and corrected under D23C-001. No native diagnostic
  occurred in those bounded selections, so this does not establish that the
  test-fixture hazard caused the historical native fault.
- **Expected:** Repeated complete Windows runs finish with no native
  diagnostic under supported capture settings.
- **Root cause:** Unverified. Prior evidence supports an intermittent
  native/runtime or connection-lifecycle interaction, not a confirmed cause.
  The D23A-003 fixed-path database correction and the earlier
  file-backed scheduling fixture mitigation did not eliminate it. The
  capture-mode sample is too small to establish a capture effect. Python
  version and SQLite runtime changed together in the newer interpreter run;
  a SQLite-only comparison was unavailable. Prompt 23C's engine-scope
  intervention was inconclusive. The separate expired-ORM-user ownership
  hazard was fixed, but no controlled native-fault reproduction correlated it
  with the access violation.
- **Corrective action:** Keep the D23C-001 test-fixture ownership correction;
  do not describe it as a native-fault repair. Continue only with bounded
  source-level experiments that change one lifecycle variable at a time.
  Preserve native diagnostics and do not call the fault harmless based on
  pytest exit status.
- **Regression test:** Repeat the full suite in separate processes with the
  diagnostic harness. The Prompt 23B seven-process Windows sample is a
  failure, not closure evidence.
- **Closure evidence:** None for the native fault. The Prompt 23C focused
  A/B runs and the corrected 25-test worktree run emitted no native
  diagnostic, but they are not full-suite acceptance runs. Three of seven
  earlier Windows runs were free of the diagnostic, but the other four were
  not. Three matching full locked Linux runs were clean and do not provide
  Windows containment.
- **Prompt 23D full-suite comparison:** Five baseline and five corrected
  processes used the same CPython 3.11.9 / SQLite 3.45.1 environment, lock,
  fd capture, and 265-node fingerprint
  `e5213d53b7243e2d75cdd18cf22e3dbd82e55669c0e10477c4d9e343f602f1ef`.
  Baseline: 0/5 diagnostics, all 265 tests passed. Corrected: 4/5
  diagnostics; four runs passed 265 tests, and one stopped after 263 passes
  with exit 3 due a separately identified harness active-marker race.
  Three native stacks correlated with SQLite reflection during
  `MetaData.drop_all()` in the scheduling fixture; a Python stack does not
  prove the C-level fault mechanism. The arm order was not randomized, and
  the sample does not establish that the fixture change caused or increased
  the fault rate. The fixture correction did not eliminate the fault.
  `run_native_pytest.py` was corrected to avoid the marker-replacement race;
  a separate clean-source-copy run then passed 265 tests without diagnostics.
  Full details are in
  `backend/docs/stage1/PROMPT23D_FULL_SUITE_COMPARISON.md`.
- **Status:** BLOCKED.

### D23C-001 — Expired test principal crossed SQLite thread ownership

- **Severity:** Medium (test-isolation and lifecycle correctness)
- **Affected files/environment:** `backend/tests/test_scheduling_contract.py`;
  Windows CPython 3.11.9, SQLite 3.45.1, SQLAlchemy 2.0.52, Starlette
  TestClient / AnyIO worker threads.
- **Reproduction:** From `backend/`, run
  `..\.venv311\Scripts\python.exe scripts\run_native_pytest.py
  --output-dir <disposable-output-dir> --capture fd -- -p
  pytest_lifecycle_instrumentation tests\test_anomaly_detector.py
  tests\test_scheduling_contract.py` with
  `GRIDSENSE_LIFECYCLE_ASSERT_CLEAN=1`. Before the correction, the 25-node
  trace observed 32 cursor operations per run on a thread different from the
  active DBAPI checkout thread.
- **Observed:** The fixture's `get_current_user` override returned a `User`
  ORM object after `db.commit()` had expired it. The setup `Session` remained
  open and owned a checked-out SQLite connection. The request's AnyIO worker
  lazily loaded the user through that same setup session/connection before
  opening its own request session.
- **Expected:** An ORM principal returned across the TestClient worker-thread
  boundary is fully loaded and detached from the setup session. The request
  must not cause the fixture-owned connection to execute on a different
  thread.
- **Root cause:** `expire_on_commit` left the overridden principal's
  attributes expired; accessing `current_user.id` in the worker caused a lazy
  refresh on the setup session.
- **Corrective action:** After commit, explicitly `db.refresh(user)` and
  `db.expunge(user)`. The fixture asserts
  `object_session(user) is None` before installing the dependency override.
- **Regression test:** `pytest tests\test_scheduling_contract.py -q` plus
  the instrumented 25-node selection with clean-teardown assertions.
- **Closure evidence:** Three baseline and three treatment processes used
  the exact same 25-node collection fingerprint. Baseline had 32
  checkout-thread mismatches per run; the refresh/detach variant had zero in
  all three runs. Concurrent SQL operations remained zero in both arms. The
  original-worktree run passed 25 tests with zero thread mismatches, zero
  teardown leaks, and no native diagnostic; the scheduling contract module
  passed 20 tests. This verifies the fixture ownership invariant only, not a
  causal repair for D23A-002.
- **Prompt 23D audit:** The scheduling override now returns a refreshed,
  detached principal. The upload override queries a fully loaded `User` in
  a request-local session and closes that session before returning; insights
  uses a `SimpleNamespace`, and external-data tests use `object()`. No other
  expired/attached ORM principal crossing a TestClient thread boundary was
  confirmed. The matched 23-test lifecycle traces had zero thread
  mismatches, concurrent DBAPI operations, or teardown leaks in either arm.
  Full-suite diagnostics still occurred with the detached-principal
  assertion active; D23C-001 is not a native-fault fix.
- **Status:** VERIFIED.

### D23A-003 — Test SQLite URLs wrote outside disposable test storage

- **Severity:** High
- **Affected files/environment:** `backend/tests/test_auth.py`,
  `test_insights_endpoints.py`, `test_ml.py`, and `test_password_reset.py`;
  Windows SQLite.
- **Reproduction:** In a newly created temporary working directory, using
  `create_engine("sqlite:///file:probe?mode=memory&cache=shared",
  connect_args={"check_same_thread": False, "uri": True})` and creating a
  table produced a disk file named `file` in that directory. The old tests
  used fixed URI-style database names while running from `backend/`.
- **Observed:** The old test URL did not provide the intended isolated
  in-memory database behavior on this Windows setup; fixed names could
  resolve to files in the working directory.
- **Expected:** Every test database is disposable, scoped to the test, and
  cannot collide with or modify developer data.
- **Root cause:** The SQLAlchemy SQLite URL/URI combination resolved as a
  working-directory database path rather than the intended shared-memory
  database. This was confirmed by the isolated reproduction.
- **Corrective action:** Replace the fixed URLs with per-test SQLite files
  under pytest `tmp_path`; dispose each engine; restore prior FastAPI
  dependency overrides and rate limiter state in `finally` blocks.
- **Regression test:** `pytest tests/test_auth.py
  tests/test_insights_endpoints.py tests/test_ml.py
  tests/test_password_reset.py -q`.
- **Closure evidence:** 23 tests passed, 7 warnings. Metadata for the
  pre-existing backend-root `file*` artifacts was unchanged during this
  focused run. A separate full suite after the change still reproduced
  D23A-002.
- **Status:** VERIFIED.

### D23A-004 — Uncertain preservation state of legacy test artifacts

- **Severity:** High (data-integrity uncertainty)
- **Affected files/environment:** Five pre-existing untracked
  `backend/file*` artifacts and earlier test executions using the old fixed
  SQLite URLs.
- **Reproduction:** The controlled D23A-003 reproduction demonstrates that
  the legacy URL form can create a database file in the current working
  directory. At least one earlier test execution occurred before all four
  fixtures were changed.
- **Observed:** No pre-run hashes or database snapshots were recorded for
  these artifacts. Their exact contents before that execution and any
  resulting change cannot now be established from the available evidence.
- **Expected:** Developer and demo database contents remain unchanged, and
  test writes are confined to disposable storage.
- **Root cause:** Tests used fixed database URLs that could escape their
  intended in-memory scope; the historical artifact state was not
  fingerprinted before that run.
- **Corrective action:** The source defect is fixed under D23A-003. Preserve
  the five artifacts in place; do not delete, rewrite, inspect, or attempt
  speculative restoration. If the owner has a trusted pre-run backup, compare
  that backup outside the worktree.
- **Regression test:** Focused isolated-database tests and metadata comparison
  are clean; no pre-run content comparison is available.
- **Closure evidence:** No evidence can establish whether earlier contents
  changed. The current source no longer points these fixtures at fixed paths.
- **Status:** BLOCKED.

### D23A-005 — Mobile web modal focus lifecycle

- **Severity:** Medium
- **Affected files/environment:** `mobile/app/(tabs)/automation.tsx`;
  Expo SDK 58 / React Native Web.
- **Reproduction:** Authenticate to the local Expo web app, navigate to
  Automation, open “Add a smart device”, then test Tab, Escape, the close
  control, focus restoration, and browser console output.
- **Observed:** Before the Prompt 23B fix, focus entered “Device Name” and
  Tab moved focus inside the modal, but Escape did not close it and closing
  by the close control left focus on `BODY`. Manual focus on the still-mounted
  trigger succeeded. No `aria-hidden` warning was emitted in the reproduction.
- **Expected:** No focused descendant is hidden by `aria-hidden`; keyboard
  focus enters the modal and returns to its trigger after close, with no
  React Native Web accessibility warning. Escape closes the modal where the
  platform supports it.
- **Root cause:** The modal was not wired to `onRequestClose`; React Native
  Web fires this callback on Escape. Focus restoration was scheduled on the
  same frame that began the closing animation, before the modal focus trap
  had dismissed.
- **Corrective action:** Wire `onRequestClose` to the existing close handler
  and move web focus restoration to the modal's `onDismiss` callback, after
  the animation and focus-trap teardown.
- **Regression test:** Authenticated browser interaction on the local Expo
  web app: modal opened from the trigger, input received focus, Tab moved
  focus to a modal control, Escape closed the dialog and restored trigger
  focus; a second open/close via the visible close control also restored
  focus. Browser console contained no `aria-hidden` warning or page error.
- **Closure evidence:** The above browser interaction passed after the
  correction. `npm run lint`, `npm run typecheck`, `npx expo install --check`,
  `npx expo-doctor` (20/20), and `npm run export:web` all passed afterward.
  Expo Notifications emitted expected unsupported-on-web warnings; they are
  unrelated to modal focus.
- **Status:** VERIFIED.

### D23A-006 — Mobile development-tool dependency advisories remain

- **Severity:** Medium
- **Affected files/environment:** `mobile/package.json`,
  `mobile/package-lock.json`; Expo SDK 58.0.22, Expo Router 58.0.29,
  React Native 0.88.1, React 19.3.0, TypeScript 6.0.3, Node 22.20.0.
- **Reproduction:** From `mobile/`, run `npm audit` and
  `npm audit --omit=dev`.
- **Observed:** After the SDK 58 upgrade and compatible `glob` and
  `@expo/fingerprint` `minimatch` overrides, `npm audit` reports 14 moderate,
  0 high, and 0 critical advisories. `npm audit --omit=dev` reports zero
  advisories. Remaining moderate paths are in ESLint/development tooling:
  `minimatch` versions used by ESLint, `eslint-plugin-import`,
  `eslint-plugin-react`, and TypeScript ESLint. The minimatch advisory is
  GHSA-g3hv-75wg-m249 (globparts amplification DoS). Prompt 23C freshly
  reran both audits and confirmed the same 14 moderate development-only
  advisories and zero production advisories.
- **Expected:** No production dependency advisories; remaining development
  advisories are either resolved by compatible parent releases or explicitly
  risk-assessed without breaking SDK-supported tooling.
- **Root cause:** The current Expo SDK 58 ESLint config depends on plugins
  whose released dependency ranges still select vulnerable minimatch 3.x;
  TypeScript ESLint selects 10.x. `npm audit fix` without `--force` reports
  no compatible fix. The affected ESLint plugins call minimatch as a function,
  whereas the installed minimatch 11 CommonJS entry point is an object; a
  blanket major-version override would be incompatible.
- **Corrective action:** The app was upgraded to the current SDK 58 package
  family rather than forcing npm's incompatible downgrade suggestion. Keep
  the passing production tree and SDK-compatible lint stack; upgrade the
  affected development parents when compatible releases are available. Do not
  force a major override, disable auditing, or describe the full dependency
  tree as advisory-free.
- **Regression test:** `npm ci`, `npm run lint`, `npm run typecheck`,
  `npx expo install --check`, `npx expo-doctor`, and `npm run export:web`;
  rerun both audits after dependency changes.
- **Closure evidence:** `npm run lint`, `npm run typecheck`,
  `npx expo-doctor`, and isolated-output Expo web export pass in Prompt 23C.
  Prior `npx expo install --check`, Expo Doctor (20/20), and Expo public
  config validation also passed. The production audit is zero; the full
  development-tree audit remains nonzero. The workflow runs pull-request
  source through CI, so the remaining DoS exposure is a potential CI
  resource-consumption risk; deployment secret jobs are guarded to push
  events, but workflow token permissions are not explicitly declared. Prompt
  23D repeated `npm ci`, lint, TypeScript, Expo Doctor (20/20), web export,
  and both audits in the source-only copy; the full audit remained at 14
  moderate advisories and the production-only audit remained at zero.
- **Status:** OPEN — development-only moderate advisories remain.

### D23A-007 — Hosted CI execution and final source checkpoint not verified

- **Severity:** Medium
- **Affected files/environment:** `.github/workflows/ci.yml`, the dirty
  worktree, and all untracked Prompt 17–23 source.
- **Reproduction:** Hosted Actions was not run. The current index is empty,
  and the repository remains at its pre-checkpoint HEAD.
- **Observed:** Hosted workflow behavior remains unverified. At the Prompt
  23D inventory, `HEAD` remains
  `d789f9814da9955db1c63ced921a95379dd08495`, branch `main`; 106 tracked
  paths are modified, the index is empty, and the untracked set contains 615
  Graphify outputs, five preserved `backend/file*` artifacts, and 56
  source/documentation candidates. The exact candidate list contains 162
  paths including modified tracked files. A clean source-only copy
  reproduced backend Ruff, all 265 backend tests, a SQLite Alembic
  upgrade/downgrade/re-upgrade, mobile `npm ci`, lint, TypeScript, Expo
  Doctor, web export, and both audits. This is a local copy, not a Git-created
  clean clone. The CI Python pin is 3.11.16 and Node pin is 22.20.0; primary
  backend jobs install the lock with hashes. The workflow declares no
  explicit `permissions:` block, uses movable action tags including Trivy
  `@master`, and its security-scan job uses unpinned pip/Safety installs and
  is non-gating. Effective token permissions depend on repository settings
  and were not established; hosted CI was not executed.
- **Expected:** The complete source-only checkpoint reproduces in a clean
  checkout, and the hosted CI workflow passes its pinned jobs.
- **Root cause:** No approved source checkpoint or hosted run exists yet.
- **Corrective action:** Review the refreshed exact staging manifest in
  `STAGE1_SOURCE_CHECKPOINT_PLAN.md`; obtain approval before staging or
  committing; make the security-scan job deterministic and appropriately
  gated; then run hosted workflow on the resulting source checkpoint.
- **Regression test:** Clean source-only checkout plus hosted GitHub Actions.
- **Closure evidence:** The clean source-only copy is useful local
  reproduction evidence, but neither it nor prior YAML parsing/local Linux
  checks prove hosted CI or review of every staging hunk.
- **Status:** BLOCKED.

## Phase decision

The engineering gate is **PARTIAL / BLOCKED**. D23A-002, D23A-004,
D23A-006, and D23A-007 remain open blockers. D23C-001 is verified as a
test-fixture ownership correction, not as the native-fault root cause.
D23A-005 remains supported by the prior authenticated browser interaction;
the browser interaction was not repeated for Prompt 23D. Prompt 24 should
not begin.

## Prompt 23E finalisation additions

| ID | Status | Cause / hypothesis | Reproduction | Risk | Next action | Release impact |
|---|---|---|---|---|---|---|
| NEM12-SRC-TIME | FIXED | Aware timestamp with `None` or unverified source-time basis was normalised and billable | `test_source_time_basis_matrix_for_aware_and_naive_timestamps` (7 cases) | Legacy `None`-basis rows may now be excluded from billing (deliberate) | Confirm with a data owner whether legacy rows need reprocessing | Billing eligibility change; document in release notes |
| SQLITE-NATIVE-AV | BLOCKED | Access violation in SQLAlchemy `do_execute` (`engine/default.py` line 952) on Windows; unconfirmed fixture link | Full suite, `scripts/run_native_pytest.py`; recurred in full-3 with exit 0 | Intermittent crash hides failures | Find the causal fixture; consider isolated PostgreSQL for Windows dev | Blocks a clean Windows stabilisation claim |
| FULL-SUITE-HANG | NOT REPRODUCED | Unexplained; candidates include HiGHS MILP time limit, held SQLite connection, `drop_all` lock contention | Five bounded runs with `faulthandler_timeout=90`; none hung | Unknown | Keep historical evidence; re-run with thread-stack capture if it recurs | Non-blocking if not reproduced |
| PIP-AUDIT-GATE | PARTIAL (was BLOCKED) | Baseline 85 findings in 15 packages. Now 5 findings, all chromadb (4 unique IDs, no upstream fix). Other packages remediated; see `backend/docs/stage1/PROMPT23E_SECURITY_REMEDIATION.md` | `pip-audit --requirement requirements-dev.lock --require-hashes` in `python:3.11-slim`; evidence in `files/prompt23e-security/` | Gate passes only with 4 documented `--ignore-vuln` exceptions; owner unassigned | Name exception owner; confirm review date 2026-12-31; re-run audit on each lock change | Gate green only through documented exceptions; not a fix |
| JWT-PYTHON-JOSE | VERIFIED FIX, SEMANTIC CHANGE | python-jose 3.5.0 (PYSEC-2026-4298, no upstream fix) replaced by PyJWT 2.15.1 in `auth.py` and `pyproject.toml` | `test_jwt_legacy_compat.py` (11 tests) checks PyJWT verdicts against python-jose verdicts on 8 synthetic fixtures; `backend/tests/test_jwt_security.py` (25 cases) passes | Auth library change; integer `sub` tokens now rejected by both libraries; pre-git tokens not inspectable | User sign-off; re-login policy in security doc Section 5 | Authentication behaviour relies on PyJWT |
| CHROMADB-ACCEPTED | ACCEPTED RESIDUAL RISK | chromadb 1.5.9 has 4 advisories with no fix (PYSEC-2026-311, -3813, -3814, -3815) concerning server, RBAC and remote-code paths | App uses only in-memory `Chroma.from_texts`; guard test `backend/tests/test_chromadb_exposure.py` | Owner UNASSIGNED; review 2026-12-31 | Name owner; split production lock or remove chromadb when a fix or replacement exists | Exposure exists only if a server or persistent client is added |
| WIN-SQLITE-NATIVE | BLOCKED | Windows "access violation" in SQLAlchemy `do_execute`; recurred in 1 of 4 native-harness runs this pass (`Native diagnostic: YES`, harness exit 1, pytest reported 320 passed) | `backend/scripts/run_native_pytest.py --output-dir files/prompt23e-security/windows-native-sqlite-run-N` | Intermittent; cause not identified | Continue source-level fixture inspection; evaluate PostgreSQL-based containment | Blocks a Windows SQLite claim; not fixed |
| NPM-MODERATE-DEV | ACCEPTED RESIDUAL RISK | 14 moderate advisories in dev-only ESLint chain (`minimatch` ReDoS) | `npm audit` full = 14 moderate; `--omit=dev` = 0 | Development tooling only | Plan ESLint major upgrade | No production exposure |
| HOSTED-CI | NOT VERIFIED | No hosted GitHub Actions run executed | n/a | Unknown | Run hosted pipeline after approval | Blocks release claim |

## Prompt 23E-Security final sign-off (Task A–D)

Verified in this pass (clean copy of the 314-file manifest, `python:3.11-slim`, hash-locked `requirements-dev.lock`):

- Ruff (`app tests scripts`): passed.
- Full suite without PostgreSQL: 331 passed, 24 skipped.
- Full suite with the restricted role `gs_it_23e` on `gridsense_test_23e`, no superuser bypass: 355 passed, 0 skipped.
- pip-audit, CI-equivalent with four ignores: exit 0, 5 ignored. Without ignores: 5 chromadb rows over 4 IDs.
- Secret scan over the 314-file set: 22 hits reviewed, none live. Live container secrets were not compared in this pass.

Superseded earlier figures: 316 files (STAGE1), 265 and 275 test counts, 320/24 (DATABASE_TEST_STABILITY, BASELINE). Use the figures above.

| ID | Status | Notes |
|---|---|---|
| NEM12-SRC-TIME | FIXED (unchanged) | Regression matrix still in suite; billing exclusion retained |
| JWT-PYTHON-JOSE | VERIFIED FIX, SEMANTIC CHANGE, sign-off pending | Legacy verdicts match python-jose on 8 synthetic fixtures; integer `sub` rejected; pre-git tokens not inspectable |
| CHROMADB x4 (PYSEC-2026-311, 3813, 3814, 3815) | PROPOSED RISK ACCEPTANCE | Owner "Project maintainer — assignment pending"; review 2026-12-31 proposed; not finally accepted |
| SQLITE-NATIVE-AV (Windows) | BLOCKED; excluded from release gates | Intermittent; no causal fix verified |
| FULL-SUITE-HANG | NOT REPRODUCED (historical) | Not re-run in this pass |
| PostgreSQL 16 restricted role | VERIFIED (Linux clean copy 355/0) | Supported integration gate |
| Hosted CI | NOT VERIFIED | No hosted run |
| Overall | PARTIAL | Prompt 24 must not begin |
