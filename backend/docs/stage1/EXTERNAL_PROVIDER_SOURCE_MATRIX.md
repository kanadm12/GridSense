# Prompt 19 — External Provider Source Matrix

**Sources checked:** 31 October 2026\
**Repository base revision:** `d789f9814da9955db1c63ced921a95379dd08495`\
**Implementation is additive and remains uncommitted.**

## Provider disposition

| Provider | Status | Verified evidence | Implemented behavior | Remaining limitation |
|---|---|---|---|---|
| Open-Meteo Forecast API | **PARTIAL** | Official hourly-variable, units, paid/free terms, attribution and pricing pages were retrieved. The Forecast API v1 schema supports the selected fields. | Paid-endpoint-only client, typed parsing/unit conversion, retrieval/target-time provenance, SQLite/PostgreSQL-persisted fetch runs and values, cache freshness, stale/unavailable states, read-only context responses, and mobile forecast display. | No paid API key or live account was available for a provider smoke test. The API does not provide an authoritative forecast issue/run timestamp in the selected response contract; model selection `best_match` does not identify a resolved numerical weather model. |
| AEMO NEMWeb dispatch market data | **BLOCKED** | The public `DispatchIS_Reports` directory was reachable and listed `PUBLIC_DISPATCHIS_*.zip` files. AEMO's market-data and NEMWeb guidance pages returned HTTP 403. | No market-price or demand parser/client was enabled. Authenticated API returns a blocked status with no values or unverified region code. The mobile UI explains the blocker and explicitly separates wholesale from retail tariffs. | Feed contents/schema, VIC region identifier, units, interval meaning, dispatch/pre-dispatch distinction, issue/target times, price status/revisions, operational-demand definitions, publication cadence, and data-use/retention/redistribution terms remain unverified. |

## Open-Meteo evidence and implementation crosswalk

| Required interpretation | Source and version | Source wording/behavior observed | Applicability and GridSense implementation |
|---|---|---|---|
| Endpoint family | [Forecast API docs](https://open-meteo.com/en/docs), accessed 31 Oct 2026; endpoint `/v1/forecast` | Hourly forecasts and hourly variables are documented. Documentation does not state a separately numbered documentation revision or effective date. | Adapter uses only `https://customer-api.open-meteo.com/v1/forecast`; free `api.open-meteo.com` is not called. API key is required and sent using the provider's documented `apikey` parameter. |
| Selected variables and units | Same Forecast API docs | `temperature_2m` and `apparent_temperature` are instantaneous temperatures; `relative_humidity_2m` and `cloud_cover` are percentages; `shortwave_radiation` is a preceding-hour mean in W/m². | Requests five variables. Source and normalized units are preserved. °F input is normalized to °C; unsupported units and malformed series are rejected. |
| Forecast horizon and model selection | Same Forecast API docs and [pricing](https://open-meteo.com/en/pricing) page | The docs describe `best_match` as selecting the highest-resolution model for the coordinates. Pricing describes hourly-normalized model output. | Request fixes `models=best_match`, `forecast_days=3`, and hourly resolution. The API response does not establish which exact model/run was selected; the implementation records the requested selection and provider metadata, not a fabricated model identity. |
| Time basis and hourly target | Same Forecast API docs | The request supports an explicit `timezone`; API time values are provided in the selected timezone. Selected docs do not provide a historical decision-time forecast issue timestamp. | Requests `timezone=UTC`; offset-free API labels are interpreted as UTC only under that explicit request. Temperature/humidity/cloud target timestamps are preserved as valid-time instants. The documented shortwave preceding-hour mean is stored with `[target_time - 1 hour, target_time]` and named field scope. Melbourne rendering uses the IANA zone `Australia/Melbourne` in the mobile client. |
| Retrieval versus issue time | Same Forecast API docs and response contract | The response exposes generation-time metadata but no trustworthy forecast issue/run timestamp for the selected endpoint. | `retrieved_at` is set when GridSense receives the response. `forecast_issued_at` remains null and `issue_time_available=false`. Retrieved forecasts are not represented as historical decision-time forecasts. |
| Free versus paid use | [Terms of Use](https://open-meteo.com/en/terms) and [pricing](https://open-meteo.com/en/pricing), accessed 31 Oct 2026 | Free API is limited to non-commercial use and is described as under 10,000 calls/day, 5,000/hour and 600/minute. Commercial products require a subscription; paid API uses `customer-api.open-meteo.com` and a key. The pricing page describes 1M calls/month Standard, 5M Professional and 50M+ Enterprise budgets. | GridSense is configured to call only the paid customer endpoint with `OPEN_METEO_API_KEY`. Without a key, the endpoint returns `provider_not_configured` and does not fall back to the free API. A production subscription must be active and sufficient for actual deployment volume. |
| Data license and attribution | [Open-Meteo license](https://open-meteo.com/en/licence) and terms | API data are offered under CC BY 4.0; the license page requires appropriate credit, a link to Open-Meteo and the license, and disclosure of modifications. | Mobile shows linked Open-Meteo attribution and CC BY 4.0. Unit/time normalization is disclosed. Raw provider payloads are not stored; original unit labels and provider metadata are retained with normalized values. |
| Provider failures and limits | Terms and pricing pages | Free-tier limits and paid monthly call budgets are documented; service availability/accuracy is not guaranteed. | One retry with a short fixed backoff is bounded to timeout/5xx only; 429 is not retried and preserves safe `Retry-After` metadata. The API applies a separate local 15/minute client-IP limit. Cache TTL defaults to 3600 seconds and is operator-configurable; this is a GridSense product policy, not an Open-Meteo guarantee. |
| Forecast retention and research | License and selected API response | CC BY 4.0 allows redistribution/adaptation with attribution. No provider-prescribed GridSense cache TTL or retention period was found in the cited pages. Forecast issue time is unavailable. | Normalized forecast runs are persisted for audit/cache behavior, keyed by rounded coordinates; no automated deletion/retention period is set. Because issue time is absent, these records must not be used as evidence that the forecast was available at an earlier historical decision time. Establish and document a product retention policy before production. |

## AEMO evidence and blocked interpretations

| Required interpretation | Official source checked | Observed evidence | Status / implementation |
|---|---|---|---|
| Public data discovery | [NEMWeb current DispatchIS report directory](https://nemweb.com.au/Reports/Current/DispatchIS_Reports/) | Directory listing contains timestamped `PUBLIC_DISPATCHIS_*.zip` files. This is directory-level evidence only; archive contents were not used to infer a schema. | Partial source discovery. No parser or polling task was enabled. |
| AEMO data specification and market-data guidance | [AEMO market-data page](https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/market-data) and [NEMWeb page](https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/market-data-nemweb) | Both AEMO guidance requests returned HTTP 403 during this review. | Blocked; exact source contract not established. |
| VIC identifier / price units / interval semantics | No retrievable authoritative data dictionary was available in this review. | No source wording or verified record was obtained for `VIC1`, AUD/MWh, five-minute interval boundaries, dispatch price status/revision rules, or demand measurements. | Unknown. API returns `region=null`, `price_aud_mwh=null` and `demand_mw=null`. |
| Dispatch versus pre-dispatch and issue time | No retrievable authoritative feed schema was available. | A file name in a dispatch directory does not establish all field meanings or a decision-time forecast contract. | Unknown. No pre-dispatch or market-price forecast is returned. |
| Rights and storage | AEMO source terms could not be retrieved or independently verified. | No cache, retention, attribution, or redistribution permission is claimed. | **Blocked.** No market data is fetched or stored. |
| Household tariff separation | Stage 1 requirements R-06 and external integration design | Wholesale market data are not customer retail contract evidence. | Market endpoint is a blocked status only. No wholesale value is fed to billing, tariff, recommendation, or scheduling calculations. |

## Operational and privacy behavior

- Weather location is provided manually by the authenticated user; no GPS
  permission or postcode geocoder is used. Values are rounded to two decimal
  places before the provider request, approximately kilometre scale in
  Victoria. The database stores a one-way hash of the rounded coordinate key,
  not clear coordinates.
- Coordinates are sent in the authenticated POST body rather than query
  parameters. Request logging omits weather coordinates. The provider API key
  is server-side only and provider exceptions are mapped to safe error codes.
- Weather retrieval is on demand. It does not depend on Redis/RQ, does not
  enqueue background work, and cannot block meter analytics, billing or
  advisory scheduling when unavailable.
- A configurable freshness cache uses persisted successful forecast runs.
  Stale fallback is permitted only while the paid provider is configured and
  for temporary provider failures; unauthorized or unconfigured responses do
  not reuse cached results.
- No AEMO feed polling, ingestion, cache, or market-data forecast feature is
  implemented.
