# GridSense Stage 1 — product one-pager

## Working

- A FastAPI backend and Expo application provide account access, meter selection,
  NEM12 upload processing, tariff configuration, usage and billing endpoints,
  recommendations, and a scheduling-preview screen.
- Upload records expose processing status and warnings. Unresolved NEM12
  direction remains `unknown`; it is not silently counted as import or
  consumption.
- A dedicated local SQLite seed provides a synthetic analytics account with a
  30 c/kWh flat tariff and a separate scheduling-only account with an invented
  time-of-use tariff. The scheduling account has no meter readings; the
  scheduling baseline is a declared synthetic request input. Neither profile
  comes from a customer file.
- The scheduling endpoint returns a feasible/infeasible result, compares an
  MILP recommendation with a deterministic reference, reports cost components
  and assumptions, and does not dispatch a device.
- Synthetic scheduling and public-dataset forecasting experiments have
  reproducible configurations, result tables, tests, and documented limits.

## Simulated

- The demo meter's 48 half-hour readings, 30 c/kWh flat rate, and one-day usage
  summary are generated for demonstration; they are not a real household
  profile, full bill, or observed customer saving. The TOU windows are invented
  illustrative rates, not observed Australian retail tariffs.
- The mobile scheduling request uses a fixed synthetic 0.8 kW baseline and
  user-declared appliance power, duration, allowed window, and preference.
- Research schedules, future prices, forecast errors, and household profiles
  are synthetic. The forecast benchmark uses one public French household and
  cannot establish Australian/customer performance.
- The repository NEM12 sample is a fabricated parser fixture. Its readings
  have unresolved direction and are suitable for import-warning demonstration,
  not consumption analytics.

## Planned / not established

- Authoritative NEM12 register-direction mapping and source clock-basis
  verification against applicable AEMO specifications and diverse retailer
  files.
- Persisted accept/reject decisions, execution history, and authorised real
  appliance dispatch.
- Verified Australian household forecasting, complete retailer-bill
  reconciliation, and customer savings or equity outcomes.
- Live PostgreSQL/Redis deployment, real worker-restart resilience, and
  PostgreSQL backup/restore execution.
- External security assessment and production operational certification.

## Appropriate product description

GridSense is a technically substantial prototype for meter-data review,
tariff-aware estimates, and advisory scheduling. Its controlled demonstration
uses synthetic data. It is not a production-secure energy platform, an
automated appliance controller, or a validated source of household bill
predictions.
