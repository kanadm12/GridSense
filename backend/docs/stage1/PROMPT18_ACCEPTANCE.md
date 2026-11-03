# Prompt 18 — Acceptance Report

**Review date:** 31 October 2026\
**Base revision:** `d789f9814da9955db1c63ced921a95379dd08495`\
**Git state before Prompt 18 changes:** worktree already contained uncommitted
Prompt 17/17B work and untracked Stage 1 docs, fixtures, and generated
Graphify outputs. Those changes were preserved. No commit or push was made.

## PASS / PARTIAL / BLOCKED

| Prompt 18 area | Status | Evidence and remaining limit |
|---|---|---|
| A — baseline and compatibility review | **PASS** | Recorded base revision and pre-existing dirty worktree; inspected tariff, billing, API, mobile, migration, Stage 1 and test surfaces. No prior changes were reverted. |
| B — immutable tariff history | **PASS** | Added append-only revision snapshots, confirmation/source/time, explicit effective dates, supported energy rates/periods, GST, feed-in and supply fields, unsupported-term tracking, and archive-only deletion. Legacy tariff rows were not asserted as confirmed or backfilled. |
| C — safe billing calculations | **PARTIAL** | Customer fallback pricing removed; missing/out-of-period rates and unpriced TOU windows are surfaced; explicit illustrative scenario is separately labelled; coverage and unsupported terms are reported. Not all retailer charges, customer invoices, exports/GST rules, or incomplete-data cases have been independently validated. |
| D — AER source verification | **PARTIAL** | AER API endpoints, public access, retailer URI discovery, request filters, schemas, pagination ceiling, endpoint versions and live response shape verified against AER/CDS sources. Numeric AER request quota and explicit redistribution, attribution, retention and caching rights were not established. |
| E — AER adapter | **PARTIAL** | Read-only typed adapter uses AER's January 2026 retailer URI snapshot, list v1/detail v3, postcode geography, bounded pagination, no persistent cache, timeouts, version/schema checks and 429 handling. Production exposure remains blocked pending confirmation of data-use rights. No public plan is written to a customer tariff. |
| F — mobile tariff experience | **PASS** | Shows current confirmed/unconfirmed tariff and revision history; adds retailer/postcode plan search and plan detail; labels generic reference offers and unsupported terms; directs user to compare retailer evidence and manually enter/confirm rates. No generic-plan activation path exists. |
| G — deterministic tests and platform checks | **PASS** | Full backend suite passed (233 tests); Prompt 18 targeted Ruff and mobile TypeScript passed; the migration upgraded, downgraded to its parent, and re-upgraded on disposable PostgreSQL 16. Repository-wide Ruff still reports unrelated/adjacent findings; see the validation record. |

## Provider-source findings

The source-grounded interpretation matrix, exact endpoint forms, source
versions, live smoke observations, provider behavior and reuse-rights blockers
are in [`AER_PRODUCT_REFERENCE_DATA.md`](AER_PRODUCT_REFERENCE_DATA.md).
Current integration decisions are reflected in
[`EXTERNAL_DATA_INTEGRATION_DESIGN.md`](EXTERNAL_DATA_INTEGRATION_DESIGN.md).

## Implementation boundaries

- Customer tariff revisions store the terms the user entered and confirmed;
  they do not prove the correctness of the retailer contract.
- Historic terms remain unknown until evidenced. Current prices are not
  retroactively applied.
- Generic AER plans are reference-only. The app does not import their rates
  into confirmed tariff revisions or use them in billing automatically.
- Customer-specific cost is unavailable when no eligible confirmed revision
  covers the billing dates. Illustrative pricing requires an explicit scenario
  request and is labelled accordingly.
- A complete bill cannot be claimed when meter coverage is incomplete or
  material tariff components are unsupported.
- No AER/DEECA plan payload is persisted or cached. Production relay of the
  public payload remains blocked by unresolved explicit reuse/redistribution
  terms.

## Final validation record

| Validation | Command | Result |
|---|---|---|
| Revision-aware recommendation/scheduling tests | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest tests\\test_recommendation_engine.py tests\\test_scheduling_contract.py -q` | **PASS — 28 passed.** Includes regression coverage proving rate/effective-date resolution uses immutable revision snapshots, blocks a horizon crossing a revision boundary, and preserves the explicit synthetic TOU scenario. One focused invocation printed transient Windows native SQLite access-violation diagnostics during teardown while still exiting 0; the final complete suite ran cleanly. |
| Full backend suite | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m pytest -q` | **PASS — 234 passed, 12 warnings, 48.87 s, exit 0.** Warnings are dependency/API deprecations. |
| Prompt 18 targeted Ruff | From `backend/`: `..\\.venv311\\Scripts\\python.exe -m ruff check` over tariff, billing, scheduling, AER adapter/schema and related tests | **PASS — no findings.** The broader repository-wide `ruff check app tests` remains failing; the separate legacy baseline documents substantial existing lint debt. |
| Mobile TypeScript | `npx tsc --noEmit` from `mobile/` | **PASS — exit 0.** |
| Disposable PostgreSQL migration check | PostgreSQL 16 disposable container; `alembic upgrade head`, `downgrade b8c9d0e1f2`, then `upgrade head` | **PASS.** Reached `c9d0e1f2a3b4`, downgraded to parent `b8c9d0e1f2`, and re-upgraded to head. The temporary container was stopped and removed; the unrelated `studentos-db` and `studentos-redis` containers were untouched. |
| Diff whitespace validation | `git diff --check` | **PASS — exit 0.** Git emitted only line-ending normalization warnings for existing modified files. |

## Overall disposition

**PARTIAL.** The application-side tariff history, safer billing behavior and
reference-only AER discovery are implemented. The milestone is not
production-cleared for generic plan redistribution, does not certify
customer-specific bills, and does not establish real NEM12 consumption until
the independent meter clock and direction blockers are resolved.
