# Prompt 20 acceptance — evidence-backed recommendations and reproducible metrics

## Overall disposition

**PARTIAL**

The implementation removes unsupported financial placeholders and gates usage
pattern and period-comparison claims on eligible data. It adds a versioned,
compact calculation-evidence response and updates mobile presentation. Durable
evidence storage, scheduling-evidence integration, notification deduplication,
and validated forecasting remain incomplete.

No Prompt 20 database migration was needed or added. Existing Prompt 17–19
worktree changes were preserved. No commit or push was made.

## Acceptance matrix

| Area | Status | Evidence and remaining limitation |
|---|---|---|
| Common evidence contract | **PARTIAL** | Recommendation responses include schema/rule versions, meter and owner IDs, date window, hashed input-set reference, input count/provenance, coverage and eligibility checks, baseline/proposed scenario descriptions, method version, values/units, assumptions, limitations, and expiry. Raw readings are not copied. The evidence is generated per request and not persisted; there is no historical immutable archive or asynchronous invalidation workflow. |
| Recommendation eligibility | **PASS for usage-pattern rules** | Pattern rules require seven completed local dates, complete eligible coverage, classified import direction, verified time basis, and measured or explicitly synthetic provenance. Ineligible history produces an unquantified data-quality action. |
| Status and expiry | **PARTIAL** | Status is derived from evidence as validated, illustrative, unquantified, unavailable, or no-supported-action. Evidence expires after one hour; the mobile screen withholds expired cards and offers refresh. Durable expiry/replay and lifecycle storage are not implemented. |
| Consumption pattern claims | **PARTIAL** | Complete measured intervals support observed timing proportions. Aggregate meter readings are explicitly not used to identify appliances or shiftable load. Synthetic/mixed inputs are labeled illustrative. No task-specific schedule evidence is attached to these recommendation cards. |
| Period comparison | **PARTIAL** | Bill comparison changes are emitted only when each period has at least seven fully covered measured days and the weekday-count vectors match. The daily brief requires yesterday plus four complete measured observations of the same weekday. Calendar-month alignment remains unimplemented. |
| Billing comparison safety | **PARTIAL** | Observed eligible energy remains separately labeled and coverage is visible. Percentage, daily-average, and cost-change metrics are withheld when comparison inputs are ineligible; cost deltas additionally require both breakdowns to be complete bills. Synthetic/mixed meter data is illustrative and cannot support a customer-estimate claim; an explicit scenario may show labeled illustrative components, never a customer estimate. Retailer bills and every contract charge are not certified. |
| Anomaly findings | **PASS for implemented rules** | Daily-spike, overnight, and shared-window observations require complete measured days. Default peak/off-peak rate spreads are no longer rendered as extra cost, and appliance-specific causal suggestions were removed. The shared peak window is not represented as the customer's tariff. |
| Forecast-dependent advice | **PASS — withheld** | Daily-brief advice explicitly reports forecast-dependent recommendations unavailable pending chronological held-out acceptance. Existing forecast endpoints remain projections and are not evidence of forecast superiority. |
| AI assistant boundary | **PARTIAL** | Chat receives no deterministic evidence object; usage context is limited to seven complete measured days. A generated-response guard replaces common numeric financial and usage-reduction claims and numeric kWh claims not present in the eligible usage context with a limitation, tested with an adversarial savings prompt. The guard is not a general natural-language proof system and must not be treated as an authorization to produce unvalidated claims. |
| Mobile evidence experience | **PASS for recommendation screen** | Cards show evidence status, provenance, coverage, assumptions, requirements, and a “How was this calculated?” detail with method, analysis window, eligibility checks, expiry, digest, and limitations. Expired cards are withheld. |
| External-data constraint | **PASS** | No weather or AEMO credentials were requested, purchased, configured, or required. Existing Prompt 19 provider adapters, mocked tests, and stale/unavailable behavior were not expanded or used as recommendation evidence. |
| Scheduling evidence and notification lifecycle | **NOT IMPLEMENTED** | Existing preferred/greedy/MILP calculation code is unchanged and no parallel optimizer was added. The new recommendation evidence schema is not yet attached to scheduling results; unchanged-advice notification deduplication is not implemented. |
| Ownership | **PASS for recommendation endpoint path** | Meter ownership is verified before recommendation generation; evidence is derived from that owned meter. No separate evidence retrieval endpoint or evidence table exists. |

## Implemented code and UX changes

- Added `RecommendationStatus`, coverage, eligibility, and
  `CalculationEvidence` response schemas.
- Added `CalculationEvidenceService`, which hashes source reading references
  and records a one-hour response-time evidence snapshot without duplicating
  raw meter rows.
- Gated recommendation patterns on complete, classified, time-resolved
  seven-day windows; missing or partial windows now yield a data-quality
  recommendation.
- Removed time-of-use rate-spread output from recommendation cards; rate
  spreads alone do not prove that a load can shift or quantify savings.
- Reworked daily brief comparisons to use four complete prior same-weekdays,
  made missing yesterday usage nullable, removed the fixed `$0.20` impact, and
  withheld forecast-dependent advice.
- Gated period comparison metrics on complete measured weekday-aligned periods;
  removed unsupported causal explanations and action suggestions.
- Marked synthetic or mixed billing inputs illustrative and prevented them
  from being presented as customer estimates; an explicitly requested
  scenario remains illustrative and is not a customer estimate.
- Removed default-rate peak anomaly cost estimates and appliance-specific
  anomaly suggestions; incomplete days no longer produce these findings.
- Restricted AI usage context to seven complete measured days and added a
  tested output guard for unsupported numeric claims.
- Updated the recommendation UI with evidence status, expiry handling and a
  calculation-detail view; updated bill-comparison labels and unavailable
  states.

## Validation record

| Check | Command | Result |
|---|---|---|
| Pre-Prompt 20 baseline | `..\\.venv311\\Scripts\\python.exe -m pytest -q` from `backend/` | **PASS — 255 passed, 12 warnings.** This baseline was recorded before Prompt 20 code changes; the worktree already contained Prompt 17–19 changes. |
| Focused Prompt 20 regressions | `..\\.venv311\\Scripts\\python.exe -m pytest tests\\test_billing.py tests\\test_vertical_slice.py tests\\test_recommendation_engine.py tests\\test_anomaly_detector.py tests\\test_insights_endpoints.py -q` from `backend/` | **PASS — 47 passed, 6 warnings.** |
| Full backend suite | `..\\.venv311\\Scripts\\python.exe -m pytest -q` from `backend/` | **PASS — 261 passed, 12 warnings, 66.17 s, exit 0.** |
| Focused Ruff | `..\\.venv311\\Scripts\\python.exe -m ruff check` over modified Prompt 20 backend modules and tests | **PASS — no findings.** |
| Mobile TypeScript | `npx tsc --noEmit` from `mobile/` | **PASS — exit 0.** |
| PostgreSQL migration check | No schema migration was added | **NOT APPLICABLE.** |
| Whitespace | `git diff --check` | **PASS — exit 0.** Git emitted line-ending normalization warnings on existing modified files. |

### SQLite native diagnostic

The final full backend run printed a `Windows fatal exception: access
violation` during `test_scheduling_contract.py` fixture teardown, with the
stack in SQLAlchemy schema `drop_all`/`_can_drop_table`, then continued to
**261 passed** and exited 0. Running `test_scheduling_contract.py` alone also
printed native access-violation diagnostics in SQLAlchemy result setup, while
all **19 tests passed**. The focused Prompt 20 regression group passed without
the diagnostic. Similar transient diagnostics were recorded before Prompt 20.
The underlying native teardown/result issue remains unresolved; passing pytest
does not establish that it is harmless.

## Remaining work before full acceptance

1. Persist immutable/versioned evidence or define a durable audit and
   invalidation policy; expose expiration semantics consistently to all
   consumers.
2. Attach the same evidence contract to scheduling comparisons while reusing
   the existing fixed-baseline, greedy-reference, and MILP results.
3. Implement a deduplication policy for unchanged recommendation
   notifications.
4. Define and pass chronological held-out evaluation before enabling any
   forecast-dependent recommendations.
5. Add separate cross-user evidence access assertions if a durable evidence
   retrieval surface is introduced; fully covered measured and synthetic
   recomputation fixtures are now present.
6. Implement calendar-period comparison only with explicit complete-date
   denominators and missing-data behavior.

No weather or wholesale-market data was used to support household load,
tariff, or savings claims.
