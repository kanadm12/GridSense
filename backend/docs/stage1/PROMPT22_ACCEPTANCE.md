# Prompt 22 Acceptance — Stage 1 Integration

**Assessment: PARTIAL**\
**Test stability: BLOCKED on Windows**\
**Date:** 2026-11-01

## Scope and baseline

Prompt 22 integrated the existing Stage 1 services into an authenticated,
advisory-only journey. It did not add another optimizer, external provider,
credentials, or a customer tariff. The measured scheduling pathway remains
unavailable without server-verified appliance submeter/disaggregation evidence.

- Repository: `kanadm12/GridSense`
- Baseline revision: `d789f9814da9955db1c63ced921a95379dd08495`
- At the start of Prompt 22 the worktree already contained extensive unstaged
  and untracked Prompt 17-21 changes. No files were staged, committed, pushed,
  reset, or discarded.
- Prompt 17's full acceptance report is absent; the available Prompt 17
  document is a migration-compatibility report. Prompt 18-21 acceptance and
  stability reports were available and reviewed.

## Implemented integration

1. **Account state isolation**
   - Meter, usage, and recommendation client state is cleared on account
     transitions.
   - Request epochs prevent responses started for an earlier account from
     repopulating user-scoped stores after logout or account change.
   - Approximate weather-location storage is keyed by user. The legacy
     device-wide key is neither read nor deleted.
2. **Advisory scheduling**
   - The existing scheduling form exposes the synthetic non-task baseline,
     supported household/grid demand limits, and the explicitly unit-labelled
     AUD-per-interval preference penalty.
   - It continues to use the existing optimizer. It does not claim that a
     schedule was accepted, installed, or physically executed.
3. **Tariff remediation**
   - Bill comparison links to tariff review when a tariff is absent, outside
     its effective period, or incomplete for the period.
4. **Actionable API validation**
   - The mobile API error helper now reads the backend's standard
     `{error, details}` response and validation detail arrays. A rejected
     registration now identifies the invalid field and reason rather than
     exposing only Axios's generic status message.
5. **Authenticated journey coverage**
   - The vertical-slice test now covers ownership rejection, unquantified
     recommendation results, the versioned illustrative scheduling fixture,
     and provider/market-unavailable results.

## Journey acceptance

| Journey | Result | Evidence and limits |
|---|---|---|
| Register/sign in | PASS | Disposable browser accounts completed registration and reached authenticated tabs. Invalid email was rejected with a field-specific validation message. |
| Add/select meter and upload NEM12 | PASS, conservative | The versioned sample uploaded and parsed 336 readings. Its direction is unresolved for the recorded NMI/register/suffix/stream identifiers; it was not treated as household import. |
| Explain direction, time, quality and coverage | PARTIAL | Parser warnings and the unavailable-usage action are visible. AEMO register/direction semantics remain unresolved; the sample does not establish eligible measured import. |
| Display eligible usage | PASS for unavailable state | Dashboard explicitly states usage is unavailable, reports no eligible import, and gives a next action. No unclassified reading is shown as consumption. |
| Confirm a customer tariff | NOT ACCEPTED in browser | Tariff setup and remediation are reachable. No retailer/customer terms were invented or confirmed in the browser. The backend fixture exercises a synthetic, test-owned tariff only. |
| Billing estimate | PASS for unavailability | Dashboard explains missing confirmed effective tariff, missing intervals and unsupported completeness; it does not invent a customer bill or savings figure. |
| Recommendations/evidence | PASS for unquantified state | The expanded backend journey asserts that insufficient support yields no quantified saving. Response evidence remains scoped to the response; there is no historical evidence archive. |
| Scheduling | PASS for blocked/illustrative paths | Browser preview without a user-owned applicable tariff returns a clear blocked reason. Backend test exercises the versioned synthetic scenario and existing preferred/greedy/MILP comparison contract. No measured appliance baseline is enabled. |
| Weather/market | PASS for unavailable states | Browser shows that the paid weather provider is not configured and that AEMO market data/reuse terms remain unverified. Wholesale prices are explicitly not retail tariff inputs. |
| Sign out/account isolation | PASS | Sign-out returned to login. A second disposable account had an empty meter list. After uploading the same test fixture to that account, weather coordinates were blank rather than inherited from the first account. Backend ownership assertions reject cross-user meter/recommendation access. |

## Validation results

| Check | Result |
|---|---|
| Focused backend (`test_vertical_slice.py`, `test_scheduling_contract.py`) | **23 passed, 7 warnings** |
| Windows full backend suite, disposable copy | **262 passed, 12 warnings, exit code 0; native access violation diagnostic observed** |
| Linux Docker full backend suite, separate disposable copy | **262 passed, 14 warnings; no native access violation observed in this run** |
| Focused Ruff | **PASS** |
| Mobile TypeScript (`npx tsc --noEmit`) | **PASS**, including the final API-error helper change |
| Expo web export | **PASS**, 1,075 modules bundled; 2.38 MB web entry bundle |
| Browser acceptance | **PASS for exercised paths**, test-only accounts and data |
| ESLint | **BLOCKED**: ESLint is not installed/configured in the workspace; invoking a fetched ESLint 10 found no `eslint.config.*`. No dependency or lint-config changes were made. |
| `git diff --check` | **PASS**; existing LF/CRLF normalization warnings were reported |
| PostgreSQL migration verification | **NOT APPLICABLE to Prompt 22**: no Prompt 22 migration was added |

The browser emitted a React Native Web `aria-hidden` focus-transition warning.
The web build also warned that push-token listeners are unsupported on web.
Neither warning was suppressed. A no-eligible-usage request returned 404 and
the dashboard presented the intended explanatory unavailable state.

## Stability blocker

The full Windows suite exited successfully but printed a Windows-native SQLite
access violation. The captured stack passed through SQLAlchemy
`do_execute`/`_exec_single_context`/`exec_driver_sql` and SQLite schema
reflection (`_get_table_pragma`/`has_table`), during test teardown/introspection.
The Linux Docker run did not reproduce it. Different Python, SQLite, and pytest
versions prevent treating the Linux result as a Windows resolution. The fault
is unsuppressed and unresolved; a passing pytest summary is not a stability
pass.

Runtime comparison recorded by the runs:

| Runtime | Python | SQLite | SQLAlchemy | pytest | pytest-asyncio | greenlet |
|---|---:|---:|---:|---:|---:|---:|
| Windows | 3.11.9 | 3.45.1 | 2.0.52 | 9.1.1 | 1.4.0 | 3.5.5 |
| Linux Docker | 3.11.16 | 3.46.1 | 2.0.52 | 9.2.0 | 1.4.1 | 3.5.5 |

## Staging and checkpoint proposal

No staging was performed. Because the worktree already contains overlapping,
unstaged Prompt 17-21 edits, these paths are only candidates for a later,
hunk-reviewed Prompt 22 checkpoint:

- `BASELINE_VERIFICATION.md`
- `DEVELOPMENT_STATUS.md`
- `backend/docs/stage1/PROMPT22_ACCEPTANCE.md`
- `backend/docs/stage1/STAGE1_END_TO_END_TEST_REPORT.md`
- `backend/docs/stage1/STAGE1_RELEASE_READINESS.md`
- `backend/docs/stage1/STAGE1_TEST_MATRIX.md`
- `backend/tests/test_vertical_slice.py`
- `mobile/app/scheduling.tsx`
- `mobile/components/BillComparison.tsx`
- `mobile/components/WeatherGridContext.tsx`
- `mobile/services/api.ts`
- `mobile/stores/index.ts`

Before any staging, review individual hunks in the pre-existing modified files.
Do not stage `.env` or credentials, SQLite/database artifacts, virtual
environments, caches, `graphify-out/` directories, `backend/app/data/`, or
machine-specific configuration. The untracked Prompt 17-21 migration and
feature files are outside a Prompt 22-only staging set.

No commit or push was made. Prompt 22 is **PARTIAL**; Windows stability remains
**BLOCKED**. See
[`STAGE1_END_TO_END_TEST_REPORT.md`](STAGE1_END_TO_END_TEST_REPORT.md) and
[`STAGE1_RELEASE_READINESS.md`](STAGE1_RELEASE_READINESS.md).
