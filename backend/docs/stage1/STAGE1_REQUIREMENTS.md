# GridSense Stage 1 requirements

**Status:** architecture baseline; implementation is not certified
**Revision reviewed:** `d789f9814da9955db1c63ced921a95379dd08495`
**Review date:** 31 October 2026
**Prompt 17 implementation status:** partial; source standard verification remains blocked

## Purpose and non-goals

Stage 1 is an advisory household-energy product. It should transform eligible
meter observations, a tariff the household has reviewed, weather or market
context where properly licensed, and user-declared appliance constraints into
understandable metrics and schedule previews.

The governing principle is:

> A result must not claim more certainty than its eligible inputs, provenance,
> coverage, tariff rules, and validation evidence support.

Stage 1 does not claim appliance dispatch, demand response, validated customer
savings, live meter access, gross household load from net-meter readings,
PV-generation measurement from import/export registers, or production
readiness. Wholesale market information is not a household retail tariff.

## Status vocabulary

- **VERIFIED** — observed in repository behavior or an executed test, within
  the stated scope only.
- **SIMULATED** — generated scenario or synthetic input; not field evidence.
- **PARTIAL** — an implementation exists but a stated acceptance condition is
  missing.
- **NOT IMPLEMENTED** — no product capability was found in the reviewed tree.
- **BLOCKED** — implementation or a claim depends on external facts, rights, or
  environments not verified here.

These labels describe evidence, not product quality grades.

## Requirements and acceptance

| ID | Requirement | Acceptance criterion |
|---|---|---|
| R-01 | Preserve source identity and register/channel direction. | Unknown direction is never used in import, export, consumption, billing, or training totals. A fixture with unresolved direction returns no consumption total. |
| R-02 | Preserve interval semantics. | Each normalized reading has interval length and an unambiguous UTC start/end instant; source timestamp and basis remain traceable. Local display uses the meter's IANA zone. |
| R-03 | Apply quality rules by feature. | Consumption, billing, forecasting, and scheduling each publish an explicit eligibility decision and excluded counts; no single ambiguous global “valid” flag silently drives all features. |
| R-04 | Quantify coverage. | Expected slots derive from the requested local civil-time window converted to UTC. A Melbourne spring-forward 30-minute day expects 46 slots; a fall-back day expects 50. |
| R-05 | Separate energy quantities. | Import, export, and net grid energy are distinct. Gross household load and PV generation remain unavailable absent validated measurement/disaggregation. |
| R-06 | Qualify tariffs and money. | A generic plan is not a confirmed customer contract. No unrequested default rate may silently price a customer estimate. Every response reports tariff status, effective date coverage, GST treatment, and included/excluded components. |
| R-07 | Version tariffs without rewriting history. | Each accepted tariff revision is immutable. Unknown historical contract periods remain unknown rather than being backfilled from the current plan. |
| R-08 | Track provenance. | Every input is classified as measured, forecast, user-entered, synthetic, or derived; source/version, relevant times, unit, and transformations are traceable. |
| R-09 | Treat provider outages honestly. | Timeout, stale cache, invalid payload, quota, and licensing failures are explicit states. No invented provider value or silent source substitution. |
| R-10 | Evidence every recommendation. | Every numeric impact is reproducible from deterministic code and identified input references; otherwise the impact is null and the recommendation is unquantified/unavailable. |
| R-11 | Make schedule comparisons fair. | Preferred, greedy-reference, and MILP results use the same task set, non-task baseline, tariff, price vector, horizon, and limits. Candidate costs independently recompute within AUD 0.01. |
| R-12 | Prevent load double-counting. | A baseline used for scheduling excludes the flexible tasks modeled by the optimizer. Raw meter load cannot be called a non-task baseline without validated disaggregation or a separately measured submeter. |
| R-13 | Preserve privacy and ownership. | Meter/tariff/evidence reads enforce owner access. Provider credentials stay server-side and are never written to logs or client payloads. |
| R-14 | Report operational limits. | No production-security, recovery, PostgreSQL/Redis runtime, external provider, or customer-performance claim without the corresponding executed verification. |

## Prompt 17 clarifications

- The conservative quality-A policy applies to **headline actual observations**
  until the authoritative source quality semantics are confirmed. It is not a
  universal judgement that estimated, substituted, or other non-A source
  records are invalid. Keep those source records and report their codes
  separately; do not merge them into actual totals.
- Demand from observed eligible intervals is reported as an
  **observed-interval average** (`eligible kWh / eligible interval-hours`) and
  an **observed interval-average peak** (`max(interval kWh × 60 / minutes)`).
  Full-period average demand is only available when the requested period has
  complete eligible coverage. It is not an instantaneous peak.
- Distinct periods are comparable only after an explicit alignment method.
  Weekday-aligned comparisons require complete local days and equal counts for
  each weekday in each period; dates are expected to differ. Calendar-aligned
  comparisons use complete calendar months, compare daily averages, and report
  the differing number of calendar days. Neither method substitutes zero for
  missing dates.
- MDFF v2.7 verifies nominal interval-end position relative to `IntervalDate`,
  not a timezone or UTC offset. When source clock/DST semantics are not
  verified, preserve source date/index and withhold UTC-dependent metrics.
- Prompt 17 records the implementation delta in
  [PROMPT17_MIGRATION_COMPATIBILITY.md](PROMPT17_MIGRATION_COMPATIBILITY.md).
  Local acceptance tests do not unblock authoritative NEM12 timestamp or
  direction semantics.
- Prompt 17B's versioned source crosswalk is in
  [AEMO_NEM12_COMPLIANCE_MATRIX.md](AEMO_NEM12_COMPLIANCE_MATRIX.md). MDFF
  v2.7 applies from 1 December 2025; it is not retroactively assumed for
  earlier files.

### Prompt 17 specification change record

| Prior ambiguity | Resolved rule | Justification |
|---|---|---|
| Comparison text could be read as requiring matching calendar dates. | Compare distinct date ranges using weekday-aligned complete-day counts or complete calendar months; never require identical dates. | Real comparison periods are normally different dates. Weekday composition or complete-month daily averages make the basis explicit without pretending missing dates are zero. |
| “100% quality A” could be read as a universal validity rule. | Quality A is a conservative policy for headline actual observations only; keep non-A readings and report them separately. | Estimated/substituted records may be meaningful for other purposes; their official semantics and permitted use have not been verified. |
| “Average demand” could imply full-period demand even with missing intervals. | Separate observed-interval average from full-period average; expose the latter only at complete eligible coverage. | The observed denominator is actual eligible interval-hours; extrapolating across missing time would fabricate evidence. |

## Stage 1 feature contract

| Feature | Current status | Inputs/formula | Eligibility and failure behavior | Dependencies and limitations |
|---|---|---|---|---|
| NEM12 ingestion | **PARTIAL** | Preserve source values/units, NMI configuration, RegisterID, NMISuffix, MDMDataStreamIdentifier, interval date/index, quality, and duration. MDFF v2.7 verifies nominal interval-end indexing and 300/400 record structure. | Upload preserves unresolved records for audit; direction remains `unknown` and NEM12 source time basis remains unverified for UTC. Unsupported units remain ineligible. | NMI Procedure, Metrology Procedure Part B, source-period specification provenance, and source-specific direction/clock rules remain blocked; see AEMO compliance matrix. |
| Consumption analytics | **PARTIAL** | Sum eligible import intervals; observed average demand = eligible kWh / eligible interval-hours; observed interval-average peak = max(interval kWh × 60 / interval minutes). | Explicit import, quality A, supported units, eligible provenance, validated time basis, and unique UTC slot required. Partial days are labeled observed eligible energy; full-period average is withheld unless eligible coverage is complete. | Coverage is now returned by usage APIs. Imported NEM12 records remain blocked by unresolved source clock/direction. Net readings do not reveal gross load/PV. |
| Tariff period analysis | **PARTIAL** | Sum eligible interval energy by customer tariff period at local interval start. | Requires tariff version covering each interval and unambiguous schedule. Otherwise period allocation is unavailable/unpriced. | Current built-in VIC windows are not universal retailer terms or holiday rules. |
| Billing estimate | **PARTIAL** | Import charge = Σ(kWh × AUD/kWh); export credit = Σ(export kWh × FiT); add separately supported fixed/demand/tax components. | Explicit direction, quality A, supported unit/provenance and valid timestamp required. No tariff/default or preset path remains explicitly illustrative; incomplete coverage is reported, not treated as actual bill evidence. | Immutable revisions are implemented, but no estimate is validated against an actual customer bill; unsupported contract terms still prevent a complete-bill claim. |
| Forecasting | **PARTIAL** | Forecast target and horizon; compare persistence/seasonal baseline with candidate model. Report MAE/RMSE, sample counts, baseline-relative MAE, and interval coverage/width. | Only train on eligible measured history and features known at issue time. If history/coverage insufficient or model fails predefined baseline criterion, forecast is unavailable. | Existing experiment is one French household, not Australian validation; no verified historical weather issue-time evidence or product acceptance threshold exists. Forecast-dependent advice remains disabled. |
| Recommendations | **PARTIAL** | Rule, observed facts, eligible evidence, action, baseline, deterministic outcome, uncertainty and expiry. | Insufficient evidence yields unquantified/unavailable; no generic savings amount. “No supported action” is valid. | Current API has conditional/unquantified fields but no durable evidence lineage or expiry. |
| Scheduling preview | **PARTIAL** | Task power × duration × interval tariff plus stated AUD preference/omission penalties; compare preferred, greedy reference, and MILP using the same profile, tariff revision, interval vector, horizon, tasks and limits. | A measured baseline requires server-validated evidence of separately measured or synchronized, defensible non-task load. A user declaration or aggregate import is insufficient. Synthetic baselines are explicitly illustrative. Infeasible or unsupported measured paths withhold cost outputs. | Synthetic scheduling uses the existing MILP and greedy optimizer and reports a preferred schedule, response-scoped evidence and local-time proposal. No validated submeter/disaggregation source is integrated; no device dispatch is performed. |
| External weather | **NOT IMPLEMENTED** | Timestamped provider forecast aligned to forecast target intervals. | Stale/unavailable weather is omitted; forecast feature status is explicit. | Open-Meteo non-commercial/commercial terms and API documentation reviewed, but product-specific commercial access and exact archived-run issue-time handling need confirmation. |
| Retail plan discovery | **PARTIAL** | Read-only AER generic plan discovery and detail with manual review; no automatic activation. | Never treat generic plan data as the user's contract. Unsupported terms make comparison incomplete/unavailable. | Interface, versions, schemas and live response shape verified; redistribution, attribution, retention and cache permissions remain unverified and block production use. |
| Wholesale market context | **NOT IMPLEMENTED / BLOCKED** | AEMO observation/forecast with market region, interval, unit and issue time. | Display as wholesale market context only. Cannot price household bills or imply retail savings without a validated contract mapping. | AEMO pages returned 403; exact feeds, terms and current procedure versions remain unverified. |

## Global release gates

1. Prompt 17 verifies meter-data direction, interval clock basis, quality rules,
   and expected-versus-eligible coverage.
2. Prompt 18 establishes immutable tariff revisions and verifies the official
   AER interface and terms before connecting a generic-plan catalog.
3. Prompt 19 verifies provider rights, endpoints, units, timestamps and failure
   semantics before any external data is used.
4. Prompt 20 makes recommendation impacts evidence-backed and reproducible.
5. Prompt 21 validates forecast/schedule inputs and proves no load double count.
6. No stage is promoted by file presence alone; tests and evidence must satisfy
   the acceptance criteria in `STAGE1_TEST_MATRIX.md`.

## Related documents

- [Capability matrix](STAGE1_CAPABILITY_MATRIX.md)
- [Metrics and data-quality specification](METRICS_AND_DATA_QUALITY_SPEC.md)
- [External integration design](EXTERNAL_DATA_INTEGRATION_DESIGN.md)
- [Recommendation evidence contract](RECOMMENDATION_EVIDENCE_CONTRACT.md)
- [Test matrix](STAGE1_TEST_MATRIX.md)
- [Implementation backlog](PHASE2_IMPLEMENTATION_BACKLOG.md)
