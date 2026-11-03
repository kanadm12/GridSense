# Stage 1 Release Readiness

**Verdict: PARTIAL for controlled demonstration; BLOCKED for production or
real-household decisions.**\
**Windows test stability gate: BLOCKED.**\
**As of:** 2026-11-01

## Capability matrix

| Capability | Stage 1 state | Evidence / limitation |
|---|---|---|
| Account registration, login and token flow | Working for local/demo environment | Authenticated API journey and browser registration/login passed. Production identity, deployment and operational controls are not established. |
| User ownership checks | Working for exercised resources | Cross-user meter/recommendation requests are rejected in integration tests; client stores clear on account changes and guard against stale responses. Not a substitute for a full security assessment. |
| NEM12 parsing and import preservation | Working with limitations | Sample parsed 336 records. Unknown/legacy direction and quality are conservatively excluded from measured import. Register/suffix semantics are not fully verified. |
| Interval usage, quality and coverage | Working for supported evidence | Unavailable/partial outcomes are visible; unresolved data are not presented as consumption. Source-time, direction and incomplete coverage can withhold metrics. |
| Tariff entry and immutable revisions | Working as a modeled input path | Effective dates and supported components are checked; a user must supply/confirm terms. No retailer-issued bill is reproduced or certified. |
| Billing estimate | Conditional | Requires eligible import plus an exactly applicable confirmed tariff and supported charge terms. The browser case correctly reported unavailability, not a fabricated amount. |
| Recommendation evidence | Conditional/unquantified when evidence is insufficient | Formula/evidence contract exists; response-scoped evidence is not a durable replay archive. No unsupported savings amounts are accepted. |
| Scheduling optimizer | Working for illustrative scenarios | Existing preferred, greedy and MILP comparison is reused and deterministic fixture tested. Missing tariff blocks browser preview. Solver status alone is not represented as savings superiority. |
| Measured appliance scheduling baseline | Unavailable | No server-verified submeter or synchronized disaggregation path proves task load is excluded. No user checkbox or aggregate/net import is sufficient. |
| Appliance dispatch or operating-system scheduling | Not implemented | UI is advisory only; no task is accepted or executed. |
| Forecast-based advice | Disabled | Historical single-household evaluation is not Australian household validation; issue-time weather evidence is absent and uncertainty/acceptance criteria are not met. |
| Weather context | Unavailable unless configured | Paid-provider credential is not configured. Per-user approximate location is stored separately; browser showed provider-unavailable state. |
| AEMO wholesale context | Blocked/unavailable | Data contract and reuse terms are still being verified. Wholesale prices are not retail tariffs and are not used in bill/savings estimates. |
| Chat/AI, automation, notifications | Not release accepted | Routes/screens exist, but real provider and end-to-end operation are not established by this acceptance run. |
| Windows backend stability | Blocked | Native SQLite access violation observed despite pytest exit 0. |
| Linux backend suite | Comparative pass only | 262 tests passed without observed native diagnostic in one Docker run; does not resolve Windows. |
| Mobile lint/accessibility | Partial | TypeScript and web export passed. ESLint could not run because no project ESLint config/executable was available; web emitted an `aria-hidden` focus warning. |

## Controlled demonstration

Acceptable only in a clearly labelled local/demo setting using disposable
accounts and synthetic fixtures:

- Registration and sign-in.
- NEM12 upload with unresolved direction clearly called out.
- Usage/billing unavailable states and next-action guidance.
- Synthetic scheduling with explicit illustrative baseline and unit-labelled
  preference penalty.
- Preferred/greedy/MILP comparison only when the required scenario inputs and
  applicable test tariff exist.
- Provider-unavailable cards and explanation of data limitations.

Do not use the demonstration to make a household tariff recommendation, assert
meter direction without validated source semantics, quote measured savings
without eligible evidence, dispatch appliances, or claim production readiness.

## Release-blocking prerequisites

1. Reproduce and resolve or independently contain the Windows SQLite native
   access violation; retain native diagnostic capture during complete-suite
   verification.
2. Verify NEM12 direction and source-time semantics against authoritative
   evidence and representative fixtures.
3. Implement and validate a server-evidenced non-task baseline before measured
   appliance scheduling can be enabled.
4. Complete and independently reconcile representative tariff/billing cases
   before presenting customer-specific costs as decision-grade.
5. Define durable evidence replay/retention requirements before claiming
   historical reproducibility.
6. Establish provider licensing, credentials, privacy, security, availability
   and operational policies before enabling weather/AEMO/AI integrations.
7. Verify deployment database migrations and production infrastructure; Prompt
   22 itself introduced no migration.
8. Resolve mobile ESLint configuration and the observed web focus warning, and
   run a dedicated mobile accessibility review.
9. Complete the broader Prompt 21 scheduling/forecast acceptance matrix and
   demonstrate consistent outputs in representative, independently sourced
   datasets.

## Source, licensing and data limitations

The checked-in sample and historical forecasting data are development/test
inputs, not a representative Australian customer population. Provider terms
remain under review for AEMO and require a configured paid integration for
weather. NEM12 field interpretation is not inferred solely from sample labels.
No external API key or customer data was used in this acceptance run.

## Git and checkpoint state

The baseline revision is `d789f9814da9955db1c63ced921a95379dd08495`. The
worktree contains pre-existing Prompt 17-21 changes, including untracked
generated graph artifacts and test/runtime artifacts. No changes were staged,
committed, pushed, reset, or discarded. See `PROMPT22_ACCEPTANCE.md` for the
candidate Prompt 22-only hunk-review staging list. Generated graph output,
database files, credentials, caches, virtual environments, and machine-local
configuration must be excluded.
