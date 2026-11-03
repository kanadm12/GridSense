# Prompt 17 metering, coverage, and migration compatibility

**Status:** PARTIAL implementation; authoritative metering interpretation BLOCKED\
**Review date:** 31 October 2026\
**Base Git revision:** `d789f9814da9955db1c63ced921a95379dd08495`\
**Commit status:** no commit or push; working-tree changes remain uncommitted

## Scope and implementation result

This note records the Prompt 17 changes and limits. It does not declare NEM12
semantics, real household savings, or customer tariff costs verified.

| Area | Status | Implemented behavior | Remaining limit |
|---|---|---|---|
| Raw reading metadata | **PARTIAL** | Nullable source value/unit, provenance, source time basis, IntervalDate/index, NMI configuration, and 300 summary method are retained. Meter stores RegisterID, NMISuffix, and MDMDataStreamIdentifier separately. | Upload/file digest and governing MDFF revision are not linked to each reading. Existing rows are not backfilled. |
| NEM12 parser and upload | **PARTIAL** | MDFF v2.7 nominal interval-end indexing and record layouts are verified; timestamps are stored as naive nominal end candidates with `unverified_nem12_clock_basis`. Direction remains `unknown`; unsupported UOMs remain preserved but ineligible. | NMI Procedure, Metrology Procedure Part B and source-specific semantics remain blocked. No NEM12 import/export mapping or UTC normalization is enabled. |
| Direction eligibility | **VERIFIED locally** | Import/export metrics require explicit direction. `direction IS NULL AND register_type == "B"` returns `legacy_direction_unverified` from the quality service and is excluded from SQL consumption filters. | Whether any register or suffix means import/export remains **BLOCKED** pending authoritative AEMO evidence. |
| Quality eligibility | **PARTIAL** | Headline actual import/export requires quality A, supported energy units, eligible provenance, nonnegative value, recognized timestamp basis, and a unique UTC interval slot. Non-A rows remain stored and counted where the time basis is placeable. | This is a conservative product policy, not an authoritative interpretation that estimated/substituted quality codes are invalid. |
| Coverage and DST | **VERIFIED locally** | Coverage is eligible slots / expected local-civil-day slots. Tests cover 24/48 partial coverage and 46/48/50 half-hour Melbourne days. Missing intervals are not zero energy. Duplicate same-direction slots are suppressed and counted. | Current API date windows are whole local dates; arbitrary partial clock-time windows are not exposed. |
| Demand | **VERIFIED locally** | Observed interval-average demand = eligible energy / eligible interval-hours. Observed interval-average peak = maximum interval energy × 60 / interval minutes. Full-period average is withheld unless eligible coverage is complete. | This is not instantaneous demand. Meter data alone does not establish gross household load or PV generation. |
| Usage API and mobile | **PARTIAL** | Additive response fields expose eligible imported/exported energy, coverage/exclusion counts, status/explanation, provenance, and demand. Mobile screens distinguish observed eligible energy, partial coverage, unavailable values, and synthetic demo values. | UI type-check is executed; no device-level visual/accessibility or production API migration test was executed. |
| Billing compatibility | **PARTIAL** | Billing now uses explicit direction and interval eligibility, distinguishes import/export channels at one timestamp, and counts exclusions/duplicates. Existing response contract remains additive. | Tariffs are not immutable customer-confirmed versions. No-tariff/preset outcomes remain explicitly illustrative and do not validate household costs. |
| Forecast/anomaly filters | **PARTIAL** | Measured import filters require explicit import, quality A, measured provenance, supported energy units, recognized timestamp basis, and nonnegative values. | Chronological feature availability and complete-day target coverage remain separate acceptance work. |
| Database migration | **VERIFIED locally** | Additive migrations add nullable provenance and NEM12 source-coordinate/channel fields only when absent. They do not rewrite timestamps, infer direction, or backfill old rows. SQLite tests and a disposable PostgreSQL upgrade/downgrade/re-upgrade cycle pass. | No production database, backup/recovery, or live service integration was tested. |
| MDFF v2.7 format clauses | **VERIFIED for cited clauses** | Official final MDFF v2.7 PDF, effective 1 December 2025, inspected at §§3.3.2–3.3.3, 4.3–4.5, Apps B–E. See `AEMO_NEM12_COMPLIANCE_MATRIX.md`. | Does not establish related procedure semantics or governing revision for historical uploads. |
| Source clock and direction | **BLOCKED** | MDFF defines nominal interval index/end coordinates and channel metadata but not UTC/DST realization or a universal import/export mapping. | Obtain applicable NMI Procedure and source-specific MSATS/meter configuration before UTC normalization or direction assignment. |
| Quality-event handling | **VERIFIED locally for MDFF v2.7 record shape** | 300 `V` is resolved only from complete ordered non-overlapping 400 ranges; invalid or incomplete event sets leave per-interval quality unresolved. A/E/F/S/V and reason-field constraints are checked structurally. | Method flag number meaning depends on Metrology Procedure Part B §2.6. Historical reason-code validity depends on source revision. |

## Data eligibility and failure behavior

### Consumption and export

The local headline policy requires all of:

1. `direction` is explicitly `import` for consumption or `export` for export.
2. Quality is `A` under the conservative headline-observation policy.
3. Source unit is `kWh` or `Wh`; parser-normalized `Reading.value` is kWh.
   `Wh` input is divided by 1000, while `source_value` and `source_unit` retain
   the original quantity/unit. Unsupported units are preserved but ineligible.
4. Provenance is `measured` or explicitly `synthetic`; synthetic outputs are
   labeled illustrative and are not customer observations.
5. Timestamp basis is explicit and recognized by the normalizer; the interval
   duration is positive and the value is finite and nonnegative.
6. There is only one record for that UTC end slot and direction. Same-time
   import and export are separate channels, not duplicates; a repeated
   same-direction slot is not summed.

Unknown direction and legacy null/B are not imports. Missing, unresolved, or
unsupported source time basis prevents UTC normalization. In those cases, keep
the raw reading, report unavailable status/explanation, and do not produce a
validated energy total from it. Non-A values are retained and counted rather
than silently deleted or reclassified.

### Coverage and demand

For each complete local civil date, the expected denominator is the UTC
duration between local midnight and the next local midnight divided by the
meter interval. Thus a Melbourne half-hour day expects 46, 48, or 50 UTC slots
around DST transitions. A subset of 24 eligible intervals on a 48-slot date
has 50% coverage and is displayed only as **observed eligible energy**.
Missing slots are never imputed as zero. Daily averages and comparisons use
complete eligible days; observed-interval average and interval-average peak
remain separately labeled and are not presented as full-period or
instantaneous demand.

## Legacy compatibility

- The previous `direction IS NULL AND register_type == "B"` SQL eligibility
  path has been removed. No register-type or suffix inference replaces it.
- Legacy null/B rows are preserved for audit. The shared validator names their
  reason `legacy_direction_unverified` when their timestamps are normalizable.
- A legacy row with no source time basis cannot be assigned to a requested
  local date. Its UTC-dependent metric remains unavailable; do not claim a
  date-scoped legacy count that the source timestamp cannot support.
- Existing upload, billing response shape, synthetic-demo pathways, and
  scheduling contracts are retained. A manually explicit synthetic path is
  required for demo data; synthetic values are never presented as measured.
- The schema migration is additive. Null fields on historical records mean
  unknown provenance/time basis, not permission to derive defaults from
  register, suffix, meter interval, or current parser assumptions.

## AEMO verification blockers

The official MDFF v2.7 document has been retrieved. The following related
authoritative details remain blocked:

1. NMI Procedure v7.4 was user-cited but not retrieved; its effective dates,
   any later revision, suffix/register semantics, and source applicability are
   unverified.
2. Metrology Procedure Part B was not retrieved; method-flag number mappings
   and detailed substitution/estimation semantics remain unverified.
3. MDFF v2.7 §§3.3.2–3.3.3 verify nominal interval end positions relative to
   IntervalDate, but source clock basis, UTC offset, DST realization, and
   repeated/nonexistent clock behavior remain unverified.
4. The MDFF 200 record identifies channels but supplies no universal
   import/export mapping. Source-specific NMI/MSATS meter configuration and
   direction evidence remain required.
5. NEM12 record 100 does not encode the MDFF revision. Existing uploaded
   periods before 1 December 2025 cannot be assumed to use v2.7.

The official metering-procedures page returned HTTP 403 in the web fetch; a
direct browser-style request returned an AEMO Cloudflare challenge. No
related-procedure versions/effective dates are asserted. See
[`AEMO_NEM12_COMPLIANCE_MATRIX.md`](AEMO_NEM12_COMPLIANCE_MATRIX.md) for the
source table and exact blockers.

## Prompt 17 acceptance status

| Acceptance area | Result | Evidence / blocker |
|---|---|---|
| Exclude unknown direction and legacy null/B | **PASS locally** | Shared service, SQL filter, billing, upload, and explicit tests. Source mapping remains blocked. |
| Retain unsupported units and raw metadata | **PASS locally** | Parser and unit tests retain raw unit/value; validator excludes unsupported units. Per-reading source-file/version linkage remains partial. |
| Retain MDFF channel/source coordinates | **PASS locally** | Versioned fixture and importer integration tests retain source date/index/configuration and MDM stream identifier; directions remain unknown. |
| Resolve record 400 mixed quality | **PASS locally** | Complete v2.7 event ranges map by 1-based position; missing, overlapping, out-of-order, or incomplete coverage leaves quality U. |
| MDFF v2.7 source interpretation | **PARTIAL** | Format-level sections/pages are documented and implemented. Governing version for pre-effective historical data is unknown. |
| Coverage counts and partial-day behavior | **PASS locally** | Versioned fixture and tests cover missing, 24/48, non-A, unresolved direction, invalid unit, duplicate, zero-energy interval. |
| Melbourne DST 46/48/50 | **PASS locally** | Parametrized tests use actual local-day UTC duration. |
| Demand labels and complete-period average | **PASS locally** | Tests distinguish observed interval-average peak from instantaneous peak; full-period mean withheld for partial coverage. |
| API/mobile compatibility | **PARTIAL** | Existing backend regression tests and mobile TypeScript check run; mobile UI was not validated on physical devices. |
| Upload, billing, synthetic demo | **PARTIAL** | Full backend suite is recorded in `BASELINE_VERIFICATION.md`; customer-specific costs remain unsupported without verified tariff/meter evidence. |
| NMI/Metrology procedures and customer direction | **BLOCKED** | Procedure page blocked; time basis, DST, method flag meanings, applicable versions, and source-specific import/export evidence remain unverified. |

## Related implementation and tests

- `backend/app/services/interval_quality.py`
- `backend/app/models/reading.py`
- `backend/app/services/nem12_parser.py`
- `backend/app/services/nem12_importer.py`
- `backend/alembic/versions/b8c9d0e1f2_add_nem12_source_coordinates.py`
- `backend/app/services/usage_analyzer.py`
- `backend/app/api/billing.py`
- `backend/app/schemas/usage.py`
- `backend/alembic/versions/a7b8c9d0e1f2_add_interval_provenance.py`
- `backend/tests/test_interval_quality.py`
- `backend/tests/fixtures/metering/prompt17_interval_quality_v1.json`
- `backend/tests/fixtures/metering/aemo_mdff_v2_7_interval_records.json`
- `backend/tests/test_nem12_parser.py`
- `mobile/services/api.ts`
- `mobile/app/(tabs)/index.tsx`
- `mobile/app/(tabs)/usage.tsx`

## Prompt 17B final verification

The full backend suite passed: **217 passed, 11 warnings**. The mobile
TypeScript check passed. Focused Ruff checks on the NEM12 parser, importer,
and related tests passed. A broader selected-file Ruff check found five
unchanged adjacent issues (an unused import, a type-checking import-order
finding, and three long lines); they were not altered as unrelated cleanup.

The new migration chain was applied to a disposable PostgreSQL 16 database,
downgraded from `b8c9d0e1f2` to `a7b8c9d0e1f2`, then upgraded again to
`b8c9d0e1f2`. All steps passed. The temporary named container was stopped and
removed. This validates migration mechanics only; it is not evidence of
production PostgreSQL integration.

Real-customer NEM12 consumption remains **BLOCKED** pending authoritative
source-time and import/export direction evidence. No historical direction or
timestamp was inferred. The exact test commands, warning summary, and source
access limitations are recorded in the root `BASELINE_VERIFICATION.md`.
