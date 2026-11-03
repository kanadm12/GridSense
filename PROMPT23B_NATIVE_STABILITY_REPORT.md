# Prompt 23B — Native Stability, Accessibility, and Checkpoint Report

**Review date:** 2 November 2026\
**Repository:** `kanadm12/GridSense`\
**Branch / HEAD:** `main` / `d789f9814da9955db1c63ced921a95379dd08495`\
**Decision:** **PARTIAL / BLOCKED — do not begin Prompt 24.**

## Executive summary

Prompt 23B did not identify a root cause or safe containment for the
intermittent Windows native SQLite access violation. A child-process
diagnostic harness was added and used for seven full Windows runs. All seven
pytest processes exited 0 and reported 265 passing tests, but four emitted a
total of six native access-violation diagnostics. The diagnostic occurred
with file-descriptor capture, Python-stream capture, and no capture. A second
isolated Python/SQLite runtime pair also faulted, but both runtime versions
changed together, so that comparison did not identify whether Python or
SQLite was responsible.

Three full locked Linux runs used the same 270-node test collection and
reported 265 passing tests without native diagnostics. They support Linux
test execution only; they do not establish Windows stability. Passing pytest
assertions and a zero exit status are not a stability result when native
diagnostics are present.

One reproducible mobile browser accessibility defect was corrected and
verified. Escape now closes the Automation add-device modal, and focus returns
to the triggering control after modal dismissal. The tested browser session
did not emit an `aria-hidden` warning or page error.

Expo SDK 58's previously audited locked dependency tree has zero production
advisories and 14 moderate development-tool advisories. This audit was not
re-run during the final Prompt 23B documentation pass; the counts are
reconciled from the same-lock SDK 58 audit evidence recorded in the Prompt
23A follow-up. Hosted CI was not executed, PostgreSQL/Redis were not freshly
revalidated in this pass, and a complete source-only clean-checkout build has
not been demonstrated. These gates remain open.

No energy features, NEM12 interpretations, external credentials, or
appliance-dispatch behavior were added. No files were staged, committed,
pushed, reset, or deleted.

## 1. Preserved repository state

| Item | Recorded state |
|---|---|
| Branch | `main` |
| HEAD | `d789f9814da9955db1c63ced921a95379dd08495` |
| Staged paths | 0 |
| Tracked modified paths | 106 |
| Untracked paths after this report | 659 |
| Untracked source/documentation candidates | 53 |
| Generated Graphify paths | 601, preserved and excluded from source checkpoint |
| Pre-existing `backend/file*` artifacts | 5, preserved in place; historical content cannot be attested |

Counts are an inventory snapshot, not an instruction to stage files. The
exact proposed source candidate paths and exclusion categories are listed in
[STAGE1_SOURCE_CHECKPOINT_PLAN.md](STAGE1_SOURCE_CHECKPOINT_PLAN.md). Ignored
developer databases, `.env` files, virtual environments, caches, model
artifacts, generated Expo output, and test outputs were left in place.

The complete source-only checkpoint remains **PARTIAL**. The Linux backend
tests ran against a sanitized source copy, but the complete 159-path
tracked-plus-untracked source candidate set was not recreated and verified
from a clean Git checkout. The five legacy backend-root artifacts have no
trusted pre-run hash/backup in the evidence available for this work; no
attempt was made to inspect or restore them.

A bounded credential-pattern scan covered exactly the 159 source paths in
the candidate manifest. It reported zero matches and printed no credential
values. This check is not a guarantee against every possible secret format;
ignored `.env` files and developer data were excluded from the scan and
preserved in place.

## 2. Diagnostic harness

The reusable harness is
[run_native_pytest.py](backend/scripts/run_native_pytest.py). It invokes
pytest in a fresh child process, preserves complete stdout and stderr, enables
Python fault handling, records runtime/dependency metadata and the collected
test-node fingerprint, and writes a JSON run summary and output files in an
explicit caller-selected disposable directory. Its pytest lifecycle marker
records the test node active when output containing a native diagnostic is
observed. It detects `Windows fatal exception`, `access violation`, and
abnormal child-process exit; a clean pytest summary does not override those
signals.

An active node ID is temporal correlation only. It identifies the test
running when the diagnostic appeared; it does not prove that the test's
assertion, SQLAlchemy frame, or SQLite call corrupted native memory. The
harness is diagnostic infrastructure, not a crash-dump debugger, and it did
not establish a DBAPI operation as the cause.

Representative invocation from `backend/`:

```powershell
..\.venv311\Scripts\python.exe scripts\run_native_pytest.py `
  --output-dir <disposable-output-dir> --capture fd
```

`<disposable-output-dir>` must resolve to a new disposable directory outside
developer data. The harness and its output directory are not a replacement
for preserving native stderr or investigating a generated dump with an
authorized debugger.

## 3. Controlled Windows/Linux evidence

### Full-suite acceptance sample

| Environment | Repetitions | Python / SQLite | Test collection | Result | Classification |
|---|---:|---|---|---|---|
| Windows x64, existing project environment | 7 separate child processes | CPython 3.11.9 / SQLite 3.45.1 | 270 nodes; fingerprint `b8f4ed30055dcdef1093938eb4fc89e7fd70f6f9373a20906c930bf394372993` | Each: 265 passed, 12 warnings, exit 0. Four runs emitted six native diagnostics. | **BLOCKED** |
| Windows x64, isolated newer runtime pair | One diagnostic comparison | CPython 3.11.15 / SQLite 3.50.4; SQLAlchemy 2.0.52, pytest 9.1.1, greenlet 3.5.5 | Same test collection was targeted | Two native diagnostics were observed. Python and SQLite changed together. | **INCONCLUSIVE; fault persists** |
| Linux x86_64, disposable container | 3 separate locked full runs | Python 3.11.16 / SQLite 3.46.1; hash-locked backend requirements | Same 270 nodes and fingerprint | Each: 265 passed, 13 warnings; no native diagnostic found. | **PASS for these Linux runs only** |

The Linux runs used image
`sha256:70645b7cac442ac6a8053efc5d6c1474e1f465a415330f863c3a91b27909a0a3`
and a sanitized read-only source mount. The exact collection match makes the
platform comparison useful, but not sufficient to generalize beyond this
container and these repeated samples.

### Hypothesis-by-hypothesis results

| Hypothesis / variable | Experiment and observed evidence | Conclusion |
|---|---|---|
| Pytest capture mode causes or suppresses the fault | Windows diagnostic runs covered `--capture=fd`, `--capture=sys`, and `-s` / no capture. Diagnostics occurred in all three modes. | Capture mode is not a demonstrated remedy or necessary trigger. |
| Python 3.11.9 patch level is the cause | Compared the existing Python 3.11.9 / SQLite 3.45.1 pair with an isolated Python 3.11.15 / SQLite 3.50.4 pair. The newer pair also faulted. | Not isolated: Python and SQLite changed together. No Python-only conclusion. |
| Linked SQLite runtime is the cause | No safely available standalone interpreter/build enabled changing SQLite alone while holding Python and dependencies constant. | Not tested independently; unresolved. |
| Module-global engines / `StaticPool` / `check_same_thread=False` cause the fault | Source lifecycle and existing fixtures were reviewed, but no controlled engine-scope intervention was run against the same full collection. | Plausible inspection target, not demonstrated. |
| TestClient lifespan or sessions cross worker-thread ownership | Authenticated browser/API operation was exercised separately, but no instrumented A/B test correlated TestClient worker-thread ownership with the native fault. | Not demonstrated. |
| Connection/session disposal order or `drop_all()` is the cause | Diagnostics sometimes correlated with database-related tests/SQLAlchemy frames; no controlled disposal-order intervention isolated a faulty operation. | Correlation only; no causation established. |
| Background work races fixture teardown | No matched A/B test selectively disabled or synchronized background work with teardown. | Not demonstrated. |

The evidence does not justify a source-level SQLite lifecycle change. No
speculative backend source modifications were made in Prompt 23B.

### Remaining bounded investigation

1. Reproduce in a clean Windows Python 3.11 environment with the exact same
   lock and test fingerprint; retain full stdout/stderr and the generated
   machine-readable summaries.
2. Obtain an independently controlled SQLite runtime comparison while
   holding the Python patch, SQLAlchemy, pytest, greenlet, and collected test
   nodes fixed. If that cannot be provisioned safely, record it as an
   environment limitation rather than infer a cause.
3. Instrument engine creation/disposal, DBAPI connection identity, thread
   identity, transaction scope, background-task lifetime, and teardown events
   in a test-only branch. Use the resulting event timeline to choose one
   controlled lifecycle intervention at a time.
4. If permitted by the developer, configure per-process Windows Error
   Reporting dump capture or attach a supported debugger to a reproducing
   child process. Do not enable invasive system-wide diagnostics without
   approval. Preserve dump and native symbols privately; do not put sensitive
   dumps in source control.
5. After a demonstrated repair or separately approved containment, repeat
   the complete Windows suite in at least five independent processes and
   the locked Linux suite repeatedly. Any native diagnostic is a failed
   sample; five clean runs are a minimum sample, not proof of impossibility.

## 4. Browser accessibility evidence

The browser check used an isolated backend with a disposable migrated SQLite
database, a disposable test account, and a visible Expo web browser page.
The account authenticated and navigated to Automation. No developer database
or production account was used.

| Interaction | Before correction | After correction |
|---|---|---|
| Open Add Device modal | Device Name input received focus; Tab remained within the dialog. | Focus still enters the dialog and keyboard navigation remains in the modal. |
| Escape | Modal remained open. | `onRequestClose` closes the modal. |
| Close control | Modal closed but focus remained on `BODY`. | `onDismiss` restores focus to the trigger after modal dismissal. |
| Focus lifecycle | Restoration occurred on the same frame the close animation began, before focus-trap teardown. | Restoration runs after the modal's dismissal lifecycle callback. |
| Browser console | No `aria-hidden` warning reproduced before or after. | No `aria-hidden` warning or page error observed. |

The source correction is limited to
[automation.tsx](mobile/app/(tabs)/automation.tsx): wire the existing close
handler to `onRequestClose` and restore the web trigger focus from `onDismiss`.
The post-change local checks recorded in the same SDK 58 environment passed:
`npm run lint`, `npm run typecheck`, `npx expo install --check`,
`npx expo-doctor` (20/20), and `npm run export:web`. Expo Notifications emitted
expected web-support warnings unrelated to the modal. The result verifies
this browser interaction; it is not a complete cross-browser or assistive
technology audit.

## 5. SDK 58 security and reproducibility disposition

The SDK 58 lockfile audit evidence recorded in the Prompt 23A follow-up is:

| Check | Recorded result | Scope |
|---|---|---|
| `npm audit` | 14 moderate, 0 high, 0 critical | Development and production dependency tree |
| `npm audit --omit=dev` | 0 advisories | Production dependency tree |
| Compatible non-force remediation | No further compatible fix was reported | Same recorded SDK 58 lock |

This audit was not freshly run during this final reporting pass. Therefore,
the counts are a reconciled prior same-lock result, not a newly executed
Prompt 23B security scan. Remaining advisories are reported in the
development dependency graph around ESLint/TypeScript ESLint and minimatch.
An earlier compatible override covered Expo's glob/fingerprint paths; the
remaining parent packages rely on the older CommonJS minimatch call shape,
so a blanket minimatch 11 override or `npm audit fix --force` was not applied.

These are not production-tree advisories, but development-tool exposure is
not zero risk: CI processes pull-request source, so maliciously crafted
development inputs could create resource-consumption risk if they exercise
affected glob matching. Keep CI jobs time-limited, avoid running untrusted
PR code with privileged secrets, and update the affected parent packages
when a compatible release is available. The advisories remain open; they are
not described as fixed or harmless.

The repository CI workflow pins Python 3.11.16 and Node 22.20.0, while the
local browser checks used the installed SDK 58 lock and Node 22.20.0. The
backend Linux runs used the hash-locked requirements. Hosted GitHub Actions
was **not executed**. The existing security-scan workflow's pip/Safety
installations are not pinned and its job is non-gating; workflow token
permissions are not explicitly declared. These workflow observations are
open hardening items, not evidence that hosted CI passed.

## 6. Source and migration checkpoint

The source checkpoint inventory is recorded in
[STAGE1_SOURCE_CHECKPOINT_PLAN.md](STAGE1_SOURCE_CHECKPOINT_PLAN.md). The
revision inspection recorded one Alembic head,
`d1e2f3a4b5c6_add_external_weather_context`, and a complete 12-revision
history from `0001_initial_schema`. The untracked revision files are included
in the candidate manifest. The new context router is imported through
`backend/app/api/__init__.py` and included by the active app in
`backend/app/main.py`.

The plan distinguishes source candidates from generated Graphify output,
backend-root artifacts, ignored databases, `.env` files, caches, virtual
environments, model files, `node_modules`, and Expo build output. The
candidate list is a review manifest only; nothing was staged. The source-only
checkpoint is not yet verified by a clean checkout build, and the GitHub
Actions workflow has not been run.

## 7. Acceptance matrix

| Requirement | Classification | Evidence and exact unmet condition | Next action |
|---|---|---|---|
| Windows native stability | **BLOCKED** | Four of seven full-suite processes emitted six native access-violation diagnostics despite 265 passed / exit 0. | Continue only with controlled, isolated runtime/lifecycle experiments; do not label stable until the acceptance sample is clean. |
| Linux locked backend suite | **PASS — scoped** | Three separate container runs, same 270-node fingerprint, 265 passed each, no native diagnostics. | Retain as independent Linux gate; repeat after any fix. |
| Diagnostic harness | **PASS — tooling** | Child process retains stdout/stderr, runtime metadata, active test marker, collection fingerprint, and JSON result; fault cases were detected. | Use for all further Windows comparisons. |
| Browser modal focus lifecycle | **PASS — tested flow** | Authenticated browser verified focus entry, Tab, Escape, close control, trigger focus restoration; no `aria-hidden` warning or page error. | Keep automated browser coverage if a browser test suite is established; do not claim a full accessibility audit. |
| SDK 58 production audit | **PASS — prior same-lock audit** | `npm audit --omit=dev`: 0 advisories in recorded audit. | Refresh audit before release/checkpoint. |
| SDK 58 development audit | **PARTIAL** | 14 moderate findings in prior same-lock audit; current audit not rerun and advisories remain open. | Refresh audit; track compatible parent-package fixes and constrain untrusted CI execution. |
| PostgreSQL migration gates | **PARTIAL / NOT FRESHLY VERIFIED** | Prior Prompt 23 evidence recorded upgrade/downgrade/re-upgrade; not rerun in Prompt 23B. | Rerun disposable PostgreSQL upgrade, downgrade, and re-upgrade before readiness. |
| Redis/RQ health and worker gates | **PARTIAL / NOT FRESHLY VERIFIED** | Prior Prompt 23 evidence only; not rerun in this pass. | Repeat isolated Redis health and worker checks. |
| Authenticated API smoke | **PARTIAL** | Disposable SQLite browser backend authenticated a test user; full migrated-database journey/ownership/eligibility smoke was not rerun in this pass. | Rerun core API flow against a migrated disposable database and record each guard. |
| Hosted CI | **BLOCKED / NOT RUN** | No hosted GitHub Actions execution. | Run only after authorized source checkpoint; pin/harden the security scan and token permissions. |
| Clean source-only reproduction | **PARTIAL** | Linux backend suite used a sanitized source copy, not a clean checkout of all 159 candidate paths. | Reproduce backend/mobile checks from a clean source snapshot after manifest review. |
| Legacy artifact preservation certainty | **BLOCKED** | Five `backend/file*` files remain untouched, but no trustworthy pre-run hashes exist. | Obtain owner-held backup/hashes if a historical content comparison is required; do not guess or restore. |
| Production readiness, meter accuracy, customer savings | **NOT ESTABLISHED** | No production deployment or field validation was performed. | Make no production, accuracy, or savings claim. |

## 8. Prompt 24 readiness decision

**Prompt 24 should not begin.** The intermittent native Windows failure is
still critical and unresolved. No verified fix or independently approved,
independently tested Windows containment exists. The PostgreSQL/Redis gates,
current npm audit, hosted CI, complete clean-checkout reproduction, and
source-checkpoint integrity remain outstanding or only historically
evidenced. Continue engineering stabilization; do not add new energy
features, forecasting changes, NEM12 interpretations, integrations, or
appliance-dispatch behavior until these blockers are dispositioned.
