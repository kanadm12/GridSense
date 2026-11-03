# External data integration design

**Review date:** 31 October 2026
**Implementation status:** Open-Meteo weather context is integrated
conditionally through its paid customer endpoint. AEMO market data remains
blocked and is not fetched. Other providers are not integrated unless
explicitly noted. No market/metering rule is inferred where authoritative
source details could not be checked.

## Design principles

1. Provider adapters normalize external records but do not decide whether a
   customer metric is eligible.
2. Persist source, schema/version, retrieval time, source-valid time, issue
   time, unit, location/region, and transformation provenance.
3. Network code is isolated from deterministic domain calculations. Unit tests
   use saved fixtures or a mocked transport, never live provider calls.
4. Provider outage, invalid response, stale data, quota exhaustion, and
   licensing restriction have distinct statuses.
5. Do not place household identifiers or API secrets in provider query strings,
   user-visible errors, metrics, or logs unless the provider contract requires
   them and the privacy design approves it.
6. Cache only as allowed by provider terms; expose cache age and freshness.
7. Preserve upstream values and normalized values separately where licensing
   permits retention.

## Candidate canonical records

These are logical contracts, not a directive to add tables before inspecting
existing persistence needs.

### Provider fetch run

`provider`, `resource_kind`, `request_window`, `retrieved_at`,
`provider_status`, `http_status` (if safe), `source_version`,
`error_category`, `retry_count`, `cache_age_seconds`, and non-secret
correlation ID.

### Time-series datum

`provider`, `source_record_id`, `provenance_kind`, `unit`,
`value_original`, `unit_original`, `value_normalized`, `interval_start_utc`,
`interval_end_utc`, `observed_at_utc`, `issued_at_utc`,
`target_start_utc`, `target_end_utc`, `retrieved_at_utc`,
`region/location`, `quality/status`, `schema_version`, `attribution`.

### Tariff reference

Separate public plan reference from customer-confirmed tariff:

- Public catalog: provider plan ID, source version, retrieved/published time,
  availability geography, terms, rate components, source URL, and license.
- Customer tariff revision: immutable user-entered/confirmed terms, effective
  dates as explicitly provided, confirmation actor/time, source bill/account
  evidence reference (not a copy of unnecessary personal data), and fields the
  product can/cannot model.

No public plan is attached as an active customer contract until the user
confirms applicability. Historical contract periods are unknown unless
separately evidenced.

## Provider findings and decisions

### AER Energy Product Reference Data

**Status: TECHNICAL INTERFACE VERIFIED; read-only adapter implemented.
Redistribution/reuse terms remain unverified for production.**

Official sources were retrieved on 31 October 2026. A browser fetch timed out,
but a direct HTTP GET of the AER page succeeded. The evidence and section-level
implementation map are recorded in
[`AER_PRODUCT_REFERENCE_DATA.md`](AER_PRODUCT_REFERENCE_DATA.md).

- AER's [Energy Product Reference Data](https://www.aer.gov.au/energy-product-reference-data)
  page says the Generic Plans and Generic Plan Detail APIs are public and do
  not require accreditation. The list is per retailer; detail is one plan.
  The published data is the generic reference data used by Energy Made Easy
  and Victoria Energy Compare, and includes geography, rates/charges, terms,
  incentives, fees and eligibility. The page says the endpoints provide
  current plans for jurisdictions using the National Energy Customer
  Framework; it does not expose historical or future plans.
- The [Consumer Data Standards](https://consumerdatastandardsaustralia.github.io/standards/)
  page identifies version 1.36.0. `Get Generic Plans` is endpoint v1 and
  `Get Generic Plan Detail` is endpoint v3. Each request uses its own `x-v`
  and optional `x-min-v`; the implementation sends `1` for the list and `3`
  for detail. The list is requested with `type=ALL`, `fuelType=ELECTRICITY`,
  `effective=CURRENT`, retailer `brand`, `page-size=1000`, and page number.
- AER's plan guidance documents a default page size of 25 and maximum of 1000.
  The fetched AER page did not publish a numeric per-minute request quota; the
  adapter bounds page fan-out, limits local requests to five per minute per
  client IP, times out provider calls, and handles HTTP 429/`Retry-After`
  without retrying automatically.
- Retailer URI mappings are bundled as a January 2026 source snapshot from
  AER's [Energy Retailer Base URIs and CDR Brands](https://www.aer.gov.au/documents/consumer-data-right-energy-retailer-base-uris-and-cdr-brands)
  document, whose change log records an update on 15 January 2026. This is a
  versioned snapshot, not an automatically refreshed source; it must be
  reviewed against AER's current document before deployment and periodically
  thereafter.
- Availability is checked against the selected Victorian postcode using the
  CDR `EnergyPlan.geography` rules. An absent `geography` means unrestricted;
  an absent `includedPostcodes` means all non-excluded postcodes; explicit
  postcode ranges are inclusive and excluded postcodes take precedence.
- List and detail data are fetched live, returned with source plan ID,
  `lastUpdated`, retrieval timestamp, endpoint version and AER source
  attribution. Provider responses are not persisted or cached. The UI labels
  them generic reference data and offers no activation path. It requires the
  user to compare the displayed terms with their own retailer evidence and
  enter/confirm a separate customer tariff revision.
- The AER page and standards reviewed did not establish an explicit
  redistribution licence, attribution wording, or cache/retention permission.
  The transient/no-cache implementation minimizes retained data but does not
  resolve deployment rights. Production redistribution remains **BLOCKED**
  pending confirmation from AER/DEECA or legal review. Do not retain a generic
  plan as customer evidence or apply it to a bill.

### Open-Meteo

**Status: PARTIAL — documented paid-endpoint adapter implemented; no live
provider account/key was available for smoke verification.**

Official pages accessed:

- <https://open-meteo.com/en/docs>
- <https://open-meteo.com/en/terms>
- <https://open-meteo.com/en/pricing>
- <https://open-meteo.com/en/licence>

The [source matrix](EXTERNAL_PROVIDER_SOURCE_MATRIX.md) records the source
pages, the Forecast API v1 endpoint contract, selected fields and units,
license/attribution, pricing evidence, and implementation mapping. The current
docs identify instantaneous 2 m temperature, apparent temperature, humidity
and cloud-cover values, and preceding-hour-mean shortwave radiation. The
selected API schema does not provide an authoritative forecast issue/run time.
Model selection `best_match` does not identify a resolved numerical model or
run.

Implementation decisions:

- The adapter calls only `customer-api.open-meteo.com/v1/forecast` and requires
  an operator-provided `OPEN_METEO_API_KEY`. It does not fall back to the free
  endpoint. Production requires an active subscription/license appropriate
  for the intended use and call volume.
- The request fixes the five documented variables, Celsius, UTC, a three-day
  horizon, and `best_match`. Offset-free target labels are treated as UTC only
  because the request explicitly asks for `timezone=UTC`. Weather is converted
  to `Australia/Melbourne` for display.
- Retrieval time and target time are preserved separately;
  `forecast_issued_at` is null. Do not treat retrieved forecasts as a
  historical decision-time snapshot or as a validated feature for
  backtesting.
- Normalized data and source/normalized unit metadata are persisted for cache
  and audit behavior. Cache TTL defaults to 3600 seconds as a configurable
  GridSense policy, not a provider guarantee. No deletion/retention policy is
  configured; establish one before production.
- The mobile display links to Open-Meteo and CC BY 4.0 and discloses that
  units/timestamps are normalized. The source matrix includes the observed
  terms and attribution requirements; recheck current terms and plan before
  deployment.
- Weather is a candidate feature only. It does not establish improved demand
  forecasts until evaluated chronologically against persistence and seasonal
  baselines.
- Outage or stale cache yields weather `stale`/`unavailable`; no-key and
  unauthorized states are explicit. Existing meter analytics, tariff
  calculations and scheduling continue without weather.

### AEMO NEMWeb and market information

**Status: BLOCKED — no market adapter implemented.**

Official pages attempted:

- <https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/market-data>
- <https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/market-data-nemweb>
- <https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/market-operations/settlements-and-metering/metering-procedures-guidelines-and-processes>

The AEMO guidance requests returned HTTP 403. The public
[NEMWeb DispatchIS directory](https://nemweb.com.au/Reports/Current/DispatchIS_Reports/)
was reachable and listed timestamped `PUBLIC_DISPATCHIS_*.zip` files, but no
archive schema or data values were used to infer a feed contract. Exact
feed/API semantics, update cadence and rights are not verified.

The authenticated context API returns a blocked status with null region,
price and demand fields. No market records are fetched or stored. Before
implementation, verify authoritative source schema, VIC region, dispatch vs
pre-dispatch, AUD/MWh and interval semantics, price status/revisions,
operational-demand units/intervals, issue/target times, publication cadence,
and data-use/storage/attribution rights. Do not use wholesale prices as
customer tariffs or household savings.

#### Prompt 17B metering-standard verification

The official [MDFF NEM12/NEM13 v2.7 specification](https://www.aemo.com.au/-/media/files/electricity/nem/retail_and_metering/market_settlement_and_transfer_solutions/2025/mdff-specification-nem12-nem13-v27.pdf)
was retrieved and inspected. Its title page states effective 1 December 2025.
Sections 3.3.2–3.3.3, 4.3–4.5, and Appendices B–E support implementation of
the nominal interval-end index, record/channel field preservation, per-value
quality events, and unit handling. See
[`AEMO_NEM12_COMPLIANCE_MATRIX.md`](AEMO_NEM12_COMPLIANCE_MATRIX.md) for page
references and the implementation crosswalk.

The official metering-procedures page still returns HTTP 403/Cloudflare
challenge. NMI Procedure v7.4, Metrology Procedure Part B, their effective
dates, and any source-specific requirements were not retrievable or
independently verified. MDFF v2.7 does not establish NEM12 UTC offset/DST
realization or universal import/export mapping. NEM12 UTC normalization,
suffix/register direction inference, and customer consumption claims remain
blocked. The NEM12 100 record does not identify which MDFF revision governed a
historical upload; do not apply v2.7 retroactively.

**Strict price separation:** AEMO market values are wholesale market context.
They must remain typed/labeled as wholesale, with source unit (for example
AUD/MWh only if confirmed from the applicable feed). They must not be passed
to the retail tariff calculator, shown as a household price, or used to claim
bill savings. Any future mapping requires the user's actual applicable retail
plan and explicit model of the retailer's pass-through/markup/fees.

### Amber or other customer-authorized retailer API

**Status: BLOCKED pending provider-contract review; not implemented.**

No endpoint, scope, auth pattern, rate limit, terms, data retention rule, or
consent flow is asserted. Before implementation, verify the current official
developer docs, customer authorization, token refresh/revocation, account and
meter linkage, dynamic retail price semantics, units/timezone/interval,
historical access, allowed caching, and commercial use. Keep this optional;
manual confirmed flat/TOU tariffs remain a distinct path.

### Consumer Data Right energy data

**Status: NOT IMPLEMENTED / BLOCKED for later legal and eligibility review.**

This is not treated as an unauthenticated public API. Before design or
implementation, determine provider/recipient eligibility, accreditation,
consent scope and expiry, revocation propagation, data minimization, security
assessment, access logs, retention/deletion obligations, exact standards and
test environment. Do not collect customer energy credentials in GridSense.

## Adapter failure contract

Each adapter must classify at least:

- `success_fresh`
- `success_cached`
- `stale_cache`
- `rate_limited`
- `unauthorized`
- `invalid_payload`
- `provider_unavailable`
- `timeout`
- `license_or_configuration_blocked`
- `not_configured`

Retries are bounded and apply only to retryable failures. Exact timeouts,
backoff, polling, and cache TTLs are provider-specific and must be derived from
verified terms and product freshness requirements—not guessed in this spec.
Failure of a provider does not block unrelated meter analytics.
