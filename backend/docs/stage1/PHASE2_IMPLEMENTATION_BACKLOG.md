# Stage 1 implementation backlog: Prompts 17–21

This sequence follows the data dependency chain. Do not start a later milestone
by assuming an earlier gate passed. No provider integration or schema migration
is authorized by this planning document alone.

## Prompt 17 — NEM12 semantics and quality/coverage foundation

**Goal:** make interval eligibility and coverage explicit and source-grounded.

**Implementation update (31 October 2026): PARTIAL.** The official MDFF
NEM12/NEM13 v2.7 PDF was retrieved; format-level interval indexing,
200-channel metadata, 300 quality flags, 400 event ranges, and unit rules have
been implemented and tested. Additive nullable source-coordinate and channel
fields preserve these records. The official procedures page remains blocked,
so time-zone/DST interpretation, direction mapping, and Metrology Procedure
Part B method semantics are not verified. See
[AEMO_NEM12_COMPLIANCE_MATRIX.md](AEMO_NEM12_COMPLIANCE_MATRIX.md),
[PROMPT17_MIGRATION_COMPATIBILITY.md](PROMPT17_MIGRATION_COMPATIBILITY.md),
and `BASELINE_VERIFICATION.md`.

Tasks:

1. Retrieve NMI Procedure v7.4 and Metrology Procedure Part B from the official
   AEMO metering-procedures page; record verified versions, effective dates,
   and source-period applicability. Determine whether later revisions apply.
2. Verify NEM12 clock, daylight-saving, channel direction, method-flag, and
   source-specific metering rules against the applicable procedures.
3. Establish version provenance for each upload; record 100 does not encode
   the MDFF revision, and v2.7 must not be applied retroactively to earlier data.
4. Replace the unproven historical `direction IS NULL AND register_type == "B"`
   consumption compatibility rule with an explicit, reversible policy.
   Migration may quarantine/report legacy rows; do not relabel based only on
   `B`, suffix, or NMI.
5. Define and implement feature-specific quality eligibility for consumption,
   billing, forecast targets, and measured scheduling baselines.
6. Add UTC-slot coverage accounting and local-day denominators, including DST,
   partial-day, duplicates, and missing-quality counts. If the source clock
   basis is unverified, preserve raw timestamps and withhold UTC-dependent
   metrics rather than applying a guessed conversion.

Acceptance gate:

- Unknown and legacy-unverified direction never appears in validated
  import/export or consumption totals.
- Full-day expected slots are 46/48/50 for Melbourne 30-minute DST/ordinary
  days, and all partial windows use clipped duration.
- A 24-of-48 interval sample reports 50% coverage and cannot be compared as a
  complete day.
- Tests use authoritative, versioned fixtures; no suffix inference without
  cited procedure evidence.

## Prompt 18 — Immutable tariff revisions and AER plan discovery

**Goal:** preserve customer tariff history and separate generic plans from
confirmed contract terms.

Tasks:

1. Design immutable tariff revisions while maintaining compatibility with the
   current single mutable tariff record.
2. Unknown historic contract dates remain unknown; never copy the current rate
   backward.
3. Verify AER official interface, terms, authentication, fields, update and
   caching rules. Endpoint versions/shape are verified and a transient
   read-only adapter exists; redistribution/retention rights remain blocked.
4. Keep public generic plan catalog separate from customer-confirmed revisions.
5. Replace silent default-rate fallback for customer estimates with unavailable
   or explicitly requested illustrative status.

Acceptance gate:

- Each saved tariff revision retains its exact data and effective/user-confirmed
  metadata; a later edit cannot mutate prior version content.
- A plan outside effective dates, lacking a rate, or containing unsupported
  terms never silently produces a full bill.
- No tariff yields no customer-specific tariff estimate.
- Generic plan remains unconfirmed until user review; API tests prove it cannot
  overwrite an existing confirmed revision.

**Implementation note (31 Oct 2026):** tariff revisions and conservative
billing behavior are implemented. AER plan list/detail browsing is available
as reference-only data, with no plan activation or persistence. Production
catalog exposure remains blocked until source-use/redistribution conditions
are confirmed. See `AER_PRODUCT_REFERENCE_DATA.md`,
`PROMPT18_MIGRATION_COMPATIBILITY.md`, and `PROMPT18_ACCEPTANCE.md`.

## Prompt 19 — External weather and AEMO market adapters

**Goal:** add only the external data whose rights, endpoints, timestamps, units,
and outage behavior have been verified.

Tasks:

1. Confirm Open-Meteo commercial plan, attribution, exact endpoint/parameters,
   model variables, call accounting, cache and archived forecast issue-time
   semantics.
2. Retrieve official AEMO market and metering documentation; current pages
   returned HTTP 403. Verify exact feeds, units, region, intervals, revisions,
   licensing and current procedure versions.
3. Build isolated adapters and normalized provider records; do not add live
   calls to domain unit tests.
4. Keep wholesale records in a market-context domain separate from retail
   tariffs, cost calculations and customer recommendations.
5. Add fixture-driven outage, stale cache, quota, invalid payload, and
   unauthorized tests.

Acceptance gate:

- No implementation is merged until official terms and interface fields are
  documented with accessed source/version/date.
- Every returned datum has provider, unit, target/observed/issue/retrieval time
  where applicable and freshness state.
- Wholesale price cannot be consumed by household bill/scheduling API as a
  retail tariff without an explicit separately approved mapping.
- Provider failure does not block meter-only analytics.

## Prompt 20 — Calculation evidence and recommendations

**Goal:** connect every recommendation to deterministic, reproducible evidence.

Tasks:

1. Implement versioned recommendation/evidence contracts with eligibility,
   input references, baseline, formula version, result/unit, assumptions,
   limitations, and expiry.
2. Reuse existing recommendation rules and deterministic billing/scheduling
   services; do not create a second calculation engine.
3. Add explicit no-action/unquantified/unavailable results and confidence
   semantics.
4. Constrain AI explanations to supplied result objects; AI never creates
   numeric impacts or reports dispatch.

Acceptance gate:

- Every numeric recommendation recomputes from referenced input rows to within
  AUD 0.01 after display rounding.
- Missing, expired, illustrative, unresolved, or below-coverage evidence
  cannot produce a customer-specific numeric saving.
- AI output cannot introduce unsupported numeric claims in contract tests.

## Prompt 21 — Validated-data forecasts and advisory scheduling

**Goal:** transition from independent synthetic demo scenarios to an eligible,
traceable baseline and forecast path.

Tasks:

1. Build feature-availability-aware forecasts and compare persistence and
   seasonal baselines with weather-enhanced models using chronological
   validation.
2. Store forecast-run model/version, issue time, target time, inputs and
   uncertainty evaluation.
3. Establish measured non-task demand using a submeter or validated
   disaggregation; never treat raw import/net-meter totals as the scheduler
   baseline without evidence.
4. Record which flexible task loads were removed from the baseline and add them
   exactly once to every schedule scenario.
5. Compare preferred, greedy, and MILP costs with identical tariff, task,
   interval, and baseline inputs. Retain the synthetic-only fallback as
   explicitly illustrative if validated measured baseline is unavailable.

Acceptance gate:

- Feature timestamp is no later than forecast issue time for every prediction.
- Candidate model must meet predeclared baseline-performance and uncertainty
  criteria or forecast-based advice is withheld.
- A known submeter fixture reconciles combined load to baseline plus each task
  exactly once.
- Preferred, greedy, and MILP costs independently recompute within AUD 0.01.
- No claim of MILP superiority absent statistically defensible matched evidence.

## Cross-cutting gate and sequencing

| Order | Milestone | Must precede |
|---|---|---|
| 17 | Source semantics, quality and coverage | Production-facing consumption/billing claims, empirical scheduling baseline |
| 18 | Tariff versioning and AER contract verification | Customer retail cost estimates or tariff-plan recommendations |
| 19 | Provider rights and adapters | Weather-aware forecast or AEMO market feature |
| 20 | Recommendation evidence | Quantified recommendation UI and assistant explanations |
| 21 | Validated forecasts and non-task scheduling baseline | Data-to-schedule pipeline claims |

Security review, PostgreSQL/Redis deployment, durable job recovery, and backup
restore remain separate operational workstreams. They must not be implied by
completion of these Stage 1 product milestones.
