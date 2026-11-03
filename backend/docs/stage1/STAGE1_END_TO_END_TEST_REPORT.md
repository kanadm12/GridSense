# Stage 1 End-to-End Test Report

**Execution date:** 2026-11-01\
**Overall result:** PARTIAL\
**Windows runtime stability:** BLOCKED

## Tested application surfaces

The authenticated API includes health/readiness and worker status; registration,
login, token refresh and account endpoints; meter ownership and NEM12 upload;
usage; tariff revisions; billing; insights; recommendations and calculation
evidence; advisory scheduling; and optional external context. Chat and
automation endpoints are present but were not accepted as production-ready
integrations in this exercise.

Expo routes exercised or inspected include:

- Authentication: login, registration and password recovery.
- Onboarding, NEM12 upload and tariff setup.
- Dashboard, usage, recommendations, chat/ask, automation and settings tabs.
- Advisory scheduling, legal terms and privacy pages.

## Test environments and outputs

| Environment/check | Actual result |
|---|---|
| Focused backend tests | `23 passed, 7 warnings` (`test_vertical_slice.py` and `test_scheduling_contract.py`) |
| Full Windows backend suite | `262 passed, 12 warnings`, exit 0; native SQLite access-violation diagnostic observed |
| Full Linux Docker backend suite | `262 passed, 14 warnings`; no native diagnostic in this run |
| Ruff | Focused checks passed |
| TypeScript | `npx tsc --noEmit` passed |
| Expo web | Export passed; 1,075 modules; 2.38 MB web JS bundle |
| Browser | Disposable test accounts and database; flows below exercised |
| ESLint | Not run successfully: no local ESLint executable/configuration; ESLint 10 reported no flat config |
| Diff whitespace | `git diff --check` passed, with existing line-ending normalization warnings |

The Windows fault remains a blocker even though pytest returned 0. The native
stack included SQLAlchemy SQLite schema reflection/`PRAGMA` access in teardown.
See `PROMPT20C_NATIVE_FAULT_REPORT.md` and `PROMPT22_ACCEPTANCE.md` for the
environment comparison and caveats.

## Browser and API flow evidence

| Step | Observed result |
|---|---|
| Create account and sign in | Disposable account reached the dashboard. The negative registration case returned HTTP 422 and showed `Validation error: body.email: value is not a valid email address...` after the API error helper change. |
| Upload meter data | `backend/tests/sample_nem12.csv` parsed 336 readings. The UI presented unresolved direction rather than calling them imports. |
| Usage | Dashboard showed `Usage is unavailable`, `No usage data found`, and the action to inspect warnings/confirm importable consumption. Eligible import remained 0.0 kWh. |
| Billing/tariff | Comparison remained unavailable, naming missing confirmed effective tariff, absent interval coverage and incomplete modeled components. The review/confirm tariff action was available. No user tariff was asserted. |
| Recommendation | The backend journey test verified unquantified results when evidence is insufficient; user-owned resource checks reject a second account. |
| Scheduling | UI exposed an illustrative synthetic-baseline flow. With no owned applicable tariff, preview was blocked with `Tariff status: missing` and `No user-owned tariff is configured.` The backend fixture exercises synthetic scheduling calculations. |
| External context | Dashboard stated weather provider credentials are not configured and AEMO data/reuse terms remain under review. Wholesale price is explicitly excluded from retail billing/savings. |
| Sign-out and second account | Sign-out returned to login. A second account had no first-account meter. After a test-only upload, its weather-coordinate fields were blank, not inherited from the first account. |

No actual retailer tariff terms, credentials, customer meter identifiers, or
live-provider results were entered. Browser validation does not establish
real-household accuracy or production authorization.

## Gaps, warnings and interpretation

- The uploaded sample's NMI/register/suffix/stream metadata do not establish
  channel direction. It is not a positive consumption acceptance fixture.
- A confirmed tariff was deliberately not fabricated in the browser. Backend
  deterministic tests use owned test data; the browser path therefore verifies
  useful blocking/unavailability, not a fully priced customer bill.
- No historical calculation-evidence archive is implemented; evidence is
  response-scoped.
- No real appliance dispatch or OS scheduling occurs.
- No measured appliance-baseline path is enabled. Aggregate import/net energy
  and user declarations are not accepted as proof that flexible load was
  excluded.
- The browser reported an `aria-hidden` focus-transition warning on route
  navigation and the expected Expo notifications-on-web limitation. A 404 from
  a no-eligible-usage request was rendered as an explicit unavailable state.
- The paid weather integration, AEMO market context, real retailer billing
  validation, PostgreSQL deployment, Redis/RQ, and external AI/Home Assistant
  integrations were not established by this demo.

## Stability and release conclusion

Linux Docker passing 262 tests without a native diagnostic is useful comparative
evidence, not a fix for the Windows-specific fault. The Windows suite emitted
the native access violation in this acceptance run, and prior Prompt 20C/21
repetitions also observed it. Do not suppress the diagnostic or mark Windows
stable based on pytest's exit code.

**Stage 1 demonstration:** Suitable only for a controlled, synthetic/advisory
demonstration that labels unresolved or illustrative data correctly.
**Real household decisions or production release:** Not accepted.
