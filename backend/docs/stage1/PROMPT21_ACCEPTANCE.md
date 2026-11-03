# Prompt 21 — integrated advisory scheduling and forecast evaluation

**Review date:** 1 November 2026\
**Base revision:** `d789f9814da9955db1c63ced921a95379dd08495`\
**Overall assessment: PARTIAL**\
**Prompt 20C Windows SQLite native-fault gate: BLOCKED / unresolved**

Prompt 21 changes preserve the existing tariff revision resolver, interval
validation, MILP optimizer and deterministic greedy reference. The new
behavior does not dispatch appliances or claim realized savings. Pre-existing
Prompt 17–20C worktree edits and untracked files were preserved; no files were
staged, committed, pushed, reset, or deleted.

## Acceptance matrix

| Area | Status | Evidence / remaining limitation |
|---|---|---|
| Canonical request and constraints | **PARTIAL** | Existing v1 schema validates meter ownership at the endpoint, meter-local IANA zone, offset/grid alignment, UTC-contiguous baseline intervals, task energy or power, duration, deadlines, preferred starts, and power limits. It still accepts only one bounded request profile (up to 2,000 intervals / 20 tasks); task interruptibility and minimum continuous-run semantics are not supported. |
| Baseline double-count protection | **PASS for conservative rejection; measured pathway BLOCKED** | Synthetic non-task profiles are allowed only as illustrative scenarios. An `independently_measured` source/method supplied by a client is now classified unavailable and blocks costed planning; a declaration is not treated as verified submeter or disaggregation evidence. The repository has no server-validated submeter or synchronized disaggregation integration yet. Raw aggregate household import, net energy, and unknown direction are never promoted to non-task demand. |
| Tariff revision | **PASS for existing resolver** | Preview continues to require a user-owned confirmed tariff revision covering the complete horizon; overlap, missing dates, and a revision boundary block a costed plan. Evidence records the used immutable revision ID and effective dates. Supply and demand charges remain excluded. |
| Preferred / greedy / MILP | **PARTIAL** | The existing optimizer now reports a preferred-start schedule when all preferred starts and power constraints are feasible, alongside its same-input greedy reference and MILP candidate. Energy charges and cost-only differences are separate from AUD preference/omission penalties. A missing or infeasible preferred schedule is explicitly `not_found`. Validation currently focuses on the deterministic synthetic fixture; broader generated/property-based reconciliation is not complete. |
| No-benefit and solver interpretation | **PASS for tested fixture behavior** | A MILP tie with greedy is explicitly a zero delta; negative candidate-vs-reference or candidate-vs-preferred cost deltas are preserved. No claim is made that solver optimality proves improvement over greedy or that any modelled delta is household savings. |
| Calculation evidence | **PARTIAL** | Scheduling responses extend the Prompt 20 evidence schema with owner/meter, response time and one-hour expiry, canonical input and task digests, tariff revision/effective period, baseline classification, formulas, formula input values, scenario values, assumptions and limitations. Raw meter data are not copied. Evidence remains response-scoped; no durable archive, replay service, retention/deletion policy, or historical invalidation workflow exists. |
| Mobile advisory workflow | **PARTIAL** | The Expo screen displays selected task and preferred/candidate/greedy times, modeled costs and differences, local time, synthetic baseline warning, feasibility/blockers, an expandable “How was this calculated?” detail and advisory-only language. It does not submit a measured baseline or execute a device. Full scenario editing, task catalog, arbitrary task sets and device-level visual/accessibility testing remain incomplete. |
| Forecast chronology and evaluation | **PARTIAL** | The existing rolling-origin UCI evaluation trains only on observations dated on or before each origin and scores common 1/7/14-day horizons. Evaluation summaries now add best-baseline identity and relative MAE change. Existing saved results show mixed Prophet performance and over-wide nominal 80% test intervals. Historical forecast issue-time weather data is absent, so no weather feature is used and forecast advice stays disabled. See [PROMPT21_FORECAST_EVALUATION.md](PROMPT21_FORECAST_EVALUATION.md). |
| Deterministic tests | **PARTIAL** | Focused tests cover synthetic baseline classification, rejection of a client-declared measured baseline, same-input preferred/greedy/MILP costs, ties, infeasible preferred starts, evidence ownership/expiry/digests, and existing tariff-boundary behavior. Required separate-submeter acceptance, overlapping/partial tariff revisions, broader DST, evidence input mutation/expiry lifecycle, and forecast unavailable-weather integration remain incomplete. |
| Native test stability | **BLOCKED** | Prompt 20C's intermittent Windows SQLite access-violation remains unresolved. Prompt 21 does not suppress diagnostics or reinterpret pytest exit code 0 as stability. Results from the final Windows suite repetitions are recorded below after validation. |
| Migration / persistence | **NOT ADDED** | Evidence stays response-scoped and no database migration is introduced. PostgreSQL migration validation is therefore not applicable. |

## Evidence and response behavior

The scheduling evidence object is created only after meter ownership is
verified. The digest binds the serialized request and tariff revision
identifier; the task-set digest separately identifies the appliance task
inputs. Scenario energy charges are recorded for preferred, greedy, and MILP
when available. The response includes formulas and AUD units and expires one
hour after generation.

This is not durable historical reproducibility. A digest is not a copy of the
request, and future replay still depends on retaining the original request and
the tariff revision. No persistence was added because retention, deletion,
invalidation, and historical ownership requirements have not been agreed.

The profile's `includes_scheduled_tasks=False` request value is not proof of
disaggregation. For now, the only path eligible for numeric scheduling is the
explicitly synthetic illustrative pathway. A future measured path requires a
server-owned validated submeter/topology or defensible synchronized
disaggregation source.

## Forecast results

The checked-in evaluation artifacts describe one French household, not
Australian households or GridSense users. On the existing held-out test
artifacts, Prophet's relative MAE versus the best baseline is +7.4% at one
day, -17.3% at seven days, and -29.9% at fourteen days. At fourteen days the
best baseline is weekday mean, not persistence. Nominal 80% interval
coverage is 96.4%, 96.6%, and 96.4%, respectively. This is mixed accuracy and
over-coverage, not a basis for customer advice. The source dataset is not
bundled in this checkout, so no fresh full Prophet run was claimed.

## Stability and environment baseline

Prompt 20C recorded the Windows environment as CPython 3.11.9, SQLite 3.45.1,
SQLAlchemy 2.0.52, pytest 9.1.1, pytest-asyncio 1.4.0, and greenlet 3.5.5.
Its Linux comparison used CPython 3.11.16 and SQLite 3.46.1 with the same
SQLAlchemy, greenlet, pytest, and pytest-asyncio package versions. The Linux
suite passed once without a diagnostic; this does not explain the Windows
fault.

Prompt 21 repeated the full backend suite in three independent Windows
processes from a disposable copy of the backend, using a temporary SQLite
database to avoid writing to the pre-existing untracked test database
artifacts:

| Environment / run | Python | SQLite | SQLAlchemy | pytest | pytest-asyncio | greenlet | Tests | Native diagnostic |
|---|---|---|---|---|---|---|---|---|
| Windows 1 | 3.11.9 | 3.45.1 | 2.0.52 | 9.1.1 | 1.4.0 | 3.5.5 | 262 passed, 12 warnings | No |
| Windows 2 | 3.11.9 | 3.45.1 | 2.0.52 | 9.1.1 | 1.4.0 | 3.5.5 | 262 passed, 12 warnings | **Yes** |
| Windows 3 | 3.11.9 | 3.45.1 | 2.0.52 | 9.1.1 | 1.4.0 | 3.5.5 | 262 passed, 12 warnings | **Yes** |
| Linux Docker | 3.11.16 | 3.46.1 | 2.0.52 | 9.2.0 | 1.4.1 | 3.5.5 | 262 passed, 14 warnings | No |

The Linux packages `pytest` and `pytest-asyncio` were installed in a
disposable `--rm` container because the existing image did not include them;
no dependency manifest or persistent image was changed. The single Linux
pass does not establish a cause or containment for the Windows diagnostic.
On Windows, traces occurred in SQLAlchemy SQLite schema teardown:
`Base.metadata.drop_all()` → `has_table()` / `PRAGMA`; one trace passed through
`cursor.fetchall`, another through `exec_driver_sql`. The focused 56-test run
also passed but printed a native access violation in this teardown path.
**Test stability remains BLOCKED** despite all pytest process exit codes being
zero.

The Prompt 21 Windows focused/full-suite commands, repetition counts, native
diagnostic scan, and outcomes are also appended to
[`BASELINE_VERIFICATION.md`](../../../BASELINE_VERIFICATION.md). Any captured
`Windows fatal exception: access violation` keeps the suite stability
assessment blocked even if pytest exits successfully.

## Change inventory

Prompt 21 edits are limited to the scheduling API/schema and baseline
eligibility service, shared calculation evidence extension, existing
scheduling optimizer, scheduling and forecast evaluation tests, Expo
scheduling screen/types, and Stage 1 acceptance/specification/report
documents. No credentials, real databases, external provider configuration,
new algorithms, or migrations were added. Generated graph artifacts, local
database files, caches, virtual environments, and other pre-existing
untracked files are not part of a proposed staging set.

## Release recommendation

**PARTIAL; not release-ready as a measured household advisory.** The
illustrative schedule pathway is supported by deterministic calculations and
response evidence. Do not present a measured cost estimate until validated
non-task measurement is integrated. Do not enable forecast-dependent advice.
Prompt 20C's Windows-native SQLite stability blocker remains an independent
release gate.
