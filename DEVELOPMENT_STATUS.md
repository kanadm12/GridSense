# GridSense Development Status

**Review date:** 31 October 2026
**Scope:** `backend/` and `mobile/`, with the root README, Docker Compose file, CI workflow, and recent Git history used for project context.

## Executive summary

GridSense is a smart-meter energy analysis product aimed at Victorian households. The intended user journey is to register, import retailer-provided NEM12 interval data, review usage and tariff-backed cost comparisons, and act on recommendations. The current repository contains considerably more than an initial upload-and-chart prototype: a substantial FastAPI service, an Expo/React Native client, tariff and billing calculations, rule-based insights, optional ML and AI services, push notifications, home-automation interfaces, and background processing are present.

The backend has the broadest and most complete feature set. It supports accounts, meters, imports, analytics, tariffs, billing, recommendations, insights, chat, notifications, and automation through a versioned API. Supporting infrastructure includes SQLAlchemy persistence, Alembic migrations, Redis/RQ jobs, a scheduler, operational health checks, Docker Compose services, and a sizable pytest suite.

The mobile app has a broad screen and service surface: authentication, onboarding, dashboard, usage, recommendations, AI chat, automation, settings, NEM12 upload, tariff setup, legal content, notification handling, and a task-scheduling preview connected to the versioned scheduling API. Some mobile capabilities are implemented as services but are not yet fully connected to the active screens and state flows. In particular, offline caching, notification preferences, and onboarding routing remain incomplete. The bill-comparison component is now mounted on the dashboard, but the sample data cannot support a real usage trend until NEM12 direction is verified.

Overall, the repository looks like a feature-rich prototype or pilot approaching production hardening, rather than a fully demonstrated production service. A local isolated API journey, an Expo web acceptance flow, and automated checks have now been run; these do not establish production deployment or external-service integration. See [BASELINE_VERIFICATION.md](BASELINE_VERIFICATION.md) for precise evidence and remaining limits.

## Product and user workflow

The product goal described in the root [README](README.md) is to help households understand electricity consumption, reduce costs, and shift usage toward more suitable times. The user-facing flow represented in code is:

1. Create an account and authenticate.
2. Select or create a meter.
3. Import smart-meter interval data in NEM12 format.
4. Inspect daily/hourly usage and trends; compare bills using a configured tariff.
5. Configure a tariff or retailer plan.
6. Review tailored recommendations, forecasts, anomaly information, and notifications.
7. Optionally connect smart devices and automation rules, and ask the AI chat assistant questions.

This makes the application a combination of an energy-data pipeline, a household analytics service, and an action-oriented mobile client. The stated geographic focus is Victoria/Australia; tariff assumptions and NEM12-specific import behavior are part of the current design.

## System architecture

| Area | Current implementation |
|---|---|
| Mobile client | React Native, Expo SDK 54-era dependencies, Expo Router, Zustand, Axios, and React Native Web. See [mobile/package.json](mobile/package.json) and [mobile/app.json](mobile/app.json). |
| API | Python 3.11+ FastAPI application with routers under `/api/v1`; health endpoints are outside that prefix. See [backend/app/main.py](backend/app/main.py). |
| Persistence | SQLAlchemy models; SQLite is the local default, while the deployment docs and Compose stack use PostgreSQL. See [backend/app/database.py](backend/app/database.py) and [docker-compose.yml](docker-compose.yml). |
| Background work | Redis and RQ worker for imports and other jobs, plus a separate scheduler process. See [backend/app/worker.py](backend/app/worker.py), [backend/app/tasks.py](backend/app/tasks.py), and [backend/app/scheduler.py](backend/app/scheduler.py). |
| Optional external capabilities | OpenAI-backed assistant/RAG, Expo push delivery, SMTP email, and Home Assistant automation. These require corresponding configuration and external services. |

The root [docker-compose.yml](docker-compose.yml) defines PostgreSQL, Redis, API, worker, and scheduler services. It applies database migrations before starting the API and includes health checks. This is a runnable multi-service development/deployment shape in configuration; its successful operation was not verified during this review.

## Backend accomplishments

### API foundations and account flows

The application entry point assembles routers, middleware, CORS, rate limiting, exception handlers, and lifecycle logging. The backend exposes API documentation through FastAPI/OpenAPI when running. The route families include:

- Authentication and account management: register, login, refresh, and current-user lookup in [backend/app/api/auth.py](backend/app/api/auth.py).
- Password reset with local and SMTP delivery options in [backend/app/api/password_reset.py](backend/app/api/password_reset.py) and [backend/app/services/email.py](backend/app/services/email.py).
- Meter creation, listing, retrieval, and deletion in [backend/app/api/meters.py](backend/app/api/meters.py).
- NEM12 file upload and upload-status retrieval in [backend/app/api/upload.py](backend/app/api/upload.py).
- Usage, recommendations, tariffs, billing, notifications, automation, chat, and insights in their corresponding modules under [backend/app/api/](backend/app/api/).
- Liveness/readiness/worker health endpoints in [backend/app/api/health.py](backend/app/api/health.py).

JWT access and refresh tokens are implemented through [backend/app/services/auth.py](backend/app/services/auth.py). Authenticated resource access uses a current-user dependency and dedicated ownership checks for meters, devices, rules, and schedules in [backend/app/api/deps.py](backend/app/api/deps.py) and [backend/app/api/ownership.py](backend/app/api/ownership.py). Rate limiting is wired through SlowAPI. Error response schemas and handlers are centralized in [backend/app/api/errors.py](backend/app/api/errors.py); request logging and structured JSON logging are configured through [backend/app/middleware.py](backend/app/middleware.py) and [backend/app/logging_config.py](backend/app/logging_config.py).

Configuration is centralized in [backend/app/config.py](backend/app/config.py). It covers database and Redis URLs, JWT settings, CORS, email, automation, and debug mode. Production-mode validation rejects weak or missing secrets and wildcard/local CORS origins, and requires appropriate provider settings for SMTP and Home Assistant.

### Data model and persistence

The model layer represents the main application concepts:

- Users, meters, interval readings, daily aggregates, and NEM12 uploads.
- Tariff configuration.
- Password reset records.
- Notification preferences, push tokens, and stored notifications.
- Chat sessions/messages.
- Smart devices, automation rules, schedules, and grid signals.
- ML training job status and metrics.

These are defined in [backend/app/models/](backend/app/models/). Alembic migration configuration and four migration files are present under [backend/alembic/](backend/alembic/). The schema has therefore been given a versioned migration workflow; however, the initial migration delegates to SQLAlchemy `Base.metadata.create_all` rather than spelling out each table operation, making the original schema less explicit to audit than later hand-authored DDL would be.

### NEM12 import and data pipeline

The import path is one of the central implemented product capabilities:

1. The upload API checks the filename/extension and imposes a 50 MB limit.
2. The parser validates the NEM12 input and parses meter details and interval records.
3. The route hashes the uploaded content and avoids re-importing an already completed identical file for the same user.
4. An upload record is created and the work is queued in RQ when Redis is available.
5. The importer associates the data with meters, persists readings, generates daily aggregates, and records status and errors.
6. The upload-status endpoint reports progress and import outcomes.
7. Post-import processing can publish alerts and schedule model training.

The parser, importer, and task implementations are in [backend/app/services/nem12_parser.py](backend/app/services/nem12_parser.py), [backend/app/services/nem12_importer.py](backend/app/services/nem12_importer.py), and [backend/app/tasks.py](backend/app/tasks.py). Tests and a sample input are present in [backend/tests/test_nem12_parser.py](backend/tests/test_nem12_parser.py), [backend/tests/test_upload.py](backend/tests/test_upload.py), and [backend/tests/sample_nem12.csv](backend/tests/sample_nem12.csv).

The initial parser assigned register type `B` to every reading, ignored 400-record quality events, converted blank intervals to zero, and keyed channels without `RegisterID`. Those behaviors were unsafe for multiple channels and unresolved direction. The follow-up implementation now preserves `RegisterID`, `NMISuffix`, quality method/reason fields, handles interval event ranges, skips missing values rather than inventing zeroes, and stores newly parsed direction as `unknown` until an authoritative suffix mapping is verified. Consumption analytics exclude such unknown readings instead of silently treating them as imports. Import tests now cover multiple channels, partial days, quality events, duplicate imports, unit conversion, unsupported units, and the upload size cap.

Direction mapping is still an explicit limitation: the current AEMO MDFF specification describes the NEM12 fields but refers suffix semantics to the separate NMI Procedure; the MDFF example is not sufficient evidence for a universal import/export mapping. Non-kWh/non-Wh UOMs are preserved on the meter but their readings are omitted from kWh analytics with an upload warning. Clock processing now persists interval duration and classifies billing/chart buckets using explicit local interval boundaries, with Melbourne DST transition tests. The fixed UTC+10 interpretation of source NEM12 timestamps still needs confirmation against an authoritative AEMO clock-basis reference.

### Usage, tariffs, billing, and recommendations

The deterministic analytics foundation is implemented in [backend/app/services/usage_analyzer.py](backend/app/services/usage_analyzer.py). It calculates usage summaries, daily and hourly patterns, and time-of-use breakdowns. The usage API exposes summary, daily, hourly, and weekly views. It no longer applies a default flat rate: estimated usage-cost fields are null because the analyzer does not price readings against the user's configured tariff.

Tariff and bill calculation are implemented in [backend/app/services/tariff.py](backend/app/services/tariff.py) and [backend/app/api/billing.py](backend/app/api/billing.py). The shared tariff classifier buckets readings into peak, shoulder, and off-peak periods. Billing supports flat, time-of-use, and custom weekday-window pricing; effective dates; supply charges; explicit export feed-in credits; optional GST treatment; period comparisons; and monthly summaries. Comparison responses now include rounded line-item breakdowns, interval coverage and direction status, and explicit limitations. Missing tariff data uses labelled illustrative defaults rather than representing those values as an actual retailer bill.

Retailer presets are marked illustrative. Bill totals reconcile to the included line items at cent precision, and GST-inclusive components are shown as memo amounts rather than added a second time. Custom schedule gaps are surfaced as unpriced intervals; readings with unresolved direction are excluded from charges. The bill-comparison component is mounted on the dashboard and labels unavailable trends when no classifiable import readings exist. See the Prompt 04 and Prompt 05 entries in [BASELINE_VERIFICATION.md](BASELINE_VERIFICATION.md) for calculation behavior, vertical-slice results, and remaining assumptions.

The tariff API in [backend/app/api/tariffs.py](backend/app/api/tariffs.py) supports user tariff configuration and presets. The mobile app also contains tariff setup for retailer presets and custom rates. The recommendation engine in [backend/app/services/recommendation_engine.py](backend/app/services/recommendation_engine.py) identifies observed patterns and possible actions; it does not claim quantified energy or dollar savings. The bill comparison component in [mobile/components/BillComparison.tsx](mobile/components/BillComparison.tsx) is mounted on the dashboard and displays period estimates, breakdowns, disclosures, and unavailable-trend messaging.

### Forecasts, anomaly detection, ML, and AI

There are two complementary analytics layers:

- Deterministic usage projection and trend calculations in [backend/app/services/forecasting.py](backend/app/services/forecasting.py); cost fields are null until configured-tariff pricing is integrated.
- Rule-based anomaly detection and insight APIs in [backend/app/services/anomaly_detector.py](backend/app/services/anomaly_detector.py) and [backend/app/api/insights.py](backend/app/api/insights.py).

An optional per-meter ML pipeline is implemented under [backend/app/ml/](backend/app/ml/). It extracts daily time series, trains Prophet daily forecasts and scikit-learn IsolationForest anomaly detectors, supports command-line training, and loads serialized per-meter model artifacts for predictions. Training can be triggered after import or through scheduled retraining. The documentation identifies these as baseline models and notes that deterministic billing/anomaly behavior remains available when data is insufficient or ML training is not usable. The system does not appear to include a model registry, model-version governance, drift monitoring, or a full evaluation/approval lifecycle.

AI chat is implemented through [backend/app/api/chat.py](backend/app/api/chat.py), [backend/app/services/chat_service.py](backend/app/services/chat_service.py), [backend/app/services/ai_assistant.py](backend/app/services/ai_assistant.py), and [backend/app/services/rag_engine.py](backend/app/services/rag_engine.py). It combines user usage context and retrieval with an OpenAI API call and has a fallback response path when the external service is unavailable. The capability is optional and depends on external credentials and service availability; it is not a local self-contained model.

### Notifications, alerts, and scheduled work

The notification subsystem stores push tokens, notifications, and user preferences. The API supports token registration/removal, preference management, unread counts, notification listing, and read-state updates. [backend/app/services/notification_service.py](backend/app/services/notification_service.py) handles persistence and Expo push delivery.

[backend/app/services/alert_service.py](backend/app/services/alert_service.py) connects anomaly detection, forecasts, recommendations, ML-training status, and weekly summaries to notifications. The current alert behavior includes:

- Post-import anomaly and high-priority recommendation notices.
- ML-training completion notices.
- A high-bill check that is suppressed while the forecast has no tariff-backed cost.
- Weekly energy summaries that report kWh, not an assumed dollar cost.

Stable deduplication keys and notification preferences are part of the alert design. [backend/app/scheduler.py](backend/app/scheduler.py) schedules weekly retraining and summaries, daily bill checks, and minute-based automation schedule checks. [backend/app/tasks.py](backend/app/tasks.py) provides the queued work, while [backend/app/worker.py](backend/app/worker.py) starts the RQ worker.

When Redis/RQ is unavailable, the upload endpoint can fall back to FastAPI in-process background execution. This is convenient during development but is not durable in the same way as a persistent job queue: an API process failure can interrupt that fallback work.

### Smart-home automation

The automation API supports device management and commands, rule creation/toggling/manual execution, schedules, suggestions, and grid-signal retrieval. The provider abstraction in [backend/app/services/automation_provider.py](backend/app/services/automation_provider.py) includes a simulator and a Home Assistant implementation. The simulator is the default; real Home Assistant operation requires URL/token configuration and compatible device/entity identifiers.

### Documentation and test foundation

The backend includes operational and feature documentation for alerts, backup/restore, deployment, workers, ML training, and phase implementation details. Relevant materials are in [backend/docs/](backend/docs/) and [backend/backend-ml-README.md](backend/backend-ml-README.md).

The pytest suite covers authentication, configuration, email, password reset, rate limits, uploads, NEM12 parsing/import, usage, billing, tariff validation, migration behavior, forecasting, ML, anomalies, notifications, insights, and an authenticated upload-to-billing API journey. The latest full backend suite passed **128 tests with 10 warnings**. Focused Ruff checks, `git diff --check`, mobile TypeScript checking, and Expo web export passed. Mobile ESLint could not be run because its executable is not installed in the current workspace dependencies. A local Expo browser flow verified upload/error/duplicate messaging, tariff setup, authentication recovery, and unavailable-trend display. Visible coverage gaps include dedicated recommendation-engine and alert-service tests, broader automation/chat integration tests, and end-to-end testing against real PostgreSQL, Redis/RQ, OpenAI, and Home Assistant services.

## Mobile accomplishments

### Screens and navigation

The app uses Expo Router file-based navigation. The route structure is under [mobile/app/](mobile/app/):

- Authentication: login, registration, and forgot/reset-password flow.
- Onboarding: a four-step introduction to finding meter data, importing it, and using personalized energy tips.
- Main tabs: dashboard, usage, AI chat, automation, recommendations/tips, and settings.
- Additional flows: NEM12 upload modal, tariff setup, privacy, and terms.

The root route and auth guards select either the auth stack or the authenticated tabs. The dashboard loads meters and usage data, shows key metrics and quick actions, and supports pull-to-refresh. The usage screen presents daily/hourly information in charts. Recommendations show savings potential and recommendation cards. Settings support meter selection/deletion, uploads, tariff setup, legal links, and sign-out.

The mobile implementation extends beyond the feature list and smaller project structure in [mobile/README.md](mobile/README.md). For example, the README does not yet describe the implemented chat, automation, tariff setup, onboarding, legal pages, and several service-level capabilities.

### API integration and state management

[mobile/services/api.ts](mobile/services/api.ts) provides a shared Axios client with bearer-token injection, a 30-second timeout, API modules for authentication/meters/uploads/usage/recommendations, and a refresh-token flow that queues concurrent requests while refreshing.

Tokens are stored in Expo SecureStore on native platforms and AsyncStorage on web. Zustand stores in [mobile/stores/index.ts](mobile/stores/index.ts) manage authentication, meters, usage, and recommendations. The auth store validates saved credentials through `/auth/me`; the meters store persists the selected meter per signed-in user; logout clears selected-meter and usage state. The usage store loads summary, daily, and hourly data concurrently.

The API URL selection includes development-oriented behavior such as using the web hostname or Expo debugger host, and falls back to `http://localhost:8000/api/v1`. A production deployment must provide a real API URL and HTTPS endpoint rather than relying on these local-development assumptions.

### Upload, tariff, automation, and chat flows

The upload screen in [mobile/app/upload.tsx](mobile/app/upload.tsx) uses Expo Document Picker, tracks idle/selected/uploading/success/error states, submits the selected file, polls backend status, and displays duplicate-upload results, parser errors, and coverage/direction warnings. Tariff setup in [mobile/app/tariff-setup.tsx](mobile/app/tariff-setup.tsx) supports retailer presets and custom flat/time-of-use rates and displays save confirmation/errors on web. The dashboard exposes usage errors and a mounted bill comparison; it reports the trend as unavailable when there are no classifiable imports. The automation screen calls backend endpoints for devices, rules, suggestions, grid signals, and commands. The chat screen loads a welcome message and sends prompts to the backend; conversations are held locally in the screen rather than persisted as a durable mobile conversation history.

### Notifications, offline support, and errors

[mobile/services/notifications.ts](mobile/services/notifications.ts) handles native permissions, Expo push-token registration, foreground/response listeners, preference calls, local scheduling, badge helpers, and reminder helpers. The root layout registers notifications for authenticated users. However, notification listener callbacks are currently no-ops, notification taps do not deep-link to relevant content, web push is skipped, and the Expo project ID in [mobile/app.json](mobile/app.json) is still a placeholder.

Offline infrastructure exists in [mobile/services/offline.ts](mobile/services/offline.ts) and [mobile/components/OfflineBanner.tsx](mobile/components/OfflineBanner.tsx): NetInfo connectivity checks, AsyncStorage cache entries with TTL/stale reads, last-sync tracking, and a reusable banner. The main stores and screens do not visibly call the cache helpers, so offline support is not yet demonstrated as a connected end-to-end user experience. The banner is also not visibly mounted app-wide.

[mobile/services/errorHandler.ts](mobile/services/errorHandler.ts) defines error parsing, classification, alerts, logging, and retry helpers; [mobile/components/ErrorFallback.tsx](mobile/components/ErrorFallback.tsx) provides a reusable fallback UI. These utilities are only partially integrated: screens use a mix of store errors, API error parsing, and direct response inspection, and a global router-level error boundary is not visible.

### UI, theme, platform, and build setup

[mobile/constants/theme.ts](mobile/constants/theme.ts) centralizes colors, spacing, typography, shadows, chart colors, and gradient presets. Reusable UI includes an error fallback, offline banner, and bill comparison component. The project configuration targets iOS, Android, and web; the package manifest uses Expo SDK 54-era dependencies, React 19, React Native 0.81, Expo Router, SecureStore, notifications, document picking, gifted charts, and React Native Web.

The package declares `lint` and `test` scripts, including Jest, and the root CI workflow includes a TypeScript check. No mobile test files were visible in the reviewed source inventory. The mobile README still says Expo SDK 50 and includes older `expo build:*` guidance, so setup documentation should be refreshed to match the current package versions and modern EAS configuration.

## End-to-end behavior represented in code

The most complete cross-component path is the meter-data import and analysis flow:

**Mobile document selection → authenticated upload → validation/hash/deduplication → RQ or local background import → meter/readings/daily aggregates → usage/billing/recommendations/insights → alert and optional ML job → mobile refresh/status display.**

Other integrated paths include:

- **Authentication:** mobile login/register → backend JWT issuance → token storage/refresh → authenticated `/auth/me` checks.
- **Tariffs:** mobile preset/custom tariff setup → backend tariff persistence → billing and comparison calculations.
- **Notifications:** mobile device token registration → backend preferences and notification storage → Expo push delivery; tap routing remains unfinished.
- **Automation:** mobile device/rule controls → backend provider abstraction → simulator or configured Home Assistant entity.
- **AI assistance:** mobile chat → backend usage context/RAG/OpenAI integration → response in the chat screen.

The authenticated upload-to-billing path has now been exercised with an isolated API test and a local Expo browser flow. The browser flow confirms the expected no-usage/unavailable-trend behavior for the current sample, not a successful measured-consumption comparison. Operation against external services such as PostgreSQL, Redis/RQ, OpenAI, and Home Assistant remains unvalidated.

## Recommendation and estimate transparency — Prompt 06

The recommendation engine previously contained fixed savings assumptions, including a 10 c/kWh rate spread, a 25% evening-use target, a 30% reducible overnight share, and appliance/solar conclusions inferred from aggregate meter data. Those savings calculations and causal claims were removed. Recommendations now separate observed interval facts from possible actions, show their baseline, assumptions, applicable intervals, uncertainty, interpretation confidence, and required inputs, and return null potential energy and dollar savings. The review thresholds still used to surface patterns are internal flags, not household benchmarks or savings targets.

A rate spread is shown only when a configured, non-illustrative tariff is effective today and has usable rates. It is explicitly not represented as savings. Recommendations remain unquantified because the product has no user-declared appliance model, appliance demand, or feasible operating-window input. Example automation schedules likewise no longer display invented savings or confidence scores. AI assistant instructions and fallback replies distinguish observed usage from inference and direct users to tariff/bill comparison for monetary estimates.

The same fixed-rate behavior was removed from usage summaries, dashboard and daily usage cost displays, monthly cost forecasts, forecast trends, daily briefs, high-bill alerts, and weekly notifications. Those usage/forecast cost values now return null or are omitted, and the mobile UI explains that bill comparison is the tariff-backed estimate surface. Forecast confidence and cost-range values are also null rather than preserving unsupported default-rate ranges.

Validation for Prompt 06 is recorded in [BASELINE_VERIFICATION.md](BASELINE_VERIFICATION.md). The recommendation, usage, forecast, and insights tests cover null cost behavior and transparent recommendation evidence. The configured-tariff bill comparison remains an estimate, not a retailer invoice; preset tariffs may be illustrative, and NEM12 direction and source clock basis still require authoritative verification.

## Versioned scheduling contract — Prompt 07

Added the authenticated `POST /api/v1/scheduling/v1/plans/preview` endpoint and a versioned `1.0` JSON contract. Requests identify a meter and scenario, provide an IANA timezone and interval duration, describe flexible tasks using exactly one energy input (`rated_power_kw` or `energy_kwh`), and include a fixed baseline profile. Validation enforces time-grid alignment, explicit offsets consistent with the named timezone, task windows and duration constraints, baseline interval contiguity and non-overlap, and baseline provenance. Raw net-meter demand is not accepted as an independent baseline.

The endpoint enforces meter and tariff ownership. Tariffs must have usable, non-illustrative rates applicable to the requested horizon; missing or unusable rates block planning explicitly. This milestone initially returned `not_evaluated` for a usable tariff; Prompt 08 below adds bounded optimization while retaining the same validation contract and preview-only behavior. At this milestone the mobile client had matching TypeScript request/response types and a preview helper; Prompt 09 below adds the screen that invokes it.

OpenAPI request/response examples are kept in parity with the synthetic versioned fixture at [backend/tests/fixtures/scheduling_v1.json](backend/tests/fixtures/scheduling_v1.json). Prompt 07 validation and its test evidence are recorded in [BASELINE_VERIFICATION.md](BASELINE_VERIFICATION.md).

## MILP scheduling preview — Prompt 08

The scheduling preview now evaluates fixed-power, non-interruptible tasks with binary start-time variables using SciPy's `scipy.optimize.milp` and its bundled HiGHS solver. Required tasks receive exactly one start; optional tasks can be omitted and support an AUD omission penalty. An optional task without that penalty uses an explicit no-savings treatment. Candidate starts must fit the allowed window, duration, and deadline. Optional household and grid power caps apply to baseline plus all overlapping scheduled load.

The objective adds interval energy charges, a configurable preference penalty per interval away from a requested start, and optional-task omission penalties. The fixed baseline is included once and is never added to itself as if it were flexible load. The response exposes candidate and reference energy costs, energy-cost delta, preference/omission penalties, and total objective; the delta compares against the rule-based reference and is not household savings. Daily supply and demand charges are outside this first optimizer.

The endpoint also returns a deterministic greedy comparator using the same task inputs, interval prices, baseline, windows, preferences, and limits. It is labelled as a reference, not an optimum. Infeasible and timeout results are explicit; on timeout the endpoint does not substitute the comparator as a candidate. The preview does not persist plans, issue device commands, or include batteries, PV curtailment, or demand response. Synthetic baselines are identified in response assumptions.

The mobile API types represent the optimizer's request and response fields, including timeout, omission, and comparator status. Prompt 09 below connects the preview endpoint to a mobile demonstration screen. Solver licensing/platform review, test evidence, and remaining backend limitations are recorded in [BASELINE_VERIFICATION.md](BASELINE_VERIFICATION.md).

## Mobile scheduling demonstration — Prompt 09

The Expo app now exposes a **Plan a Task** action from the dashboard and registers a modal `scheduling` route. The screen loads the user's selected meter and tariff, renders tariff windows, and submits the existing authenticated v1 preview contract. Its demo preset clearly labels a fixed 0.8 kW synthetic baseline and an estimated appliance load; neither is represented as measured household behavior.

The task form captures appliance, estimated power, one of four durations (30–120 minutes), earliest start, latest finish, optional preferred start, and required/optional status. Times are entered as meter-local wall time and converted to explicit offsets using the meter's IANA timezone; invalid date/time values, off-grid 15-minute values, and nonexistent daylight-saving times are rejected. Optional tasks can specify an AUD omission penalty or leave it blank to use the backend's explicit no-savings treatment.

The preview displays the original preference, MILP candidate (including an explicit omitted-task result), deterministic reference, tariff assumptions, modeled energy-cost comparison, preference/comfort shift, and backend blockers for blocked, infeasible, and timeout outcomes. It distinguishes energy charges from the full bill and never claims household savings. **Keep recommendation / Keep task omitted** and **Keep original** only change a local preview choice; editing the form clears the old result. No plan is persisted and no device is controlled.

Prompt 09 browser verification and its test evidence are recorded in [BASELINE_VERIFICATION.md](BASELINE_VERIFICATION.md). The web result screenshot is [prompt09-scheduling-result.png](mobile/prompt09-scheduling-result.png).

## Forecast evaluation — Prompt 10

Added a repeatable, leakage-conscious evaluation command for daily household active-energy forecasts. It downloads the UCI Individual Household Electric Power Consumption dataset on first run (or accepts an extracted local file), records dataset digests and package versions, and produces predictions, metrics, a chart, a machine-readable configuration, a dataset README, and a results report. The evaluation uses one French household and daily kWh derived from minute-average `Global_active_power`; it does not identify PV generation, meter import/export direction, or a GridSense customer's underlying load.

Minute readings are not interpolated. Days below 99% expected coverage are excluded, with expected sample counts accounting for Europe/Paris daylight-saving days. The retained calendar is split chronologically into train, validation, and test ranges (70/15/15). Seven-day expanding origins compare persistence, a 28-day historical weekday mean, and a Prophet fit; forecasts are evaluated at 1-, 7-, and 14-day horizons. Each fit only uses valid observations through its origin. Repeated predictions overlap and are not independent samples.

The completed run retained 1,407 daily targets and wrote 504 forecast rows and 72 summary rows. On the held-out test period, Prophet MAE was **5.320 kWh** (1 day; 28 forecasts), **3.169 kWh** (7 days; 29 forecasts), and **3.269 kWh** (14 days; 28 forecasts). The corresponding persistence MAEs were 4.952, 3.832, and 4.893 kWh; weekday-mean MAEs were 6.158, 4.154, and 4.665 kWh. Prophet's nominal 80% interval coverage was 96.4%, 96.6%, and 96.4%, with mean widths around 17–18 kWh. These descriptive results are from one old French household and small, overlapping forecast samples; they do not establish deployment accuracy or interval calibration, and they support no bill or savings claim. See [backend/reports/forecast_evaluation/REPORT.md](backend/reports/forecast_evaluation/REPORT.md) for all test metrics and limitations.

Run from `backend/` with `python scripts/evaluate_forecasting.py`; outputs are written to `backend/reports/forecast_evaluation/`. Dataset attribution and preprocessing details are in [backend/docs/forecast-evaluation-dataset.md](backend/docs/forecast-evaluation-dataset.md). Focused test and command evidence is in [BASELINE_VERIFICATION.md](BASELINE_VERIFICATION.md).

## Research-grade scheduling experiment audit — Prompt 11B

The Prompt 11 benchmark has been revised to distinguish algorithm effects from information effects and to make every reported energy charge reproducible. It remains a **synthetic sensitivity experiment**, not evidence about measured customers or observed Australian retail tariffs. Full methods, assumptions, and limitations are in [backend/docs/scheduling-experiment.md](backend/docs/scheduling-experiment.md); generated values and figures are in [backend/reports/scheduling_experiment/REPORT.md](backend/reports/scheduling_experiment/REPORT.md).

The six strategies are preferred-start S0, greedy nominal S1, nominal-price MILP S2, forecast-informed MILP, a perfect-information MILP optimizing energy plus the preference penalty, and a separate energy-only oracle. S1 and nominal S2 receive the identical nominal price vector. Thus nominal S2-minus-S1 is the algorithm comparison; forecast-MILP-minus-nominal-MILP isolates forecast information. The oracle receives realized prices. The energy-only oracle uses zero preference penalty and is a lower bound only for modeled energy charge within this feasible set.

The default design reuses **eight generated profiles** across 192 factorial cells (2/6/10-hour flexibility, spread factors 0/1, forecast-error factors 0/0.5, and light/mixed appliance tasks), yielding 1,152 strategy rows and 576 paired comparison rows across three comparisons. The 192 cells are not 192 independent households; profile-level intervals average repeated comparisons within the eight profiles and are descriptive, not population inference.

Every feasible strategy charge is recomputed from the exported interval-level realized prices, baseline demand, and exported appliance schedules after reloading the three CSV files. Runs fail if charge reconciliation differs by more than **1e-8 AUD**. `non_flexible_baseline_energy_cost_aud` is fixed non-flexible demand cost; the legacy `baseline_energy_cost_aud` remains an alias for compatibility and is not the full S0 cost. `s0_reference_energy_cost_aud` is the complete preferred-start charge.

In the executed default experiment, mean energy charges were **$7.3591** (S0), **$6.8873** (greedy nominal), **$6.8861** (MILP nominal), **$6.8955** (MILP forecast), **$6.8616** (perfect-information MILP), and **$6.8577** (energy-only oracle). These aggregate means are descriptive only. The matched nominal MILP-minus-greedy mean difference was **−$0.0011**, with a profile-level 95% descriptive t interval of **[−$0.0039, $0.0016]** and 4/2/186 matched energy wins/losses/ties. This does **not** establish MILP superiority over greedy. Forecast MILP minus nominal MILP was **+$0.0094** (95% interval **[−$0.0060, $0.0247]**, 62/32/98 wins/losses/ties); this does not establish a general advantage from forecast information. The energy-only oracle's lower mean energy charge is accompanied by a higher mean weighted objective (**$6.9853**) and more mean inconvenience (**6.38 h**) than the perfect-information MILP (**$6.9122**, **2.53 h**), illustrating why energy charge alone does not establish a superior schedule.

Robustness outputs include a valid single-slot window made infeasible by a power cap, overlapping mandatory tasks that jointly exceed the cap, baseline demand already above the cap, an injected solver failure explicitly recorded as `solver_error`, and a measured greedy-suboptimal case where MILP energy charge is **$4.95 lower**. That constructed case is a stress example, not a population-wide claim. Synthetic prices assume a known nominal TOU profile; realized and forecast perturbations are uncalibrated Gaussian sensitivity parameters with a $0.01/kWh floor. Their post-clipping deviations need not remain zero-mean and are not calibrated from observed retail or forecast data.

The output includes `results.csv`, `summary.csv`, paired CSVs, `interval_prices.csv`, `task_schedules.csv`, `robustness.csv`, `config.json`, three synthetic-labeled figures, and the generated `REPORT.md`. The default run was executed twice; all checked result data matched exactly except hardware-dependent runtime fields. The experiment, optimizer, and API contract suites reported **35 passed, 6 warnings**. Windows also printed native SQLAlchemy access-violation messages during the contract tests even though pytest exited successfully; this remains an environment/test-process concern. Ruff formatting and lint checks passed for the changed experiment files. The full command and environment are recorded in [BASELINE_VERIFICATION.md](BASELINE_VERIFICATION.md).

## Equity and distributional evaluation — Prompt 12

Added predeclared evaluation definitions to the synthetic scheduling experiment before its equity outcome tables: technical eligibility of complete input data (not human software access), technical feasibility/completion, and modeled benefit distribution using realized energy-charge levels, absolute AUD savings versus matched S0, inconvenience, and weighted-objective change. Economic worth is not classified because no acceptable-benefit threshold is declared; practical actionability, user acceptance, and device execution are not measured. Negative savings remain visible. Generated-profile counts, profile-level descriptive intervals, and distribution quantiles are reported; repeated configurations are not independent observations.

The only available groups are **synthetic flexibility-hour** and **appliance-mix** categories. No housing tenure, income, health, demographic, or protected-group labels are inferred. Available input profiles do not encode verified PV/BESS/generation/DER ownership, and an EV charging task is only a modeled load. Those population and DER comparisons are therefore marked missing/not estimable, not imputed. The new [equity provenance ledger](backend/reports/scheduling_experiment/equity_provenance.csv) records fields, definitions, unavailable categories, and interpretation boundaries.

The executed default run generated 15 synthetic group summaries. All 64 scenario cells in each flexibility category and all 96 cells in each appliance-mix category had technically eligible inputs and zero technically infeasible/incomplete schedules for the three implementable strategy variants; these figures measure only this designed simulation, not real software access or practical user actionability. The regenerated flexibility CSV reports `technically_incomplete_or_infeasible_*` fields explicitly and retains `no_actionable_*` aliases for compatibility. The 2-hour-versus-wider sensitivity has **32/32 ties under flat synthetic prices and 0/32 under TOU prices** for each strategy at both comparator windows. Thus all ties are attributable to flat-price cases in this run; flat-price ties are not evidence of equivalent performance under TOU tariffs. In matched sensitivity cases, 2-hour flexibility minus 6-hour flexibility changed mean modeled savings by **−$0.4040** for greedy nominal, **−$0.4074** for nominal MILP, and **−$0.4160** for forecast MILP; the eight-profile descriptive intervals were below zero. Relative to 10-hour flexibility, the corresponding differences were **−$0.5642**, **−$0.5642**, and **−$0.5887**. The shorter window also reduced mean start-time inconvenience in this constructed setup. As a counterexample to a guaranteed benefit claim, **3 of 192 forecast-MILP cases** had negative modeled savings versus S0; the worst was **−$0.1889 AUD**. These are scenario sensitivities—not claims about a demographic group or energy-equity impact.

The generated [equity summary](backend/reports/scheduling_experiment/equity_summary.csv), [limited-flexibility sensitivity](backend/reports/scheduling_experiment/equity_flexibility_sensitivity.csv), [constructed boundary cases](backend/reports/scheduling_experiment/equity_boundary_cases.csv), [distribution figure](backend/reports/scheduling_experiment/equity_savings_distribution.png), and [provenance ledger](backend/reports/scheduling_experiment/equity_provenance.csv) accompany the updated [research report](backend/reports/scheduling_experiment/REPORT.md). Boundary checks execute a mandatory single-start task and a case where **$0.005** possible modeled charge reduction is outweighed by a **$0.01** shift penalty; unavailable appliances are marked not representable rather than treated as feasible. Focused experiment, optimizer, and API-contract tests reported **38 passed, 6 warnings**; Ruff format and check both passed. No poverty-reduction, demographic-fairness, verified-access, or measured-customer-benefit conclusion is supported. A future valid equity evaluation depends on consented and governed demographic provenance, actual app/accessibility/uptake observations, and source profiles with validated DER dimensions.

## Operational reliability and demo safety — Prompt 13

Per-user SHA-256 uniqueness now prevents duplicate upload rows for the same file. The new Alembic revision preserves duplicate legacy upload records but leaves one canonical hash (preferring a completed record) and clears duplicate hashes before creating the unique index. Repeated submissions reuse the upload ID; an RQ terminal failure can be re-enqueued, and the importer skips timestamps committed before a retry. The in-process Redis fallback owns a separate database session rather than borrowing a request-scoped session. Its limitation remains explicit: it is not durable, and a process crash can interrupt work without an automatic outbox/recovery mechanism.

Readiness now returns HTTP 503 with a non-sensitive dependency status when the database cannot be reached. Worker health uses an explicit 503 for Redis failures. Import/queue errors use safe messages and error types; meter identifiers and push tokens are excluded from the changed import/push logs. Alert publication and optional model-training enqueue failures no longer reverse a completed import. OpenAI remains optional and falls back locally without a key; local email and simulator automation remain defaults, while Expo push and Home Assistant are optional integrations. The Compose API no longer hard-depends on Redis; worker/scheduler services still require it.

Added [synthetic demo seed/reset instructions](backend/docs/demo-data.md) and a seed script restricted to the dedicated `gridsense-demo.db` SQLite filename. It creates a clearly synthetic account, meter, interval data, and tariff; its password must be supplied through a local environment variable. The reset operation drops tables only in that dedicated demo database.

The final backend suite reported **188 passed, 11 warnings**. An earlier Windows run printed native access-violation diagnostics during teardown of an existing SQLite scheduling-contract fixture; the final run exited 0 without reproducing them. Ruff formatting passed for the changed Python files. Default Ruff lint still reports four pre-existing findings in the edited AI/notification modules (one trailing whitespace and three SQLAlchemy boolean-comparison rules); the changed-file lint run passes when only those recorded legacy rules are excluded. `docker compose config --quiet` passed, but `docker info` could not connect to the Docker Desktop Linux-engine named pipe on 2026-10-31. The backup guide's compressed-archive validation command was corrected, and [a disposable PostgreSQL restore verifier](backend/scripts/verify_postgres_restore.sh) now compares core table counts while refusing to overwrite an existing restore target. Its Bash syntax and argument guard pass, but the verifier could not be run against PostgreSQL. Therefore a fresh Compose run, real Redis outage/worker restart, PostgreSQL staging migration, and staging backup/restore remain **unverified**. Tests simulate Redis enqueue failure and a worker-task interruption after a committed chunk; they do not substitute for killing/restarting a real Compose worker.

## Stage 1 demonstration package — Prompt 15

Added a timed 5–7 minute [demo runbook](backend/docs/demo/DEMO_RUNBOOK.md), [product one-pager](backend/docs/demo/PRODUCT_ONE_PAGER.md), [deck outline](backend/docs/demo/DECK_OUTLINE.md), and [claim-evidence matrix](backend/docs/demo/CLAIM_EVIDENCE_MATRIX.md). The seed now creates distinct synthetic analytics and scheduling accounts: the former retains 48 known-import intervals and a 30 c/kWh flat tariff; the latter has no meter readings and a clearly labeled invented TOU schedule. This separation is required by the current one-tariff-per-user data model and does not provide a consumption-derived scheduling pipeline. The optional fabricated NEM12 parser fixture still imports 336 rows with unresolved direction and cannot be used for consumption analytics.

The [Stage 1 architecture diagram](backend/docs/demo/architecture.svg) was redrawn as a scalable, readable SVG showing the app/API/database/worker boundary, separate research paths, and unverified deployment stages. The [visual guide](backend/docs/demo/SCREENSHOTS.md) uses the existing readable schedule-preview capture and generated experiment figures, with captions and capture guardrails; no data was altered or template placeholder represented as a product screenshot. The evidence matrix states which claims can be narrowed to executed tests/results and which claims (actual Australian household savings, equity impact, device automation, production security/recovery) must remain conceptual or unclaimed.

The added synthetic TOU regression test exercises the preview API with a 2.4 kW, 60-minute task, 06:00–10:00 window, and 09:00 preferred start. It verifies the 06:00 MILP and greedy schedules, $0.68 fixed-baseline energy charge, $0.92 total energy charge, $0.06 preference penalty, $0.98 weighted objective, and a $0.36 modeled task-energy-charge difference from the 09:00 fixed-start counterfactual. This is a synthetic scenario, not household savings; both methods choose the same schedule. The mobile result now displays candidate and reference weighted objectives alongside the cost comparison.

The focused demo/upload/scheduling suite reports **41 passed, 6 warnings**; changed-file Ruff lint and mobile TypeScript validation pass. A first targeted run initially failed only because the test expected UTC serialization while the API returned the equivalent Melbourne offset; the assertion was corrected and the rerun passed. A live local browser walkthrough verified the synthetic analytics dashboard (12.96 kWh for one local day, rounded to 13.0 kWh in the UI, plus an explicitly partial $3.89 active-energy estimate) and the separate TOU scheduling preview with the expected 06:00 candidate, 09:00 preference, $0.06 inconvenience penalty, and matching $0.98 weighted objectives for MILP and greedy. Screenshots were captured during this session, but not saved as repository assets; the entire timed walkthrough, parser-upload screen sequence, and fallback video recording remain pending. The top dashboard summary's separate “Cost estimate” field still displays “Unavailable”; the configured-tariff estimate is shown in the lower Bill Comparison card. Prompt 15 documentation is prepared for the repository's existing Markdown/SVG format; no conference venue template or manuscript source is present. Live PostgreSQL/Redis, actual backup restore, and externally validated NEM12 interpretation remain prerequisites for broader claims. Exact evidence and non-verification limits are recorded in [BASELINE_VERIFICATION.md](BASELINE_VERIFICATION.md).

## Delivery, CI, and repository history

The GitHub Actions workflow at [.github/workflows/ci.yml](.github/workflows/ci.yml) is configured for backend lint/import checks, backend pytest with PostgreSQL and Redis services, migration upgrade/downgrade checks, mobile TypeScript validation, Docker image/Compose checks, a Compose staging smoke test, dependency/container security scans, and conditional staging/production deployment jobs. Configuration shows intended automation, not the current pass/fail state of those jobs.

The latest five visible commits show the following broad progression:

1. **21 April 2026:** initial GridSense project and MIT license.
2. **26 August 2026:** fixes for runtime-fatal insights/billing/usage issues, including unifying Victorian time-of-use logic.
3. **26 August 2026:** application code brought under version control while ignoring research artifacts.
4. **27 August 2026:** work to get the app running on web in a development environment.

This is a sparse history of five reachable commits, so it cannot establish a full feature-by-feature chronology. At report time, `mobile/constants/theme.ts` was already modified in the worktree. That change was left untouched.

## Maturity, discrepancies, and work still needed

### Most established areas

- Backend API composition, account flows, ownership helpers, and structured error/logging foundations.
- NEM12 upload/parsing/import and the core analytics/billing/tariff flow.
- Rule-based observed-pattern recommendations, deterministic usage projections/anomaly detection, and optional per-meter ML models.
- Backend notification persistence and scheduled alert generation.
- Mobile authentication, multi-meter dashboard/usage/recommendations, upload, tariffs, automation, and chat flows.
- A development/deployment topology and CI workflow covering many of the expected checks.

### Partially integrated or not independently established

- **Documentation drift:** the root roadmap still lists intelligence, notifications, and automation as future phases even though substantial corresponding backend and mobile code exists. The backend and mobile READMEs also understate current functionality and/or list obsolete package versions.
- **Mobile offline mode:** cache and connectivity services exist, but primary stores do not appear to use them and the offline banner is not visibly installed globally.
- **Mobile onboarding:** the screen exists, but unauthenticated first-run routing goes directly to login; first-run completion/persistence is not visible.
- **Mobile notifications:** registration and preference helpers exist, but response behavior, deep linking, preference UI wiring, web push, and production EAS project configuration are incomplete.
- **Unwired mobile feature surfaces:** weekly usage is exposed by the API client but not integrated into the store/screen flow. Bill comparison is mounted, but the current sample cannot produce a classifiable usage trend.
- **Background durability:** the in-process upload fallback is not equivalent to durable queued execution.
- **ML lifecycle:** model files are local per-meter artifacts, with no evident registry, versioning, deployment promotion, or monitoring.
- **NEM12 edge cases:** source direction remains unknown pending a verified NMI Procedure mapping; fixed UTC+10 source-time interpretation is implemented but needs confirmation from an authoritative AEMO reference.
- **Tariff history and bill accuracy:** one mutable tariff row is stored per user, so historical rates cannot be reconstructed after edits. Custom windows have no public-holiday calendar, preset rates are illustrative, demand charges are estimates, and feed-in credits have no separate GST adjustment. Bill estimates disclose missing/unresolved data and do not claim to reproduce retailer invoices.
- **Tariff-backed cost surfaces:** usage and forecast cost fields are currently unavailable rather than applying a default rate. Future work can integrate effective-dated user tariffs into those views and restore cost-based alerts only after such pricing is covered by tests.
- **Scheduling preview:** the API and mobile preview flow are connected, but plans and accept/reject choices are not persisted and no execution/dispatch path exists. The mobile demo uses a synthetic baseline; a dashboard action now keeps the preview reachable for the no-readings scheduling account. It does not demonstrate measured household load or realized savings.
- **Maintenance consistency:** both `notifications.py` and `notifications_new.py` exist; alert documentation says an alert-specific test file remains to be added even though notification-service tests exist.
- **Integration confidence:** local API/browser upload-to-billing acceptance and the SQLite migration test are verified; no live PostgreSQL/Redis, OpenAI, or Home Assistant integration, backup restore, or production deployment was run.

### Practical next development priorities

1. Refresh root/backend/mobile documentation so that roadmaps, feature lists, package versions, onboarding, and deployment instructions describe the code that actually exists.
2. Connect offline cache flows to the relevant stores/screens, mount the offline banner, define cache invalidation, and test offline transitions.
3. Complete mobile onboarding and notification behavior, including deep links, user-facing preference management, and real EAS project configuration.
4. Add integration tests for automation, alert generation, recommendations, chat failure/fallback paths, and the queued import lifecycle.
5. Verify the AEMO NMI Procedure suffix/register direction mapping and source clock basis, then safely classify imports/exports; the current sample imports 336 readings but cannot yield classifiable consumption. Continue validating timestamps against DST boundaries and diverse retailer data.
6. Improve operational durability and reproducibility for background jobs and ML artifacts, and verify database migrations, backup/restore, and deployment procedures in CI or staging.
7. Reconcile duplicate notification route code and documentation/test inconsistencies.


## Evidence and limits

The report synthesizes the source trees, project documentation, mobile/backend manifests, CI workflow, Docker Compose configuration, and the recent Git log. Feature presence means the code or configuration exists; it does not mean the feature is fully integrated, production-deployed, or currently passing tests. Documentation statements such as “complete,” “production-ready,” or “zero regressions” are reported as project documentation claims and were not independently verified here.

## Latest Prompt 15 demo verification — 31 October 2026

The final local prototype flow now has newly captured browser evidence. The
synthetic analytics account displayed 12.96 kWh for one local day and a $3.89
partial configured-tariff estimate; the fabricated NEM12 fixture imported 336
readings while retaining an unresolved E1 direction warning. The synthetic
scheduling account has no readings but reaches the preview from its dashboard.
The exercised TOU preview selected 06:00 for both MILP and the deterministic
reference against a 09:00 preference, with $0.92 proposed/reference energy
charges, $0.06 preference penalty, and matching $0.98 weighted objectives.
Independent tariff arithmetic gives a modeled fixed-09:00 task charge of
$0.60 versus $0.24 at 06:00; this is not a household savings result.

The complete backend suite passed (**189 passed, 11 warnings**) and mobile
TypeScript validation passed. Repository-wide Ruff still reports 226 findings;
mobile lint and test commands cannot start because ESLint and Jest are absent.
Fourteen local browser PNGs are indexed in
[`backend/docs/demo/SCREENSHOTS.md`](backend/docs/demo/SCREENSHOTS.md). The
5–7-minute uninterrupted presentation and video capture remain incomplete, so
Prompt 15 final acceptance is **PARTIAL**, not signed off. See the detailed
[`final demo acceptance report`](backend/docs/demo/FINAL_DEMO_ACCEPTANCE.md).
These local SQLite results do not validate PostgreSQL/Redis, backup restore,
actual NEM12 register direction/clock basis, customer savings, appliance
dispatch, or production readiness.
