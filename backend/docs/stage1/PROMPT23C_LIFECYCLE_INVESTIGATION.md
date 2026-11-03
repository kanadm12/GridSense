# Prompt 23C — SQLite Lifecycle Investigation

- **Review date:** 2 November 2026
- **Repository:** `kanadm12/GridSense`
- **Branch / HEAD:** `main` / `d789f9814da9955db1c63ced921a95379dd08495`

**Windows SQLite result:** **BLOCKED** — a test-fixture connection-ownership defect was isolated and corrected, but its causal relationship to the historical native access violation is unproven.

## Executive disposition

The investigation produced new, controlled lifecycle evidence and one narrow
test-only correction. It did **not** establish the root cause of the Windows
SQLite access violation and does not satisfy the five-process Windows
acceptance gate.

The 25-test anomaly-plus-scheduling selection had the exact same collected
node list in every controlled arm:

`5a56558f0f5698d8b55feadd46400862c6c97ecac14ed1e37a273cc889a7072f`

Changing the anomaly test's module-global in-memory engine to a
fixture-scoped, disposed engine did not distinguish the native-fault
hypothesis: all three baseline and all three treatment runs passed, and none
emitted a native diagnostic.

The scheduling fixture exposed a separate, concrete ownership hazard. Its
authentication override returned an expired `User` ORM instance still
attached to the setup `Session`. A request on an AnyIO worker thread caused
that session's checked-out SQLite connection to execute SQL on the worker
thread. Refreshing and detaching the fixture user before TestClient entry
removed every measured checkout-thread mismatch in three repeated runs. The
correction is now in the original worktree and has a fixture assertion that
the user is detached. This verifies the test-lifecycle correction; it does not
prove that this hazard caused the historical C-level access violation.

**Prompt 24 must not begin.** D23A-002 (native fault), D23A-004 (historical
artifact-state uncertainty), D23A-006 (development-only npm advisories), and
D23A-007 (hosted CI and clean source checkpoint) remain unresolved blockers.

## Baseline and execution environment

- Windows 10 x64, build `10.0.26200`.
- CPython `3.11.9`, MSC v.1938; SQLite runtime `3.45.1`,
  `sqlite3.threadsafety == 3`.
- SQLAlchemy `2.0.52`; pytest `9.1.1`; pytest-asyncio `1.4.0`;
  greenlet `3.5.5`; Ruff `0.16.3`.
- The prior Prompt 23B baseline remains seven complete Windows test processes:
  four emitted six native access-violation diagnostics; all seven reported
  265 passed and exit code 0. Three locked Linux full-suite processes were
  clean. Capture-mode experiments were not repeated.
- Controlled focused runs used the locked working virtual environment and
  the same 25-node collection. Each run was a fresh harness child process.
- All experiment copies and SQLite databases were placed under disposable
  session-state directories. The application `DATABASE_URL` was explicitly
  set to a disposable SQLite file. The sanitized copies excluded `.env`;
  worktree-run settings explicitly used disposable DB, local/simulator
  providers, and blank external-service credentials. No developer database
  or `backend/file*` artifact was accessed or changed; no `.env` file was
  modified, and no secret values were printed or persisted.

## Test-only lifecycle instrumentation

`backend/scripts/pytest_lifecycle_instrumentation.py` is an opt-in pytest
plugin. It is not imported by the application during normal runtime. It
records structured JSONL events for:

- Engine creation/disposal and the creating source location.
- Pool connect, checkout, check-in, close, invalidation, checked-out state,
  and checkout-thread identity.
- SQLAlchemy connection begin/commit/rollback/close and cursor-operation
  start/end/error. SQL text and parameter values are not recorded; only the
  statement's first keyword is retained.
- DBAPI connection identity, SQLAlchemy connection identity, and thread
  identity for connection operations.
- ORM session creation, transaction lifecycle, connection binding,
  commit/rollback, and close.
- FastAPI TestClient entry/exit and dependency-override mutation.
- Starlette `BackgroundTask` start/completion/error.
- Metadata `create_all`/`drop_all`, fixture phases, and Python GC collection
  counters.
- Optional clean-teardown assertions before metadata drop or engine dispose.

The instrumentation deliberately does not capture credentials, user records,
SQL parameters, meter data, or raw memory addresses as the sole identifier.
Its DBAPI and SQLAlchemy identities are process-local stable labels. The
operation trace covers SQLAlchemy cursor events; it is not a C-level SQLite
trace and cannot, by itself, identify arbitrary native finalizer activity.
A source scan found no explicit `weakref.finalize` or `__del__` definitions
under `backend/app` or `backend/tests`.

The native harness now records the exact `pytest_collection_finish` node list
and its SHA-256 fingerprint in addition to its prior stdout/stderr-derived
observations. The exact collected list is authoritative when textual test
output counts differ.

Example PowerShell invocation from `backend\`:

```powershell
$env:PYTHONPATH = ".\scripts"
$env:GRIDSENSE_LIFECYCLE_LOG = "$env:TEMP\gridsense-lifecycle.jsonl"
$env:GRIDSENSE_LIFECYCLE_ASSERT_CLEAN = "1"
..\.venv311\Scripts\python.exe scripts\run_native_pytest.py `
  --output-dir "$env:TEMP\gridsense-native-runs" --capture fd -- `
  -p pytest_lifecycle_instrumentation `
  tests\test_anomaly_detector.py tests\test_scheduling_contract.py
```

The output directory and JSONL path must be disposable. The plugin fails
explicitly when `GRIDSENSE_LIFECYCLE_LOG` is unset. `GRIDSENSE_LIFECYCLE_ASSERT_CLEAN=1`
is a test-only assertion mode, not a production setting.

## Controlled experiments

Within each paired experiment below, baseline and treatment used the same
Windows interpreter, SQLite runtime, dependency versions, native harness,
instrumentation revision, 25 collected nodes, and collection fingerprint.
The checkout-thread fields were added to the plugin between Experiments 1 and
2, so the two experiments should not be compared as instrumentation-identical
timing samples. Each run used a separate disposable application DB.

| Experiment | Intervention and exact test-only diff | Runs and collection | Result | Interpretation |
|---|---|---|---|---|
| 1 — module-global versus fixture-scoped engine | In a disposable source copy only, removed the module-global `engine`/`TestingSessionLocal` in `tests/test_anomaly_detector.py`; created the same in-memory engine and session factory inside the `db` fixture; closed the session, dropped metadata, and disposed the engine in fixture teardown. Exact diff retained outside the repository. | 3 baseline + 3 variant; 25 nodes and the identical fingerprint in all six. | All six exited 0; zero native diagnostics. | Does not support or rule out engine scope as the historical fault cause. A small clean sample is not Windows stability evidence. |
| 2 — expired setup user and TestClient worker thread | Baseline kept the current fixture. Variant added `db.refresh(user)` and `db.expunge(user)` after `db.commit()`. | 3 baseline + 3 variant; 25 nodes and the identical fingerprint in all six. | Baseline: 32 connection operations per run occurred on a thread different from that connection's active checkout thread. Variant: zero in all three runs. Concurrent SQL operations on one DBAPI connection remained zero in both arms. No native diagnostics occurred in either arm. | Demonstrates a concrete test-fixture ownership hazard and that the isolated intervention removes it. It does not show that the hazard caused the C-level access violation. |
| 3 — teardown leak assertion | In a separate disposable copy, moved only `db.close()` after `Base.metadata.drop_all()`. | One scheduling API test; expected negative control, not a stability run. | The test failed as intended before schema drop: `lifecycle.leak.detected` recorded one checked-out connection and one active session. No native diagnostic. The correct baseline fixture reached schema drop with zero checked-out connections and zero active sessions. | Confirms the teardown assertion detects this deliberately injected leak. It does not establish that the historical fault was a teardown-order fault. |
| 4 — background work and broader TestClient path | Ran existing upload and vertical-slice tests with the opt-in plugin and clean-teardown assertions; no background work was disabled. | 13 nodes; fingerprint `afe9972bbe6b8f8d4f2624e6954f858d0901a5e737ced8d673c87b8604463897`. | Exit 0; three background tasks started and completed, zero task errors, eight TestClient entry/exit pairs, zero observed concurrent operations, zero teardown-leak events, and no native diagnostic. | The observed tasks completed during the requests. This bounded sample does not rule out other background-task races in the full suite. |
| 5 — PostgreSQL backend isolation | Used an ephemeral PostgreSQL 16 container with no host volume. Applied all Alembic revisions to head, downgraded to base, verified zero rows in `alembic_version`, and re-upgraded to head. | Complete 12-revision migration chain; final head `d1e2f3a4b5c6`. | Upgrade, downgrade, and re-upgrade passed. | Confirms this migration round trip on PostgreSQL; it is not evidence about Windows SQLite memory safety. |

### Connection and TestClient findings

In the original 25-test lifecycle trace:

- 4,456 SQLAlchemy cursor operations were observed; no same-DBAPI operation
  overlapped another operation.
- In the scheduling fixture, 11 TestClient contexts entered and exited.
  Request sessions closed; then the managed client exited; then the fixture's
  setup session closed; then `drop_all` and engine disposal occurred.
  Scheduling fixture schema teardown observed zero checked-out connections
  and zero active tracked sessions.
- The expired `User` object was not fully refreshed after commit. Returning it
  from the `get_current_user` override let a request access it on an AnyIO
  worker while the setup session still owned the SQLite connection. This
  caused the observed operation-thread mismatch. Refreshing and expunging it
  moved those reads before TestClient entry and left the request session to
  acquire its own DBAPI connection.
- No matching concurrent DBAPI cursor operations were observed. This is
  narrower than proving every possible C-level access safe.
- In the 13-test upload/vertical slice sample, the three Starlette background
  tasks all completed before teardown.

The earlier implementation of instrumentation flushed/opened the JSONL log
for every event and substantially slowed the run. It was changed to buffered
logging with periodic and lifecycle-boundary flushes before the reported
samples. Instrumentation can still perturb scheduling; the A/B results
should be read as measured lifecycle evidence, not a timing-neutral proof.

## Implemented test-fixture correction

The original `backend/tests/test_scheduling_contract.py` now refreshes and
expunges the overridden principal after the setup transaction and asserts it
is detached:

```diff
-from sqlalchemy.orm import sessionmaker
+from sqlalchemy.orm import object_session, sessionmaker
@@
     db.commit()
+    db.refresh(user)
+    db.expunge(user)
+    assert object_session(user) is None
     db.refresh(meter)
```

Validation in the original worktree:

- `pytest tests\test_scheduling_contract.py -q`: **20 passed**, 6 warnings.
- The 25-node anomaly-plus-scheduling selection with lifecycle leak
  assertions: **25 passed**, exit 0, same collection fingerprint, zero
  native diagnostics, zero cross-thread checkout mismatches, zero concurrent
  DBAPI operations, and zero leak events.
- Full `ruff check app tests`: **passed**.

This correction is scoped to the test fixture's ownership invariant. It is
not represented as a repair for the Windows native access violation.

## Additional gates freshly checked

| Gate | Fresh evidence | Result |
|---|---|---|
| Mobile lint | `npm run lint` | **PASS** |
| Mobile TypeScript | `npm run typecheck` | **PASS** |
| Expo Doctor | `npx expo-doctor` | **PASS** |
| Expo web export | `npx expo export --platform web --output-dir <session-state>` | **PASS**; output kept outside repository |
| Full npm audit | `npm audit` | **14 moderate, 0 high, 0 critical**; findings remain in ESLint/development tooling, including minimatch globparts-amplification DoS paths |
| Production npm audit | `npm audit --omit=dev` | **0 advisories** |
| PostgreSQL migration round trip | PostgreSQL 16, disposable container, no host volume | **PASS** |
| Redis health and RQ execution | Redis 7 `PING`; RQ `SimpleWorker` ran the actual `app.tasks.execute_automation_rule_task` with a nonexistent ID against a disposable SQLite schema | **PASS**; job finished with the expected `not_found` result. This checks RQ task execution in-process, not production worker process supervision. |
| Authenticated API journey | Disposable migrated SQLite DB; synthetic account registered, logged in, authenticated `/auth/me` and `/meters` calls | **PASS**; HTTP 201 / 200 / 200 / 200, no user data or token retained in repository. |
| Browser modal retest | Integrated browser tool failed to connect over CDP within 30 seconds; no browser interaction was executed in this pass. | **NOT RE-VERIFIED**. The Prompt 23B authenticated browser flow remains the prior evidence for focus entry, Tab, Escape, close-control focus return, and absence of `aria-hidden` warnings. |
| Hosted CI | No hosted GitHub Actions run was performed. | **NOT VERIFIED** |
| Full Windows/Linux suites after this correction | Not repeated: the correction has not been shown to fix the native fault, so no stability acceptance sample is claimed. | **NOT VERIFIED in this pass** |

The development-only audit risk remains open rather than accepted as
remediated. The npm audit output identifies the remaining issue as
globparts-amplification denial of service through development tooling. The
production dependency tree is clean, but CI evaluates pull-request source, so
resource-exhaustion exposure remains relevant until CI trust boundaries and
the compatible dependency paths are reviewed.

## Source checkpoint and preservation

The fresh `git status --porcelain=v1 -z --untracked-files=all` inventory at
the recorded HEAD contained:

- 106 tracked modified paths.
- 54 untracked candidate source/documentation paths before this report.
- 601 generated Graphify paths, excluded but preserved.
- 5 legacy `backend/file*` artifacts, excluded and preserved.
- Zero staged paths; no commit, push, reset, cleanup, or staging was done.

Adding this report makes the current untracked candidate count 55. The
updated exact manifest and exclusions are recorded in
[`STAGE1_SOURCE_CHECKPOINT_PLAN.md`](../../../STAGE1_SOURCE_CHECKPOINT_PLAN.md).
The inventory is a worktree candidate manifest, not a clean-checkout
reproduction; the full source-only checkpoint has not been built from a
clean Git clone. All test databases, diagnostic summaries, event logs,
web-export output, and test-service logs were kept outside the repository.

## Remaining blockers and readiness

1. **D23A-002 — High, BLOCKED:** Historical intermittent Windows native
   access violations remain unexplained. No native diagnostic occurred in
   the bounded Prompt 23C selections, but no full-suite acceptance sample
   after a demonstrated native-fault repair exists.
2. **D23A-004 — High, BLOCKED:** Historical content of five legacy
   `backend/file*` artifacts cannot be established. Preserve them; do not
   delete, rename, inspect, or speculate about restoration.
3. **D23A-006 — Medium, OPEN:** 14 moderate development-tool advisories
   remain; production-only audit is clean. Continue compatible dependency
   review and explicitly assess CI processing of untrusted pull requests.
4. **D23A-007 — Medium, BLOCKED:** Hosted CI has not run, and the complete
   source candidate set has not been reproduced from a clean checkout.
   Existing CI security-job pinning and token-permission concerns remain.
5. **Browser retest — NOT VERIFIED in this pass:** The prior Prompt 23B flow
   passed, but the current integrated browser connection could not be
   established to repeat it.

The isolated user-session ownership defect is corrected and regression
asserted; the engine-scope, teardown-negative-control, background-task, and
PostgreSQL results are documented above. None establishes the root cause of
the native fault. **Windows stability is BLOCKED, the engineering phase is
PARTIAL, and Prompt 24 should not begin.**
