# GridSense Baseline Verification

**Run date:** 31 October 2026 | **Scope:** Prompt 01 in `GridSense_Detailed_Implementation_Prompts.md`
**Purpose:** Record the current reproducible baseline and blockers before feature implementation.

## 0. Final closure status (Prompt 23E-Security, current round)

| Gate | Result |
|---|---|
| Backend suite, restricted PostgreSQL 16 | 389 passed, 0 skipped, exit 0 |
| Ruff 0.16.3 (`alembic app scripts tests`) | Passed |
| actionlint 1.7.7 with ShellCheck | Exit 0 |
| Gitleaks (clean copy, `.gitleaksignore`) | Exit 0; negative controls exit 1 |
| Security gate | Exit 1 (9 unaccepted ChromaDB findings; intended) |
| Source manifest | 321 included / 706 excluded |
| Hosted CI | NOT VERIFIED |
| Windows SQLite native fault | BLOCKED; unsupported |

Figures in sections 2 onward are the original Prompt 01 baseline and are kept for history.

## 1. Observed environment

| Tool/runtime | Observed version/state | Notes |
|---|---|---|
| Python | 3.11.9 | Matches the backend's Python 3.11+ requirement and the checked-in CI target. |
| Node.js | 22.20.0 | Mobile CI targets Node 20; local runtime differs from CI. |
| npm | 11.6.2 | `mobile/package-lock.json` is present and `mobile/node_modules` is installed. |
| Project Python environment | `.venv311` is Python 3.11.9 | Has pytest, Ruff, FastAPI, SQLAlchemy, and Alembic available. Use this environment for backend checks. |
| Default `python` on PATH | Python 3.11.9, but project dependencies absent | `python -m pytest` and `python -m ruff` fail from this interpreter; this is avoidable by selecting `.venv311`. |
| Docker CLI | 29.7.2 | Docker Desktop Linux engine was not running/reachable at verification time. |
| Backend dependency declaration | `backend/pyproject.toml` | Python 3.11+; install with `python -m pip install -e ".[dev]"` from `backend/`. |
| Mobile dependencies | `mobile/package-lock.json` | Install with `npm ci` from `mobile/`. |

No values from `.env` were copied into this report. Configuration keys referenced by the application and example configuration include:

- Core: `DEBUG`, `APP_NAME`, `API_V1_PREFIX`, `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `CORS_ORIGINS`.
- AI: `OPENAI_API_KEY`.
- Email/password reset: `EMAIL_PROVIDER`, `EMAIL_FROM`, `FRONTEND_RESET_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`.
- Automation: `AUTOMATION_PROVIDER`, `HOME_ASSISTANT_URL`, `HOME_ASSISTANT_TOKEN`.
- Mobile API endpoint: `EXPO_PUBLIC_API_URL`.

Secrets such as `SECRET_KEY`, `OPENAI_API_KEY`, SMTP credentials, and the Home Assistant token must be supplied through a local secret/configuration mechanism and must not be committed.

## 2. Verification matrix

Exit codes below are from the final relevant invocation; `0` means the command succeeded.

| Check | Command / setup | Result | Classification |
|---|---|---|---|
| Backend tests | `..\.venv311\Scripts\python.exe -m pytest -q` (run from `backend/`) | **PASS — exit 0; 90 passed, 7 warnings, 37.36 s.** | Pass; warnings include deprecated Pydantic config and Starlette status-code usage. |
| Backend Ruff | `..\.venv311\Scripts\python.exe -m ruff check app tests --statistics` (run from `backend/`) | **FAIL — exit 1; 275 existing lint findings.** | Application/repository quality backlog. Counts: 99 whitespace-only blank lines, 91 long lines, 38 unused imports, 32 unsorted imports, 5 trailing whitespace, 4 unused variables, 3 boolean-comparison findings, 3 non-lowercase local names. |
| Mobile TypeScript | `npx tsc --noEmit` (from `mobile/`) | **PASS — exit 0.** | Pass. |
| Mobile web export | `npx expo export --platform web` (from `mobile/`) | **PASS — exit 0; web bundle exported.** | Pass; creates `mobile/dist/` build output, not a production-device release validation. |
| Expo config | `npx expo config --type public` (from `mobile/`) | **PASS — exit 0.** | Pass; output includes placeholder EAS project ID `your-project-id`. |
| Mobile lint | `npm run lint` (from `mobile/`) | **FAIL — exit 1; `eslint` executable unavailable.** | Missing development tooling/configuration: `eslint` is not declared as a direct dev dependency in `mobile/package.json`. |
| Mobile test script | `npm test -- --runInBand` (from `mobile/`) | **FAIL — exit 1; `jest` executable unavailable.** | Missing development tooling/configuration: Jest is not declared in the mobile package manifest and no mobile test suite was found in the reviewed tree. |
| Alembic clean upgrade | `..\.venv311\Scripts\python.exe -m pytest -q tests\test_migrations.py` (from `backend/`, isolated temporary SQLite database) | **PASS — exit 0; 1 passed.** The regression test upgrades a clean database to head and confirms `meters.is_active` and the expected Alembic revision. | Fixed by making the existing `is_active` migration conditional on the column's presence, covering both metadata-created clean schemas and older schemas. |
| Docker Compose services | `docker compose ps` / `docker ps` | **FAIL — Docker API unavailable; Docker Desktop Linux engine pipe not found.** | Environment restriction; PostgreSQL, Redis, API, worker, and scheduler could not be started in containers. |
| API smoke flow | Isolated FastAPI `TestClient` + temporary SQLite database created from current SQLAlchemy model metadata; sample NEM12 file | **PASS — exit 0.** `health/live` 200; `health/ready` 200/ready; register 201; login, `/auth/me`, upload, upload status, meters, usage summary, and billing comparison all 200. Upload completed and imported 336 readings. | Pass with scope limitation: uses ORM `Base.metadata.create_all`, not the failing Alembic chain and not PostgreSQL/Redis. |

The `pytest` and Ruff commands were first attempted with the system Python, which did not contain those packages. They were then run with the repository's `.venv311`, where pytest passed and Ruff reported the findings above. No dependencies were installed or manifests changed during this baseline.

## 3. Migration blocker details and resolution

The migration failure is reproducible on a brand-new temporary SQLite database:

1. `0001_initial_schema` uses `Base.metadata.create_all()`. The current `Meter` model already contains `is_active`, so the initial schema includes the column.
2. `0002_schedule_execution` adds `device_schedules.last_executed_at`.
3. `e6f168c90ff8_add_progress_percent_to_uploads.py` drops `device_schedules.last_executed_at`.
4. `a1b2c3d4e5f6_add_is_active_to_meters.py` attempted to add `meters.is_active` again and failed.

The migration now checks the live schema before adding or dropping `is_active`, so it works when the column was created by the metadata-based initial revision and when upgrading an older database that lacks it. `backend/tests/test_migrations.py` runs the full clean SQLite upgrade in a temporary directory, verifies the column, and confirms the head revision. This test passes. The API smoke test still demonstrates a different path (`Base.metadata.create_all`) and is not evidence about PostgreSQL/Redis deployment behavior.

## 4. API smoke-test scope

The smoke check used `backend/tests/sample_nem12.csv` and an isolated temporary database. It covered:

1. `GET /health/live`
2. `GET /health/ready`
3. `POST /api/v1/auth/register`
4. `POST /api/v1/auth/login`
5. `GET /api/v1/auth/me`
6. `POST /api/v1/upload`
7. `GET /api/v1/upload/{upload_id}`
8. `GET /api/v1/meters`
9. `GET /api/v1/usage/summary/{meter_id}` with the sample's explicit April 2025 date range
10. `GET /api/v1/billing/comparison/{meter_id}` for explicit current/previous periods

The sample is historical relative to the run date, so the first smoke attempt using the usage endpoint's default “recent” date window correctly returned no data. Re-running with an explicit range matching the fixture succeeded. This is a test-range correction, not evidence that default usage windows contain historical imports.

## 5. Changed files and reason

- Added this file to preserve baseline evidence before implementation.
- No application source, dependency manifests, migrations, tests, local `.env`, or database files were changed.
- Existing worktree changes and untracked archives were left untouched.

## 6. Reproduction commands

From the repository root in PowerShell:

```powershell
Push-Location backend
& ..\.venv311\Scripts\python.exe -m pytest -q
& ..\.venv311\Scripts\python.exe -m ruff check app tests --statistics
Pop-Location

Push-Location mobile
npx tsc --noEmit
npx expo export --platform web
npm run lint
npm test -- --runInBand
Pop-Location
```

For migration checks, use an isolated database and do not point at a developer's persistent database:

```powershell
$dbPath = Join-Path $env:TEMP ("gridsense-baseline-" + [guid]::NewGuid().ToString("N") + ".db")
$env:DATABASE_URL = "sqlite:///" + $dbPath.Replace("\", "/")
$env:DEBUG = "true"
Push-Location backend
& ..\.venv311\Scripts\python.exe -m alembic upgrade head
Pop-Location
```

The migration currently fails as shown above. Remove the temporary database after use.

## 7. Known limitations and next dependency

- Docker-backed PostgreSQL/Redis startup, worker/scheduler checks, and Compose integration smoke tests remain unverified because Docker Desktop was unavailable.
- The clean SQLite Alembic chain now reaches head; PostgreSQL-specific migration behavior remains unverified because Docker Desktop was unavailable.
- Ruff has a large pre-existing finding set; lint cannot currently be treated as clean.
- Mobile `lint` and `test` scripts refer to tools that are absent from the declared dependencies.
- Local Node 22 differs from the CI Node 20 runtime; the successful TypeScript/web export checks do not prove CI parity.
- The successful API flow used SQLite plus ORM-created tables and a test client; it is not an end-to-end Docker/PostgreSQL/RQ verification.
- Mobile EAS project configuration still has a placeholder project ID.

**Follow-up status:** see Section 8 for the migration repair and NEM12 semantics implementation that followed this baseline.

## 8. Follow-up implementation update — NEM12 and migrations

After the original baseline run, the clean migration failure was fixed and Prompt 02 implementation began:

- The existing `is_active` migration is now conditional on the live schema, and a migration regression test exercises clean upgrade, downgrade, and re-upgrade in temporary SQLite.
- A new migration adds meter `register_id` and reading direction/quality detail fields (`quality_method`, `reason_code`, and `reason_description`).
- NEM12 record 200 channels are keyed by NMI, RegisterID, and NMISuffix. Raw register ID and suffix are stored; each new parsed reading is marked direction `unknown` and legacy `register_type` `U` until direction semantics are verified.
- Record 300 quality methods and reason metadata are retained. Record 400 interval ranges update per-interval quality metadata. Missing interval values are skipped with warnings; shortened records retain trailing quality data when its position is identifiable. Unresolved quality does not default silently to actual.
- Wh energy values are converted to kWh. Other UOMs are preserved on the meter but omitted from kWh analytics with warnings.
- Re-importing the same channel/time intervals through the importer no longer creates duplicate readings. The upload endpoint reads no more than 50 MiB + 1 byte before rejecting oversized input.
- Billing, usage summaries, forecasts, anomaly detection, and daily aggregates only count explicit imports or legacy readings without direction metadata. New unresolved channels are excluded pending classification.

The current AEMO MDFF Specification NEM12 & NEM13 v2.6 (effective 4 November 2024, §4.3–4.5, Appendix C and Appendix G) defines the record fields and quality metadata but does not establish a universal suffix-to-direction mapping in that document. Its Appendix H example is not treated as a general rule. Source: [AEMO MDFF Specification NEM12 & NEM13 v2.6](https://www.aemo.com.au/-/media/files/electricity/nem/retail_and_metering/market_settlement_and_transfer_solutions/2024/mdff-specification-nem12-nem13-v26-clean-final.pdf?la=en).

Focused validation initially exposed two rate-limit tests that accidentally used a persistent database; they are now isolated on an in-memory schema. Final full-suite validation after that fix: **101 tests passed, 10 warnings**. The original 90-test baseline result above predates the new tests and should not be read as a current full-suite result. PostgreSQL behavior remains unverified because Docker Desktop is unavailable.

**Next dependency:** verify suffix/register direction mapping against the separate AEMO NMI Procedure and add import/export reconciliation fixtures before enabling direction-specific billing for NEM12 channels.

## 9. Clock and interval-boundary implementation — Prompt 03

- The NEM12 parser records each reading at the source interval **end**, preserves its naive fixed-market-time timestamp, and now persists the source `interval_minutes` (5, 15, or 30). Interval length is migrated with a backward-compatible 30-minute default for existing rows.
- `Reading.timestamp` remains the preserved source value; its clock basis is interpreted by the NEM12 parser contract rather than duplicated in a per-reading timezone field. The `Meter.state` field selects the local civil timezone.
- Billing date ranges are interpreted in the meter state's local calendar and translated to exclusive/inclusive fixed-market-time bounds. Local tariff periods use the interval **start**, computed from the end instant and stored duration; this fixes boundary cases such as a 30-minute interval ending at 15:00 being priced from its 14:30 start.
- Victorian, NSW/ACT, Queensland, South Australian, Tasmanian, and Northern Territory time zones are explicitly mapped. Local conversions use IANA time-zone data, so Melbourne spring-forward skips the nonexistent hour and the autumn repeated hour is resolved from the unique market-time instant (`fold=1` for the second 02:00).
- Daily summaries assign intervals ending exactly at local midnight to the preceding local day. Hourly/weekly chart buckets use local interval-start boundaries; daily buckets and billing-date filters use interval ends. This keeps boundary inclusion consistent and preserves energy when summing intervals.
- Tests cover both Melbourne DST transitions, 23-/25-hour local days (46/50 half-hour intervals), tariff-boundary classification, a summer import-to-bill example, leap day, parser timestamps, and a clean migration cycle. Final full backend suite: **112 passed, 10 warnings**.

**Clock-basis caveat:** the code's ingestion contract treats NEM12 wall-clock values as fixed UTC+10 market time and converts those instants to meter-local time. The cited MDFF sections directly verify interval-end semantics and the fixed interval sequence, but the authoritative NEM clock-basis reference has not yet been located. Treat this time-basis assumption as pending confirmation; unknown meter states fail explicitly rather than silently defaulting. Direction mapping remains unresolved for the same evidence-based reason described above.

## 10. Tariff and bill reconciliation — Prompt 04

- Extended tariff storage and API schemas with effective dates, GST inclusion, feed-in rates, and custom local-clock tariff windows. Custom windows support selected weekdays and are rejected when invalid or overlapping. Retailer presets are identified as illustrative examples rather than verified current offers.
- Added a reversible Alembic migration for the new tariff fields. The migration-chain regression test covers upgrade to head, downgrade through the tariff and interval/direction changes, and re-upgrade.
- Billing now returns a detailed breakdown for both compared periods: import energy by rate bucket, explicit export feed-in credits, daily supply, an observed-peak-demand estimate where configured, GST treatment, total cost, and counts for expected/observed/missing, unresolved, and unpriced intervals.
- Monetary components are rounded to cents using half-up rounding. GST-inclusive amounts report the included GST as a memo item rather than adding it twice; GST-exclusive configured charges add 10%. The total reconciles to the included line items.
- Effective dates constrain when a tariff is used. If a requested period falls outside the configured range, the calculation uses clearly identified illustrative defaults and reports why. Custom schedule gaps are reported as unpriced rather than silently assigned a rate.
- The mobile bill comparison component now labels estimates, displays line items and limitations, and formats billing dates as local calendar dates rather than UTC-converted dates.
- Validation after Prompt 04: full backend suite **126 passed, 10 warnings**; focused Ruff checks and `git diff --check` passed; mobile TypeScript `tsc --noEmit` passed. The mobile ESLint executable is not installed, so mobile lint was not run.

**Remaining tariff/billing limitations:** tariffs are still stored as one mutable row per user, so changing a tariff overwrites it and does not preserve historical versions. The custom schedule has no public-holiday calendar; default time-of-use buckets use GridSense's schedule, not retailer-specific rules. Preset rates are illustrative. Demand charges estimate from maximum observed interval-average import and may not match a retailer's demand window. Feed-in credits have no separate GST adjustment. Missing readings can understate cost; unresolved-direction and unpriced intervals are explicitly excluded from energy charges and disclosed. Direction mapping and the fixed UTC+10 source clock basis remain pending authoritative AEMO verification as described above.

## 11. Authenticated upload-to-billing vertical slice — Prompt 05

- Added `backend/tests/test_vertical_slice.py`, an isolated API journey test using in-memory SQLite and the local background-task fallback. It covers registration/login, meter creation, NEM12 upload and status polling, tariff setup, usage/billing requests, duplicate-upload handling, malformed-file rejection, and expired access-token refresh. It requires no manual database edits and does not depend on external Redis.
- The test asserts the sample fixture imports 336 readings but does **not** produce classifiable import consumption while direction is unknown. The usage endpoint therefore returns no usage rather than interpreting an unverified NEM12 suffix as import. This is an intentional safety behavior, not a successful consumption-analysis result.
- NEM12 parsing now warns about gaps between daily interval records. Billing comparison preserves missing-coverage status when direction is unresolved and returns an unavailable trend, null percentage changes, and no usage-saving recommendation when neither period has classifiable import readings.
- Mobile session handling clears the session and redirects to sign-in when refresh fails. Meter selection is persisted per user; logout clears meter and usage state. The dashboard mounts the existing bill-comparison component and displays visible usage errors, unavailable comparisons, estimate breakdowns, and an explanation when no usage trend can be calculated. Upload UI surfaces duplicate results, parser errors, and coverage/direction warnings; settings links to tariff setup, whose web flow shows save confirmation and errors.
- Browser acceptance checks exercised registration/login, upload and status, duplicate upload messaging, malformed-file feedback, tariff navigation/save, and authentication recovery. After restarting the local API, the browser was also used to verify the unavailable-usage/trend explanation and the tariff-save confirmation. A dashboard screenshot was captured in the interactive browser session; no screenshot file was added to the repository.
- Latest validation: full backend suite **128 passed, 10 warnings**; focused Ruff checks and `git diff --check` passed; mobile `tsc --noEmit` passed; Expo web export passed. Mobile ESLint remains unavailable because its executable is not installed.

**Remaining Prompt 05 limitation and next dependency:** the demo file is accepted and imported, but its NEM12 register/suffix direction cannot safely be classified without authoritative AEMO NMI Procedure evidence. Therefore a genuine positive-consumption journey, nonzero usage trend, and data-backed bill comparison have not been demonstrated. The dashboard correctly shows usage and trend as unavailable instead of inventing consumption. Verify the direction mapping (and source clock basis noted above) against authoritative references and a representative fixture before relaxing this guard. Docker/PostgreSQL/Redis deployment behavior also remains outside this local verification.

## 12. Recommendation and estimate transparency — Prompt 06

- Removed the recommendation engine's assumed 10 c/kWh savings spread, 25% evening-use target, 30% reducible overnight share, and appliance/solar conclusions inferred from aggregate interval totals. It now reports measured patterns and presents actions as review opportunities, without claiming a particular appliance caused the pattern or can be shifted.
- Recommendation responses now separate observed facts from proposed actions and include the analyzed baseline, assumptions, applicable intervals, uncertainty, interpretation confidence, missing data requirements, estimate status, and tariff provenance. Potential kWh and dollar savings remain null because there is no appliance declaration/demand model or feasible operating-window input.
- A rate spread is returned only for a configured, non-illustrative tariff whose effective dates include today and whose rate data is usable. Flat tariffs report a zero spread. A spread is not represented as savings, and the tariff recommendation cautions that rate comparisons do not establish a lower bill.
- Mobile recommendations show evidence, actions, assumptions, uncertainties, and requirements instead of a monthly-savings headline. Automation examples no longer show invented dollar savings or confidence values. AI instructions and fallback responses avoid invented rates/bills and clarify that chat is explanatory rather than an authoritative bill.
- Removed fixed-rate estimates from usage summaries and daily summaries, forecast cost projections/trends, daily briefs, high-bill alerts, and weekly notification copy. Cost fields now return null (or are omitted from notification payloads), the unsupported forecast confidence/range is null, and the mobile dashboard/usage UI identifies cost estimates as unavailable. Configured-tariff bill comparison remains the supported estimate surface.
- Added focused coverage for recommendation evidence, missing inputs, illustrative/expired/configured tariffs, flat tariffs, export exclusion, and non-quantified results. Usage, forecast, insight endpoint, and high-bill alert tests verify unpriced costs are null or suppressed.
- Validation: full backend suite **137 passed, 10 warnings**; focused Ruff line-length checks passed for changed production code and recommendation/forecast tests; mobile `npx tsc --noEmit` passed; `npx expo export --platform web` passed. The Expo export generated `mobile/dist/`, which was removed after validation.

**Remaining Prompt 06 limitations:** a user-declared appliance model, rated demand, and feasible operating schedule are required before any household-specific opportunity can be quantified. Forecasting currently projects kWh only; integrating effective-dated user tariffs into forecast and usage summaries is future work. Bill comparison may still use clearly labelled illustrative defaults where tariff configuration is absent or out of range, and it is not a retailer invoice. The AEMO NEM12 direction and source clock-basis dependencies described above remain unresolved.

## 13. Versioned scheduling contract — Prompt 07

- Added the versioned `1.0` request and response schemas, exposed in OpenAPI with synthetic request and response examples. The JSON fixture in `backend/tests/fixtures/scheduling_v1.json` is checked against both the endpoint response and OpenAPI examples.
- Added authenticated `POST /api/v1/scheduling/v1/plans/preview`. It validates meter ownership/timezone, optional tariff ownership, tariff provenance and effective dates, task energy inputs, interval alignment, timezone-aware windows, task duration/deadline fit, and baseline source/coverage/contiguity/non-overlap.
- Task energy must be specified as exactly one of rated kW or energy kWh. Timestamps require offsets matching the request's IANA timezone. Baselines must be explicit, fixed, nonnegative interval profiles from independently measured data or a synthetic fixture; raw net-meter demand cannot be labelled as an independent baseline.
- Missing, illustrative, stale, or unusable tariffs return an explicit blocked result. At the end of Prompt 07, a usable tariff returned `not_evaluated` because optimization had not yet been implemented. Prompt 08 below replaces that result with a bounded MILP preview.
- Added matching mobile TypeScript request/response types and a `schedulingApi.previewV1` client helper; no mobile scheduling UI calls it yet.
- Validation: focused `pytest tests\test_scheduling_contract.py -q` — **14 passed**; full backend suite — **151 passed, 11 warnings**; focused Ruff check and format check — **passed**; mobile `npx tsc --noEmit` — **passed**; `git diff --check` — **passed**. The warnings are existing dependency/deprecation warnings (plus the 422 response deprecation exercised by the new validation test).

**Remaining Prompt 07 limitations at that milestone:** the initial contract did not optimize, persist, execute, or dispatch schedules. The subsequent Prompt 08 implementation adds optimization while retaining the contract's validation and preview-only boundaries.

## 14. MILP scheduling preview — Prompt 08

- **Solver selection:** added direct `numpy` and `scipy` dependencies to the backend manifest, with SciPy `>=1.11.0` to guarantee the MILP API and Python 3.11 compatibility. SciPy's [`scipy.optimize.milp`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html) wraps HiGHS and supports mixed-integer constraints, sparse matrices, a per-solve time limit, and distinct optimal, time-limit, and infeasible statuses. SciPy is BSD-3-Clause licensed ([license](https://raw.githubusercontent.com/scipy/scipy/v1.11.0/LICENSE.txt)); HiGHS is MIT licensed ([license](https://raw.githubusercontent.com/ERGO-Code/HiGHS/master/LICENSE.txt)). SciPy 1.11's [toolchain roadmap](https://docs.scipy.org/doc/scipy-1.11.0/dev/toolchain.html) lists Python 3.11 support and official Linux x86/arm and Windows wheel targets. The local Windows Python 3.11 environment was verified to have SciPy 1.17.1 with `milp` available. The deployment image targets Python 3.11 on Linux, but a Docker build was not run, so image installation remains to be verified in CI/staging.
- **Task model:** each legal task start is a binary variable over the validated interval grid. Required tasks have exactly one start; optional tasks have at most one start and an explicit omission variable. Optional tasks can provide an omission penalty in AUD; without one, the no-savings treatment omits the optional task. Task input remains exactly one of fixed rated kW or task kWh over a fixed non-interruptible duration.
- **Constraints:** start windows, deadline completion, interval alignment, and every task duration are enforced. Optional household/grid kW limits constrain the sum of fixed baseline demand and all scheduled tasks in each interval; the tighter configured cap governs. DST schedules use absolute UTC instants for interval continuity and return starts/ends in the meter's local IANA zone.
- **Objective:** minimizes task interval energy charges plus a configurable `preference_penalty_aud_per_interval` for each interval away from `preferred_start`, plus optional-task omission penalties. Energy prices resolve only from a usable owned tariff: flat rates, custom local-clock periods, or the existing Victorian ToU classifier for VIC tariffs. Missing interval coverage blocks planning rather than falling back to default rates. GST-excluded rates are grossed up at 10%; fixed supply charges and demand charges are excluded and disclosed.
- **Accounting and comparator:** baseline energy and cost are included exactly once; task demand is incremental. Candidate and deterministic greedy reference schedules use the same request, rate vector, baseline, windows, preferences, and power caps. The response reports each schedule's energy and energy cost plus candidate/reference objective components. Energy-cost delta means candidate minus comparator cost, not household savings. The greedy comparator is explicitly labelled as a heuristic, not an optimum, and may return `not_found` even where an optimal plan exists.
- **Failure safety:** returns `feasible`, `infeasible`, or `timeout` when tariff validation passes. The MILP has a five-second time limit. A timeout does not present an unproven MILP incumbent or promote the greedy reference to a candidate. The route only returns a preview; it does not persist schedules or send device commands.
- **Excluded scope:** no device controls, appliance communications, batteries, PV curtailment, demand response, supply/demand charge optimization, or user-facing mobile scheduling screen. Synthetic baselines are clearly identified in response assumptions; measured baselines must be provided as independently measured profiles.
- **Verification:** scheduling-focused contract and optimizer tests — **29 passed**; full backend suite — **166 passed, 11 warnings**; focused Ruff check/format, mobile `npx tsc --noEmit`, and `pip check` passed. Docker was not available for a container build.

**Remaining Prompt 08 limitations:** Docker installation and deployed Linux runtime are not verified locally. Tariff history is still mutable; custom tariff windows do not include holidays. Only the energy-charge component is optimized, not complete retailer-bill cost. A greedy reference can fail to place required tasks because it is a heuristic; `not_found` is not proof of infeasibility. No schedule is saved or executed, and the mobile flow is not yet connected.

## 15. Mobile scheduling demonstration — Prompt 09

- Added the Expo `scheduling` route and a dashboard **Plan a Task** quick action. The screen loads the user's meter and tariff, displays the tariff windows, and calls the existing authenticated scheduling v1 preview endpoint. It uses a clearly labelled synthetic 0.8 kW baseline and does not treat the demo load as measured household data.
- Added the appliance/power/duration/window/preference/required-or-optional form. Meter-local date/time input is validated and converted to offset-bearing timestamps; 30-minute grid alignment and daylight-saving gaps are checked before submission. Optional tasks may provide a nonnegative AUD omission penalty or leave it blank for the no-savings behavior.
- Results show the original preference, MILP candidate (including task-omission results), deterministic greedy reference, modeled energy costs, preference shift, assumptions, and blocked/infeasible/timeout messages. **Keep recommendation / Keep task omitted** and **Keep original** only label a local preview choice. Editing the form clears the old response. The screen does not save a plan or dispatch a device.
- **Automated checks:** mobile `npx tsc --noEmit` — **passed**; `npx expo export --platform web` — **passed**. A mobile lint run remains unavailable: this checkout has no working ESLint configuration/dependency; an `npx eslint` attempt used ESLint 10 and stopped because no `eslint.config.*` exists. No Jest suite was run because Jest is not declared in the mobile package.
- **Browser-to-API flow:** using Expo web and a temporary SQLite database under the OS temp directory, registered a disposable demo account, created a temporary VIC meter and a non-illustrative 30 c/kWh flat tariff, and submitted the synthetic task through the screen to the local API. The required 2.4 kW / 60-minute task produced a feasible 09:00 recommendation matching the requested start. Baseline energy cost was **$0.96**, proposed and reference costs were each **$1.68**, and candidate-minus-reference energy-cost delta was **$0.00**; these are synthetic model outputs, not a bill or savings claim. An optional task with no omission penalty returned **Task omitted** and the expected no-savings explanation. The **Keep original** and **Keep recommendation** choices showed local-only confirmation text. An off-grid `08:15` time was rejected with the 30-minute alignment message.
- Captured the feasible recommendation screen at [mobile/prompt09-scheduling-result.png](mobile/prompt09-scheduling-result.png). The browser run also emitted existing Expo web warnings (deprecated shadow/pointer-events styles and unsupported web push-token listener); no scheduling API or browser error blocked the flow.

**Remaining Prompt 09 limitations:** browser verification used an isolated development API/database and synthetic tariff/baseline/task values. Native iOS/Android builds were not exercised. Scheduling results and user choices are transient; plans are not persisted, and no device control or execution exists. A real household recommendation requires independently valid meter direction/time data, a current usable tariff, and an independently measured baseline that excludes scheduled task demand.

## 16. Forecast evaluation and leakage controls — Prompt 10

- Added `backend/app/ml/forecast_evaluation.py` and `backend/scripts/evaluate_forecasting.py` to acquire the UCI Individual Household Electric Power Consumption dataset and compare the existing Prophet approach with persistence and a 28-day historical weekday-mean baseline. The CLI accepts an extracted dataset path and an output directory; its default writes to `backend/reports/forecast_evaluation/`.
- The target is daily kWh from minute-average `Global_active_power`. Invalid values are not interpolated; days below 99% expected minute coverage are excluded. Expected minute counts use Europe/Paris local calendar days, including 23- and 25-hour DST transitions. The dataset source, attribution/license, target construction, chronology, and limits are documented in `backend/docs/forecast-evaluation-dataset.md`.
- Chronological evaluation uses a 70/15/15 train/validation/test date split and seven-day expanding forecast origins at 1-, 7-, and 14-day horizons. Every fit uses only valid observations dated on or before its origin. Test predictions overlap by horizon/origin and therefore are not independent samples. A deterministic seed and source archive/data SHA-256 digests, split dates, model setup, and library versions are recorded in `config.json`.
- **Observed run:** 1,407 daily targets retained; 504 prediction rows; 72 metric rows. Test MAE (kWh) by horizon:

  | Horizon | Persistence | Prophet | 28-day weekday mean | Prophet forecasts |
  |---:|---:|---:|---:|---:|
  | 1 day | 4.952 | 5.320 | 6.158 | 28 |
  | 7 days | 3.832 | 3.169 | 4.154 | 29 |
  | 14 days | 4.893 | 3.269 | 4.665 | 28 |

  Prophet's nominal 80% interval coverage was 96.4%, 96.6%, and 96.4% respectively, with average widths of 18.015, 17.337, and 17.368 kWh. Intervals are not demonstrated to be calibrated guarantees.
- **Artifacts:** generated `predictions.csv`, `metrics.csv`, `config.json`, `forecast_evaluation.png`, `REPORT.md`, and `DATASET_README.md` reside under `backend/reports/forecast_evaluation/`. Dataset and evaluation details and all subgroup metrics are in the generated report.
- **Verification:** `python scripts/evaluate_forecasting.py --output-dir reports\forecast_evaluation` completed end-to-end using the verified local Python 3.11 environment; the corrected run output was reviewed. A second evaluation reproduced all **504 prediction rows** and **72 metric rows** exactly, excluding hardware-dependent fit runtime fields. Focused forecast evaluation and existing forecast tests — **11 passed**; Ruff format and check — **passed**. A regression test verifies the overall metric aggregation across seasons. Europe/Paris DST expected coverage was checked as 1,380 minutes on 2024-03-31 and 1,500 minutes on 2024-10-27. Prophet emitted a non-blocking optional Plotly warning; static plot output was produced.

**Remaining Prompt 10 limitations:** this is one household in Sceaux, France, not GridSense customer or Australian household evidence. The target does not distinguish PV, underlying load, or import/export direction. Small overlapping forecast samples, one held-out chronology, historical data quality, and possible regional/seasonal differences preclude broad accuracy claims. No tariffs are applied, so the benchmark cannot establish bill or savings performance. Runtime measurements are hardware-dependent.

## 17. Research-grade scheduling experiment audit — Prompt 11B

The scheduling benchmark was revised in place; it was not replaced and no results were fabricated. The implementation is `backend/app/ml/scheduling_experiment.py`, run by `backend/scripts/run_scheduling_experiment.py`; detailed methodology is in `backend/docs/scheduling-experiment.md`.

### Methods and outputs

- The six strategies are S0 preferred-start, S1 greedy nominal, S2 MILP nominal, S2 MILP forecast, perfect-information MILP (realized energy charge plus preference penalty), and an energy-only oracle (realized prices, zero preference penalty). Nominal S1 and S2 receive the exact same nominal price vector; S2-minus-S1 therefore compares algorithms under matched information. Forecast MILP-minus-nominal MILP isolates forecast information.
- The default factorial run uses eight generated profiles repeatedly across 192 household/configuration cells, producing **1,152 strategy rows**, **576 paired-comparison rows**, **144 grouped summary rows**, **9,216 interval-price rows**, and **3,456 task-schedule rows**. The 192 repeated configuration cells are not 192 independent households.
- Charges for every feasible result are recomputed by reloading the exported `results.csv`, `interval_prices.csv`, and `task_schedules.csv`. The audit fails above a documented `1e-8 AUD` tolerance. Its regression test also tampers with an exported charge and verifies that the mismatch raises an error.
- `non_flexible_baseline_energy_cost_aud` means non-flexible baseline demand only. `baseline_energy_cost_aud` is retained as a compatibility alias for that same amount; `s0_reference_energy_cost_aud` is the complete S0 preferred-start charge.
- The generated files are `results.csv`, `summary.csv`, `paired_comparisons.csv`, `paired_summary.csv`, `interval_prices.csv`, `task_schedules.csv`, `robustness.csv`, `config.json`, `REPORT.md`, `paired_s1_s2.png`, `flexibility_forecast_error.png`, and `cost_inconvenience.png`. The old `strategy_comparison.png` was removed so it cannot be mistaken for a current figure.

### Executed default results

Mean energy charges were **$7.3591** for S0, **$6.8873** for greedy nominal, **$6.8861** for nominal MILP, **$6.8955** for forecast MILP, **$6.8616** for perfect-information MILP, and **$6.8577** for the energy-only oracle. All are synthetic energy-charge results, not full bills.

The matched nominal MILP-minus-greedy mean energy-charge difference was **−$0.0011 AUD**, with an eight-profile descriptive 95% t interval **[−$0.0039, $0.0016]** and 4/2/186 matched wins/losses/ties. This does not support a superiority claim. Forecast MILP-minus-nominal MILP was **+$0.0094 AUD**, with interval **[−$0.0060, $0.0247]** and 62/32/98 wins/losses/ties; this also does not establish a general forecast-information advantage. The energy-only oracle reduced energy charges while increasing inconvenience: its mean weighted objective was **$6.9853** and mean inconvenience **6.38 h**, versus **$6.9122** and **2.53 h** for the perfect-information MILP. These outcomes show why energy charge alone does not establish overall schedule superiority.

The generated robustness cases include a single-slot appliance window infeasible under its power cap, two overlapping mandatory tasks that jointly exceed the cap, baseline demand above the cap, a solver failure explicitly recorded as `solver_error`, and a measured greedy-suboptimal case with MILP-minus-greedy energy charge **−$4.95**. The latter is a constructed stress scenario only.

### Verification record

Observed environment: **Windows 10**, Python **3.11.9**, NumPy **2.4.6**, pandas **3.0.5**, SciPy **1.17.1** with its HiGHS MILP backend.

| Check | Command from `backend/` | Result |
|---|---|---|
| Full experiment and reproducibility | `run_experiment(output)` twice in the `.venv311` Python process; all generated result tables compared | **PASS**; two full runs matched exactly except `runtime_ms` and `mean_runtime_ms`. |
| Experiment, optimizer, API contract tests | `..\\.venv311\\Scripts\\python.exe -m pytest -q tests\\test_scheduling_experiment.py tests\\test_scheduling_optimizer.py tests\\test_scheduling_contract.py` | **PASS — 35 passed, 6 warnings, 11.77 s; exit 0.** |
| Ruff format | `..\\.venv311\\Scripts\\python.exe -m ruff format --check app\\ml\\scheduling_experiment.py tests\\test_scheduling_experiment.py scripts\\run_scheduling_experiment.py` | **PASS.** |
| Ruff lint | `..\\.venv311\\Scripts\\python.exe -m ruff check app\\ml\\scheduling_experiment.py tests\\test_scheduling_experiment.py scripts\\run_scheduling_experiment.py` | **PASS.** |

The six pytest warnings are existing dependency deprecations from `pythonjsonlogger`, Pydantic class-based configuration, and Starlette's HTTP 422 constant. One earlier combined test invocation printed native SQLAlchemy **access-violation** messages during the API contract test even though pytest exited successfully; the final focused rerun did not reproduce them. This intermittent behavior was not a failing pytest assertion, but remains an environment/test-process concern and should not be hidden.

The repeatability check was executed in PowerShell from `backend/` with this inline Python:

```powershell
@'
from pathlib import Path
import pandas as pd
from app.ml.scheduling_experiment import run_experiment

output = Path("reports/scheduling_experiment")
runs = []
for _ in range(2):
    paths = run_experiment(output)
    runs.append({
        key: pd.read_csv(paths[key])
        for key in ("results", "summary", "paired_comparisons", "paired_summary",
                    "equity_summary", "equity_flexibility_sensitivity",
                    "equity_provenance", "robustness", "interval_prices", "task_schedules")
    })
for key in runs[0]:
    left, right = runs[0][key], runs[1][key]
    if key == "results":
        left, right = left.drop(columns=["runtime_ms"]), right.drop(columns=["runtime_ms"])
    elif key == "summary":
        left, right = left.drop(columns=["mean_runtime_ms"]), right.drop(columns=["mean_runtime_ms"])
    pd.testing.assert_frame_equal(left, right, check_dtype=False)
print("Two full runs matched exactly except runtime fields.")
'@ | ..\.venv311\Scripts\python.exe -
```

### Limits

Profiles, prices, perturbations, appliances, and outcomes are synthetic. The reused profiles do not support population inference. The prices and forecast errors are uncalibrated assumptions, not observed Australian retail tariffs. The model is a one-day, 30-minute, energy-only simulation and excludes complete retailer bills, supply/demand charges, tax/export treatment, PV/BESS, customer compliance, measured comfort, multi-day effects, and device execution. AUD changes are not customer savings or bill estimates.

## 18. Equity and distributional evaluation — Prompt 12

### Predeclared metrics and provenance

The report defines metrics before the equity outcome tables:

- **Software access:** not measured. Complete simulation inputs are only a technical pipeline-eligibility proxy, not evidence that a person can access or use the advisory software.
- **Technical feasibility/completion:** a schedule is technically complete when it is feasible and every mandatory task completes. The flexibility CSV now reports explicit `technically_incomplete_or_infeasible_*` counts alongside the backward-compatible `no_actionable_*` aliases; both represent technical non-completion only.
- **Economic worth:** not classified; no minimum acceptable benefit or welfare threshold is declared.
- **Practical actionability and user acceptance:** not measured. Complete synthetic inputs and feasible schedules do not establish software access, user acceptance, or ability to act.
- **Benefit distribution:** realized synthetic energy-charge level, absolute savings against same-case S0 (negative values retained), inconvenience hours, and weighted-objective change.
- **Uncertainty and size:** profile-level means, descriptive 95% t intervals, 10th/90th profile quantiles, generated profile counts, and scenario-cell counts. Repeated configurations are not independent households.
- **Permitted categories:** generated flexibility-hour and appliance-mix scenarios only. The analysis does not infer tenure, income, health, demographics, or protected attributes from consumption.
- **Missing comparisons:** no consented demographic groups or documented demographic provenance; no validated PV/BESS/generation/DER ownership categories. EV charging is just a synthetic task load, not a DER ownership marker.

`backend/reports/scheduling_experiment/equity_provenance.csv` is the machine-readable source/definition/limitations ledger. The analysis distinguishes technical input eligibility and feasibility from software access, economic worth, practical actionability/user acceptance, and device execution.

### Executed outcomes

The regenerated default run wrote **15 equity group rows**, **6 matched flexibility-sensitivity rows**, and **7 provenance rows**. For the three implementable strategy variants, every 2/6/10-hour flexibility group had **64/64** technically eligible scenario inputs; each light/mixed appliance group had **96/96**. The simulation recorded **zero technically incomplete or infeasible schedules** in those groups. These counts describe the synthetic experiment only, not service reachability, practical actionability, or real households.

Each flexibility sensitivity comparison had **32/32 flat-tariff ties and 0/32 TOU ties** for every strategy, at both 6-hour and 10-hour comparator windows. This confirms the 32 ties per comparison arise from the flat-price cases in this run; it does not imply tied behavior under TOU tariffs.

Matched 2-hour-minus-6-hour mean savings differences were **−$0.4040** for greedy nominal, **−$0.4074** for nominal MILP, and **−$0.4160** for forecast MILP; the respective eight-profile descriptive 95% intervals were **[−$0.4774, −$0.3306]**, **[−$0.4827, −$0.3321]**, and **[−$0.5036, −$0.3285]**. Matched 2-hour-minus-10-hour differences were **−$0.5642**, **−$0.5642**, and **−$0.5887**, with intervals **[−$0.6897, −$0.4387]**, **[−$0.6897, −$0.4387]**, and **[−$0.7256, −$0.4517]**. In these constructed scenarios, 2-hour flexibility also had lower mean start-time inconvenience than the wider comparator. These do not support claims about actual customer groups or equity effects.

As an observed counterexample, **3 of 192 forecast-MILP scenarios** had negative modeled savings versus S0; the worst was **−$0.1889 AUD**. This rules out claiming every simulated recommendation saves energy charges, while remaining a synthetic result.

The new `equity_savings_distribution.png` shows generated-profile mean S2 nominal savings by flexibility, with median/IQR and profile dots, separately for flat and TOU price cases. `equity_boundary_cases.csv` reports a mandatory task with only one allowed start, a **$0.005** possible energy-charge reduction outweighed by the modeled **$0.01** shift penalty, and an unavailable-appliance row marked not representable because the v1 request requires at least one task and has no appliance availability field. These are constructed optimizer checks, not household groups.

### Verification

| Check | Command from `backend/` | Result |
|---|---|---|
| Regenerate experiment outputs | `..\\.venv311\\Scripts\\python.exe scripts\\run_scheduling_experiment.py` | **PASS.** Report, CSVs, and four figures regenerated; sensitivity CSV includes explicit technical non-completion columns and compatibility aliases; boundary-case CSV has three rows. |
| Experiment and equity-output repeatability | `run_experiment(output)` twice; compare results, summary, paired outputs, equity outputs, robustness, price traces, and schedules | **PASS**; all compared tables matched, excluding runtime fields in main results and summary. |
| Experiment, equity, optimizer, API contract tests | `..\\.venv311\\Scripts\\python.exe -m pytest -q tests\\test_scheduling_experiment.py tests\\test_scheduling_optimizer.py tests\\test_scheduling_contract.py` | **PASS — 38 passed, 6 warnings, 30.77 s; exit 0.** |
| Ruff format | `..\\.venv311\\Scripts\\python.exe -m ruff format --check app\\ml\\scheduling_experiment.py tests\\test_scheduling_experiment.py scripts\\run_scheduling_experiment.py` | **PASS.** |
| Ruff lint | `..\\.venv311\\Scripts\\python.exe -m ruff check app\\ml\\scheduling_experiment.py tests\\test_scheduling_experiment.py scripts\\run_scheduling_experiment.py` | **PASS.** |

One earlier combined pytest invocation printed native SQLAlchemy access-violation messages despite all tests passing and pytest returning exit 0; the final focused invocation did not reproduce them. Six pre-existing dependency deprecation warnings were also reported. This remains an intermittent environment/test-process concern.

### Limitations and next dependency

This is not a demographic analysis, app usability study, retail-bill analysis, or verified energy-equity outcome. Profiles do not provide DER ownership or generation data; groups are synthetic scenarios; only eight generated profiles underlie descriptive intervals. To assess actual equitable access and outcomes, the project needs consented and governed demographic provenance, app reachability/accessibility/uptake observations, and source profiles with validated DER dimensions and complete tariff/bill data. No poverty-reduction or demographic fairness conclusion is supported.

## 19. Operational reliability and demo safety — Prompt 13

### Implemented behavior

- A unique per-user file-hash index prevents repeated content from creating duplicate upload records. The Alembic upgrade keeps upload history and chooses one canonical duplicate hash (preferring a completed record) before creating the index.
- Duplicate requests reuse the same upload record. Failed/missing RQ jobs can be retried by resubmitting the file; committed NEM12 timestamps are skipped during retry.
- The Redis-unavailable API fallback now runs with a task-owned database session. It is intentionally documented as **non-durable**: a process crash can interrupt in-process work, and there is no outbox or automatic recovery.
- Database readiness failures return HTTP 503 with a generic dependency status; worker readiness errors no longer expose raw connection strings. Queue/import failure state uses safe messages and error types. Changed import and notification logs omit meter identifiers and push tokens.
- Optional alert publication and training enqueue failures do not mark a completed import as failed. Missing OpenAI credentials use the local fallback; local email and simulator automation defaults keep SMTP and Home Assistant optional. Expo push remains optional.
- Compose no longer makes the API container depend on Redis; worker/scheduler containers still require Redis.
- `backend/scripts/demo_seed.py` and `backend/docs/demo-data.md` create/reset a dedicated synthetic SQLite demo database with a locally supplied password. The reset flag is restricted to `gridsense-demo.db` and must not be used with a user/staging/production database.

### Verification

| Check | Command / setup | Result |
|---|---|---|
| Full backend suite | `..\\.venv311\\Scripts\\python.exe -m pytest -q` (from `backend/`) | **PASS — 188 passed, 11 warnings, 75.62 s; exit 0.** An earlier Windows run emitted native access-violation diagnostics while tearing down an existing SQLite scheduling-contract fixture; the final run did not reproduce them. |
| Import retry after committed chunk | Unit test simulates an interruption after the first 100 readings commit, then reruns the same RQ task and verifies 336 unique readings | **PASS** as an application-level retry simulation; an actual worker process kill/restart was not run. |
| Duplicate and failed-job retry | Upload API test submits identical content twice, confirms one job/upload, then reports RQ failure and verifies resubmission reuses the upload ID | **PASS.** |
| Redis enqueue unavailable | Upload API test forces enqueue failure and verifies the request-independent fallback session completes the import | **PASS** in-process simulation; no real Redis outage test was possible. |
| Readiness failure | Database dependency raises; `/health/ready` returns 503 without the exception text | **PASS.** |
| Demo seed/reset | Test seeds a temporary `gridsense-demo.db`, repeats idempotently, then resets/reseeds and verifies counts | **PASS.** |
| Alembic migration | `..\\.venv311\\Scripts\\python.exe -m pytest -q tests\\test_migrations.py` | **PASS**; clean upgrade/downgrade/re-upgrade, unique-index lifecycle, and duplicate legacy hashes verified. |
| Compose syntax | `docker compose config --quiet` (repository root) | **PASS.** |
| Docker engine | `docker info --format '{{.ServerVersion}}'` | **BLOCKED**; Docker Desktop Linux-engine named pipe was unavailable. |
| Compose smoke / actual worker restart / PostgreSQL staging boot / backup restore | Would require a running Compose engine and disposable staging database | **NOT VERIFIED.** No staging restore or service restart claim is made. |
| Restore-verifier static checks | `bash -n backend/scripts/verify_postgres_restore.sh`; invoke without arguments | **PASS.** Bash syntax and argument guard verified; the script was not run against PostgreSQL because the Docker engine was unavailable. |
| Ruff format | `..\\.venv311\\Scripts\\python.exe -m ruff format --check` over changed Python modules/tests | **PASS** for the selected changed files. |
| Ruff lint | Default `ruff check` over changed files | **4 pre-existing findings** remain in the edited AI/notification modules: one `W291` trailing space and three `E712` SQLAlchemy boolean comparisons. All other selected rules pass when excluding `E712,W291`. |

`backend/docs/worker.md` documents the RQ and fallback trade-off. `backend/docs/backup-restore.md` marks the procedure as unverified, uses the Compose database name, and directs restores to a disposable database. `backend/scripts/verify_postgres_restore.sh` now checks a compressed custom-format archive and compares core table row counts after restore; it has only passed static checks and remains unverified against a running PostgreSQL service.

## 20. Stage 1 demonstration package — Prompt 15

### Deliverables

- `backend/docs/demo/DEMO_RUNBOOK.md`: reproducible, timed 5–7 minute walkthrough; Windows PowerShell setup/reset; separate analytics and TOU-scheduling accounts; synthetic-data boundaries; schedule scenario narration; loopback-only API binding; pre-demo checklist and recording fallback.
- `backend/docs/demo/PRODUCT_ONE_PAGER.md`: separately lists Working, Simulated, and Planned/not established.
- `backend/docs/demo/DECK_OUTLINE.md`: eight-slide short presentation outline with required caveats.
- `backend/docs/demo/CLAIM_EVIDENCE_MATRIX.md`: maps implementation claims to code, tests/commands, data, generated findings, artifacts, and permitted manuscript wording.
- `backend/docs/demo/architecture.svg`: scalable Stage 1 diagram distinguishing product services, optional integrations, unverified production components, non-dispatch boundary, and separate research paths.
- `backend/docs/demo/SCREENSHOTS.md`: readable preview and research figure gallery, captions, and screenshot guardrails.

### Claim and demonstration boundaries

The fabricated parser fixture imports **336** readings but keeps direction unresolved; it is only a parser/import-warning demonstration and cannot support consumption analytics. The safe analytics path uses the dedicated local seed with **48 synthetic known-import readings for one date** and a synthetic flat tariff. The separate schedule account has no readings; the 0.8 kW baseline is an explicit synthetic API input, not a consumption-derived profile. A focused TOU API test selects 06:00 over the 09:00 preference: $0.68 fixed-baseline energy charge, $0.92 proposed total energy charge, $0.06 preference penalty, and $0.98 weighted objective. The fixed 09:00 task counterfactual costs $0.60 versus $0.24 for the proposed task interval, a $0.36 modeled task-charge difference. The greedy reference also selects 06:00, so the MILP-vs-reference charge difference is $0.00; this does not establish household savings or method superiority. The schedule screen remains preview-only and does not persist acceptance or dispatch an appliance. The broader scheduled experiment's nominal MILP-versus-greedy mean energy difference is **−$0.0011 AUD**, with a profile-level descriptive interval **[−$0.0039, $0.0016]** and **4/2/186** matched win/loss/tie counts; no overall superiority claim is supported. Forecast evidence is restricted to the documented single-household UCI benchmark.

### Validation

| Check | Command / evidence | Result |
|---|---|---|
| Synthetic analytics and TOU seed repeatability | `..\\.venv311\\Scripts\\python.exe -m pytest -q tests\\test_demo_seed.py` (from `backend/`) | **PASS.** Two synthetic accounts seed idempotently; the analytics account retains 48 half-hour readings and a 30 c/kWh flat tariff; the scheduling account has a distinct meter, no readings, and four invented all-week TOU periods. Reset remains scoped to the named dedicated SQLite filename. |
| Matched-input synthetic TOU schedule | `..\\.venv311\\Scripts\\python.exe -m pytest -q tests\\test_scheduling_contract.py::test_synthetic_tou_demo_uses_cheaper_start_and_reports_real_tradeoff` (from `backend/`) | **PASS.** API response chooses 06:00 for both MILP and greedy, candidate energy total $0.92 including $0.68 baseline, preference penalty $0.06, weighted objective $0.98, candidate/reference cost delta $0.00, and synthetic fixed-09:00 task-energy counterfactual $0.60 vs proposed task charge $0.24. |
| Upload and scheduling integration behavior | `..\\.venv311\\Scripts\\python.exe -m pytest -q tests\\test_demo_seed.py tests\\test_vertical_slice.py tests\\test_upload.py tests\\test_scheduling_contract.py tests\\test_scheduling_optimizer.py` | **PASS — 41 passed, 6 warnings, 21.07 s; exit 0.** Includes fabricated fixture import, unresolved direction, demo seed, and schedule contract/optimizer behavior. |
| Changed backend Ruff lint | `..\\.venv311\\Scripts\\python.exe -m ruff check scripts\\demo_seed.py tests\\test_demo_seed.py tests\\test_scheduling_contract.py` (from `backend/`) | **PASS — exit 0.** |
| Mobile compile/type validation | `npx tsc --noEmit` (from `mobile/`) after dashboard navigation change | **PASS — exit 0.** |
| SVG and demo-package link validation | Parse `backend/docs/demo/architecture.svg` as XML and verify local links in the six demo package files | **PASS.** SVG parsed and no broken local links found. |
| Compose configuration syntax | `docker compose config --quiet` (repository root) | **PASS.** This does not constitute a live service smoke test. |
| Local API/browser setup | Seed dedicated SQLite demo DB; run Uvicorn on `127.0.0.1:8000` and Expo Web on localhost; `GET /health/live`; authenticate both synthetic accounts | **PASS for local key paths.** API liveness returned 200; both accounts accepted login; dashboard showed 12.96 kWh for one local day (13.0 rounded) and the configured-tariff card showed a $3.89 partial active-energy estimate with missing-interval warnings. |
| Browser account switching | Sign out through Settings, accept the browser confirmation, then sign in to the other seeded account | **PASS.** Web confirmation appeared; accepting it cleared the session and returned to login. The analytics account then signed in and rendered its seeded dashboard. |
| Browser dashboard-to-scheduler navigation | Sign in as the synthetic scheduling account, whose meter intentionally has no readings; use the dashboard action | **PASS.** The dashboard clearly reports usage unavailable and exposes **Preview a schedule with synthetic baseline**; selecting it opened `/scheduling` with the synthetic baseline disclosure and labeled synthetic TOU tariff. This avoids relying on direct URL navigation while preserving the no-readings limitation. |
| Browser TOU scheduling walkthrough | Authenticate as the synthetic scheduling account; submit 2.4 kW/60-minute task, 06:00–10:00 window, 09:00 preferred start | **PASS for the synthetic browser scenario.** The UI displayed 06:00 MILP and deterministic-reference schedules, $0.68 baseline, $0.92 candidate/reference energy charge, $0.06 preference penalty, and $0.98 for each weighted objective. The API test separately verifies the 09:00 fixed-start task charge is $0.60 versus the proposed $0.24. Browser screenshots were viewed in-session but not saved to the repository. |
| Screenshot review | Existing `mobile/prompt09-scheduling-result.png` and live browser screenshots | **PASS for visual readability of the viewed dashboard and TOU result.** The existing repository screenshot still depicts an earlier flat-rate case; no new screenshot asset or screen-recording video was saved. |
| Full timed 5–7 minute demonstration | Follow `backend/docs/demo/DEMO_RUNBOOK.md` including optional fixture upload and all narration | **NOT YET ACCEPTED.** The live browser usage and scheduling paths passed, but the complete timed run was not performed without interruption, and no fallback recording has been captured. |
| Venue-template compile | No manuscript source or venue template is present | **NOT APPLICABLE / NOT VERIFIABLE.** |

This package is a reproducible script and evidence-alignment guide. It is not evidence of live PostgreSQL/Redis integration, actual NEM12 semantic validity, customer savings, production security, or appliance execution. The API binds to `127.0.0.1` for the local browser walkthrough; do not expose the debug server on `0.0.0.0`. The top dashboard usage summary still displays an unavailable cost field; the lower Bill Comparison card provides the configured-tariff estimate and explicitly warns that the current-period data is partial. The fallback recording instructions are documented, but a recording still needs to be captured from a clean local browser session.

## Latest final-demo verification — 31 October 2026

This section supersedes older Prompt 15 statements above where they say that
new live captures were not saved or that only focused backend tests had run.

| Check | Command / evidence | Result |
|---|---|---|
| Current source identity | `git rev-parse HEAD`; initial `git status --short` | HEAD `518616c3b02319d39c384fb9106ec506e20a8c23`; 95 modified/untracked entries were present before this verification. Results apply to that revision plus its dirty working tree, not the commit in isolation. |
| Complete backend test suite | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest -q` | **PASS — 189 passed, 11 warnings, 40.99 s, exit 0.** Warnings are deprecations from python-json-logger, Pydantic class-based config, Starlette's 422 status constant, and Alembic path-separator handling. |
| Mobile TypeScript | From `mobile/`: `npx tsc --noEmit` | **PASS — exit 0.** |
| Full backend Ruff | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m ruff check .` | **FAIL — 226 findings.** The current repository-wide lint debt remains; no broad cleanup was attempted as part of demo verification. |
| Mobile lint/test commands | From `mobile/`: `npm run lint`; `npm test -- --runInBand` | **Not runnable — exit 1.** The `eslint` and `jest` executables are not installed in the mobile workspace. |
| Demo service readiness | Dedicated seeded SQLite file; Uvicorn `127.0.0.1:8000`; Expo Web `localhost:8081`; `GET /health/live` | **PASS.** API liveness returned HTTP 200. Docker Engine reported version 29.7.2 and `docker compose config --quiet` passed; Compose services were not started for this demo run. |
| Browser fixture + analytics | Upload `backend/tests/sample_nem12.csv`, select the seeded analytics meter | **PASS.** The fixture reported 336 imported readings and unresolved direction for E1; dashboard retained **Synthetic demo meter**, showed 12.96 kWh for one local day (13.0 rounded), and its lower bill-comparison card showed a $3.89 partial configured-tariff estimate. |
| Browser recommendations and account switch | View Tips; sign out in Settings; accept browser confirmation; sign in as the other synthetic user | **PASS.** Two conditional, unquantified recommendation cards were displayed; web sign-out returned to login and the separate scheduling account authenticated successfully. |
| Browser scheduling + arithmetic | Use the dashboard's synthetic-baseline action; submit 2.4 kW / 60-minute task, 06:00–10:00 window, 09:00 preferred | **PASS.** Both MILP and deterministic reference selected 06:00; baseline $0.68, proposed/reference energy charges $0.92, preference penalty $0.06, weighted objectives $0.98, and candidate-minus-reference delta +$0.00. An independent Decimal calculation from the periods gives a 06:00 task charge of $0.24 vs $0.60 at fixed 09:00, a modeled $0.36 task-charge difference. |

## Prompt 23 — Engineering baseline update (1 November 2026)

This append-only update supersedes earlier statements in this file that mobile
ESLint was unavailable or that `pytest-cov` was undeclared. It supplements,
but does not erase, the historical Prompt 01–22 observations.

- Git snapshot: `main`, HEAD
  `d789f9814da9955db1c63ced921a95379dd08495`; inventory found 70 tracked
  modified paths, 653 untracked paths, and no staged paths. The detailed
  inventory and exact source/exclusion lists are in
  [STAGE1_SOURCE_CHECKPOINT_PLAN.md](STAGE1_SOURCE_CHECKPOINT_PLAN.md).
- The Alembic chain is continuous through `d1e2f3a4b5c6`. PostgreSQL 16
  upgrade-to-head, downgrade-to-base, and re-upgrade passed after replacing
  the old migration downgrade type `sa.DATETIME()` with `sa.DateTime()`.
- `backend/requirements-dev.lock` is hash-pinned and was installed in clean
  Windows and Linux Python 3.11 environments. The Linux full suite completed
  with **265 passed, 13 warnings**, no native diagnostic, and exit 0.
- Three Windows full-suite runs each reported **265 passed, 12 warnings**.
  The native SQLite access-violation diagnostic appeared in **2/3** runs.
  Windows stability remains **BLOCKED**; pytest exit 0 is not a stability
  pass.
- The worker-health bug was reproduced and fixed: the old health endpoint
  imported a helper from a module where it did not exist and used a
  `Queue.workers` attribute absent from locked RQ 2.11. It now uses
  `app.tasks.get_redis_conn` and `Worker.all(..., queue=...)`. No-worker and
  Redis-unreachable cases return explicit HTTP 503 states. Focused health and
  migration tests passed (**4 passed, 8 warnings**).
- PostgreSQL/Redis operational checks used disposable services. The
  authenticated API smoke passed registration/login, ownership denial,
  conservative usage eligibility, tariff separation, and deterministic
  synthetic scheduling. Separately, TestClient exercised `/health/worker`
  with a test-user dependency override and a real disposable RQ worker, which
  validates route/worker behavior but not production authentication. No
  external provider credentials were configured.
- A clean disposable mobile copy passed `npm ci`, ESLint (**0 errors, 18
  warnings**), TypeScript, and Expo web export (**1,075 modules; about
  2.38 MB entry bundle**). npm reported **64 advisories** (2 low, 43
  moderate, 18 high, 1 critical); no broad audit fix was applied.
- Full `ruff check app tests` remains **FAIL** with 174 findings. The
  existing backend CI lint job runs this command and will not be green until
  those findings are addressed. Focused Ruff on the worker-health change
  passes. The CI YAML parses as nine jobs, but hosted GitHub Actions was not
  run.

Overall Prompt 23 status is **PARTIAL**. The Windows native diagnostic is
unresolved; full Ruff is failing; production deployment and real-household
validation remain unproven. See
[PROMPT23_ENGINEERING_BASELINE.md](PROMPT23_ENGINEERING_BASELINE.md) for the
full evidence, acceptance table, and Prompt 24 conditions. No repository
files were staged, committed, pushed, reset, or deleted; task-scoped
disposable validation artifacts were removed after use.
| Saved visual evidence | `backend/docs/demo/captures/*.png` | **PASS — 14 PNGs** covering clean login, analytics, bill estimate, recommendations, fixture selection/result, scheduling account dashboard, tariff configuration, TOU windows, task inputs, recommendation, cost comparison, and preview-only disclosure. See [`backend/docs/demo/SCREENSHOTS.md`](backend/docs/demo/SCREENSHOTS.md). |
| Timed walkthrough / video | [`backend/docs/demo/DEMO_RUNBOOK.md`](backend/docs/demo/DEMO_RUNBOOK.md) | **PARTIAL / NOT CAPTURED.** Core browser interactions were exercised but not timed as an uninterrupted 5–7 minute presentation. No video was produced; local `ffmpeg` and OBS commands were unavailable. See [`FINAL_DEMO_ACCEPTANCE.md`](backend/docs/demo/FINAL_DEMO_ACCEPTANCE.md) for per-criterion status. |

The verification environment was Windows with Python 3.11.9 (`.venv311`),
Node.js 22.20.0, npm 11.6.2, Docker 29.7.2, Expo Web, Uvicorn, and local
SQLite. The temporary, named `backend/gridsense-demo.db` was confirmed absent
before seeding and removed after the browser session. The API and Expo processes
were stopped afterward. This run does not verify PostgreSQL/Redis runtime
behavior, database recovery, real NEM12 semantics, customer savings, device
dispatch, or production readiness.

## Prompt 16B Stage 1 documentation baseline

| Check | Command / evidence | Result |
|---|---|---|
| Current source identity | `git rev-parse HEAD`; initial `git status --short --untracked-files=all` | HEAD `d789f9814da9955db1c63ced921a95379dd08495`. At task start, tracked files were clean and 192 untracked entries were already present; they were preserved. The Stage 1 specification files added by this task are also untracked until explicitly staged/committed. |
| Backend regression suite | From repository root: `Push-Location backend; ..\\.venv311\\Scripts\\python.exe -m pytest -q` | **PASS — 189 passed, 11 warnings, 36.76 s, exit 0.** Existing warnings are the python-json-logger move, Pydantic class-based config, Starlette 422 constant, and Alembic `path_separator` deprecations. |
| Documentation link check | Python link-validation script over `backend/docs/stage1/*.md` | **PASS — all relative Markdown links in the seven Stage 1 documents resolve.** |
| Whitespace / patch check | `git diff --check`; trailing-whitespace check over the seven Stage 1 documents and both updated root documents | **PASS.** |
| Scope | Git diff and source inspection | No application source, schema migration, provider integration, or external-network unit test was added. The documents specify future acceptance criteria; the backend suite does not prove those new criteria are implemented. |
| External-source confirmation | Official-source checks recorded in `backend/docs/stage1/EXTERNAL_DATA_INTEGRATION_DESIGN.md` | AER PRD page timed out; AEMO market-data and metering pages returned HTTP 403. MDFF v2.7 and NMI Procedure v7.4 applicability/effective dates remain unconfirmed. Open-Meteo docs/terms/pricing were accessible, but archived-run semantics and subscription entitlement remain unresolved. Dependent implementation is blocked pending authoritative confirmation. |

This is a documentation-only architecture baseline. Historical Prompt 15
results above are separate evidence and have not been presented as checks of
the new specification requirements. No commit or push was made.

## 21. Prompt 17 metering and coverage implementation — 31 October 2026

| Check | Command / setup | Result |
|---|---|---|
| Current source revision | `git rev-parse HEAD` | `d789f9814da9955db1c63ced921a95379dd08495`; Prompt 17 changes remain uncommitted. |
| Backend regression suite | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest -q` | **PASS — 203 passed, 11 warnings, 36.01 s, exit 0.** Includes migration, parser/upload, billing, usage, recommendation, vertical-slice, scheduling, and existing ownership tests. Warnings are Pydantic/Starlette/Alembic and python-json-logger deprecations. |
| Core interval-quality Ruff | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m ruff check app/services/interval_quality.py app/services/usage_analyzer.py app/schemas/usage.py` | **PASS — no findings.** |
| Changed-Python undefined/unused check | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m ruff check --select F` over all changed backend Python files | **PASS — no findings.** |
| Mobile types | From `mobile/`: `npx tsc --noEmit` | **PASS — exit 0.** |
| Patch whitespace | `git diff --check` | **PASS — exit 0.** Git printed only line-ending normalization warnings for existing LF files on Windows. |
| Migration compatibility | Included `tests/test_migrations.py::test_clean_database_migrates_to_head`; isolated temporary SQLite database | **PASS.** New fields are additive/nullable; migration avoids duplicate additions when the metadata-created schema already includes them. No production or PostgreSQL database was touched. |
| AEMO metering standards | Official metering procedures/guidelines page and candidate MDFF document access reattempted | **BLOCKED — HTTP 403.** Exact applicable document titles/versions/effective dates, NEM12 clock and interval-boundary rules, register/suffix direction semantics, quality/reason meanings, substitutions, and multiple-register rules remain unverified. No mapping was inferred. |
| Visual/mobile integration | Dashboard and usage screens updated; no device/browser visual run | **PARTIAL.** TypeScript compiles, but this run did not validate device rendering or accessibility. |
| External services, production data | No live provider calls, customer accounts, or production database were used | **NOT TESTED / BLOCKED** as applicable; no external API was added. |

The full backend suite initially exposed a migration clean-schema duplicate-column
case and outdated fixture assumptions. The migration was made idempotent for
metadata-created clean databases; import/export channels sharing a timestamp
are no longer treated as duplicates; parser tests now assert unsupported units
are preserved but ineligible; and tests use explicit provenance/direction. The
final Python 3.11 run above completed with no test failures. An earlier full
run printed Windows background-thread access-violation reports despite pytest
continuing; the final rerun did not reproduce those reports. No cause was
established, so rerun the suite if similar process-level symptoms recur.

Prompt 17 is **PARTIAL**, not fully accepted: local calculations and interface
contracts are tested, but NEM12 records remain ineligible for verified
UTC-dependent customer metrics until authoritative AEMO metering semantics can
be inspected. See
[`backend/docs/stage1/PROMPT17_MIGRATION_COMPATIBILITY.md`](backend/docs/stage1/PROMPT17_MIGRATION_COMPATIBILITY.md)
for the acceptance table, migration behavior, compatibility policy, and exact
unresolved source questions. No commit, push, or user-file cleanup was done.

## 22. Prompt 17B AEMO NEM12 validation — final checks

| Check | Command / setup | Result |
|---|---|---|
| Current source revision | `git rev-parse HEAD` | `d789f9814da9955db1c63ced921a95379dd08495`; Prompt 17B changes remain in the existing dirty worktree. No commit or push was made. |
| Complete backend test suite | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest -q` | **PASS — 217 passed, 11 warnings, 40.40 s, exit 0.** Warnings are deprecations from python-json-logger, Pydantic, Starlette, and Alembic. |
| Focused NEM12 Ruff | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m ruff check app\\services\\nem12_parser.py app\\services\\nem12_importer.py tests\\test_nem12_parser.py tests\\test_upload.py tests\\test_migrations.py` | **PASS — no findings.** |
| Broader selected-file Ruff | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m ruff check app\\services\\nem12_parser.py app\\services\\nem12_importer.py app\\api\\meters.py app\\tasks.py app\\models\\meter.py app\\models\\reading.py app\\schemas\\meter.py app\\schemas\\reading.py tests\\test_nem12_parser.py tests\\test_upload.py tests\\test_migrations.py` | **PARTIAL — 5 findings** on unchanged adjacent lines: one unused `HTTPException` import, one TYPE_CHECKING import-order issue, and three pre-existing long lines. These were not changed as unrelated cleanup. |
| Mobile TypeScript | From `mobile/`: `npx tsc --noEmit` | **PASS — exit 0.** |
| PostgreSQL migration cycle | Disposable local `postgres:16-alpine`, database `gridsense`; Alembic upgrade to head, downgrade to `a7b8c9d0e1f2`, then upgrade to head | **PASS.** Revision reached `b8c9d0e1f2` before and after the downgrade/re-upgrade cycle. The named `--rm` container was stopped and removed. No persistent database was used. |
| Patch whitespace | `git diff --check` | **PASS — exit 0 after the final documentation updates.** Git emitted only existing Windows line-ending normalization warnings for other modified Python files. |
| Authoritative-source status | AEMO MDFF v2.7 PDF and official related procedures | **PARTIAL/BLOCKED.** The MDFF document is verified, but related procedures/source-specific direction and clock evidence remain inaccessible or unverified. No customer direction or UTC timestamp interpretation was enabled. |

The first PostgreSQL invocation used the `psycopg` SQLAlchemy driver, which is
not installed in the project environment. The retry used the project's
installed `psycopg2` driver; no dependency or manifest was changed. The
PostgreSQL cycle verifies migration DDL behavior, not production database
availability, backup/recovery, or live application integration. See
[`backend/docs/stage1/PROMPT17_MIGRATION_COMPATIBILITY.md`](backend/docs/stage1/PROMPT17_MIGRATION_COMPATIBILITY.md)
and
[`backend/docs/stage1/AEMO_NEM12_COMPLIANCE_MATRIX.md`](backend/docs/stage1/AEMO_NEM12_COMPLIANCE_MATRIX.md)
for implementation status and unresolved semantic blockers.

## 23. Prompt 18 tariff revision and AER catalog verification — 31 October 2026

| Check | Command / setup | Result |
|---|---|---|
| Current source revision | `git rev-parse HEAD` | `d789f9814da9955db1c63ced921a95379dd08495`; Prompt 18 changes remain uncommitted alongside the pre-existing Prompt 17/17B worktree changes. No commit or push was made. |
| Full backend suite | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest -q` | **PASS — 234 passed, 12 warnings, 48.87 s, exit 0.** Warnings are dependency/API deprecations. |
| Recommendation and scheduling regressions | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest tests\\test_recommendation_engine.py tests\\test_scheduling_contract.py -q` | **PASS — 28 passed.** New coverage confirms confirmed revision snapshots, not the mutable legacy projection, govern effective dates and scheduling rates, and a horizon spanning revisions is blocked. One focused invocation printed transient Windows native SQLite access-violation diagnostics during teardown while still exiting 0; the final full-suite run completed cleanly. |
| Prompt 18 targeted Ruff | From `backend/`: Ruff on changed tariff, billing, scheduling, AER service/schema, and relevant test modules | **PASS — no findings.** Repository-wide `ruff check app tests` still fails with lint findings; no broad unrelated cleanup was attempted. |
| Mobile TypeScript | From `mobile/`: `npx tsc --noEmit` | **PASS — exit 0.** |
| PostgreSQL migration cycle | Isolated `postgres:16-alpine` disposable container; Alembic upgrade to head, downgrade to `b8c9d0e1f2`, then upgrade to head | **PASS.** Head was `c9d0e1f2a3b4` before and after the cycle. The temporary container was stopped and removed. Existing `studentos-db` and `studentos-redis` containers were not touched. |
| Patch whitespace | `git diff --check` | **PASS — exit 0.** Git emitted line-ending normalization warnings for existing modified files only. |
| AER data-use and customer evidence | AER API/source review and tariff integration boundaries | **PARTIAL/BLOCKED.** The adapter does not persist/cache generic plan payloads and does not activate a plan as a customer tariff; explicit redistribution/attribution/retention rights remain unverified. Customer-specific bills and real NEM12 consumption are not certified. |

These are Prompt 18 results, separate from the historical Prompt 17B
verification above. Full backend tests validate the implemented contracts but
do not establish AER data-use permissions, retailer-contract correctness,
complete bill accuracy, or authoritative NEM12 direction/time interpretation.
See
[`backend/docs/stage1/PROMPT18_ACCEPTANCE.md`](backend/docs/stage1/PROMPT18_ACCEPTANCE.md)
and
[`backend/docs/stage1/PROMPT18_MIGRATION_COMPATIBILITY.md`](backend/docs/stage1/PROMPT18_MIGRATION_COMPATIBILITY.md).

## 24. Prompt 19 weather and grid context — 31 October 2026

| Check | Command / setup | Result |
|---|---|---|
| Current source revision and worktree | `git rev-parse HEAD`; initial `git status --short` | HEAD `d789f9814da9955db1c63ced921a95379dd08495`. Existing Prompt 17/17B/18 changes and untracked files were preserved. No commit or push was made. |
| Baseline backend tests before Prompt 19 edits | From repository root: `..\\.venv311\\Scripts\\python.exe -m pytest -q` | **PASS — 234 passed, 12 warnings, exit 0.** The run printed a transient Windows/SQLite access-violation diagnostic despite exit 0. |
| Baseline mobile TypeScript | From `mobile/`: `npx tsc --noEmit` | **PASS — exit 0.** |
| Open-Meteo provider and migration tests | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest tests\\test_external_data.py tests\\test_migrations.py -q` | **PASS — 22 passed, 8 dependency deprecation warnings.** |
| Full backend suite | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest -q` | **PASS — 255 passed, 12 warnings, 94.51 s, exit 0.** Intermittent Windows SQLite native access-violation diagnostics were printed during teardown; pytest completed successfully with all tests passing. |
| Prompt 19 targeted Ruff | From `backend/`: Ruff on changed provider/API/schema/model/tests | **PASS — no findings.** |
| Mobile TypeScript | From `mobile/`: `npx tsc --noEmit` | **PASS — exit 0.** |
| PostgreSQL migration cycle | Disposable PostgreSQL 16 instance; Alembic upgrade to `d1e2f3a4b5c6`, downgrade to `c9d0e1f2a3b4`, re-upgrade | **PASS — final revision `d1e2f3a4b5c6`.** Disposable container was removed and unrelated containers were untouched. |
| Patch whitespace | `git diff --check` | **PASS — exit 0.** Git printed line-ending normalization warnings for existing modified files. |
| Open-Meteo source/terms | Official docs, terms, pricing and license pages; see `EXTERNAL_PROVIDER_SOURCE_MATRIX.md` | Forecast API v1 fields/units, CC BY 4.0 attribution and paid customer endpoint documented. No paid key/account was available for live verification; issue time and resolved `best_match` model remain unknown. |
| AEMO market data | AEMO official guidance and public NEMWeb directory | AEMO guidance returned HTTP 403; public DispatchIS file listing was reachable. Feed schema, VIC mapping, timing, revisions and use rights remain blocked; no adapter or market data is enabled. |

Prompt 19 acceptance is **PARTIAL**: weather context is available only with
operator-configured paid access; market data is **BLOCKED**. See
[`backend/docs/stage1/PROMPT19_ACCEPTANCE.md`](backend/docs/stage1/PROMPT19_ACCEPTANCE.md)
and
[`backend/docs/stage1/EXTERNAL_PROVIDER_SOURCE_MATRIX.md`](backend/docs/stage1/EXTERNAL_PROVIDER_SOURCE_MATRIX.md).
Provider failure does not block meter analytics, tariff calculations or
scheduling. No customer savings claim is derived from wholesale market data.

## 25. Prompt 20 recommendations and reproducible metrics

| Check | Command / setup | Result |
|---|---|---|
| Pre-Prompt 20 baseline | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest -q` | **PASS — 255 passed, 12 warnings, exit 0.** Existing worktree included prior Prompt 17–19 changes; no user changes were reverted. |
| Focused Prompt 20 regressions | `..\\.venv311\\Scripts\\python.exe -m pytest tests\\test_billing.py tests\\test_vertical_slice.py tests\\test_recommendation_engine.py tests\\test_anomaly_detector.py tests\\test_insights_endpoints.py -q` | **PASS — 47 passed, 6 warnings, exit 0.** |
| Full backend suite | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest -q` | **PASS — 261 passed, 12 warnings, 66.17 s, exit 0.** A native access-violation diagnostic appeared during SQLAlchemy schema teardown in `test_scheduling_contract.py`; pytest completed all tests. |
| SQLite diagnostic isolation | Focused Prompt 20 regression group and `pytest -q tests\\test_scheduling_contract.py` | **PASS — 47 and 19 tests.** The focused Prompt 20 group did not reproduce the diagnostic; the scheduling-contract module did print native access-violation diagnostics in SQLAlchemy schema/result handling. No root cause was established. |
| Focused Ruff | `..\\.venv311\\Scripts\\python.exe -m ruff check` over modified Prompt 20 backend modules and tests | **PASS — no findings.** |
| Mobile TypeScript | From `mobile/`: `npx tsc --noEmit` | **PASS — exit 0.** |
| PostgreSQL migration check | No Prompt 20 schema migration was added | **NOT APPLICABLE.** No database changes were required for response-time evidence. |
| Patch whitespace | `git diff --check` | **PASS — exit 0.** Existing CRLF normalization warnings remain on unrelated dirty files. |

Prompt 20 is **PARTIAL**. The recommendation evidence is response-time only,
not durably persisted or historically replayable; recommendation notifications
are not deduplicated; scheduling outputs do not yet use the new common evidence
schema; and no forecast-dependent recommendation is enabled pending held-out
evaluation. See
[`backend/docs/stage1/PROMPT20_ACCEPTANCE.md`](backend/docs/stage1/PROMPT20_ACCEPTANCE.md)
for behavior-by-behavior status and remaining gaps. No external API credential
was requested or configured, and no commit or push was made.

## 26. Prompt 20B SQLite native diagnostics and stability — 1 November 2026

| Check | Command / setup | Result |
|---|---|---|
| Revision and staged state | `git rev-parse HEAD`; `git diff --cached --name-only` | HEAD `d789f9814da9955db1c63ced921a95379dd08495`; worktree already contained Prompt 17–20 edits. No files were staged. No reset, commit, or push was performed. |
| Runtime versions | `.venv311`; Python `sys.version`, SQLite `sqlite3.sqlite_version`, package `__version__` values | Windows 10 build `10.0.26200`; CPython 3.11.9; SQLite 3.45.1; sqlite module 2.6.0; SQLAlchemy 2.0.52; pytest 9.1.1; greenlet 3.5.5; aiosqlite unavailable. SQLite reports serialized threading (`threadsafety=3`, `THREADSAFE=1`, `MUTEX_W32`). |
| Before-fix module repetitions | `pytest -q tests\test_scheduling_contract.py`, three separate runs | 2/3 emitted Windows native access-violation diagnostics while reporting 19 passed, 6 warnings; one run had no diagnostic. |
| Before-fix individual test | `test_scheduling_fixture_validates_and_openapi_exposes_v1`, three separate processes | 3/3 passed, no diagnostic. |
| After-fix scheduling module | Same captured module command repeated three times; also one run with `pytest -s -q` | 4/4 module runs: 19 passed, no diagnostic. |
| After-fix individual DB-backed scheduling tests | Each of the 10 fixture-using tests run separately | 10/10 passed; no diagnostic. |
| Scheduling/integration checks | `pytest -s -q tests\test_scheduling_contract.py tests\test_vertical_slice.py tests\test_migrations.py` | **PASS — 23 passed, 10 warnings; no diagnostic.** |
| Full backend suite | `pytest -q` after fixture change, three separate runs | **Tests PASS / stability FAIL — 3/3 runs had 261 passed, 12 warnings; durations 58.44 s, 49.53 s, 66.63 s.** Native diagnostics in 2/3 runs (two traces in one run); one run was clean. A stack ended in `test_scheduling_contract.py` fixture teardown during `Base.metadata.drop_all()` SQLite PRAGMA schema introspection; another trace was in SQLAlchemy result processor setup. |
| Ruff | `ruff check tests\test_scheduling_contract.py` | **PASS.** |
| Mobile TypeScript | `npx tsc --noEmit` from `mobile/` | **PASS.** |
| Migration scope | No migration changed; migration tests included in focused integration | **PASS for covered migration tests; PostgreSQL service was not rerun.** |
| Staged secrets/data/artifacts | `git diff --cached --name-only` and staged-path check | **None staged.** No credentials, local DB, virtual environment, cache, or generated graph artifact is in the index. |

The scheduling fixture's in-memory `StaticPool` was replaced with a per-test
file-backed SQLite database to avoid sharing one DBAPI connection among the
fixture setup session and TestClient request sessions running on worker
threads. Isolated repetitions no longer reproduced the diagnostic. Three
post-change full-suite runs all passed 261 tests, but two still printed the
native diagnostic (one clean run; one diagnostic run printed two traces).
This is a useful fixture-isolation mitigation, **not a confirmed complete
root-cause fix**. The disposable SQLite files retained by the latest pytest
sessions were removed; pytest's temp directories were left intact. Stability
remains **PARTIAL** and Prompt 21 should not treat the current full-suite
result as clean until the native fault is isolated or independently contained.
The detailed trace, limitations, containment plan, and proposed staging list
are in
[`PROMPT20B_STABILITY_REPORT.md`](backend/docs/stage1/PROMPT20B_STABILITY_REPORT.md).

## 27. Prompt 20C native SQLite fault isolation — 1 November 2026

| Check | Command / setup | Result |
|---|---|---|
| Revision / staged state | `git rev-parse HEAD`; `git diff --cached --name-only` | HEAD `d789f9814da9955db1c63ced921a95379dd08495`; the Prompt 17–20B worktree remained dirty and preserved; index empty; no credentials, local DBs, caches, virtual environments, or generated artifacts staged. |
| Windows environment | `.venv311` interpreter and package versions | Windows 10 build `10.0.26200`; CPython 3.11.9; SQLite 3.45.1; SQLAlchemy 2.0.52; pytest 9.1.1; pytest-asyncio 1.4.0; greenlet 3.5.5. |
| Scheduling alone after 20B mitigation | 3 captured and 1 uncaptured runs | All four runs: 19 passed, no diagnostic. |
| Anomaly/scheduling order | Three runs in each order | Both `anomaly -> scheduling` and reverse emitted diagnostics in 1/3 runs; no deterministic ordering effect established. |
| Reduced anomaly/scheduling combination | Full anomaly module plus one scheduling smoke test, five runs per order | 0/10 diagnostics. Individual anomaly class groups followed by scheduling also did not reproduce in three group runs. |
| Other fixture-order checks | StaticPool API group then scheduling, 3 runs; reverse, 3; shared-memory module group then scheduling, 1 | StaticPool-first 0/3 diagnostics; scheduling-first 1/3; shared-memory group no diagnostic. One ORM-heavy group (billing, anomaly, forecasting, usage) then scheduling printed diagnostics. Results are intermittent and not causal proof. |
| Windows full suite | `..\\.venv311\\Scripts\\python.exe -m pytest -q`, 3 independent processes | 3/3 runs: 261 passed, 12 warnings; durations 58.44 s, 49.53 s, 66.63 s. Native diagnostics in 2/3 runs, none in 1/3. |
| Capture-mode comparison | Full suite with `pytest -s -q` twice and `pytest --capture=sys -q` once | All 3 runs: 261 passed, 12 warnings; no diagnostic. Preliminary association: default fd capture showed diagnostics in 2/3 runs, but samples are too small to infer causality. |
| Linux focused comparison | Disposable `gridsense-api:latest` container; anomaly + scheduling tests | 24 passed, 7 warnings; no diagnostic in the one run. |
| Linux full suite comparison | Same disposable image; `python -m pytest -q` | 261 passed, 13 warnings; no diagnostic in the one run. Container Python 3.11.16 / SQLite 3.46.1; SQLAlchemy 2.0.52 / greenlet 3.5.5 / pytest 9.1.1 / pytest-asyncio 1.4.0. |
| Ruff / mobile / integration | Ruff on scheduling fixture; `npx tsc --noEmit`; scheduling + vertical-slice + migrations tests with `-s` | Ruff **PASS**; TypeScript **PASS**; integration **23 passed**, no native diagnostic. |
| Patch whitespace | `git diff --check` | **PASS.** |

Prompt 20C searched all backend fixtures using SQLite, SQLAlchemy metadata,
TestClient and dependency overrides. Several module-global engines are not
explicitly disposed; several TestClient fixtures use `StaticPool` with
`check_same_thread=False`; and some fixtures clear rather than restore global
dependency overrides. The existing per-test file-backed scheduling fixture
removes one concrete connection-sharing hazard, but none of the audit findings
was isolated as the remaining cause.

**Root cause unresolved; no new source fix was made.** The intermittent native
diagnostic occurs on Windows but was not observed in one Linux full-suite run.
This comparison is limited: the prebuilt Linux image supplied runtime
dependencies, and only pytest test packages were installed in the disposable
container; Python/SQLite versions differ from Windows. Do not treat either
passing pytest counts or Linux's one clean run as proof of stability.

Two Windows full-suite runs with capture disabled and one with Python-stream
capture had no diagnostic. This suggests default file-descriptor capture as a
testable variable, not a proven trigger or containment.

Stability remains **PARTIAL**. Prompt 21 readiness for a clean test baseline is
**BLOCKED** until repeated Windows full-suite runs are free of native
diagnostics or an independently verified containment is documented. See
[`PROMPT20C_NATIVE_FAULT_REPORT.md`](backend/docs/stage1/PROMPT20C_NATIVE_FAULT_REPORT.md)
for the fixture audit, order experiments, trace evidence, environment caveats,
and staging recommendation. No source feature, migration, dependency change,
commit, or push was made for Prompt 20C.

## 28. Prompt 21 scheduling evidence and Windows stability — 1 November 2026

| Check | Command / setup | Result |
|---|---|---|
| Revision / preserved state | `git rev-parse HEAD`; `git diff --cached --name-only` | HEAD remains `d789f9814da9955db1c63ced921a95379dd08495`; Prompt 17–20C worktree edits and existing untracked files were preserved; no files were staged. Existing oddly named SQLite test artifacts and generated graph outputs were not touched or staged. |
| Windows runtime | `.venv311` | CPython 3.11.9; SQLite 3.45.1; SQLAlchemy 2.0.52; pytest 9.1.1; greenlet 3.5.5. |
| Focused advisory regressions | Scheduling contract/optimizer, forecast evaluation, recommendation engine and vertical slice tests | **56 passed, 7 warnings, exit 0.** The run printed `Windows fatal exception: access violation` from SQLAlchemy SQLite `has_table` / `PRAGMA` during `Base.metadata.drop_all()` in the scheduling fixture. Test count does not establish stability. |
| Windows full backend suite | Three independent pytest processes in a disposable copy of the backend, with temporary SQLite database and capture enabled | **3/3 runs: 262 passed, 12 warnings, exit 0.** Native diagnostics occurred in **2/3** runs. One clean run does not establish stability. |
| Linux full backend suite | Disposable `gridsense-api:latest` container, disposable bind-mounted source copy, test packages installed inside `docker run --rm` container | **262 passed, 14 warnings, exit 0; no native diagnostic.** Runtime: Python 3.11.16; SQLite 3.46.1; SQLAlchemy 2.0.52; pytest 9.2.0; pytest-asyncio 1.4.1; greenlet 3.5.5. This differs from Windows and does not isolate a cause. |
| Native traces | Same full-suite logs | Run 2 included SQLAlchemy cursor `fetchall` → SQLite `_get_table_pragma` / `has_table` → `Base.metadata.drop_all()` at the scheduling fixture teardown (`test_scheduling_contract.py:113`). Run 3 included `exec_driver_sql` → SQLite `_get_table_pragma` / `has_table` → the same teardown. The focused run additionally showed `_setup_result_proxy` / `do_execute` frames. Root cause remains unresolved; no suppression or dependency upgrade was introduced. |
| Temporary-run isolation | Disposable copied source tree under `%TEMP%`; tests executed from copied backend working directory | Avoided modifying the pre-existing untracked `backend/file*` SQLite artifacts. An initial run directly from a temporary working directory was invalid because repository tests use CWD-relative Alembic and sample-file paths; it is excluded from the three-run suite result. |
| Focused Ruff | Changed scheduling, forecast-evaluation modules and related tests | **PASS — no findings.** |
| Mobile TypeScript | `npx tsc --noEmit` from `mobile/` | **PASS — exit 0.** |
| Whitespace | `git diff --check` | **PASS — exit 0**, with pre-existing LF/CRLF normalization warnings. |
| Forecast evaluation | Existing UCI generated predictions/metrics inspected; matched baseline-relative metrics computed | Prophet MAE change vs best matched baseline: +7.4% at 1 day, -17.3% at 7 days, -29.9% at 14 days. Nominal 80% interval coverage is about 96% at all three horizons. One French household only; no verified historical weather issue-time features. Forecast advice remains disabled. |
| Migration checks | No Prompt 21 migration added | **NOT APPLICABLE.** |

Prompt 21 integrates preferred, greedy and MILP comparison into the existing
optimizer, adds conservative baseline eligibility and response-scoped
scheduling evidence, and updates the Expo advisory view and chronological
forecast summary. A user-declared measured baseline is blocked because there
is no server-verified submeter/disaggregation source. The synthetic flow is
illustrative, and no schedule is executed.

**Prompt 21 status: PARTIAL. Test stability: BLOCKED.** Prompt 20C's Windows
SQLite native diagnostic remains unresolved and was observed in the focused
run and two of three full-suite repetitions. See
[`PROMPT21_ACCEPTANCE.md`](backend/docs/stage1/PROMPT21_ACCEPTANCE.md) and
[`PROMPT21_FORECAST_EVALUATION.md`](backend/docs/stage1/PROMPT21_FORECAST_EVALUATION.md).
No commit or push was made.

## Prompt 22 — Stage 1 end-to-end baseline

**Assessment: PARTIAL. Windows runtime stability: BLOCKED.**

Baseline revision remains `d789f9814da9955db1c63ced921a95379dd08495`. The worktree
already contained overlapping Prompt 17-21 changes. Prompt 22 added account
state invalidation, per-user weather-location keys, a tariff remediation
action, editable illustrative scheduling inputs, expanded vertical-slice
assertions and structured mobile display of backend validation details. No
migration, external credential, commit, or push was added.

| Verification | Prompt 22 result |
|---|---|
| Focused backend (`test_vertical_slice.py`, `test_scheduling_contract.py`) | **23 passed, 7 warnings** |
| Full Windows backend suite, disposable copy | **262 passed, 12 warnings; exit 0, native SQLite access violation observed** |
| Full Linux Docker suite, disposable copy | **262 passed, 14 warnings; no native diagnostic observed in that run** |
| Focused Ruff | **PASS** |
| Mobile `npx tsc --noEmit` | **PASS** |
| Expo web export | **PASS**; 1,075 modules and 2.38 MB JS entry bundle |
| Browser journeys | **PASS for exercised demo/unavailable paths**; test-only accounts and data |
| ESLint | **BLOCKED**; local executable/configuration unavailable, no configuration changed |
| `git diff --check` | **PASS**, with line-ending normalization warnings |
| PostgreSQL migration check | **NOT APPLICABLE**; no Prompt 22 migration |

The Windows diagnostic occurred during SQLAlchemy SQLite schema
reflection/`PRAGMA` access in test teardown despite exit code 0. This remains
unresolved; Linux passing does not establish Windows stability. AEMO
direction/source-time interpretation, measured appliance-baseline eligibility,
customer tariff confirmation and durable evidence replay remain incomplete.

See
[`PROMPT22_ACCEPTANCE.md`](backend/docs/stage1/PROMPT22_ACCEPTANCE.md),
[`STAGE1_END_TO_END_TEST_REPORT.md`](backend/docs/stage1/STAGE1_END_TO_END_TEST_REPORT.md),
and
[`STAGE1_RELEASE_READINESS.md`](backend/docs/stage1/STAGE1_RELEASE_READINESS.md).
No changes were staged, committed, pushed, reset, or discarded.

## Prompt 23A — Engineering stabilization update (2 November 2026)

This update supersedes the Prompt 23 lint and mobile-dependency status above.
It preserves the historical results and records the Prompt 23A reruns.

| Gate | Command / evidence | Result |
|---|---|---|
| Full backend Ruff | From `backend/`: `..\.venv311\Scripts\python.exe -m ruff check app tests` | **PASS — exit 0; All checks passed.** The 174 findings recorded in Prompt 23 have been fixed without blanket `noqa` or rule suppression. |
| Focused database/API regression | From `backend/`: `..\.venv311\Scripts\python.exe -m pytest tests\test_auth.py tests\test_insights_endpoints.py tests\test_ml.py tests\test_password_reset.py -q` | **PASS — 23 passed, 7 warnings, 27.19 s.** The four fixtures now use per-test `tmp_path` databases and engine disposal. |
| Full backend suite, Windows | From `backend/`: `..\.venv311\Scripts\python.exe -m pytest -q --capture=fd` | **Assertion PASS / stability BLOCKED — 265 passed, 12 warnings, 71.92 s, exit 0; two unsuppressed `Windows fatal exception: access violation` diagnostics.** A SQLAlchemy trace includes `engine.cursor.fetchall`. |
| Full backend suite, Linux | Disposable `gridsense-api:latest` container, read-only backend mount; hash-locked development requirements installed, then `pytest -q -p no:cacheprovider` | **PASS for this Linux environment — 265 passed, 13 warnings, 58.31 s; no native diagnostic found.** This does not resolve the Windows failure. |
| Mobile dependencies | Clean `npm ci` from `mobile/` | **PASS.** Expo 54.0.38, Expo Router 6.0.24, React Native 0.81.5, React 19.1.0, TypeScript 5.9.3. |
| Mobile ESLint | `npm run lint` | **PASS — exit 0.** |
| Mobile TypeScript | `npm run typecheck` | **PASS — exit 0.** |
| Expo SDK compatibility | `npx expo install --check` | **PASS — dependencies are up to date.** |
| Expo web export | `npm run export:web` | **PASS — exported 1,086 modules; 2.42 MB JavaScript entry bundle.** |
| npm security audit | `npm audit`; `npm audit --omit=dev` | **BLOCKED — 49 total (1 low, 43 moderate, 5 high); production tree 36 (1 low, 30 moderate, 5 high).** High advisories remain in `expo-router`, `query-string`, `decode-uri-component`, `image-size`, and `postcss`; no verified SDK-compatible resolution was established. |
| Mobile web modal focus | Code review plus static checks | **PARTIAL.** Automation modal blur/input-focus/restore logic is implemented; browser focus and `aria-hidden` warning verification remains outstanding. |
| PostgreSQL / Redis / authenticated API | Prompt 23 disposable service evidence | **PASS — prior baseline evidence only.** Not rerun in this Prompt 23A pass; not production deployment validation. |
| Hosted CI | GitHub Actions | **NOT RUN.** Local workflow parsing does not establish a hosted pass. |
| Git/source state | `git status`, `git diff --check` | Branch `main`, HEAD `d789f9814da9955db1c63ced921a95379dd08495`; 0 staged paths; 103 tracked modified paths and 657 untracked paths. `git diff --check` exits 0, with CRLF normalization warnings. |

### Test database and preservation note

A controlled reproduction of the legacy SQLite URL
`sqlite:///file:probe?mode=memory&cache=shared` with `uri=True` created a
disk file in the temporary working directory. The four affected test modules
were changed to use `tmp_path` databases; the focused regression passed, and
metadata for the five pre-existing backend-root `file*` artifacts did not
change during that focused run.

At least one earlier run used the legacy URLs before the fixture fix, and no
pre-run hashes or snapshots exist for those artifacts. Their historical
contents therefore cannot be certified as unchanged. They remain preserved
in place; no deletion, rewrite, or speculative restoration was attempted.
See [ENGINEERING_DEFECT_REGISTER.md](ENGINEERING_DEFECT_REGISTER.md),
especially D23A-003 and D23A-004.

Prompt 23A is **PARTIAL / BLOCKED**. The Windows SQLite native diagnostic,
artifact-preservation uncertainty, browser verification, remaining
development-tool advisories, and hosted CI remain open. Prompt 24 should not
begin. See
[PROMPT23A_STABILIZATION_REPORT.md](PROMPT23A_STABILIZATION_REPORT.md) and
[ENGINEERING_DEFECT_REGISTER.md](ENGINEERING_DEFECT_REGISTER.md).

### Post-Prompt 23A mobile SDK/security follow-up

The preceding Prompt 23A section records the Expo SDK 54 mobile state at that
time. It is superseded for current mobile dependencies by the SDK 58
modernization recorded in
[PROMPT23A_STABILIZATION_REPORT.md](PROMPT23A_STABILIZATION_REPORT.md):

| Gate | Command / evidence | Current result |
|---|---|---|
| Expo dependency alignment | `npx expo install --check` | **PASS**, dependencies up to date. |
| Expo project validation | `npx expo-doctor` | **PASS**, 20/20 checks. |
| Public Expo config | `npx expo config --type public --json` | **PASS**. |
| Mobile TypeScript | `npm run typecheck` | **PASS**, exit 0. |
| Mobile lint | `npm run lint` | **PASS**, exit 0. |
| Expo web export | `npm run export:web` | **PASS**, web bundle exported. |
| Full npm audit | `npm audit` | **14 moderate**, 0 high, 0 critical; remaining advisories are development-tool dependencies. |
| Production dependency audit | `npm audit --omit=dev` | **0 advisories**. |
| Mobile modal browser acceptance | Prompt 23B isolated API + Expo web authenticated flow | **PASS for tested flow**; focus entry, Tab navigation, Escape, close control, and focus restoration passed; no `aria-hidden` warning or page error. |

The mobile source includes the SDK 58 package set, updated splash
configuration, TypeScript 6-compatible config and fixes for newly surfaced
React/React Native type and lint errors. A non-forced `npm audit fix` found no
additional compatible updates. Do not treat the zero production audit as a
zero-advisory full tree; the remaining moderate development-tool findings are
tracked as D23A-006.

This follow-up does not change the overall engineering decision. Windows
SQLite native diagnostics, artifact-preservation uncertainty, and hosted CI
remain open; Prompt 24 should not begin.

## Prompt 23B engineering reconciliation

The original verification tables above are historical snapshots from the
named runs. This section records the later Prompt 23B evidence and supersedes
the earlier mobile-browser status; it does not retroactively change results
from those earlier environments.

| Gate | Prompt 23B evidence | Classification |
|---|---|---|
| Windows backend suite / native fault | Seven child-process full-suite runs, same 270-node fingerprint. Each reported 265 passed, 12 warnings, exit 0; four runs emitted six native access-violation diagnostics. | **BLOCKED** |
| Capture-mode comparison | Native diagnostics observed under file-descriptor capture, Python-stream capture, and no capture. | **INCONCLUSIVE as cause; no mode is a remedy** |
| Runtime comparison | Python 3.11.9 / SQLite 3.45.1 compared with isolated Python 3.11.15 / SQLite 3.50.4; newer pair also faulted, but both versions changed together. | **INCONCLUSIVE** |
| Linux locked suite | Three disposable-container full runs on Python 3.11.16 / SQLite 3.46.1; same test fingerprint, 265 passed each, no native diagnostics. | **PASS — scoped to those Linux runs** |
| Mobile browser accessibility | Authenticated Automation browser flow verified modal focus entry, Tab movement, Escape dismissal, close-control dismissal, and focus return; no `aria-hidden` warning or page error. | **PASS — tested flow, not full accessibility certification** |
| SDK 58 security audit | Same-lock audit recorded 14 moderate development-tool advisories and zero production-tree advisories; audit not freshly run in the final reporting pass. | **PARTIAL / prior evidence** |
| PostgreSQL / Redis / full API integration | Prompt 23 evidence exists, but these gates were not rerun in Prompt 23B. | **PARTIAL / NOT FRESHLY VERIFIED** |
| Hosted CI | GitHub Actions was not executed. | **BLOCKED / NOT RUN** |
| Source-only clean-checkout reproduction | Linux tests used a sanitized source copy; no clean checkout of all source candidates was built. | **PARTIAL** |

The reusable child-process diagnostic harness is
[run_native_pytest.py](backend/scripts/run_native_pytest.py); details,
controlled experiment limitations, and the next bounded investigation are in
[PROMPT23B_NATIVE_STABILITY_REPORT.md](PROMPT23B_NATIVE_STABILITY_REPORT.md).
The fault remains unresolved. Four of seven clean-exit Windows processes
emitted native diagnostics, so neither the Windows suite nor the repository
can be called stable. The Linux result does not contain or repair the Windows
fault.

Prompt 23B fixed the reproduced React Native Web modal lifecycle issue in
[automation.tsx](mobile/app/(tabs)/automation.tsx): Escape now requests
closure, and focus restoration waits for `onDismiss`. This was tested against
a disposable migrated SQLite backend and a disposable account. The test does
not constitute a complete browser/assistive-technology audit.

The source inventory in
[STAGE1_SOURCE_CHECKPOINT_PLAN.md](STAGE1_SOURCE_CHECKPOINT_PLAN.md) records
the current review candidate list. At this snapshot HEAD remains
`d789f9814da9955db1c63ced921a95379dd08495`, branch `main`, and no paths were
staged. The source-only checkpoint, hosted CI, current dependency audit,
PostgreSQL/Redis repeat, and historical `backend/file*` artifact certainty
remain unresolved. **Prompt 24 should not begin.**

## Prompt 23C lifecycle follow-up — 2 November 2026

The bounded Prompt 23C lifecycle investigation and fresh gates are documented
in
[PROMPT23C_LIFECYCLE_INVESTIGATION.md](backend/docs/stage1/PROMPT23C_LIFECYCLE_INVESTIGATION.md).
The result is **PARTIAL / BLOCKED**; it does not supersede the seven-process
full-Windows evidence above.

| Gate | Prompt 23C evidence | Classification |
|---|---|---|
| Windows SQLite native stability | Six controlled 25-node A/B runs (three per arm), plus one corrected original-worktree run, emitted no native diagnostic. The prior 4/7 full Windows runs with diagnostics remain unrefuted; no five-process full-suite acceptance sample was run. | **BLOCKED** |
| TestClient/session ownership | Baseline scheduling fixture had 32 SQL operations per run on a thread different from the connection's active checkout thread. Refreshing and detaching the fixture's expired user removed all mismatches in three repeated treatment runs; concurrent DBAPI cursor operations remained zero. | **VERIFIED test-fixture invariant only; native-fault causality unproven** |
| Teardown leak assertions | Deliberate negative control failed before `drop_all()` with one checked-out connection and one active session; correct fixture teardown observed none. | **PASS — assertion validation** |
| Background work | Upload/vertical-slice selection: 13 tests; three background tasks completed, no task errors or teardown leaks. | **PASS — bounded selection only** |
| Backend Ruff | Full `ruff check app tests` | **PASS** |
| Backend focused tests | Scheduling contract: 20 passed; anomaly+scheduling instrumented selection: 25 passed. | **PASS — focused** |
| PostgreSQL migration cycle | Disposable PostgreSQL 16 upgrade to `d1e2f3a4b5c6`, downgrade to base (zero revision rows), and re-upgrade passed. | **PASS — migration round trip** |
| Redis/RQ | Disposable Redis 7 `PING`; RQ `SimpleWorker` executed the actual automation-task function and completed the expected not-found job against a disposable SQLite schema. | **PASS — in-process worker smoke** |
| Authenticated API | Disposable migrated SQLite: registration, login, `/auth/me`, and authenticated `/meters` all succeeded. | **PASS — core journey** |
| Mobile lint / TypeScript / Expo Doctor / web export | All four checks rerun; export output was outside the repository. | **PASS** |
| npm audits | Full tree: 14 moderate, zero high/critical; production tree: zero advisories. | **PARTIAL — development-only risk remains open** |
| Automation modal browser retest | Integrated browser connection timed out before opening a page. Previous Prompt 23B interaction evidence remains; no fresh interaction was executed. | **NOT RE-VERIFIED in Prompt 23C** |
| Hosted CI / clean source checkpoint | Not run / not reproduced from a clean Git clone. | **BLOCKED** |

Prompt 23C corrected the scheduling test fixture by refreshing and expunging
the test `User` before returning it through a dependency override; the fixture
asserts `object_session(user) is None`. This prevents its expired ORM state
from causing a worker-thread lazy load through the setup session. This is a
test-lifecycle correction and is **not** claimed as the Windows native-fault
repair.

The 25-node controlled selection fingerprint was
`5a56558f0f5698d8b55feadd46400862c6c97ecac14ed1e37a273cc889a7072f`.
The result does not qualify as a full-suite stability acceptance run. The
current exact source candidate inventory is 106 tracked modified paths plus
55 untracked source/documentation paths; generated Graphify output and five
legacy `backend/file*` artifacts remain excluded and preserved. No paths were
staged, committed, pushed, reset, or deleted. **Windows stability remains
BLOCKED; Prompt 24 should not begin.**

## Prompt 23D full-suite comparison — 2 November 2026

The full report is
[PROMPT23D_FULL_SUITE_COMPARISON.md](backend/docs/stage1/PROMPT23D_FULL_SUITE_COMPARISON.md).
The original and corrected scheduling fixtures were tested in isolated
source copies with the same CPython 3.11.9, SQLite 3.45.1, dependency lock,
fd capture, and 265-node collection fingerprint
`e5213d53b7243e2d75cdd18cf22e3dbd82e55669c0e10477c4d9e343f602f1ef`.
The original fixture emitted no diagnostic in five complete runs; the
corrected fixture emitted a diagnostic in four of five processes. One
corrected run additionally exposed a Windows active-marker replace/read
race in the test harness and stopped after 263 passes; this separate
harness defect has been corrected. The result does not establish that the
fixture correction caused or increased the access-violation rate, but it
demonstrates that the correction does not eliminate the fault.

Faulthandler stacks in three corrected runs correlated the diagnostic with
SQLAlchemy SQLite table reflection during the scheduling fixture's
`MetaData.drop_all()` teardown. A matched 23-test lifecycle-instrumented
comparison did not reproduce the fault and observed zero checkout-thread
mismatches, concurrent DBAPI operations, or teardown leaks in either arm.
The timing-sensitive native mechanism remains unknown.

One clean source-only copy reproduced 265 backend tests (12 warnings),
full backend Ruff, SQLite Alembic upgrade/current/downgrade/re-upgrade,
mobile clean install, lint, TypeScript, Expo Doctor (20/20), and web export.
The same clean copy reported 14 moderate development-tool audit findings
and zero production advisories. This local copy is not a hosted CI run or a
Git-created clean clone.

| Gate | Prompt 23D evidence | Classification |
|---|---|---|
| Windows SQLite native stability | Baseline 0/5 diagnostics; corrected 4/5. Updated-harness clean-copy run: 0/1. | **BLOCKED — no verified fix** |
| Test-principal ownership | Detached-principal assertion retained; no additional expired/attached ORM override confirmed. | **PASS for known fixture invariant only** |
| Backend Ruff / full suite | Clean copy: Ruff passed; 265 passed, 12 warnings. | **PASS for this run** |
| SQLite migrations | Upgrade to `d1e2f3a4b5c6`, downgrade to base, re-upgrade passed. | **PASS** |
| Mobile lint / TypeScript / Expo Doctor / web export | Clean `npm ci`; all checks passed, Expo Doctor 20/20. | **PASS** |
| npm audits | Full: 14 moderate; production-only: zero. | **PARTIAL — development risk remains open** |
| Hosted CI and token permissions | No hosted run; workflow has no explicit `permissions:` declaration. | **NOT VERIFIED / OPEN** |
| Source checkpoint | Local source-only copy passed; no Git-created clean clone and no staging. | **PARTIAL** |

The exact staging candidate inventory is refreshed in
[STAGE1_SOURCE_CHECKPOINT_PLAN.md](STAGE1_SOURCE_CHECKPOINT_PLAN.md). The
five legacy `backend/file*` artifacts remain preserved with historical
provenance unresolved. No source was staged, committed, pushed, reset,
cleaned, or deleted. Overall status is **PARTIAL / BLOCKED**; Prompt 24
should not begin.

## Prompt 23E baseline additions

- Restricted PostgreSQL (`gridsense-it-pg16-23e`, PG 16.13, port 55433, role `gs_it_23e` non-superuser): 35 passed, 0 skipped, in 3 runs before and 3 after the lint fix, plus Linux container 35/35. Status: PASS.
- SQLite non-integration suite: 275 passed on Linux container and on Windows from a clean copy of the kept source set. Status: PASS for those runs. Windows native fault remains BLOCKED.
- Targeted NEM12 source-time tests: 85 passed (interval, billing, usage analyzer, NEM12 parser).
- Alembic upgrade/downgrade/re-upgrade (head `d1e2f3a4b5c6`) on a disposable DB: PASS.
- Redis 7.4.8 PONG and RQ job result 5: PASS.
- Backend `ruff check app tests`: PASS. Mobile lint, typecheck, expo-doctor 20/20, web export: PASS.
- npm audit: full 14 moderate (dev-only), production 0 — accepted residual risk.
- pip-audit gate on locked deps: BLOCKED (85 vulnerabilities, 15 packages).
- Hosted CI: NOT VERIFIED.
- Hang investigation: not reproduced in 5 bounded runs. Historical evidence retained.

Overall: **PARTIAL / BLOCKED**. Prompt 24 should not begin.

## Security-remediation verification (Prompt 23E-Security)

- Adopted lock `backend/requirements-dev.lock` (SHA256 6A1DE8A5...8997069; 158 pins; hash-locked; Python 3.11 universal).
- Full backend suite: Windows 320 passed / 24 skipped; Linux `python:3.11-slim` 320 passed / 24 skipped (`files/prompt23e-security/linux/full-linux-run-1.txt`). Skips are the PostgreSQL integration tests, which run only when the URL is set.
- Restricted PostgreSQL integration: Windows 35 passed (`pg-windows-run-1.txt`); Linux 35 passed (`linux/pg-linux-run-1.txt`), role `gs_it_23e`, no superuser bypass.
- Alembic: upgrade head, downgrade base, upgrade head, all exit 0 on a disposable schema, dropped afterwards.
- Redis/RQ: job enqueued, worker executed it, status FINISHED, result 5 (`linux/redis-rq-run-1.txt`).
- Windows native SQLite harness: 4 runs. Runs 1, 3 and 4 clean. Run 2 `Native diagnostic: YES`, exit 1. Remains BLOCKED.
- Hang (`test_synthetic_tou_demo_uses_cheaper_start_and_reports_real_tradeoff`): not reproduced in this pass; historical evidence retained.
- Hosted CI: NOT VERIFIED.
- Details: [PROMPT23E_SECURITY_REMEDIATION.md](/C:/Users/Kanad/Desktop/PROJECTS/GridSense/backend/docs/stage1/PROMPT23E_SECURITY_REMEDIATION.md).

## Prompt 23E-Security final sign-off (Task A–D)

- Clean-copy results (314-file manifest, Python 3.11 slim container): Ruff passed; no-PostgreSQL suite 331 passed, 24 skipped; restricted PostgreSQL 355 passed, 0 skipped.
- Hosted CI: NOT VERIFIED. Windows SQLite: BLOCKED and explicitly unsupported.
- Superseded counts from earlier passes (265, 275, 320/24) are retained for history only.
- Overall: **PARTIAL**. Prompt 24 must not begin.
