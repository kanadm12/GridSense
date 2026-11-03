# Metrics and data-quality specification

**Specification version:** draft 1.1 for implementation planning
**Review date:** 31 October 2026

This contract defines conservative defaults for future implementation. It does
not assert that the current product already satisfies them. Source semantics
that depend on AEMO procedures remain blocked until the applicable documents
are retrieved and reviewed.

**Prompt 17 implementation note (31 October 2026):** The repository now has a
local coverage/eligibility implementation for explicitly classified records.
NEM12 upload remains partial: the current parser preserves source fields but
marks direction unknown and its timestamp basis unverified, so those records
do not enter UTC-dependent customer metrics. Test evidence is summarized in
`PROMPT17_MIGRATION_COMPATIBILITY.md`; passing local fixtures does not verify
Australian metering semantics.

## 1. Canonical provenance

Every input or derived value must carry a `provenance_kind`:

| Kind | Meaning | Required metadata |
|---|---|---|
| `measured` | Meter/submeter observation or supplied meter record. | Source/file identifier and digest where available; source version; NMI/register/suffix; direction status; source timestamp/basis; interval duration; raw and normalized unit/value; quality code; import time. |
| `forecast` | Prediction for a future target, or a historical archived forecast. | Provider/model/version; `issued_at` or archived run time; `target_start`/`target_end`; retrieval time; units; location/region; feature availability at issue time. Observed weather is not a forecast. |
| `user_entered` | Household-entered tariff, appliance, preference, or location. | User/tenant reference; entered/confirmed time; effective interval if supplied; confirmation state; original value/unit; user-edit history. |
| `synthetic` | Generated or seeded scenario input. | Scenario/profile ID, generator/version/seed when available, explicit synthetic label. Never eligible as a customer observation. |
| `derived` | Calculated result from other records. | Formula and version; stable input references; execution time; output unit; assumptions; status and limitations. |

“Actual” is a source quality classification, not a synonym for all measured
data. A measured reading can be estimated/substituted or unresolved.

## 2. Units and time

Canonical units:

- Interval energy: `kWh`.
- Average demand: `kW`.
- Retail energy rate: `AUD/kWh`; stored/presented cents per kWh must be
  explicitly converted (`c/kWh ÷ 100`).
- Market wholesale rate: `AUD/MWh`; convert to `AUD/kWh` only for a
  separately labeled market metric (`AUD/MWh ÷ 1000`). Never pass it to a
  household retail-cost calculation without a verified retail contract mapping.
- Currency: `AUD`; round displayed monetary components to cents using
  `ROUND_HALF_UP`, and calculate totals from the unrounded interval quantities
  or a consistently documented line-item rounding ledger.
- `Wh → kWh`: divide by 1000.

Canonical event times are timezone-aware UTC instants. Preserve the original
source string/time basis and the conversion rule. A local timestamp is for
display and tariff-calendar lookup, not a globally unique instant.

Each energy interval represents `[interval_start, interval_end)` and stores
duration. MDFF v2.7 verifies the nominal NEM12 interval-end index relative to
`IntervalDate` (§3.3.2–3.3.3, pp. 7–8), but does not establish a UTC offset or
daylight-saving realization. GridSense preserves `IntervalDate` and interval
number and does not normalize NEM12 timestamps to UTC until the applicable
NMI/Metrology procedures and source-specific rules are verified. See
[`AEMO_NEM12_COMPLIANCE_MATRIX.md`](AEMO_NEM12_COMPLIANCE_MATRIX.md).
Never silently reinterpret existing stored timestamps.

## 3. Coverage denominators

For a requested local civil period:

1. Construct local start-of-day and the exclusive local end boundary in the
   meter's IANA timezone.
2. Convert both boundaries to UTC.
3. `expected_slots = UTC duration / interval_duration`.
4. Require the duration to be an exact multiple of the supported interval
   duration; otherwise report a contract/data error rather than rounding.
5. Map each source interval to a unique UTC slot. Duplicate slots are not
   counted twice; report duplicate records separately.
6. `eligible_slots` counts distinct expected slots with valid direction, quality,
   units, timestamp, and value for the named feature.
7. `coverage = eligible_slots / expected_slots`.
8. Report `missing_slots`, `excluded_quality_slots`,
   `unresolved_direction_slots`, `invalid_unit_slots`, and duplicates
   separately. Do not treat missing and excluded intervals as equivalent.

For Australia/Melbourne 30-minute intervals:

- Ordinary 24-hour day: 48 expected slots.
- Spring-forward 23-hour local day: 46 expected slots.
- Fall-back 25-hour local day: 50 expected slots.

Partial-day intervals use the clipped UTC duration of the selected local
window; do not retain a 48-slot denominator for a half-day request.

**Stage 1 comparison gate:** a day is `complete` only at 100% eligible
coverage. A day with at least one but less than 100% eligible coverage is
`partial`; the observed eligible sum may be displayed as “observed eligible
energy” with coverage, but not extrapolated. Comparing separate periods does
not require the same calendar dates:

- **Weekday-aligned:** compare complete local dates grouped by weekday. Each
  period must have at least seven complete days and the same weekday-count
  vector (e.g. one complete Monday through Sunday per period). Compare totals
  only for equal complete-day counts and weekday composition; otherwise return
  `unavailable_insufficient_coverage`.
- **Calendar-aligned:** compare complete calendar months. Report the date count
  and total for each; use mean kWh per complete local date for the relative
  comparison when month lengths differ. All dates in each named month must be
  complete. Do not compare different month totals as if the periods had equal
  duration.

Dates in compared periods are distinct by design. Missing dates are never
imputed as zero. Seven complete days is a conservative minimum gate, not a
claim that a week is statistically representative.

## 4. Quality eligibility by feature

Until authoritative NEM quality-method semantics are checked, Stage 1 uses the
following conservative **headline actual-observation policy**: quality code
`A` is the only code included in the primary actual-observation totals. Codes
`E`, `F`, `S`, `V`, `U`, blank, and unknown codes are retained and counted
separately. This is not a universal judgement that those readings are invalid;
in particular, an estimated or substituted source reading may have a legitimate
use in a separately labeled metric after its semantics and intended use are
verified. Do not relabel or merge such values into the headline actual figure.

| Feature | Eligible input | Excluded or separate treatment |
|---|---|---|
| Consumption | Explicitly confirmed `import` direction; finite nonnegative energy in supported unit; quality `A`; unique valid interval; measured provenance. Synthetic data is allowed only in a separately labeled illustrative path. | Export, unknown direction, legacy null/B, non-A/unknown quality, invalid/duplicate records. Keep counts; never net or infer gross load. |
| Export | Explicitly confirmed `export` direction; same unit/time/value/quality checks as consumption. | Unknown direction and all legacy null/B rows excluded. |
| Billing energy charge | Eligible import readings above; tariff version explicitly confirmed by user and effective over each charged interval; applicable rate exists. | Non-A values excluded from headline customer charge; may only appear as a distinct unpriced/excluded quality subtotal. No default retail rate. |
| Billing export credit | Eligible export readings plus confirmed FiT for each interval. | Missing FiT means credit unavailable, not zero-dollar evidence of no value. |
| Forecast training/scoring | Eligible actual import daily target with 100% slot coverage initially; feature timestamps available at forecast issue time. | Partial days, synthetic, estimated/substituted, unresolved, duplicate, or future-leaking features excluded. A later validated coverage relaxation requires a versioned rule and sensitivity tests. |
| Scheduling baseline | Nonnegative demand in kW on a regular timezone-aware interval grid; provenance explicitly `measured` with supported submeter/validated-disaggregation method and source quality/coverage evidence, or explicitly `synthetic` for simulation. | Raw net-meter values, unknown-direction readings, synthetic profile represented as household observation, or baseline that already includes scheduled appliance load are ineligible for measured non-task baseline. |
| Recommendation evidence | Inputs must meet the eligibility of the metric used; all exclusions and rule checks are retained. | If required inputs fail, return unquantified/unavailable, not a low-confidence numeric saving. |

If a value uses user-entered data, the result must say so. If a synthetic input
is present, the result is illustrative even if the arithmetic is correct.

## 5. Energy and demand definitions

Let `I` be eligible import intervals and `X` eligible export intervals:

- Imported energy: `E_import = Σ(i ∈ I) energy_i_kWh`.
- Exported energy: `E_export = Σ(x ∈ X) energy_x_kWh`.
- Net grid energy: `E_net = E_import - E_export`, only over matched time
  windows with both directions classified. It can be signed; it is not gross
  household load.
- Household gross load: unavailable from net grid energy alone.
- PV generation: unavailable from import/export data alone.
- Interval-average import demand: `energy_kWh × 60 / duration_minutes`.
- Average demand over an interval set: `Σ eligible_import_kWh /
  Σ eligible_interval_hours`.
- Observed-interval average demand: eligible imported energy divided by the
  summed duration of the eligible observed intervals. Label it as the average
  over observed intervals.
- Observed interval-average peak demand: maximum eligible interval-average
  import kW, never “instantaneous peak”.
- Full-period average demand: eligible energy divided by the full requested
  period hours, available only at complete coverage; otherwise unavailable.

For an illustrative 30-minute import reading of 0.8 kWh, interval-average
demand is `0.8 × 60 / 30 = 1.6 kW`.

## 6. Period and tariff metrics

Daily, weekly and monthly totals are sums of eligible import intervals grouped
by their local interval-start/end semantics after the source clock basis is
verified. Calendar-period averages divide by complete eligible days, not by
days merely containing a reading. Partial periods show both observed total and
coverage.

Peak/shoulder/off-peak buckets require the user-confirmed tariff's
effective-dated time windows, weekday/day rules, and any supported holiday
exceptions. A generic default Victorian schedule is not a confirmed customer
tariff. If the applicable plan rules are not represented, return
`period_breakdown_unavailable` or a separately labeled illustrative scenario.

## 7. Cost calculation and unavailable states

For rate-covered imports:

`import_energy_charge_AUD = Σ(import_kWh_i × applicable_rate_AUD_per_kWh_i)`

For rate-covered exports:

`export_credit_AUD = -Σ(export_kWh_i × confirmed_FiT_AUD_per_kWh_i)`

The displayed estimate must list:

- `energy_charge`, `export_credit`, `supply_charge`, `demand_charge`,
  GST treatment, discounts, other fees, and total—each with status and source.
- Tariff version and confirmation status.
- Eligible, excluded, unpriced, expected, and missing intervals.
- Covered dates and calculation/formula version.
- Explicit exclusions such as demand windows, discounts, public holidays,
  taxes, or unsupported terms.

States:

- `unavailable_no_confirmed_tariff`: no user-confirmed tariff; no customer
  estimate is calculated.
- `illustrative_scenario`: only when user explicitly requests an example; uses
  labeled hypothetical rates and never feeds customer savings/recommendations.
- `partial_estimate`: some eligible energy is priced, but data or tariff
  coverage is incomplete; report the priced subset and unpriced kWh separately.
- `unavailable_unsupported_tariff`: required rate or billing rule is not modeled.
- `complete_component_estimate`: all supported requested components are
  calculated; do not label it a complete retailer bill unless every contract
  component and eligibility term is represented.

No tariff, out-of-range tariff, missing rate window, overlapping periods,
unsupported demand-charge method, or unconfirmed generic plan must not silently
fall back to a default tariff. Existing default-price behavior is an explicit
Prompt 17/18 remediation item.

GST calculation must follow the plan's documented tax-inclusion semantics.
For GST-inclusive taxable charges, the memorandum GST component is
`inclusive_taxable_amount / 11`; for GST-exclusive taxable charges, add
`taxable_amount × 0.10`. Export-credit tax treatment must be separately
verified for the applicable contract; do not assume one universal rule.

## 8. Forecast and scheduling metrics

Forecast target: import kWh for a specified period only when direction,
quality, coverage and clock basis meet the forecast eligibility above.

For target `y_t` and prediction `ŷ_t` over `n` valid forecasts:

- `MAE_kWh = Σ|y_t - ŷ_t| / n`
- `RMSE_kWh = sqrt(Σ(y_t - ŷ_t)^2 / n)`
- Prediction interval coverage = fraction of actual values within a
  predeclared interval; report interval width and sample count.

Report by horizon, season/time segment where sample size allows, and compare
against persistence and a predeclared seasonal baseline. No performance claim
is accepted without the test period, target population, sample count, data
coverage and baseline.

Scheduling energy cost:

`Σ_i((baseline_demand_kW_i + scheduled_task_demand_kW_i) × interval_hours × retail_rate_AUD_per_kWh_i)`

This is valid only when baseline demand is non-task demand and excludes the
flexible tasks modeled by the optimizer. The preferred, greedy, and MILP
scenarios must use identical fixed inputs. Report energy charge, preference
penalty, omission penalty, objective, displacement, feasibility and completion
separately. Never call `preferred_cost - proposed_cost` verified household
savings; label it modeled scenario difference. Candidate versus reference
delta is not a household savings estimate.

## 9. Prompt 20 recommendation and comparison eligibility

Customer usage-pattern recommendations require the latest seven **completed**
local dates, each with 100% eligible import coverage, quality-A intervals,
classified import direction, verified source time basis, and measured or
explicitly synthetic provenance. Incomplete windows produce a data-quality
action with no energy or financial impact. Synthetic or mixed inputs produce
an `illustrative` status. Aggregate interval data does not identify appliances
or prove that any load is flexible.

Period-to-period change claims require at least seven fully covered measured
days in each period and identical weekday-count vectors. A period with missing,
unresolved, synthetic, or mixed inputs has unavailable percentage changes and
daily averages. The daily brief compares yesterday only with four complete
prior observations from the same weekday; it does not impute missing readings
as zero and does not infer a cause. No forecast-dependent recommendation is
enabled without a separate chronological held-out acceptance result.

Recommendation evidence is presently a compact response-time object rather
than a persisted audit record. It contains a hashed reading-set reference,
record count, provenance and eligibility summaries, local-date window, formula
and rule versions, assumptions, limitations, and an expiry. It is rebuilt
when requested and expires after one hour. This safely avoids copying raw
meter datasets into recommendations, but it does not provide durable
historical evidence, immutable audit retention, or automatic invalidation
events; those capabilities remain incomplete.

Billing period breakdowns may retain observed eligible energy and a clearly
labeled partial component estimate. Period comparison changes are withheld
unless both periods are complete measured observations with matched weekday
composition. Synthetic meter inputs are marked illustrative and cannot support
a customer-estimate claim; an explicitly requested scenario may still show
clearly labeled illustrative components.
