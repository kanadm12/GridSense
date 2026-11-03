# Prompt 23A — Engineering Defect Resolution and Stabilization Report

**Review date:** 2 November 2026\
**Repository:** `kanadm12/GridSense`\
**Branch / HEAD:** `main` / `d789f9814da9955db1c63ced921a95379dd08495`\
**Assessment:** **PARTIAL — critical engineering gates remain blocked.**\
**Prompt 24 readiness:** **NO — do not begin Prompt 24.**

## Executive summary

Prompt 23A's initial assessment was made against the then-current Expo SDK 54
dependency tree and before the Prompt 23B browser investigation. That
historical snapshot reported five high-severity production advisories and
unverified mobile focus behavior; those statements do not describe the
current SDK 58 dependency tree or the Prompt 23B browser result.

Prompt 23A resolved the repository-wide backend Ruff backlog and corrected a
confirmed test-database isolation defect. The backend assertions passed on
Windows and Linux, though native Windows diagnostics continued. The Prompt
23B reconciliation below records the current state: the SDK 58 production
dependency audit is zero; 14 moderate development-tool advisories remain;
the browser focus defect is fixed and verified; Windows native stability,
legacy artifact certainty, and hosted CI remain blocked.

No features, external providers, credentials, or energy algorithms were
introduced. No files were staged, committed, pushed, reset, or intentionally
deleted.

## Defect disposition

See [ENGINEERING_DEFECT_REGISTER.md](ENGINEERING_DEFECT_REGISTER.md) for
reproduction commands, root-cause confidence, corrective actions, regression
checks, evidence, and status for each issue.

| ID | Requirement | Result | Evidence |
|---|---|---|---|
| D23A-001 | Full backend Ruff | **PASS / VERIFIED** | `ruff check app tests` → `All checks passed!` |
| D23A-002 | Windows native SQLite stability | **BLOCKED** | Prompt 23B: seven full Windows runs; all reported 265 passed, but four emitted six native diagnostics. |
| D23A-003 | Disposable test databases | **PASS / VERIFIED** | Four fixed-path fixtures now use `tmp_path`; targeted suite: 23 passed, 7 warnings. A controlled legacy-URL probe created a file in its temporary working directory. |
| D23A-004 | Preservation of existing `backend/file*` artifacts | **BLOCKED / UNKNOWN** | Earlier tests ran before the fixed URLs were corrected; no pre-run content hashes or backup are available. Artifacts remain in place. |
| D23A-005 | React Native Web modal focus | **VERIFIED** | Prompt 23B browser test verified focus entry, Tab navigation, Escape, close control, trigger-focus restoration, and no `aria-hidden` warning. |
| D23A-006 | Mobile dependency audit | **OPEN — development tooling only** | SDK 58 same-lock audit evidence: 0 production advisories; 14 moderate development advisories remain. |
| D23A-007 | Hosted CI and clean source checkpoint | **BLOCKED** | Hosted GitHub Actions was not run; the full source-only checkpoint has not been reproduced from a clean Git checkout. |

## Backend

### Ruff

The previous baseline recorded 174 findings. Mechanical Ruff fixes were
followed by manual review of changes with possible runtime implications.
Current full gate:

```text
ruff check app tests
All checks passed!
```

### Backend tests and native stability

| Environment | Command | Result | Classification |
|---|---|---|---|
| Windows x64, CPython 3.11.9, SQLite 3.45.1, SQLAlchemy 2.0.52 | `python -m pytest -q --capture=fd` | **265 passed, 12 warnings, 71.92 s, exit 0**; two native access-violation diagnostics, including a trace in SQLAlchemy `cursor.fetchall`. | **Assertions PASS; stability BLOCKED.** |
| Linux x86_64, Python 3.11.16 / SQLite 3.46.1 in disposable `gridsense-api:latest` container | Locked requirements installed with `pip install --require-hashes -r requirements-dev.lock`, then `pytest -q -p no:cacheprovider` | **265 passed, 13 warnings, 58.31 s, exit 0**; no native diagnostic found. | **PASS for this Linux environment only.** |
| Windows focused database/API modules | `pytest tests/test_auth.py tests/test_insights_endpoints.py tests/test_ml.py tests/test_password_reset.py -q` | **23 passed, 7 warnings, 27.19 s.** | **PASS for fixture isolation regression.** |

The latest Windows diagnostic demonstrates that the remaining native failure
is not explained by the fixed-path URL defect alone. Capture/timing and
connection-lifecycle interactions remain hypotheses, not established causes.
Do not treat an exit code of zero or a passing test summary as proof of
Windows stability.

### Test database isolation and preservation

The four test modules listed above now use unique file-backed databases under
pytest `tmp_path`, dispose their engines, and restore FastAPI dependency
overrides and limiter state where applicable. A safe reproduction of the
previous SQLite URL in a fresh temporary directory created a disk file named
`file`, confirming that the previous URL did not behave as intended on this
Windows path.

The five pre-existing backend-root `file*` artifacts were preserved and
excluded from staging. Since their hashes were not recorded before at least
one earlier test execution with the old URL form, their exact prior content
cannot be certified. No speculative restore, deletion, or rewrite was
attempted. This is a data-integrity uncertainty and is a blocker, not a
claim that the artifacts were definitely altered.

## Mobile dependency and quality gates

At the historical Prompt 23A audit snapshot, the locked dependency tree was Expo 54.0.38, Expo Router 6.0.24, React Native
0.81.5, React 19.1.0, and TypeScript 5.9.3. A clean `npm ci` installed 1,078
packages and audited 1,079.

| Check | Result |
|---|---|
| `npm run lint` | **PASS**, exit 0 |
| `npm run typecheck` | **PASS**, exit 0 |
| `npx expo install --check` | **PASS**, dependencies up to date |
| `npm run export:web` | **PASS**, web bundle exported; 1,086 modules, 2.42 MB entry bundle |
| `npm audit` (historical SDK 54 snapshot) | **49 total**: 1 low, 43 moderate, 5 high, 0 critical |
| `npm audit --omit=dev` (historical SDK 54 snapshot) | **36 production-tree**: 1 low, 30 moderate, 5 high, 0 critical |

At that historical snapshot, the five high-severity production advisories involved `expo-router`,
`query-string`, `decode-uri-component`, `image-size`, and `postcss`.
`expo-router` and its `query-string` / `decode-uri-component` path would
require an Expo Router SDK-major update to take the offered fix.
`image-size` is reached through the Expo 54 Metro dependency graph and its
available fix crosses the current major range. The nested PostCSS path is
also reported by npm. No verified SDK-compatible resolution was established
for these advisories. A forced upgrade or blanket `npm audit fix --force`
would risk breaking Expo compatibility and was not used. These are unresolved
risks, not accepted as harmless.

The historical Prompt 23A review had not yet verified the Automation modal
in a browser. Prompt 23B subsequently reproduced two defects: Escape did not
close the dialog and closing left focus on `BODY`. The modal is now wired to
React Native Web's `onRequestClose`; web focus restoration runs from
`onDismiss`, after the focus trap is torn down. Authenticated browser tests
verified both close paths and did not reproduce an `aria-hidden` warning.

## Infrastructure, API, and CI

- Prompt 23 baseline evidence records a disposable PostgreSQL 16 migration
  upgrade-to-head, downgrade-to-base, and re-upgrade-to-head as passing.
- Prompt 23 baseline evidence records Redis/RQ health and worker checks, plus
  a migrated-database authenticated smoke journey covering registration,
  login, ownership denial, eligible-usage guards, tariff separation, and
  deterministic synthetic scheduling. These checks were not repeated in this
  Prompt 23A pass because the affected infrastructure paths were unchanged;
  they remain evidence from the named Prompt 23 environment, not production
  validation.
- The CI workflow was parsed in Prompt 23, but hosted GitHub Actions was not
  run. CI is not reported as passed.
- Docker Linux validation used a read-only mount of the current backend
  source and a disposable container. The Python lock was installed with
  hashes; external API credentials were not used.

## Source checkpoint and Git state

At the original Prompt 23A inspection (historical snapshot), `main` remained
at `d789f9814da9955db1c63ced921a95379dd08495`; the index contained zero
staged paths and the worktree reported 103 tracked modified paths and 657
untracked paths. Prompt 23B's refreshed inventory supersedes those counts:
106 tracked modified paths, 659 untracked paths, and 159 reviewed
tracked-plus-untracked source/documentation candidates, with zero staged.
The exact current candidate list is in
[STAGE1_SOURCE_CHECKPOINT_PLAN.md](STAGE1_SOURCE_CHECKPOINT_PLAN.md).

The source plan is updated in
[STAGE1_SOURCE_CHECKPOINT_PLAN.md](STAGE1_SOURCE_CHECKPOINT_PLAN.md). Exclude
credentials, ignored local configuration, databases and the five existing
`backend/file*` artifacts, Graphify output, caches, `node_modules`, Expo build
output, and other generated files. The current source changes are not a clean
source-only checkpoint, and hosted CI is still outstanding. Do not stage,
commit, or push without approval.

## Acceptance matrix

| Gate | Classification | Evidence / remaining condition |
|---|---|---|
| Backend Ruff | **PASS** | Full `ruff check app tests` exits 0. |
| Backend assertions on Windows | **PASS** | Full run reports 265 passing tests. |
| Windows stability | **BLOCKED** | Native access-violation output appears despite pytest exit 0. |
| Backend assertions on Linux | **PASS** | Locked disposable Docker run reports 265 passing tests without native diagnostic. |
| Disposable DB fixture regression | **PASS** | 23 focused tests pass; old URL behavior reproduced safely under temp storage. |
| Mobile lint / TypeScript / Expo compatibility / web export | **PASS** | Clean install and all named commands exit 0. |
| Mobile browser focus and `aria-hidden` check | **PASS — tested flow** | Prompt 23B browser test verified focus entry, Escape, close-control dismissal, focus restoration, and no warning/page error. |
| SDK 58 production npm audit | **PASS — prior same-lock audit** | Zero production-tree advisories recorded; audit was not freshly repeated in Prompt 23B. |
| SDK 58 development npm audit | **PARTIAL** | Fourteen moderate development-tool advisories remain in the prior same-lock audit. |
| PostgreSQL / Redis / authenticated smoke | **PASS (prior baseline evidence)** | Prompt 23 disposable-infrastructure evidence; not a new hosted deployment check. |
| Hosted CI | **BLOCKED / NOT RUN** | Must run after approval of a source checkpoint. |
| Source-only checkpoint completeness | **PARTIAL** | Dirty tree and existing generated artifacts remain; exact staging requires review and approval. |
| Production readiness / household energy claims | **NOT ESTABLISHED** | No claim of production readiness, meter accuracy, customer savings, or device execution is made. |

## Decision

Prompt 23A remains **PARTIAL / BLOCKED** after the Prompt 23B follow-up. Do
**not** begin Prompt 24. The Windows native fault, artifact-preservation
uncertainty, remaining development-tool advisories, hosted CI, and clean
source-checkpoint reproduction are still open. Browser focus is now verified
for the tested flow, and the SDK 58 production audit supersedes the
historical SDK 54 advisory counts below.

## Follow-up — Expo SDK 58 modernization

To address the user's requirement to avoid outdated libraries and unnecessary
vulnerabilities, the mobile app was moved from Expo SDK 54 to the SDK 58
package family without `npm audit fix --force`:

| Component / check | Current result |
|---|---|
| Expo / Expo Router | 58.0.22 / 58.0.29 |
| React Native / React | 0.88.1 / 19.3.0 |
| TypeScript / ESLint / Node | 6.0.3 / 9.39.1 / 22.20.0 |
| `npm run typecheck` | **PASS**, exit 0 after correcting SDK 58 ref, list-token, color, timer and web-file typings. |
| `npm run lint` | **PASS**, exit 0. |
| `npx expo install --check` | **PASS**, dependencies up to date. |
| `npx expo-doctor` | **PASS**, 20/20 checks. |
| `npx expo config --type public --json` | **PASS**, public app config parsed. |
| `npm run export:web` | **PASS**, SDK 58 web bundle exported. |
| `npm audit` | **14 moderate**, 0 high, 0 critical; all remaining findings are in development tooling. |
| `npm audit --omit=dev` | **0 advisories** in the production dependency tree. |

Compatible `glob` 14.0.3 and `@expo/fingerprint`'s `minimatch` 11.0.3
overrides clear the prior high findings and production-tree advisories.
`npm audit fix` without `--force` reports no further compatible fixes. The
remaining minimatch findings are in ESLint and TypeScript ESLint dependencies.
Their current consumers include plugins that call the older CommonJS API as a
function; the installed minimatch 11 entry point exports an object, so a broad
major override is not safe without replacing or upgrading those parents.
This is a nonzero development-tool audit, not a clean full-tree audit.

Prompt 23B started an isolated API against a disposable migrated SQLite
database, created a disposable test account, and authenticated through the
Expo web login flow. In Automation, focus entered the Device Name field,
Tab moved focus to a control within the dialog, Escape closed it and returned
focus to the trigger, and the close control did the same. No `aria-hidden`
warning or page error was observed. Expo Notifications still emits expected
warnings that web push-token/listener handling is unsupported.

The current SDK 58 audit remains **14 moderate development-only advisories**
and **zero production-tree advisories**. No forced or incompatible dependency
override was applied. Prompt 23B adds three repeated clean full locked Linux
runs and seven Windows full runs, four of which still emitted native
diagnostics. The SDK migration and browser fix do not change the overall
decision: **PARTIAL / BLOCKED**. Prompt 24 should not begin until the Windows
fault is resolved or independently contained, artifact preservation is
addressed, and hosted CI passes on an approved source checkpoint.
