# Claim–evidence matrix

Use this as the source of truth when editing a manuscript or presentation.
“Supported” means only that the named implementation/test/result supports the
narrow wording shown; it is not independent validation or field evidence.

| Proposed claim | Evidence path | Test / command | Dataset and observed result | Figure / artifact | Allowed wording and status |
|---|---|---|---|---|---|
| GridSense accepts and processes NEM12 input. | `backend/app/api/upload.py`; `backend/app/services/nem12_parser.py`; `backend/app/services/nem12_importer.py` | `backend/tests/test_upload.py`, `backend/tests/test_nem12_parser.py`, `backend/tests/test_vertical_slice.py` | Fabricated repository fixture; vertical-slice test records 336 imported readings and an unresolved-direction warning. | `backend/tests/sample_nem12.csv`; `backend/docs/phase4-implementation.md` | **Supported narrowly:** “The prototype parses/imports the fabricated fixture and exposes the unresolved direction.” Do not claim validated consumption for this channel. |
| The prototype can calculate an energy-charge estimate from classified readings and a configured tariff. | `backend/app/services/tariff.py`; `backend/app/api/billing.py`; `backend/app/services/usage_analyzer.py` | `backend/tests/test_billing.py`, `backend/tests/test_tariff.py`, `backend/tests/test_vertical_slice.py` | Local tests use constructed readings and configured tariff inputs. Demo seed has 48 synthetic import readings and a 30 c/kWh flat rate. No retailer bill or actual customer's tariff is evaluated. | `backend/scripts/demo_seed.py`; `backend/docs/demo-data.md` | **Supported narrowly:** “The code returns a configured-tariff energy estimate for eligible inputs.” Label demo estimates synthetic and partial; not a retailer invoice. |
| NEM12 values in the sample support consumption analytics. | Same importer/usage path as above. | `backend/tests/test_vertical_slice.py::test_authenticated_nem12_to_tariff_and_billing_journey` | **Not supported:** the test explicitly asserts 336 imported readings, unresolved-direction warnings, zero classified import kWh, and unavailable usage trend. | Test result and fixture; no consumption chart should be attributed to it. | **Must remain unclaimed.** Use the dedicated synthetic seed for analytics; keep unresolved readings excluded. |
| MILP preview is compared with a deterministic reference under common inputs. | `backend/app/api/scheduling.py`; `backend/app/services/scheduling_optimizer.py`; `mobile/app/scheduling.tsx` | `backend/tests/test_scheduling_contract.py`; `backend/tests/test_scheduling_optimizer.py`; `backend/tests/test_vertical_slice.py` | Synthetic v1 request/profile; the UI states that its baseline is synthetic and preview-only. The observed browser TOU case selects 06:00 over the 09:00 preference; the deterministic rule-based reference also selects 06:00. | [`captures/scheduling-inputs.png`](./captures/scheduling-inputs.png); [`captures/scheduling-recommendation.png`](./captures/scheduling-recommendation.png); [`captures/scheduling-result.png`](./captures/scheduling-result.png); [`captures/preview-only-disclosure.png`](./captures/preview-only-disclosure.png); `backend/tests/fixtures/scheduling_v1.json` | **Supported narrowly:** “The preview displays an MILP candidate and a deterministic greedy comparator for the submitted scenario.” The TOU case demonstrates a modeled tariff-driven shift, not MILP superiority or household savings. Do not call the comparator an optimum or the preview an automated control system. |
| Nominal MILP is superior to greedy nominal scheduling. | `backend/app/ml/scheduling_experiment.py`; generated paired comparison. | `backend/tests/test_scheduling_experiment.py`; from `backend/`: `..\\.venv311\\Scripts\\python.exe scripts\\run_scheduling_experiment.py` | Synthetic experiment: nominal MILP minus greedy mean energy-charge difference **−$0.0011 AUD**, profile-level 95% interval **[−$0.0039, $0.0016]**, and matched win/loss/tie counts **4/2/186** over 192 scenario cells and eight recurring profiles. Interval includes zero; cells are not independent households. | `backend/reports/scheduling_experiment/paired_comparisons.csv`; `paired_s1_s2.png`; generated `REPORT.md` | **No superiority claim.** Say the matched synthetic comparison showed near-zero average difference with many ties and no supported overall superiority. |
| The forecast-informed MILP improves on nominal MILP. | Same experiment implementation and paired comparison. | `backend/tests/test_scheduling_experiment.py`; regenerate with command above. | Synthetic forecast MILP minus nominal MILP mean energy difference **+$0.0094 AUD**, profile-level 95% interval **[−$0.0060, $0.0247]**, counts **62/32/98** (wins/losses/ties for left-minus-right sign convention in report). This is an uncalibrated stress experiment, not a real forecast trial. | `paired_comparisons.csv`; `flexibility_forecast_error.png`; generated `REPORT.md` | **No superiority claim.** Describe as a synthetic forecast-information sensitivity comparison only. |
| The forecasting model is accurate for Australian households. | `backend/app/ml/forecast_evaluation.py`; `backend/scripts/evaluate_forecasting.py` | `backend/tests/test_forecast_evaluation.py`; from `backend/`: `..\\.venv311\\Scripts\\python.exe scripts\\evaluate_forecasting.py` | Public UCI active-power data for **one household in Sceaux, France**. Prophet MAE: 5.320 kWh at 1 day (28 forecasts), 3.169 kWh at 7 days (29), 3.269 kWh at 14 days (28). At 1 day persistence MAE is 4.952 kWh; at 7/14 days Prophet is lower than those listed baselines. Origins overlap. | `backend/reports/forecast_evaluation/REPORT.md`; `forecast_evaluation.png`; `config.json` | **Descriptive benchmark only.** No Australian transferability, customer forecasting, bill, or savings claim. |
| GridSense improves energy equity, access, or customer welfare. | Synthetic equity experiment and provenance ledger. | `backend/tests/test_scheduling_experiment.py`; regenerate scheduling experiment. | Eight generated profiles repeated across factors; no consented demographics, accessibility/uptake observations, DER ownership, or customer outcomes. Flat-price flexibility ties and other synthetic sensitivities are not population evidence. | `backend/reports/scheduling_experiment/equity_provenance.csv`; `equity_summary.csv`; `equity_savings_distribution.png` | **Must remain conceptual.** Describe only the synthetic software-pipeline sensitivity and explicit missing measures; no equity-impact conclusion. |
| GridSense automatically schedules or controls appliances. | Scheduling API response assumptions and mobile preview selection. | `backend/tests/test_scheduling_contract.py`; `backend/tests/test_scheduling_optimizer.py` | The endpoint returns a preview. The UI states “Nothing is executed”; accept/reject is not persisted and no dispatch path is wired. | `backend/docs/scheduling-experiment.md`; mobile preview screenshot. | **Must remain future capability.** Say “advisory preview only”; no execution, interoperability, or demand-response claim. |
| The service is production-secure and deployment-reliable. | Source-level Prompt 14 review; Compose and local tests. | `docker compose config --quiet`; local pytest; `docker info` was blocked by unavailable Docker Desktop Linux engine. | No confirmed vulnerability in the reviewed scope is not a security certification. PostgreSQL/Redis, actual worker restart, backup/restore, and external assessment remain unverified. | `BASELINE_VERIFICATION.md`; `backend/docs/backup-restore.md` | **Must remain a limitation.** Do not say secure, production-ready, or operationally validated. |

## Manuscript disposition

### Claims that can be revised to match executed evidence

- Describe the software architecture and implemented API/UI flow as prototype
  functionality, referencing tests rather than inferring behavior from file
  presence.
- Report the UCI single-household forecasting benchmark with its split,
  horizon, sample counts, metrics, and geographic/single-home limitations.
- Report scheduling outputs as synthetic matched comparisons, including the
  near-zero/inconclusive nominal algorithm comparison, comfort objective, and
  repeated-profile limitation.
- Report the synthetic equity pipeline categories and missing data explicitly.

### Claims that must remain conceptual or be removed

- Real Australian household forecast accuracy, bill accuracy, household savings,
  retail tariff representativeness, or customer adoption.
- Measured comfort, behavioral response, appliance compliance, or welfare.
- Demographic fairness, poverty reduction, equitable access, or causal
  household benefit.
- PV/BESS/DER ownership optimization, validated net-demand forecasting, or
  export treatment.
- Automatic device interoperability, dispatch, demand response, or persistent
  schedule acceptance.
- Production security, PostgreSQL/Redis reliability, disaster recovery
  readiness, or successful staging deployment.

No venue template or manuscript source was present in the repository at review
time. This matrix aligns claims and evidence; it does not compile or certify a
submission. Re-run each listed command before publishing changed numerical
claims.

The latest browser, screenshot, full-suite, and independent tariff-recalculation
evidence is consolidated in
[`FINAL_DEMO_ACCEPTANCE.md`](./FINAL_DEMO_ACCEPTANCE.md). The screen captures
are synthetic local-demo evidence only; the full timed run and video recording
remain incomplete.
