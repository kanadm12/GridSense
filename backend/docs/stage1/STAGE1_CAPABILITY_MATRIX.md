# Stage 1 capability and evidence matrix

**Base revision reviewed:** `d789f9814da9955db1c63ced921a95379dd08495`
**Implementation review date:** 31 October 2026
**Working-tree changes:** Prompt 17 implementation is uncommitted; exact checks are in `BASELINE_VERIFICATION.md`.

“Verified” below means verified only at the referenced implementation/test
scope. It does not imply field validation, customer performance, or production
readiness.

| Capability | Status | Current implementation/evidence | Gap before Stage 1 acceptance |
|---|---|---|---|
| Authenticated user and meter ownership | **VERIFIED** | FastAPI auth/ownership dependencies and API tests. | External-provider authorization and provider-secret handling need dedicated tests. |
| NEM12 parser and upload | **PARTIAL** | MDFF v2.7 format clauses are verified for nominal interval-end positions, 200/300/400 layouts, and quality flags. Parser preserves raw value/unit, NMI configuration, channel identifiers, interval date/index, quality metadata, and unresolved direction; valid 400 ranges are applied per interval. | NMI Procedure, Metrology Procedure Part B, effective-version provenance, source clock/DST basis, and source-specific direction evidence remain blocked. See `AEMO_NEM12_COMPLIANCE_MATRIX.md`. |
| Import/export classification | **PARTIAL** | `Reading.direction` must explicitly equal `import` or `export`; parser keeps NEM12 channels `unknown`, preserves RegisterID, NMISuffix, and MDMDataStreamIdentifier separately, and separates channels by data-stream identifier. | The MDFF 200 record is not direction evidence. NMI Procedure/MSATS and source-specific mapping remain unavailable; historical direction is not backfilled. |
| Consumption totals | **PARTIAL** | Coverage-aware usage responses report eligible/missing/excluded/duplicate counts, import/export separation, observed energy and demand, and Melbourne DST denominators. | Imported NEM12 data is still unavailable for UTC-dependent metrics until clock and direction evidence is verified. Public period-comparison endpoints are not yet fully gated by weekday/calendar comparability. |
| Timezone and DST tariff alignment | **PARTIAL** | Local-day coverage uses UTC boundary durations and accepts 46/48/50 slots for 30-minute Melbourne days. New imported records retain a source time-basis field. | NEM12 source clock/boundary semantics and applicable external procedure version remain blocked; existing tariff helper behavior is not authoritative metering evidence. |
| Billing breakdown | **PARTIAL** | Confirmed, effective-dated tariff revisions are priced without a customer fallback rate; missing/out-of-period rates and absent TOU windows remain unpriced. Explicit illustrative scenarios are labeled. Coverage and unsupported components are returned. | A complete retailer bill is not established by user entry alone. Meter-channel/time evidence and unsupported tariff terms can leave amounts partial or unavailable. |
| Tariff entry/history | **PARTIAL** | Stable per-user tariff identity with append-only revision snapshots, confirmation/source, effective dates, GST, tariff periods, supply/FiT fields, unsupported-term disclosure and archive behavior. Legacy mutable rates are not backfilled as confirmed history. | User-entered terms still require comparison with retailer evidence. Complex demand, controlled-load, conditional discount and other contract rules are not fully priced. |
| Forecast research | **SIMULATED** | Chronological persistence/weekday baseline and Prophet evaluation on one French household dataset; leakage/coverage helpers have tests. Retrieved Open-Meteo forecasts are persisted with retrieval/target timestamps, but no issue time is available. | Not a validated Victorian household forecast; no verified historical decision-time weather feature, uncertainty gate, or evidence that weather improves performance. |
| Monthly bill forecast API | **PARTIAL** | Projects kWh from current and previous-period daily averages; cost fields are null. | Current implementation does not compute expected coverage and its confidence is null; it should be presented as a rough usage projection, not a bill. |
| Rule-based recommendations | **PARTIAL** | Typed response includes assumptions, uncertainty, data requirements, tariff status and unquantified state; tests cover missing tariff and no invented savings. | No durable calculation/input references, rule version, lifecycle expiry, or universal quality/coverage eligibility. |
| Scheduling contract and optimizer | **VERIFIED for synthetic contract; PARTIAL for product pipeline** | Versioned schema, tariff resolution, time-aware validation, bounded MILP, deterministic greedy comparator, explicit preview-only response and contract tests. | Synthetic UI baseline remains separate from meter-derived analytics. A measured baseline requires proven non-task demand and no flexible-load duplication. |
| Device automation | **PARTIAL** | Models/API and Home Assistant provider code exist. | No evidence in this task of end-to-end live dispatch, safe customer authorization, device validation, or relationship to scheduling preview. Scheduling must remain advisory. |
| AER generic plan catalog | **PARTIAL** | Current retailer URI snapshot, public list/detail API adapter, version-specific headers, postcode filtering, transient terms display and mobile reference-plan browsing. Mocked tests cover pagination, geography, version mismatch/schema changes, timeout and 429. | AER/DEECA redistribution, attribution, retention and caching permissions are not established. No provider payload is persisted; production use remains blocked pending confirmation. Public generic data never activates a customer tariff. |
| Weather & Grid Context | **PARTIAL** | Authenticated weather forecast API, provider status, persisted fetch/forecast records, freshness/stale states, unit normalization, and Expo dashboard context are implemented. The paid Open-Meteo endpoint is used only when an operator key is configured; mobile accepts manually entered approximate coordinates. | No paid key/live provider smoke test; exact resolved model and forecast issue time are unavailable. No historical decision-time forecast evaluation or automatic background polling. Provider retention policy must be decided before production. See `EXTERNAL_PROVIDER_SOURCE_MATRIX.md`. |
| Open-Meteo forecast adapter | **PARTIAL** | Official Forecast API v1 docs, units, selected fields, terms/pricing and CC BY 4.0 attribution reviewed; typed paid-only adapter and fixed fixtures implemented. | Paid account/key and live schema verification unavailable. `best_match` does not provide the resolved model/run; issue time remains null. Recheck subscription/terms before deployment. |
| AEMO wholesale market adapter | **BLOCKED** | The public DispatchIS directory listing is reachable; AEMO market-data/NEMWeb documentation requests returned HTTP 403. No adapter is implemented; context response has blocked status and null market fields. | Verify authoritative schema, VIC region, price/demand units and intervals, dispatch/pre-dispatch/revisions, issue time, publication and data-use rights. No wholesale value is fed to tariffs or customer savings. |
| Amber / authorized retail dynamic price | **NOT IMPLEMENTED / BLOCKED** | No Amber provider adapter found. | Verify current official API contract, authorization scope, user consent, retention, and use terms; never infer retail prices from wholesale data. |
| CDR energy-data import | **NOT IMPLEMENTED / BLOCKED** | No CDR flow found. | Eligibility/accreditation, consent/revocation, data-holder interfaces, privacy impact, and retention need a separate approved design. |
| PostgreSQL/Redis deployment and recovery | **NOT VERIFIED** | Compose syntax and restore script were previously checked; database/worker/restore execution was not performed. | Run disposable PostgreSQL/Redis integration and restore verification in a supported environment. |

## Prompt 17 implementation evidence

The reusable interval eligibility and coverage service is
`backend/app/services/interval_quality.py`. The additive migration adds nullable
raw value/unit, provenance, source-time-basis, NEM12 source-coordinate and
channel-identification fields without backfilling historical rows. Usage API
schemas and mobile dashboard/usage surfaces expose
eligible imported energy, coverage/missing counts, unavailable/partial
explanations, demand terminology, and synthetic-data labeling. Regression
results are in the Prompt 17 section of `BASELINE_VERIFICATION.md`.

This is a PARTIAL implementation, not verified customer NEM12 consumption.
MDFF v2.7 format clauses were retrieved and implemented where determinate.
Clock-basis and direction rules still depend on inaccessible related AEMO
procedures; no suffix/register mapping has been adopted.

## Prompt 18 tariff and AER evidence

Immutable customer tariff revisions, safe unavailable/partial billing, and
the read-only AER reference catalog are implemented with the boundaries
described in [`PROMPT18_MIGRATION_COMPATIBILITY.md`](PROMPT18_MIGRATION_COMPATIBILITY.md)
and [`AER_PRODUCT_REFERENCE_DATA.md`](AER_PRODUCT_REFERENCE_DATA.md).
Current test and migration outcomes are recorded in
[`PROMPT18_ACCEPTANCE.md`](PROMPT18_ACCEPTANCE.md).

## Compatibility decision: old direction/register rows

The prior expression
`direction IS NULL AND register_type == "B"` is a compatibility heuristic,
not an authoritative direction record. From the Stage 1 contract onward:

1. New ingestion must set an explicit normalized direction only when confirmed
   by source metadata and an approved mapping; otherwise use `unknown`.
2. The historical `NULL`/`B` predicate is removed from `consumption_reading_filter()`.
   It is **not eligible** for validated consumption, billing, forecast training,
   or measured scheduling baselines.
3. When interval time is normalizable, the shared quality service reports the
   reason `legacy_direction_unverified` and counts it separately. If source
   time is unverified, the record cannot be assigned to an exact requested
   local-day window; retain it and report the time-basis blocker instead.
   Eligibility requires an auditable correction or a reviewed migration
   supported by authoritative evidence and reconciliation tests.
4. Do not bulk relabel legacy B rows, infer direction from suffix alone, or
   delete them as part of this documentation milestone.

## Evidence references

- `backend/app/models/reading.py`
- `backend/app/services/nem12_parser.py`
- `backend/app/services/usage_analyzer.py`
- `backend/app/api/billing.py`
- `backend/app/models/tariff.py`
- `backend/app/services/forecasting.py`
- `backend/app/ml/forecast_evaluation.py`
- `backend/app/schemas/recommendation.py`
- `backend/app/schemas/scheduling.py`
- `backend/app/api/scheduling.py`
- `backend/app/services/scheduling_optimizer.py`
- `backend/tests/test_vertical_slice.py`
- `backend/tests/test_tariff.py`
- `backend/tests/test_billing.py`
- `backend/tests/test_forecast_evaluation.py`
- `backend/tests/test_recommendation_engine.py`
- `backend/tests/test_scheduling_contract.py`
