# Recommendation evidence contract

**Status:** partially implemented by Prompt 20 and extended for scheduling by
Prompt 21. Recommendation and scheduling evidence are generated in API
responses and are not durably persisted.

## Current implementation boundary

The recommendation API now returns a versioned evidence object with owner and
meter IDs, an analysis date window, hashed reading-set reference, provenance
counts, coverage and eligibility checks, rule/method versions, scenarios,
calculated usage-pattern values, assumptions, limitations, and a one-hour
expiry. It does not duplicate raw readings. Evidence is rebuilt for each API
request, so corrected or deleted source data are reflected on the next
evaluation. No historical evidence archive, immutable audit record, deletion
workflow, or durable expiry job exists yet; consumers must not treat a prior
response as a current opportunity after its expiry.

Current customer recommendation rules are unquantified observations and
data-quality actions. They do not calculate household cost or energy savings.
No tariff revision is attached to these observations because no tariff
counterfactual is modeled. Synthetic inputs are labeled illustrative.

The scheduling preview now returns a response-scoped extension of this
contract. It binds a canonical request digest and task-set digest to the owned
meter, immutable tariff revision (when used), baseline classification,
formula version, scenario values, expiry, assumptions, and limitations. It
does not copy raw meter readings. A client-supplied `independently_measured`
label is not proof: because no server-verified submeter or validated
disaggregation source is integrated, that path returns unavailable and no
costed plan. The synthetic pathway remains illustrative. The existing
optimizer's preferred, deterministic-greedy, and MILP scenarios are compared
without treating a MILP optimum as proof of advantage over greedy.

Evidence remains response-scoped because durable replay retention, evidence
ownership lifecycle, deletion, invalidation, and expiry-job requirements have
not been agreed. The request digest and tariff revision reference support
integrity checks while the original request is available; they do not
constitute a historical archive or guarantee replay after source changes.

## Required recommendation object

Every recommendation returned or persisted must contain the following logical
fields. Persistence shape is deliberately not prescribed until existing
retention and migration requirements are reviewed.

| Field | Requirement |
|---|---|
| `recommendation_id`, `schema_version` | Stable identity and versioned response contract. |
| `type` | Enumerated class: usage observation, tariff issue, flexible-task shift, forecast caution, or data-quality action. |
| `trigger_rule_id`, `trigger_rule_version` | Deterministic rule that caused the recommendation. |
| `status` | `validated`, `estimated`, `illustrative`, `unquantified`, `unavailable`, `expired`, or `no_supported_action`. |
| `created_at`, `expires_at` | UTC evaluation and expiry. Re-evaluate or withhold after expiry. |
| `subject` | Owned meter and optional tariff revision/task; no cross-user references. |
| `eligibility` | Required checks, pass/fail, thresholds/version, exclusions and human-readable reasons. |
| `input_references` | Stable, privacy-minimized IDs/digests for readings, quality report, tariff revision, forecast run and task input. |
| `explanation` | Plain-language explanation of the observed fact and why the rule fired. |
| `action` | Concrete user action; no implication it was executed. |
| `baseline` | Named comparison scenario and period, including whether it is measured, user-entered, forecast, derived, or synthetic. |
| `outcome` | Nullable amount, unit, formula version, and comparison basis. A value must be reproducible. |
| `inconvenience` | Displacement/time/constraint and optional explicit user penalty; do not represent a penalty as measured comfort. |
| `assumptions`, `limitations` | Complete list of assumptions and unmodeled contract/quality effects material to the result. |
| `confidence` | Evidence/interpretation status, not a probability that savings will occur. |
| `calculation_method` | Deterministic service and formula version; never an LLM-generated amount. |

## Status semantics

- `validated`: required inputs satisfy the named rule; this does not mean
  independently field-validated customer savings.
- `estimated`: a deterministic estimate exists with disclosed assumptions or
  incomplete but permitted inputs.
- `illustrative`: at least one input is synthetic or a hypothetical tariff;
  may be used for demonstration only.
- `unquantified`: rule may justify a non-numeric action, but no defensible
  impact amount is available.
- `unavailable`: prerequisites fail; state the missing/invalid evidence.
- `expired`: previously generated evidence is outside its configured validity
  window and must not be presented as current.
- `no_supported_action`: eligible evidence was evaluated and no safe,
  beneficial action was supported. This is not an error.

## Calculation and comparison rules

1. All energy/money results originate in deterministic calculation services.
2. Store the reference scenario and proposed scenario; comparisons must use
   the same eligible intervals, tariff revision, price source, horizon, and
   calculation version.
3. For scheduling, present preferred-start cost, greedy-reference cost, and
   MILP-proposed cost separately. A difference from the user's preferred
   schedule is not the same as improvement over greedy.
4. Do not call either modeled difference “savings” without qualification. Use
   “modeled energy-charge difference for this scenario” until field evidence
   supports stronger language.
5. If any numeric output cannot be recomputed from referenced inputs and
   formula version within AUD 0.01 after display rounding, reject the numeric
   claim.
6. User-entered appliance power, duration, and flexibility are assumptions,
   not measured device behavior.
7. If tariff is public generic, illustrative, stale, not confirmed, incomplete,
   or outside effective dates, it cannot support a customer-specific monetary
   recommendation.
8. If data are synthetic, recommendation status is `illustrative`, regardless
   of arithmetic accuracy.
9. Missing or poor-quality evidence cannot be repaired by assigning low
   confidence to an otherwise unsupported number; withhold the number.
10. Scheduling energy charges, preference penalties, and omission penalties
    are distinct AUD-valued quantities. Never combine a dimensionless
    preference score with an AUD energy charge.
11. A measured scheduling baseline is eligible only when server-side evidence
    validates that modeled flexible-task load has been excluded. A profile
    assertion, checkbox, aggregate import, net grid energy, or unknown
    direction is not disaggregation evidence.

## Example

> Consider running the declared 2.4 kW task from 06:00 to 07:00 instead of
> 09:00 to 10:00. In this synthetic scenario, its modeled energy charge is
> $0.24 at 06:00 and $0.60 at 09:00 under the configured illustrative rate
> windows. The greedy reference also selects 06:00, so the MILP has no
> additional modeled cost advantage over that reference. The result uses
> user-entered task power and a synthetic baseline; it is not a bill or
> household savings estimate. Nothing is executed.

This is an explanatory example only; do not reuse its numbers as a live
recommendation.

## AI assistant boundary

The assistant may explain a supplied recommendation object, cite its
limitations, or answer questions about the deterministic calculation inputs.
It must not:

- invent, recompute, or modify financial/energy values;
- create a recommendation that is absent from the evidence service;
- turn an illustrative/estimated value into a verified claim;
- state that an appliance was scheduled, controlled, or dispatched unless a
  separate verified execution record exists.

If a question asks where a number came from, return the recorded source
references, calculation version, equation, tariff, interval set, and
assumptions. If any are unavailable, say that the amount cannot be traced and
withhold it.

The current chat endpoint does not receive recommendation evidence. Its model
response is therefore guarded against customer-specific numeric financial or
usage-reduction claims; an unsupported claim is replaced with an explicit
limitation rather than silently edited.
