# GridSense final demo acceptance report

**Verification date:** 31 October 2026 | **Overall result:** **PARTIAL** | **Source revision:** `518616c3b02319d39c384fb9106ec506e20a8c23`
**Source state:** The worktree was already dirty before this verification and
had 95 modified/untracked entries at the initial status check. Verification
therefore applies to the recorded revision plus the then-current working tree;
the revision alone does not reproduce the uncommitted state.

## Release criteria

| Criterion | Status | Evidence / result |
|---|---|---|
| Clean, isolated synthetic database | **PASS** | Confirmed `backend/gridsense-demo.db` absent before seeding; ran the guarded seed against the dedicated file. Used only the local synthetic accounts and removed that exact generated file after testing. |
| Complete 5–7 minute walkthrough without interruption | **PARTIAL** | Exercised the documented UI path through upload, analytics, recommendations, account switching, tariff windows, and scheduling result. The interactions were not timed as a continuous 5–7 minute presentation and the full scripted narration/closing was not run uninterrupted. |
| Synthetic-data labels and no customer data | **PASS** | Seeded accounts, tariff windows, NEM12 fixture and schedule baseline were explicitly synthetic. UI labels state the scheduling profile has no readings and the baseline is not measured household behavior. |
| Intended analytics meter selected | **PASS** | After fixture upload, the dashboard showed **Synthetic demo meter** selected and displayed its seeded one-day usage. The imported fixture was not used for analytics. |
| Tariff configuration shown and assumptions identified | **PASS** | Captured the tariff selection form and the scheduling account's four invented TOU windows. The TOU tariff is labeled “not a retail offer”; the form describes preset rates as illustrative. |
| Actual schedule and comparable methods shown | **PASS** | The no-readings account's usage-summary request returned 404 and the dashboard clearly rendered “Usage is unavailable”; this is expected because the synthetic scheduling meter has no readings. The browser preview then showed a feasible result: 09:00 preference, 06:00 MILP start, and 06:00 deterministic-reference start using the same displayed synthetic input scenario. The comparison explicitly says the reference is not an optimum. |
| TOU arithmetic independently verified | **PASS** | Recomputed interval charges below from the seeded periods and 30-minute schedule; values match the API/browser output and focused contract test. |
| Feasible, infeasible and no-benefit messaging | **PARTIAL** | The browser showed the feasible result and the rule-based tie (`+$0.00` candidate-minus-reference). Infeasible and no-benefit states were not separately demonstrated in this browser session; the backend suite exercises contract and optimizer boundary cases. |
| Readable screenshots captured | **PASS** | Fourteen credential-free PNGs are saved in [`captures/`](./captures/), including login, analytics, bill estimate, recommendations, fixture warning, tariff, task inputs, result and preview-only disclosure. |
| Screen-recording fallback captured | **FAIL** | No video was produced. The integrated browser exposed screenshot capture only, and `ffmpeg`/OBS were not available in the local command environment. |
| Credentials and private customer data absent from captures | **PASS** | Captures show no passwords, API tokens, connection strings or customer data. They show only synthetic account/device/tariff context. |
| Full backend suite and mobile TypeScript validation | **PASS** | Complete backend pytest suite: **189 passed, 11 warnings**. `npx tsc --noEmit`: exit 0. |
| Full lint/mobile test tooling | **FAIL** | Full Ruff returned **226 findings**. Mobile `npm run lint` could not run because `eslint` is not installed; `npm test -- --runInBand` could not run because `jest` is not installed. No packages/manifests were changed to add tools. |
| Presentation outline reconciled with evidence | **PASS** | Updated deck outline and claim-evidence matrix to reference the newly captured TOU browser screenshots and retain synthetic/preview-only wording. No compiled slide deck or manuscript was present. |
| Updated documentation links | **PASS** | Checked 146 local Markdown links across the runbook, claim matrix, deck outline, screenshot guide, acceptance report, baseline verification, and development status; no broken targets found. |
| PostgreSQL/Redis runtime integration | **NOT RUN** | Docker CLI/engine info and Compose configuration were available, but this demo verification used the documented isolated SQLite database; PostgreSQL, Redis, worker durability and backup restore were not exercised. |

## Commands and environment

| Purpose | Command / setup | Result |
|---|---|---|
| Full backend tests | From `backend/`: `..\.venv311\Scripts\python.exe -m pytest -q` | **189 passed, 11 warnings, 40.99 s, exit 0.** |
| Mobile types | From `mobile/`: `npx tsc --noEmit` | **PASS, exit 0.** |
| Backend lint | From `backend/`: `..\.venv311\Scripts\python.exe -m ruff check .` | **FAIL, 226 findings.** |
| Mobile lint | From `mobile/`: `npm run lint` | **FAIL to start:** `eslint` executable unavailable. |
| Mobile tests | From `mobile/`: `npm test -- --runInBand` | **FAIL to start:** `jest` executable unavailable. |
| Compose syntax / engine check | `docker info --format '{{.ServerVersion}}'`; `docker compose config --quiet` | Engine reported **29.7.2**; Compose syntax passed. No Compose services were started for this acceptance run. |
| Demo seed | From `backend/`, set `DATABASE_URL=sqlite:///./gridsense-demo.db` and a local-only `GRIDSENSE_DEMO_PASSWORD`; run `..\.venv311\Scripts\python.exe scripts\demo_seed.py` | **PASS.** Used the guarded named SQLite demo file; no password value is recorded here. |
| Local API | From `backend/`, `..\.venv311\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`; `GET /health/live` | **PASS.** API bound to loopback; liveness returned HTTP 200. |
| Local web client | From `mobile/`, `npm run web -- --host localhost` | **PASS.** Expo Web served locally at `http://localhost:8081/`. |
| Browser evidence | Integrated browser against the local API and Expo app; upload `backend/tests/sample_nem12.csv` | **PASS for demonstrated interactions.** Fixture result: 336 readings with unresolved `E1` direction warning. |
| Independent TOU arithmetic | Decimal calculation against the tariff rates and actual 06:00 schedule, see below | **PASS.** All assertions matched expected values to the cent. |

Environment: Windows, Python **3.11.9** (`.venv311`), Node.js **22.20.0**,
npm **11.6.2**, Docker **29.7.2**, Expo Web, local SQLite, and local Uvicorn.
The verification date was 31 October 2026 in Australia/Melbourne. The schedule
preview used 1 November 2026 local time.

## Independently recomputed schedule result

The scheduling profile uses a fixed synthetic baseline of **0.8 kW** for eight
30-minute intervals from 06:00 to 10:00. The seeded TOU periods charge
**10 c/kWh** from 00:00–07:00 and **25 c/kWh** from 07:00–16:00:

- Baseline energy: 0.8 kW × 0.5 h × 2 intervals at $0.10/kWh, plus
  0.8 kW × 0.5 h × 6 intervals at $0.25/kWh = **$0.68**.
- Proposed 2.4 kW × 1 hour task at 06:00: 2.4 kWh × $0.10/kWh = **$0.24**.
- Fixed 09:00 task counterfactual: 2.4 kWh × $0.25/kWh = **$0.60**;
  modeled task-charge difference = **$0.36**.
- Proposed total energy charge: $0.68 + $0.24 = **$0.92**.
- Preference penalty: $0.01 × six 30-minute intervals from 09:00 to 06:00 =
  **$0.06**; weighted objective = **$0.98**.
- The deterministic reference also selected 06:00, so its total was **$0.92**,
  weighted objective **$0.98**, and MILP candidate-minus-reference energy
  charge delta **+$0.00**.

These are synthetic model outputs, not observed tariff offers, a bill, measured
comfort, customer savings, or evidence that MILP outperforms the reference.
Daily supply and demand charges are excluded from the scheduling objective.

## Captured assets and remaining gates

The full capture index and descriptions are in [`SCREENSHOTS.md`](./SCREENSHOTS.md).
The screenshots are saved artifacts; they do not substitute for the absent
video. The current final-demo release remains **PARTIAL** until a clean,
uninterrupted 5–7 minute run and a fallback recording are produced. Full Ruff
lint cleanup and adding/configuring mobile lint and test tools are separate
quality tasks, not blockers to the demonstrated browser flow.

The experience remains a prototype: the schedule is advisory, acceptance is
not persisted, and no device is dispatched. Real NEM12 direction/clock-basis
validation, PostgreSQL/Redis service behavior, backup/restore execution, and
production security remain outside this verification.
