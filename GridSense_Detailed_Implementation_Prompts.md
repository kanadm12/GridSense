# GridSense — Detailed Implementation Prompts

Based on the supplied development status and repository ZIPs. Execute one prompt at a time; do not assume features work without tests.

## 01 — Repository baseline, reproducible environment and test inventory

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Identify runtime versions, dependency installation commands, environment variables and secrets required, without exposing secrets. 2. Start PostgreSQL/Redis/backend/worker/scheduler where possible; apply Alembic migrations. 3. Run backend tests, mobile TypeScript checks, lint/build commands, and record exact outcomes. 4. Exercise readiness, auth, sample NEM12 upload, meter retrieval, usage and billing endpoints. 5. Classify each issue as missing dependency, test failure, configuration, environment restriction, or application defect. 6. Create a concise verified-status matrix; no feature development in this task.

REQUIRED TESTS / VERIFICATION:
Include commands and exit codes for pytest, migrations, TS checks, health and one API smoke test; do not hide failed tests.

DEFINITION OF DONE:
A fresh developer can follow a README and reproduce the supported stack; a baseline test report and blocker list exist.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 02 — NEM12 semantics: intervals, direction, quality and import safety

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Trace CSV record types, header fields, suffixes, channel/register identifiers, interval counts and energy units against the actual AEMO MDFF specification. 2. Investigate the hardcoded register_type="B" behaviour and all downstream dependencies; never assume B always means import or export. 3. Define explicit direction and quality metadata; preserve raw fields for audit. 4. Test multiple channels/registers, exports, missing intervals, repeated uploads, malformed files and 50 MB limits. 5. If schema changes are necessary, add reversible migrations and compatibility logic. 6. Return clear import warnings when data direction cannot be resolved; do not silently relabel unknown registers.

REQUIRED TESTS / VERIFICATION:
Unit tests with fabricated NEM12 fixtures for import-only, export, mixed, malformed and duplicate files; importer/database integration tests.

DEFINITION OF DONE:
Import/export totals reconcile to fixtures; direction/quality ambiguity is explicit; tests and migration pass.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 03 — Clock, interval boundaries and daylight-saving consistency

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Document whether each meter interval timestamp indicates start or end, clock basis, time zone, DST adjustment and whether AEST/AEDT applies to each source. 2. Define one canonical internal timestamp representation and keep original source metadata. 3. Design tests around Melbourne DST forward/back transitions and ambiguous/nonexistent times, plus leap days and midnight boundary. 4. Make billing and chart bucketing derive from explicit interval boundaries, not guessed local hours. 5. Flag data that cannot be aligned unambiguously. 6. Include a worked 30-minute interval example showing correct tariff classification.

REQUIRED TESTS / VERIFICATION:
DST fixtures for both transitions; hourly/daily kWh conservation; rate-boundary tests; API import-to-bill integration where feasible.

DEFINITION OF DONE:
Every imported interval maps to exactly one expected local billing window without silent time shifts.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 04 — Tariff engine and bill reconciliation

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Inventory existing tariff presets and assumptions. 2. Define tariff schema for effective dates, flat/TOU windows, weekday/weekend/holiday distinctions where supplied, import rates, feed-in rates, fixed charges and optional demand charges. 3. Ensure unknown tariffs trigger an explicitly labelled illustrative estimate rather than a purported real bill. 4. Ensure import and export directions come from Task 02, tariff windows from Task 03, and GST treatment is explicit. 5. Generate a bill breakdown that reconciles itemised intervals with totals. 6. Compare with a hand-calculated fixture and document exclusions.

REQUIRED TESTS / VERIFICATION:
Golden fixtures: flat tariff, weekday/weekend TOU, export credit, DST boundary, incomplete tariff, missing data; billing totals to cent rounding policy.

DEFINITION OF DONE:
For each fixture, the API cost and ledger match hand calculations; UI clearly labels estimated vs configured tariff.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 05 — End-to-end product vertical slice

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Run an actual user flow: register/login, select/create meter, upload demo NEM12, poll status, select tariff, view usage and billing. 2. Fix only blocking API payload mismatches, auth refresh, meter selection persistence and error states. 3. Display import errors and data-coverage warnings, not a silent success toast. 4. Integrate the existing bill-comparison component only if computed from the verified tariff engine. 5. Capture a deterministic demo fixture and screen-level acceptance steps.

REQUIRED TESTS / VERIFICATION:
Minimum API integration test plus end-to-end manual or automated web flow, including duplicate upload, invalid upload, and expired auth.

DEFINITION OF DONE:
One scripted user journey works from clean setup with no manual DB edits and reproducible screenshots.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 06 — Recommendation honesty and savings transparency

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Catalogue each current recommendation and its savings equation. 2. Identify fixed assumed rate differentials, standby fractions and inferred appliance claims. 3. Split outputs into (a) observed fact, (b) potential user action, (c) conditional estimated opportunity, with confidence/data requirements. 4. Use actual configured tariffs for monetary estimates. 5. For appliance-related savings, require a user-declared appliance, rated power or energy demand, and available window; otherwise state that savings are unquantified. 6. Add explanation fields: baseline, proposed action, assumptions, rate difference, applicable interval and uncertainty. 7. Keep AI chat explanatory, not authoritative for billing.

REQUIRED TESTS / VERIFICATION:
Tests for no tariff, missing appliance, flat tariff, overnight-load observation, TOU price difference, export data and zero savings.

DEFINITION OF DONE:
No UI card presents a fixed assumed dollar saving as verified household saving.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 07 — Define the scheduling API and data contract

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Define versioned request/response schemas for mandatory/optional tasks, rated power or energy, duration, earliest start, deadline, preferred start, tariff, interval duration, user timezone, fixed baseline profile and scenario identifier. 2. Decide how baseline is sourced: independently measured/disaggregated or synthetic; reject attempts to infer baseline from raw net demand without a valid method. 3. Specify time-index conventions, costs in AUD, kW/kWh units, and validation rules. 4. Return feasibility status, objective breakdown, candidate schedule, reference schedule and transparent assumptions. 5. Add appropriate ownership checks; do not create a premature large database redesign.

REQUIRED TESTS / VERIFICATION:
Pydantic/API validation for invalid duration, window, units, missing tariff, unresolvable baseline, overlap, empty windows, unauthorised meter.

DEFINITION OF DONE:
OpenAPI schema and example JSON fixture are versioned, stable and consumable by mobile.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 08 — Implement Stage 1 MILP appliance scheduling

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Select a deployable MILP solver after checking license and platform constraints. 2. Model binary start-time variables for fixed-power noninterruptible tasks, one start for required tasks, at-most-one for optional tasks with explicitly defined omission penalty or no-savings treatment. 3. Enforce start windows, deadline, household/grid power bounds when given, and interval price cost. 4. Include user preference penalty as a documented configurable parameter. 5. Produce feasible/infeasible/timeout statuses and no unsafe fallback command. 6. Do not double count baseline demand; label synthetic profiles. 7. Implement a transparent deterministic rule-based comparator on the exact same inputs. 8. Omit real device controls, batteries, PV curtailment and DOE from the first deliverable.

REQUIRED TESTS / VERIFICATION:
Manually solvable 4–8 interval golden cases; forced infeasible tests; flat tariff ties; comfort trade-off; DST/index checks; objective accounting; repeated deterministic runs.

DEFINITION OF DONE:
Solver returns physically feasible, explained schedules and beats/matches comparator only where justified by actual fixture outputs.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 09 — Make the scheduler demonstrable in Expo

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Add a simple task form: appliance, estimated power, duration, earliest/latest feasible time, preferred start, mandatory/optional flag. 2. Show original schedule, proposed schedule, tariff windows, predicted cost delta, comfort trade-off and assumptions. 3. Distinguish “recommended” from “executed”; allow accept/reject/edit but do not falsely claim execution. 4. Show no-savings, missing-data and infeasible outcomes clearly. 5. Preserve existing navigation, state store and theme, and avoid unnecessary UI redesign. 6. Include a reproducible demo preset with synthetic appliance characteristics.

REQUIRED TESTS / VERIFICATION:
Native/web typecheck plus end-to-end scheduling API-to-screen flow; user override and validation tests; screenshots for evidence.

DEFINITION OF DONE:
Demo operator can submit a task and see a feasible, explainable schedule from the solver.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 10 — Forecasting evaluation, no leakage

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Catalogue current forecast targets, temporal resolution, inputs, retraining and serialized artifacts. 2. Select licensed dataset and document coverage, training/validation/test chronological split and missing-data handling. 3. Compare persistence and historical averages to existing Prophet or other ML where implemented. 4. Ensure no future consumption or leakage via preprocessing. 5. Report MAE/RMSE by household, season and horizon; assess forecasts of net demand separately from behind-the-meter PV/underlying load. 6. Save scripts/configuration/seeds and failure cases. 7. Do not claim LSTM is implemented if it is not.

REQUIRED TESTS / VERIFICATION:
One-command reproducible evaluation; unit/shape checks; chronological split assertion; exported CSV + figures + dataset README.

DEFINITION OF DONE:
Testable, repeatable metrics exist, including a simple baseline and uncertainty/limitations.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 11 — Research experiment: S0/S1/S2 and oracle

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Define S0 no intervention, S1 rule-based, S2 forecast-informed MILP, and perfect-information oracle explicitly. 2. Use common household profiles/tariffs across scenarios and identify which loads are synthetic vs measured. 3. Avoid leakage; calculate realised cost against held-out data with exactly the same billing function. 4. Report per-household absolute AUD, percentages only for positive baselines, peak, feasible task completion, inconvenience, runtime and infeasibilities. 5. Add ablations for flexibility window, forecast error, appliance mix and tariff spread. 6. Save config, solver version, seeds and raw result tables. 7. Never claim real customer behaviour or bill savings from simulated schedule compliance.

REQUIRED TESTS / VERIFICATION:
Repeatable command generates result CSV, summary tables, plots and plain-language limitations; reconciles every cost to interval prices.

DEFINITION OF DONE:
Paper-ready evidence exists showing benefit or no benefit, with transparent assumptions and no fabricated outcomes.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 12 — Equity and distributional evaluation

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Define measurable accessibility (can use data and advisory service), actionability (feasible recommendations), and benefit distribution (absolute AUD, inconvenience, savings) before looking at results. 2. Compare no DER, PV, EV/BESS only when source profiles support those distinctions. 3. Do not infer housing tenure, income, health or demographics from consumption. 4. Use real demographic group labels only with documented consent/data provenance; otherwise label synthetic scenario categories. 5. Report missing categories, group sizes and uncertainty; quantify who receives no actionable recommendation. 6. Separate software access from verified energy-equity outcome.

REQUIRED TESTS / VERIFICATION:
Automated group summaries; counterexamples; provenance ledger; sensitivity analysis for limited flexibility.

DEFINITION OF DONE:
The equity section can cite actual supported comparative outcomes, with no unsupported poverty-reduction claims.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 13 — Operational reliability and demo safety

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Test queued upload with Redis/RQ and document fallback durability risk. 2. Ensure retries and idempotence for duplicate files; avoid concurrent double imports. 3. Confirm health checks, migration boot and backup/restore in staging. 4. Create reproducible demo seed/reset procedure using only artificial or consented data. 5. Make external services (AI, SMTP, Expo push, Home Assistant) optional and non-blocking for the core demo. 6. Add visible errors and reconciliation logs without exposing meter data or tokens.

REQUIRED TESTS / VERIFICATION:
Fresh Compose smoke test, worker restart mid-import, duplicate import, backup restore, missing Redis and missing OpenAI credentials.

DEFINITION OF DONE:
Demo survives predictable interruptions or fails clearly; clean reset is documented.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 14 — Privacy/security and device-control boundary review

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Threat-model uploaded metering data, tokens, AI context, user-meter ownership, device commands and logging. 2. Verify HTTPS/prod CORS configuration, secrets handling, permissions, file validation and account deletion/retention behaviour. 3. Confirm Home Assistant simulator is clearly labelled; never imply real commands were sent unless verifiably acknowledged. 4. Document external APIs and data sent to them. 5. Verify any privacy notice/consent is accurate for the implemented product, not merely aspirational. 6. Report vulnerabilities and mitigation priorities; no unverified security certification claims.

REQUIRED TESTS / VERIFICATION:
Cross-user meter/automation access tests, malformed uploads, unauthorised command tests, no-secret logging audit, offline-token handling review.

DEFINITION OF DONE:
Demo and documentation clearly separate simulated features, authorised real integrations and unsupported claims.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```

## 15 — Presentation package and manuscript evidence alignment

```text
You are working inside the existing GridSense repository (FastAPI backend, Expo/React Native mobile). Do not replace existing architecture or assume a feature is working merely because files exist. Inspect relevant code and tests first; make the smallest coherent patch. Preserve backwards compatibility unless a correctness issue requires a documented migration. Do not invent savings, model accuracy, device interoperability, or real-time grid data.

TASK:
1. Create a 5–7 minute reproducible demo script: login, import, reconcile usage/tariff, show insights, create flexible task, compare S1 vs S2, explain assumptions. 2. Prepare a short deck outline and product one-pager with separate headings for Working / Simulated / Planned. 3. Generate a claim-evidence matrix mapping each proposed paper claim to code path, test, dataset, result and figure. 4. Flag which manuscript claims must remain conceptual and which can be revised based on real evidence. 5. Rewrite the architecture diagram and screenshots for readability; remove template placeholders. 6. Include a clean startup/reset runbook and fallback screen recording. 7. Do not upgrade paper claims until tests and experiments are actually completed.

REQUIRED TESTS / VERIFICATION:
Dry-run with clean setup; check screenshot readability; compile output in selected venue template; results can be regenerated from commands.

DEFINITION OF DONE:
A demonstrable GridSense Stage 1 product plus reproducible experimental artifacts and honest paper-ready claims.

OUTPUT FORMAT: (1) observed current behaviour, (2) files changed and why, (3) tests run and pass/fail evidence, (4) before/after example, (5) known limitations, (6) next dependency. Do not claim successful execution of tests you did not run.
```
