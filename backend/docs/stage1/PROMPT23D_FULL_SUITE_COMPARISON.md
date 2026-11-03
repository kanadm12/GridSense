# Prompt 23D — Full-Suite Fixture Comparison

- **Review date:** 2 November 2026
- **Repository:** `kanadm12/GridSense`
- **Branch / HEAD:** `main` / `d789f9814da9955db1c63ced921a95379dd08495`
- **Decision:** **PARTIAL / BLOCKED** — the scheduling-fixture ownership correction is retained, but Windows SQLite stability is not verified and the fixture change did not eliminate the native diagnostic.

## Executive result

The original and corrected fixtures were run in separate disposable backend
source copies with the same CPython 3.11.9 / SQLite 3.45.1 environment,
dependency lock, pytest capture mode, application settings, and exact
265-node test collection. The source copies differed only in
`tests/test_scheduling_contract.py`: the baseline removed the Prompt 23C
`object_session` import and the three-line refresh/expunge/detachment
assertion; the corrected copy retained them.

The earlier Prompt 23B report counted 270 nodes. This Prompt 23D run used the
current 265-node collection and does not claim that its node set is identical
to the historical 270-node run. The two A/B arms and the clean-copy run did
share the exact current 265-node fingerprint.

| Arm | Full-suite processes | Collection | Native-fault processes | Pytest outcomes |
|---|---:|---|---:|---|
| Original fixture | 5 | 265 nodes; fingerprint `e5213d53b7243e2d75cdd18cf22e3dbd82e55669c0e10477c4d9e343f602f1ef` in every run | 0/5 (0%) | 5/5 exited 0; 265 passed in every run |
| Corrected fixture | 5 | Same 265 nodes and fingerprint in every run | 4/5 (80%; five matching log lines) | 4/5 exited 0 with 265 passed; 1/5 exited 3 after 263 passed because the harness's active-test marker replacement raised `PermissionError` |

The corrected-arm rate is not evidence that the fixture change caused or
increased the native fault: the sample is small, the runs were performed in
arm blocks rather than randomized order, and the original arm's five runs
were all clean. It does establish that the correction does **not** prevent
the native diagnostic. The observed difference is therefore inconclusive
about causality and does not qualify as a verified repair. The prior Prompt
23B result (4 of 7 complete Windows processes with six diagnostics) remains
relevant; the new 0/5 baseline sample does not refute it.

**Windows stability remains BLOCKED.** Prompt 24 must not begin.

## Baseline protection and experiment setup

- The working tree remained on `main` at
  `d789f9814da9955db1c63ced921a95379dd08495`; the index was empty.
- Both A/B copies were created outside the repository from the current
  source. No baseline edit was made in the working tree.
- Each copy contained 154 non-cache backend source files. A byte-level
  comparison found exactly one source file difference:
  `tests/test_scheduling_contract.py`. The only semantic changes in that
  file were the `object_session` import and:

  ```python
  db.refresh(user)
  db.expunge(user)
  assert object_session(user) is None
  ```

- The baseline and corrected copies used the same `backend/requirements-dev.lock`
  SHA-256:
  `87cde03fe40ec2795935813f15bc4e5810ac29729acdf38f7d322ffd7473d78b`.
  The clean source copy's `mobile/package-lock.json` matched SHA-256
  `99a1dc8aa9907260831447f4e9c04f624397f14c398140edb99c9c6ff98c313f`.
  The full suite used the same `.venv311` interpreter for every run:
  CPython 3.11.9 (MSC v.1938, x64), SQLite 3.45.1, SQLAlchemy 2.0.52,
  `sqlite3` module 2.6.0 (`threadsafety=3`), pytest 9.1.1,
  pytest-asyncio 1.4.0, and greenlet 3.5.5. The harness summary also records
  SQLite compile options, the extension path, and the system-library lookup.
- All A/B runs used pytest `fd` capture, `-vv`, the same application
  configuration, and a distinct SQLite file under the disposable Prompt
  23D session-state output directory. External-service credentials were
  blank or removed. No repository database, `.env`, or legacy
  `backend/file*` artifact was used.
- Complete stdout, stderr, per-run JSON summary, collection node list, and
  each disposable database are retained outside the repository in the
  `prompt23d/runs/` experiment directory. The first PowerShell launch was
  interrupted by native stderr handling and is excluded; the table uses the
  five later runs per arm that completed the harness process.

### Per-process results

All run summaries report the same 265-node fingerprint stated above.

| Arm / run | Pytest exit | Assertions | Native events | Active test recorded for diagnostic |
|---|---:|---|---:|---|
| Original 1 | 0 | 265 passed, 12 warnings | 0 | — |
| Original 2 | 0 | 265 passed, 12 warnings | 0 | — |
| Original 3 | 0 | 265 passed, 12 warnings | 0 | — |
| Original 4 | 0 | 265 passed, 12 warnings | 0 | — |
| Original 5 | 0 | 265 passed, 12 warnings | 0 | — |
| Corrected 1 | 3 | 263 passed, 11 warnings; pytest internal error during the next test start | 2 matching lines; event multiplicity indeterminate | `tests/test_vertical_slice.py::test_authenticated_nem12_to_tariff_and_billing_journey` |
| Corrected 2 | 0 | 265 passed, 12 warnings | 1 | `tests/test_scheduling_contract.py::test_scheduling_prices_from_revision_not_mutable_projection` |
| Corrected 3 | 0 | 265 passed, 12 warnings | 1 | Same scheduling test |
| Corrected 4 | 0 | 265 passed, 12 warnings | 1 | Same scheduling test |
| Corrected 5 | 0 | 265 passed, 12 warnings | 0 | — |

In corrected runs 2–4, faulthandler recorded a Python stack in SQLAlchemy's
DBAPI execution/reflection path:
`DefaultDialect.do_execute` (or its version-specific counterpart),
`Connection._execute_context`, SQLite dialect `_get_table_pragma` /
`has_table`, DDL reflection, `MetaData.drop_all`, and the scheduling fixture
teardown at `test_scheduling_contract.py:116`. The native diagnostic itself
was `Windows fatal exception: access violation`. The diagnostic in corrected
run 1 pointed to `sqlalchemy.engine.cursor.Cursor.__init__`. The three
teardown stacks correlate those events with a SQLite-backed schema operation;
the Python stacks do not expose the corrupting C operation and do not prove
that SQLAlchemy or `drop_all()` caused the memory fault.

Corrected run 1's stderr contained two regex-matching diagnostic lines at the
same recorded timestamp, one embedded in the truncated/interleaved
faulthandler output. The available output does not reliably establish
whether that was one or multiple native events. The process-level rate is
unambiguous: four of five corrected processes emitted at least one match.

For runs 2–4, the harness marker identified the scheduling test at the
diagnostic time, while the final stdout-derived `last_observed_test` was the
last vertical-slice test. The event is asynchronous relative to pytest's
separate output streams; the marker and final observed node must not be
treated as identical evidence.

## Harness race found and corrected

Corrected run 1 exposed a separate harness race. When the stderr-pump thread
read `active-test.txt` after the native diagnostic while pytest was
atomically replacing that same file, Windows raised `PermissionError` from
the embedded `ActiveTestMarker.pytest_runtest_logstart` callback at
`os.replace(active-test.tmp, active-test.txt)`. That harness exception caused
pytest's exit 3 after 263 tests; it is **not** the cause of the native
access violation.

`backend/scripts/run_native_pytest.py` now writes the small active-test
marker in place instead of replacing it and falls back to the in-memory
active node if a concurrent marker read is denied. Collection-list writing
remains atomic and occurs once after collection. The updated harness was
then exercised in:

- A clean source-copy full-suite run: **265 passed**, 12 warnings, exit 0,
  same fingerprint, zero native diagnostics, and no marker internal error.
- A paired lifecycle-instrumented 23-test selection in the baseline and
  corrected source copies: both exited 0, same fingerprint
  `82c2f7a2967286d536d9d7fd6e28266d79e5432a7de5b37094468f21bda05488`,
  zero native diagnostics, and no harness marker error.

The clean full-suite run is an additional corrected-fixture run with the
updated harness, not part of the five-per-arm rate above. It is one clean
sample and does not establish stability.

## Lifecycle and authentication-override audit

The opt-in `pytest_lifecycle_instrumentation` plugin was enabled for the
same 23 tests in each A/B copy. The traces were retained outside the
repository. Summary:

| Trace measure | Original fixture | Corrected fixture |
|---|---:|---:|
| Structured lifecycle events | 6,699 | 6,669 |
| Connection operations on a thread other than the active checkout thread | 0 | 0 |
| Concurrent operations on the same DBAPI connection | 0 | 0 |
| Checked-out connections at fixture `drop_all()` / engine disposal | 0 | 0 |
| Teardown-leak events | 0 | 0 |
| Background-task starts / completions | 1 / 1 | 1 / 1 |

The focused instrumented run did not reproduce the native diagnostic. Its
timing and smaller test selection may differ from the full suite. In
particular, the three full-suite diagnostics occurred with the corrected
principal-detachment assertion in place, while the instrumented selection
showed no checked-out connection at schema teardown. No additional
connection/session ownership violation was identified from this evidence.

All test authentication overrides were searched:

- `test_scheduling_contract.py` returns the setup `User`; it is now refreshed
  and detached before the override is installed, with an explicit
  `object_session(user) is None` assertion.
- `test_upload.py` queries a fresh `User` inside the request override and
  closes that query's session before returning the fully loaded ORM object.
  The session is created and closed in the request worker; this does not
  return an attached setup-session principal across the TestClient boundary.
- `test_insights_endpoints.py` returns `SimpleNamespace(id=...)`, not an ORM
  principal.
- `test_external_data.py` returns `object()`, not an ORM principal.

No further confirmed expired/attached ORM-principal violation was found;
therefore no additional fixture change was justified.

## Clean source-copy reproduction and quality gates

A 405-file source-only copy was assembled outside the repository. It
included the working-tree source and migrations while excluding `.git`,
Graphify output, `.env` files, virtual environments, caches, `node_modules`,
SQLite databases, the five `backend/file*` artifacts, and the local research
archive that is not part of the source checkpoint. The Python and npm lock
files were byte-identical to the worktree locks. Tests and exports used
disposable paths outside the source copy where possible.

After verification, the final Prompt 23D report was copied into the source
copy and the generated `node_modules`, `.expo`, Python bytecode, pytest, and
Ruff caches were removed. The final source-only copy contained 406 files.

| Gate | Clean-copy evidence | Result |
|---|---|---|
| Backend Ruff | `python -m ruff check app tests` | **PASS** |
| Windows backend suite | Updated native harness; 265 collected, 265 passed, 12 warnings, same collection fingerprint; zero native diagnostics; exit 0 | **PASS for this run only; stability still BLOCKED** |
| SQLite migration round trip | Alembic upgrade to `d1e2f3a4b5c6`, `alembic current`, downgrade to base, and re-upgrade using a disposable SQLite database | **PASS** |
| Mobile dependency install | `npm ci`; lockfile hash matched the source lock | **PASS** |
| Mobile lint / TypeScript | `npm run lint`; `npm run typecheck` | **PASS** |
| Expo Doctor | `npx expo-doctor` | **PASS — 20/20 checks** |
| Expo web export | `npm run export:web -- --output-dir <disposable-output>` | **PASS** |
| Full npm audit | `npm audit` | **14 moderate; zero high/critical.** The reported minimatch globparts-amplification DoS has no compatible fix in the current tree. |
| Production npm audit | `npm audit --omit=dev` | **PASS — zero advisories** |

Clean-copy Node was 22.20.0 and npm was 10.9.3. The lockfile uses Expo SDK
58. The full audit finding is development-tool exposure rather than a
production dependency advisory. However, CI runs lint/build checks on
pull-request source; the remaining moderate denial-of-service risk is not
automatically irrelevant to CI.

## CI, hosted workflow, and source checkpoint

- `.github/workflows/ci.yml` has no explicit top-level or job-level
  `permissions:` declaration. The effective `GITHUB_TOKEN` permissions
  therefore depend on repository/organization settings and were not
  independently established here.
- Third-party GitHub Actions use movable major-version tags, and the
  Trivy step uses `aquasecurity/trivy-action@master`; the security-scan job
  installs pip/Safety dependencies without the backend lock and is
  non-gating (`continue-on-error` and `|| true`). These are reproducibility
  and least-privilege follow-ups, not evidence that hosted CI has failed.
- The workflow triggers on `pull_request` (not `pull_request_target`) and
  runs lint/build/test work on proposed source. Keep pull-request jobs
  secret-free, declare least-privilege token permissions per job, grant
  `security-events: write` only where SARIF upload requires it, and impose
  job/resource limits. Until compatible dependency releases resolve the
  minimatch advisory, treat its moderate DoS as potential CI resource
  consumption—not as a production-tree advisory.
- Hosted GitHub Actions was not executed: **NOT VERIFIED**.
- The source-only copy demonstrates local reproduction, but is not a
  Git-created clean clone and does not close hosted CI or review of every
  staging hunk.
- At inventory time, the index was empty; 106 tracked paths were modified.
  Of 675 untracked paths, 615 were generated Graphify output, five were the
  preserved legacy `backend/file*` artifacts, and 55 were source or
  documentation candidates. Adding this report makes 56 untracked source
  candidates (162 candidate paths including the 106 modified tracked
  paths). The exact refreshed path list and exclusions are recorded in
  `STAGE1_SOURCE_CHECKPOINT_PLAN.md`.
- The five legacy artifacts remain preserved; their historical contents
  and provenance remain unresolved separately from current functional
  verification.

No source was staged, committed, pushed, reset, cleaned, or deleted. No
developer database or credentials were accessed or changed.

## Final disposition and next evidence

1. Retain the scheduling fixture correction because it enforces a valid
   detached-principal ownership invariant.
2. Do not call it a native-fault fix. The full-suite comparison had
   diagnostics in 4/5 corrected-fixture runs and 0/5 original-fixture runs;
   the order and sample size prevent causal interpretation.
3. Keep D23A-002 **BLOCKED**. The access violation remains intermittent,
   native diagnostics remain unsuppressed, and the observed teardown stack
   does not establish the underlying C-level corruption mechanism.
4. Keep hosted CI **NOT VERIFIED** and retain the development-only npm
   advisory disposition as open.
5. As interim containment, use the repository's Linux-based backend CI
   target and retain the prior three clean locked-Linux suite runs as
   platform-scoped evidence only. Revalidate the exact source checkpoint on
   Linux when available; this does not repair or verify Windows-native
   SQLite.
6. **Prompt 23D overall: PARTIAL / BLOCKED. Prompt 24 is not ready to begin.**
