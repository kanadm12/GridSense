# GridSense Stage 1 — short deck outline

Suggested eight-slide, 5–7 minute presentation. Presenter's notes should retain
the synthetic-data labels on every relevant slide.

1. **The problem and the prototype scope** — Fragmented meter data and difficult
   timing choices; GridSense explores analysis and advisory scheduling, not
   automatic control.
2. **What is implemented today** — Mobile client, FastAPI services, upload
   status, tariff setup, analytics, recommendation, and schedule preview.
3. **Data provenance and safety boundary** — Seeded synthetic meter for
   analytics; fabricated NEM12 test fixture demonstrates import and unresolved
   direction warning; no customer data.
4. **From readings to estimated costs** — Show the synthetic meter dashboard
   and configured flat tariff; disclose one-day coverage and excluded bill
   components.
5. **How a schedule preview works** — Use the separate synthetic TOU scheduling
   account. Show the 09:00 preferred start and 06:00 MILP/reference outcome,
   tariff windows, energy charges, $0.06 preference penalty, and matching
   $0.98 weighted objectives. Explain that this is a synthetic fixed-start
   comparison, not household savings or MILP superiority. Label all values
   synthetic.
6. **What the experiments do and do not show** — Scheduling comparisons use
   eight repeated generated profiles; forecasting uses one public French
   household. Report the measured metrics with their limits; avoid a
   superiority claim where matched evidence is inconclusive.
7. **Current release gates** — NEM12 direction/clock basis, PostgreSQL/Redis
   deployment and recovery verification, security assessment, and non-persisted
   scheduling decisions/device dispatch.
8. **Next milestone** — Validate meter semantics and deployment in controlled
   infrastructure, then evaluate persisted decisions and user/device workflows
   before any real-data pilot.

## Visuals

- Product flow: [`architecture.svg`](./architecture.svg)
- Captured synthetic analytics and bill estimate:
  [`captures/analytics-dashboard.png`](./captures/analytics-dashboard.png) and
  [`captures/analytics-bill-estimate.png`](./captures/analytics-bill-estimate.png).
- Captured synthetic TOU tariff and schedule:
  [`captures/tou-tariff-windows.png`](./captures/tou-tariff-windows.png),
  [`captures/scheduling-inputs.png`](./captures/scheduling-inputs.png),
  [`captures/scheduling-recommendation.png`](./captures/scheduling-recommendation.png),
  [`captures/scheduling-result.png`](./captures/scheduling-result.png), and
  [`captures/preview-only-disclosure.png`](./captures/preview-only-disclosure.png).
- Other captured flow screens are listed in
  [`SCREENSHOTS.md`](./SCREENSHOTS.md). These are still images, not the
  outstanding full-length screen recording.
- Synthetic scheduling experiment: `../../reports/scheduling_experiment/paired_s1_s2.png`
- Synthetic flexibility/forecast-error ablation:
  `../../reports/scheduling_experiment/flexibility_forecast_error.png`
- Synthetic cost/inconvenience trade-off:
  `../../reports/scheduling_experiment/cost_inconvenience.png`

Do not crop off the synthetic/preview labels or edit numerical values in figures.
