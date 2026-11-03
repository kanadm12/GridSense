# Stage 1 verification and acceptance test matrix

Tests below are required before the associated feature is considered accepted.
Numerical thresholds are contract-level acceptance criteria, not claims about
current behavior. Provider tests must use versioned fixtures or mocked HTTP
transports; no live external dependency belongs in deterministic tests.

| ID | Area | Test and expected behavior | Numerical/assertion criterion | Current test evidence |
|---|---|---|---|---|
| T-01 | Unit conversion | Convert Wh and kWh with explicit unit tags; preserve the raw value/unit. | 1,000 Wh = 1 kWh; unsupported units remain auditable but ineligible. | **PASS locally:** parser tests plus `test_interval_quality.py`; AUD/MWh remains future market-context conversion. |
| T-02 | Direction | Import, export, and unresolved channels remain separate; distinct directions in one slot are not duplicates. | Unknown and legacy null/B contribute 0 to validated totals; same-direction duplicate is suppressed and counted. | **PASS locally:** `test_interval_quality.py`, billing, usage, and upload tests. AEMO register/suffix interpretation remains **BLOCKED**. |
| T-03 | Quality policy | `A` accepted for headline actual observations; non-A/unknown excluded and reported. | Eligible sum includes only quality A; non-A count is explicit; records are retained. | **PASS locally:** interval eligibility and usage/billing tests; policy is conservative, not a normative interpretation of non-A codes. |
| T-04 | Partial coverage | Partial days are not presented as complete daily consumption. | For a normal 48-slot day, 24 eligible intervals => 50% coverage; status partial, observed energy labeled, full-day comparison unavailable. | **PASS locally:** `test_interval_quality.py` and coverage-aware usage tests. |
| T-05 | DST coverage | Expected-slot denominator follows local civil-day duration. | Melbourne 30-minute spring-forward = 46; ordinary = 48; fall-back = 50. | **PASS locally:** parametrized `test_interval_quality.py`. |
| T-06 | Duplicate/invalid intervals | Duplicate UTC slots do not inflate sum or coverage; invalid timestamps/units are reported. | Numerator never exceeds denominator; conflicts are excluded and separately counted. | **PASS locally:** duplicate, Wh/kWh, unsupported-unit, zero-value and unresolved-time tests. |
| T-07 | Period comparison | Compare distinct complete periods using explicit weekday or calendar alignment. | Weekday mode requires >=7 complete days in each period and identical weekday-count vectors; calendar mode requires complete full months and compares daily averages when lengths differ. No same-date requirement and no zero imputation. | **PARTIAL:** billing comparison now withholds changes unless both periods are complete measured data with matching weekday counts; daily brief requires four complete prior same-weekdays. Full calendar-month API alignment remains future work. |
| T-08 | Tariff effective dates/history | Every billed local date is covered by exactly one confirmed immutable revision. | Boundary day uses exactly one version; zero or multiple matches => unavailable/partial. Legacy tariff history is not backfilled. | **PASS locally:** revision history, confirmation, and date-boundary billing tests. |
| T-09 | Tariff unsupported components | Unsupported/missing tariff terms never fall back silently. | No tariff => no customer-specific cost; explicit scenario => illustrative; missing rate windows and unpriced dates are reported. Unsupported charges prevent a complete-bill claim. | **PASS for implemented behavior:** focused billing/vertical-slice tests. Customer invoices and all retailer charge classes remain unvalidated. |
| T-10 | GST and bill ledger | Inclusive/exclusive GST and each supported component reconcile. | Inclusive GST memo = taxable inclusive amount / 11; exclusive GST = taxable amount × 0.10; total equals included line items within AUD 0.01. Export tax handling requires verified fixture/rule. | Existing billing tests cover some GST/reconciliation. |
| T-11 | Demand charge | Peak demand formula and applicable demand interval/window are explicit. | Interval average kW = kWh × 60 / interval minutes; unsupported retailer demand window => demand charge unavailable, not guessed. | Existing code uses max interval average; contract-specific demand rules remain limited. |
| T-12 | AER provider fixtures | Parse plan list/detail, geography and changed/malformed response without activating customer tariff. | Exact endpoint version asserted; postcode/range filters match CDS; missing required schema fails explicitly. | **PASS locally:** mocked AER adapter tests; live smoke confirms list v1/detail v3 shape only. |
| T-13 | AER outage/quota | Timeout and 429 are distinct, with `Retry-After` preserved; no retry or stale-cache fallback. | Timeout => 504; 429 => 503 and optional retry header; local fan-out bounded. | **PASS locally:** mocked timeout and 429 tests. AER numeric upstream quota and reuse terms remain **BLOCKED**. |
| T-14 | Forecast leakage | Every feature timestamp is no later than its forecast issue time. | For every forecast record, `feature_available_at <= issued_at < target_start`; any violation fails the run. | Existing forecast evaluation test verifies training dates precede target; external feature timing absent. |
| T-15 | Forecast evaluation | Compare persistence/seasonal baseline and candidate chronologically. | MAE/RMSE recompute from exported rows to 1e-9; report sample counts, relative MAE against the best matched baseline, and interval coverage. A candidate failing a predeclared baseline criterion is not used as advice. | **PARTIAL:** rolling-origin UCI artifacts report matched 1/7/14-day metrics; Prompt 21 adds best-baseline identity/relative-MAE calculations and tests. Prophet test MAE is worse at 1 day, better at 7/14 days, and nominal 80% intervals cover about 96%; one household and absent issue-time weather keep product advice disabled. |
| T-16 | Scheduling price/cost | Independently recompute baseline, task, preferred, greedy reference and MILP candidate charges. | Per-scenario recomputation differs from API response by ≤ AUD 0.01 after rounding. All strategies receive identical fixed inputs. Ties report zero; negative candidate-cost deltas remain negative. | **PARTIAL:** optimizer/API now report preferred, greedy and MILP energy charges and differences from identical inputs; tests confirm the synthetic cost reconciliation and ties. No separately measured household inputs are available. |
| T-17 | No double counting | Measured baseline excludes modeled flexible tasks. | A validated separate submeter or synchronized validated disaggregation is required; aggregate household import, net grid energy, a user checkbox, and unsupported/unknown direction cannot establish non-task load. | **PASS for conservative rejection:** measured client assertions are blocked because no server-verified source is integrated. Synthetic non-task load is explicitly illustrative. No measured submeter acceptance path exists yet. |
| T-18 | Scheduler boundary | Infeasible task, unavailable appliance, missing tariff, no-benefit, optional omission. | Infeasible returns no candidate schedule; missing tariff is blocked; equal-price shift shows 0.00 energy delta; unavailable appliance generates no numeric opportunity. | Existing optimizer/contract tests cover several cases; add actionability/no-benefit scenarios. |
| T-19 | Recommendation/scheduling evidence | Every numeric impact ties to references and a formula version. | Recompute agrees within AUD 0.01; missing evidence => amount null and status unavailable/unquantified. Expired evidence cannot be called current. | **PARTIAL:** recommendation evidence retains prior contract; scheduling adds owner/meter, task/input digests, tariff revision/coverage, baseline classification, formulas, scenario values, assumptions and expiry. Both are response-scoped, not archived. |
| T-20 | Ownership and privacy | Cross-user tariff/meter/evidence access denied; provider secrets not returned/logged. | Unauthorized API returns standard 403/404 contract; test log and response fixtures contain no credential values. | Existing ownership tests exist; provider flows absent. |
| T-21 | AI boundary | Assistant explains supplied facts only. | Prompt asking for unsupported savings cannot produce a numeric claim absent a calculation object; any numeric output must match the supplied object. | **PARTIAL:** no calculation evidence is supplied to chat; usage context requires seven complete measured days, and an adversarial output guard replaces numeric financial/usage-reduction claims. |
| T-22 | Property invariants | Generate allowed interval, unit, time, coverage, tariff, and task cases. | Coverage in [0,1]; numerator ≤ denominator; costs reconcile; no unknown direction enters totals; UTC interval slots are unique; candidate schedule obeys task constraints. | Property-based tooling not identified; use existing test stack until approved. |
| T-23 | NEM12 date/index | For MDFF v2.7, the 1-based position maps to the nominal interval end relative to `IntervalDate`; the final position is midnight of the following date. | For 30 minutes: position 1 = `IntervalDate` 00:30; position 48 = next date 00:00; preserve source date and position. | **PASS locally:** `test_nem12_parser.py`; timezone/UTC realization remains **BLOCKED**. |
| T-24 | NEM12 DST record shape | Keep 48 nominal half-hour values separate from the Melbourne local-day expected-slot denominator. | For 2025-04-06, record count 48 vs local-day slots 50; for 2025-10-05, 48 vs 46; NEM12 UTC conversion returns unavailable absent verified source basis. | **PASS locally:** parser plus `interval_quality.py` tests; actual NEM12 DST mapping remains **BLOCKED**. |
| T-25 | NEM12 channels | Preserve NMI configuration, RegisterID, NMISuffix, and MDMDataStreamIdentifier; do not infer direction from any identifier. | Distinct MDM stream IDs remain separate even for identical NMI/register/suffix; parser assigns `unknown` direction to all source channels. | **PASS locally:** version-labelled parser fixture and upload integration test. Authoritative direction evidence remains **BLOCKED**. |
| T-26 | NEM12 quality events | Resolve each interval's quality/method/reason from complete ordered 400 ranges when 300 uses `V`. | Inclusive 1-based ranges cover all 48 positions with no gaps/overlaps; malformed, missing, or partial ranges leave all affected interval qualities unresolved. | **PASS locally:** v2.7 mixed-quality fixture and invalid-range tests. Method-number meanings remain **BLOCKED** on Metrology Procedure Part B. |
| T-27 | NEM12 quality/reason fields | Preserve A/E/F/S/V distinctions, method text, reason codes, and required/forbidden field relationships. | F/S method flag rules; S requires reason; F/V forbid reason; code 0 requires description; Wh 1,000 -> 1 kWh; unsupported UOM not converted. | **PARTIAL:** structural tests and unit tests pass; individual Part B method meanings, historical reason-code applicability and full source-version validation remain **BLOCKED**. |
| T-28 | Weather provider contract | Parse documented Open-Meteo fields/units, distinguish retrieval and target time, preserve preceding-hour radiation interval, and reject malformed schemas. | Fahrenheit normalizes to Celsius with original unit retained; invalid percentage/unit/time fails; no issue time is fabricated; 429 is not retried. | **PASS locally:** `test_external_data.py` uses a version-labelled Forecast API v1 fixture and mocked HTTP transport. Live paid-account response remains unverified. |
| T-29 | Provider failure/cache | Timeout, 401/403, 429, 5xx, fresh cache, stale cache, and missing configuration are distinct and never expose credentials. | At most one timeout/5xx retry; no 429 retry; stale fallback only for configured transient provider failures. | **PASS locally:** mocked provider and cache tests. Production quota/retention policy remains operator responsibility. |
| T-30 | Market-data safety | No unverified AEMO region/price/demand contract is surfaced or used as retail tariff evidence. | Blocked/unavailable response has null region and values; no AEMO request, persistence, billing, or savings path. | **PASS locally:** market summary API test asserts blocked status and null market values. |

## Required fixture families

1. Fully classified import-only, export-only, and mixed direction data.
2. Unknown direction, legacy null/B, estimated/substituted/void/unmapped quality.
3. Missing and duplicate intervals; normal and DST local days.
4. Flat and TOU tariffs with valid, missing, overlapping, stale, changed, and
   out-of-range effective periods.
5. Inclusive/exclusive GST, supply, supported/unsupported demand, export credit,
   and a bill ledger with cent reconciliation.
6. Provider weather/plan/market fixtures with attribution and timestamps,
   plus malformed/stale/timeout/429/5xx variants.
7. Scheduling measured submeter baseline excluding task load, synthetic
   baseline, and intentionally double-counted/unknown net-meter baselines.
8. Recommendation evidence object with valid, incomplete, expired, and
   non-reproducible calculations.

## Existing relevant suites to preserve

- `backend/tests/test_nem12_parser.py`
- `backend/tests/test_vertical_slice.py`
- `backend/tests/test_tariff.py`
- `backend/tests/test_billing.py`
- `backend/tests/test_usage_analyzer.py`
- `backend/tests/test_forecast_evaluation.py`
- `backend/tests/test_recommendation_engine.py`
- `backend/tests/test_scheduling_contract.py`
- `backend/tests/test_scheduling_optimizer.py`
- `backend/tests/test_scheduling_experiment.py`

## Prompt 22 end-to-end acceptance evidence

| ID | Area | Prompt 22 result |
|---|---|---|
| T-22-01 | Register/sign in and validation | **PASS locally:** disposable browser registration/login succeeded; invalid email displayed the backend field-level 422 validation message. |
| T-22-02 | NEM12 upload and direction | **PASS for conservative handling:** the sample's 336 records were parsed, but unresolved direction remained ineligible for measured import. |
| T-22-03 | Unavailable usage/billing | **PASS for clear unavailability:** UI stated no eligible usage, absent tariff/coverage and the next actions; no customer amount was fabricated. |
| T-22-04 | Recommendation evidence | **PASS for unquantified result:** authenticated vertical-slice test checks insufficient evidence and ownership boundaries. Historical evidence remains response-scoped. |
| T-22-05 | Synthetic scheduling | **PASS for tested fixture/blocker:** existing optimizer contract is reused; missing user tariff blocks the web preview. No measured baseline or dispatch is enabled. |
| T-22-06 | Optional provider states | **PASS for unavailable UX:** browser and integration test state weather credential and AEMO contract/reuse limitations explicitly. |
| T-22-07 | Account isolation | **PASS for exercised paths:** backend rejects cross-user meter/recommendation access; logout clears stores, stale requests are invalidated, weather location is per-user. |
| T-22-08 | Full-suite runtime stability | **BLOCKED:** Windows reported native SQLite access violation with pytest exit 0; Linux Docker passed 262 tests without a diagnostic in one run. |
| T-22-09 | Mobile static/build | **PASS:** TypeScript and Expo web export passed. ESLint unavailable due missing local executable/configuration; navigation focus warning remains. |

Detailed outputs and boundaries are recorded in
[`STAGE1_END_TO_END_TEST_REPORT.md`](STAGE1_END_TO_END_TEST_REPORT.md) and
[`STAGE1_RELEASE_READINESS.md`](STAGE1_RELEASE_READINESS.md).
