# Prompt 19 — Acceptance Report

**Review date:** 31 October 2026\
**Base revision:** `d789f9814da9955db1c63ced921a95379dd08495`\
**Pre-change status:** Existing Prompt 17/17B/18 worktree changes and untracked
Stage 1 documents, fixtures and Graphify outputs were present and preserved.
No commit or push was made.

## Provider status

| Provider | Status | Evidence and limitation |
|---|---|---|
| Open-Meteo Forecast API | **PARTIAL** | Current official docs, terms, pricing and CC BY 4.0 license were retrieved and mapped. Typed paid-endpoint adapter, normalized weather data, persistence/cache, API and mobile display are implemented. No paid key/account was available for live provider validation. Forecast issue time and exact resolved `best_match` model are not supplied by the selected response contract. |
| AEMO NEMWeb/Victorian market | **BLOCKED** | Public DispatchIS directory listing is accessible, but AEMO market-data guidance returned 403 and archive/schema/rights could not be verified. No market data client/parser was implemented. API and mobile return a blocked status with all market values null. |

## Acceptance matrix

| Prompt 19 area | Status | Evidence / remaining limit |
|---|---|---|
| A — baseline and compatibility | **PASS** | Recorded base revision and pre-change worktree. Baseline full backend suite: 234 passed, 12 warnings, exit 0; a Windows SQLite access-violation diagnostic appeared during the run despite successful pytest completion. Baseline mobile TypeScript passed. Existing meter, tariff, demo and scheduling behavior was preserved. |
| B — shared external-data contracts | **PARTIAL** | Shared provider/data-kind/status/freshness contracts plus typed weather time/unit/location/attribution/source metadata. Provider-specific metadata remains extensible. AEMO data contracts are intentionally not invented. |
| C — Open-Meteo | **PARTIAL** | Forecast API v1 docs, selected fields, units, shortwave preceding-hour semantics, terms and attribution verified. Adapter requires the paid customer endpoint key, stores retrieval time and target time, preserves original/normalized units, and leaves forecast issue time null. Live call and active subscription are unverified. |
| D — AEMO | **BLOCKED** | Feed listing observed, but documentation, record schema, region code, price/demand units, issue/revision timing and data-use rights remain unresolved. No price or demand values are returned. |
| E — persistence, cache and background updates | **PARTIAL** | New provider run and hourly forecast tables; cache keyed by rounded coordinate hash; TTL is configurable (default 3600 seconds); at most one retry on timeout/5xx; no retry on 429. On-demand operation needs no Redis/RQ. No automated retention purge is configured and production retention requires policy. No background polling was added. |
| F — APIs/mobile | **PARTIAL** | Authenticated weather summary/hourly endpoints, provider availability endpoint, blocked market summary, and dashboard Weather & Grid Context card. The UI shows forecast status, retrieval time in Melbourne local time, Open-Meteo attribution, no-key/outage states, and a clear wholesale-versus-retail distinction. No live market values are available. |
| G — forecasting research | **PARTIAL** | Forecast retrievals persist their retrieval timestamp and target time; issue time is null and explicit. This is not sufficient to claim historical decision-time availability or weather-enhanced accuracy. No future-realized forecast is labelled as an earlier-issued one. |
| H — tests | **PASS locally** | Fixed Open-Meteo fixture and mocked HTTP transport cover units, malformed/schema changes, duplicate times, timeouts, 401/403/429/5xx, retries, stale/fresh cache, revised runs, authenticated API response shape and blocked AEMO values. |

## Safety and product boundaries

- Weather is optional context. Provider failure leaves meter analytics, tariff
  calculations, and advisory scheduling independent.
- The free Open-Meteo endpoint is never called. Live weather remains
  unavailable until a correctly licensed paid key is configured.
- The selected Open-Meteo response has no verified forecast issue time.
  `forecast_issued_at` is null; retrieval time is not misrepresented as issue
  time.
- AEMO wholesale market values are not substituted for customer tariffs and
  cannot enter a household bill or savings calculation.
- No AEMO data is persisted because its schema and rights are not yet verified.
- No automatic weather polling or unsupported retention period is configured.
- The mobile client stores only the manually entered, two-decimal location
  locally. The API persists a hash of the rounded location key, not raw
  coordinates.

## Source matrix

See [`EXTERNAL_PROVIDER_SOURCE_MATRIX.md`](EXTERNAL_PROVIDER_SOURCE_MATRIX.md)
for exact source URLs, dates, terms, parameter/field decisions, and blockers.

## Final validation record

| Validation | Command | Result |
|---|---|---|
| Baseline backend tests before code changes | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest -q` | **PASS — 234 passed, 12 warnings.** Exit 0; transient Windows SQLite access-violation output was printed during this run. |
| Baseline mobile types | From `mobile/`: `npx tsc --noEmit` | **PASS — exit 0.** |
| Provider and migration tests | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest tests\\test_external_data.py tests\\test_migrations.py -q` | **PASS — 22 passed, 8 dependency deprecation warnings.** |
| Full backend suite | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest -q` | **PASS — 255 passed, 12 warnings, 94.51 s, exit 0.** Windows printed intermittent SQLite native access-violation diagnostics during teardown; pytest completed successfully with all tests passing. |
| Focused Ruff | Changed Prompt 19 backend files | **PASS — no findings.** |
| Mobile TypeScript | From `mobile/`: `npx tsc --noEmit` | **PASS — exit 0.** |
| Disposable PostgreSQL migration cycle | PostgreSQL 16 isolated container; upgrade to `d1e2f3a4b5c6`, downgrade to `c9d0e1f2a3b4`, re-upgrade | **PASS — final revision `d1e2f3a4b5c6`.** Temporary validation container was removed; existing user containers were not touched. |
| `git diff --check` | Repository root | **PASS — exit 0.** Git printed line-ending normalization warnings for existing modified files. |

## Overall disposition

**PARTIAL.** Weather integration is implemented behind a paid key and with
explicit retrieval-time/freshness limitations. AEMO market-data integration
remains **BLOCKED** until the official feed schema and use rights are verified.
Neither provider is used to modify tariffs or claim household savings.
