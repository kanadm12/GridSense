# GridSense Stage 1 demonstration runbook

**Audience:** university demonstration / controlled prototype review | **Target duration:** 5–7 minutes
**Data boundary:** synthetic local demo data only. Do not use customer meter
records in a recorded or public demonstration.

## What this demonstration proves

It demonstrates local synthetic usage and tariff estimates, followed by a
separate synthetic time-of-use scheduling profile and an advisory MILP preview
compared with the deterministic rule-based reference using the same request.
The fabricated NEM12 parser fixture is an optional side path, not the source of
the seeded analytics data or the scheduling baseline.

It does **not** validate the NEM12 direction of an actual retailer channel,
reproduce an actual retailer bill, demonstrate measured customer savings,
dispatch an appliance, or establish production deployment reliability.

## One-time clean setup

Use PowerShell from the repository root. Do not point the demo API at a
developer, staging, or production database.

```powershell
Set-Location backend
$env:GRIDSENSE_DEMO_PASSWORD = "choose-a-local-demo-password"
$env:DATABASE_URL = "sqlite:///./gridsense-demo.db"
..\.venv311\Scripts\python.exe scripts\demo_seed.py
```

The seed is idempotent and creates two separate synthetic accounts:

- `demo.synthetic@example.com`: one synthetic VIC meter, 48 half-hour
  import readings for the **previous Melbourne calendar day at seed time**, a flat
  **30 c/kWh** tariff, and its
  daily aggregate for the analytics demonstration.
- `demo.scheduling@example.com`: a separate synthetic VIC meter with a
  labeled illustrative time-of-use tariff. Its custom periods are 00:00–07:00
  at 10 c/kWh, 07:00–16:00 at 25 c/kWh, 16:00–21:00 at 55 c/kWh, and
  21:00–24:00 at 10 c/kWh, every day. These invented values are not observed
  Australian retail tariffs or a retail offer.

Both accounts use the local password supplied in `GRIDSENSE_DEMO_PASSWORD`.
The scheduling profile has no meter readings. Its 0.8 kW baseline and
appliance task are explicit synthetic request inputs. The separate accounts
preserve the flat-rate billing example because the current tariff model permits
one tariff per user. Neither profile is an authoritative billing record or
consumption-derived scheduling pipeline.

Start the API in a first terminal:

```powershell
Set-Location backend
$env:DATABASE_URL = "sqlite:///./gridsense-demo.db"
$env:DEBUG = "true"
..\.venv311\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start Expo Web in a second terminal:

```powershell
Set-Location mobile
$env:EXPO_PUBLIC_API_URL = "http://127.0.0.1:8000/api/v1"
npm run web -- --host localhost
```

Open the local Expo URL it prints in a browser on the same computer. The API
listens only on loopback (`127.0.0.1`) and is not exposed to other network
interfaces. Do not change the bind address for a presentation. A physical
phone is not supported by this local-only setup; `localhost` on a phone is the
phone itself.

## Timed demo script (5–7 minutes)

| Time | Screen/action | Narration and guardrail |
|---|---|---|
| 0:00–0:25 | Introduce the dashboard and data label. | “GridSense is a prototype for meter-data review and energy scheduling advice. This demonstration uses a local synthetic account and generated readings.” |
| 0:25–1:05 | Sign in as `demo.synthetic@example.com` with the password supplied during setup. | Do not show the password or any developer environment variables. The account is an artificial demo identity. |
| 1:05–1:55 | Open Upload, select `backend/tests/sample_nem12.csv`, submit, and wait for completion. | This is a fabricated parser fixture, not a customer's retailer export. The import status demonstrates parsing and import processing (336 intervals in the checked-in fixture). Explain that the parser conservatively records its channel direction as unknown; those readings must not be presented as consumption or used to create an energy trend. |
| 1:55–2:10 | Return to the dashboard. Select **Synthetic demo meter** if the upload added another meter. | The imported test meter is intentionally distinct from the seeded analytics meter. The app should not turn unresolved channels into a plausible-looking consumption chart. |
| 2:10–3:05 | Show the synthetic meter's usage summary/chart and the Bill Comparison estimate. | The API returns **12.96 kWh for one local day** (the dashboard rounds to 13.0 kWh). The configured 30 c/kWh tariff produces an approximately **$3.89 active-energy estimate** in the current-period bill card. It is explicitly partial data with expected intervals absent; it is not a full-month forecast or retailer bill. If the top summary's cost field is unavailable, use the lower Bill Comparison card, which shows the configured-tariff calculation. Point out that the readings cover one generated day only. |
| 3:05–3:35 | Open the recommendations/insights view. | Describe only the actual advisory text and values displayed. Rule-based recommendations depend on the available synthetic meter and configured tariff. If no recommendation is available, show the unavailable state rather than inventing an insight. |
| 3:35–4:05 | Sign out of the analytics account in Settings, confirm the browser prompt, and sign in as `demo.scheduling@example.com`. The dashboard correctly shows no usage for this meter; select **Preview a schedule with synthetic baseline** and verify the TOU meter and rate windows. | Explain that this is a separate synthetic account because the current product stores one tariff per user. The new action is available without meter readings; this is not a continuous meter-data-to-recommendation pipeline. |
| 4:05–5:30 | Declare a 2.4 kW water-heater task, 60-minute duration, earliest start 06:00, deadline 10:00, and preferred start 09:00 on the same local date. Keep the 0.01 AUD-per-interval preference penalty and request a preview. | The verified test case selects 06:00, the off-peak window, while the preferred start is 09:00 in shoulder pricing. In the checked scenario, the baseline charge is $0.68, the proposed total energy charge is $0.92, and the task's 06:00 energy charge is $0.24; a fixed 09:00 task would cost $0.60, a $0.36 modeled task-charge difference. The preference penalty is $0.06, making the proposed weighted objective $0.98. The rule-based reference also selects 06:00, so MILP's energy-cost delta versus that comparator is $0.00. These are synthetic scenario calculations, not a bill or a household savings estimate. |
| 5:30–6:10 | Review the original preference, proposed time, rule-based reference, energy costs, weighted objectives, and preview-only status. | The example illustrates tariff-aware shifting versus the requested start, not MILP superiority over the rule-based method. The preference weight is a modeling assumption, not a measured comfort value. Call out feasibility and any omitted/blocked task explicitly. |
| 6:10–6:40 | Close on the preview-only boundary and next validation gate. | “Accepting a preview records a choice only in this screen session. It does not persist a decision or control a device. Real NEM12 direction and clock-basis validation, PostgreSQL/Redis deployment checks, and recovery testing remain open.” |

### Latest local browser evidence

On 31 October 2026, the local SQLite/API/Expo browser flow exercised the fixture
upload, selected synthetic analytics meter, bill estimate, recommendations,
web sign-out/account switch, no-readings scheduling dashboard, tariff windows,
task inputs, computed preview, and preview-only disclosure. The upload showed
336 imported readings and the unresolved E1 direction warning; the seeded
analytics view showed 12.96 kWh for one day and a $3.89 partial configured-tariff
estimate. The scheduling result and arithmetic are recorded in
[`FINAL_DEMO_ACCEPTANCE.md`](./FINAL_DEMO_ACCEPTANCE.md). Readable PNGs are in
[`captures/`](./captures/) and indexed in [`SCREENSHOTS.md`](./SCREENSHOTS.md).
The interaction sequence was not timed as an uninterrupted 5–7 minute
presentation, and no video recording was captured; those acceptance items
remain open.

### Optional shorter path when time is limited

Skip the test-fixture upload and state why: its register direction is unresolved.
Show the seeded synthetic usage and the scheduling preview. This is the preferred
path if the purpose is to explain product value rather than parser behavior.

## Pre-demo checklist

- [ ] Confirm the API points only to `backend/gridsense-demo.db`.
- [ ] Confirm the synthetic analytics and scheduling accounts and meters are visible.
- [ ] Check that the selected analytics meter is **Synthetic demo meter**.
- [ ] Confirm the configured tariff is the labeled 30 c/kWh synthetic flat rate.
- [ ] Sign in separately to the scheduling account and verify all four synthetic TOU windows.
- [ ] Confirm unresolved-direction warnings remain visible for any uploaded
      parser fixture; do not select it as an analytics source.
- [ ] Confirm the scheduling form labels its baseline synthetic and its result
      preview-only.
- [ ] Confirm the task window is 06:00–10:00 with 09:00 preferred, and present
      the actual result even if it differs from the checked scenario.
- [ ] Keep the API bound to `127.0.0.1`; do not expose the debug server to LAN.
- [ ] Hide terminals, environment settings, local tokens, and personal data.
- [ ] Explain that the sample day is the previous calendar day when the
      database was seeded (Australia/Melbourne local date).

## Reset and clean shutdown

Stop the API and Expo processes with `Ctrl+C`. To recreate the demo database,
first verify the current directory and database URL, then run only the guarded
demo reset:

```powershell
Set-Location backend
$env:GRIDSENSE_DEMO_PASSWORD = "choose-a-local-demo-password"
$env:DATABASE_URL = "sqlite:///./gridsense-demo.db"
..\.venv311\Scripts\python.exe scripts\demo_seed.py --reset
```

The script refuses non-SQLite engines and paths whose filename is not exactly
`gridsense-demo.db`; nevertheless, verify the resolved target before running
`--reset`. Never use this command for another database.

## Fallback screen recording

Record a local browser session from the clean setup above. Start with the
synthetic-data disclosure visible, keep the full browser frame and readable
font size, and capture the seeded meter summary followed by the separate
synthetic TOU account, actual schedule comparison, weighted objective, and
preview-only notice. Do not record credentials, tokens, connection strings,
real customer files, or a fabricated savings claim.

If a live upload stalls or the API is unavailable, stop the demo and use a
recording made from the same synthetic seed and a previously completed preview.
Label it **recorded synthetic prototype flow**, state that it is not a live
integration test, and do not imply that the scheduling choice was dispatched.

## Regeneration and validation commands

From `backend/`:

```powershell
..\.venv311\Scripts\python.exe -m pytest -q tests\test_demo_seed.py tests\test_vertical_slice.py tests\test_upload.py
..\.venv311\Scripts\python.exe -m pytest -q tests\test_scheduling_contract.py tests\test_scheduling_optimizer.py
```

The first command validates seed behavior and upload/vertical-slice behavior;
the second validates the schedule contract and optimizer. A passing SQLite test
does not validate the PostgreSQL/Redis Compose deployment. See
[`BASELINE_VERIFICATION.md`](../../../BASELINE_VERIFICATION.md) and
[`../backup-restore.md`](../backup-restore.md) for deployment gates.
