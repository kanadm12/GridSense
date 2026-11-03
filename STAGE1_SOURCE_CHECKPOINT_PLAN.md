# Stage 1 Source Checkpoint Plan

- **Review date:** 2 November 2026
- **Repository:** `kanadm12/GridSense`
- **Branch / HEAD:** `main` / `d789f9814da9955db1c63ced921a95379dd08495`
- **Disposition:** Proposal only. No repository files were staged, committed,
  pushed, reset, or deleted. Task-scoped disposable validation artifacts were
  removed after use.

## 0. Final closure status (Prompt 23E-Security, current round)

Supersedes the 314/318/319-file counts and the 678/706 exclusion counts below.

| Item | Result |
|---|---|
| Source manifest | 322 included (128 tracked unchanged, 114 modified, 80 untracked); commit delta 194 (114 modified + 80 untracked); 706 excluded (615 Graphify, 5 legacy `backend/file*`, 61 `files/` evidence, 25 git-ignored local evidence); 0 unaccounted within the declared scope. Verified against a fresh clean copy: 0 SHA256 mismatches. |
| Historical 678→681 delta | NOT VERIFIED (no trustworthy earlier snapshot). |
| Secret scan | Gitleaks v8.24.2 with `.gitleaksignore` (10 fingerprints, synthetic JWT fixtures only) exits 0 on the clean copy. Negative controls (fake secret in the fixture and in `test_auth.py`) exit 1. |
| Backend tests (restricted PostgreSQL 16) | 389 passed, 0 skipped, exit 0 (includes 34 release-gate policy tests). |
| Ruff 0.16.3 | Passes on `alembic app scripts tests`. |
| actionlint 1.7.7 (ShellCheck on) | Exit 0 after four ShellCheck corrections in `ci.yml`. |
| Security gate | Exit 1 with 9 unaccepted ChromaDB findings (pip-audit 5, Trivy 4, all chromadb 1.5.9, no fixed version). Intended. |
| ChromaDB risk acceptances | PROPOSED (owner "Project maintainer — approval pending", review by 2026-12-31). Not approved. |
| Hosted CI | NOT VERIFIED. |
| Windows SQLite native fault | BLOCKED; explicitly unsupported; not reopened. |

Git boundary: no staging, commit, push, deploy or real-data change has been performed. The manifest-only staging plan is in section 9 of this document, and it has not been executed.

## 1. Preservation baseline

At inventory time the index was empty. The worktree contained 70 tracked
modified paths and 653 untracked files:

| Untracked category | Count | Treatment |
|---|---:|---|
| Graphify-generated output | 601 | Preserve in place; exclude from a source checkpoint. |
| Backend-root test artifacts named `file*` | 5 | Preserve in place; exclude. Four are legacy SQLite test artifacts and one is an empty file. |
| Untracked implementation, fixtures, and documentation | 47 | Preserve and include in a reviewed source checkpoint. |

The inventory includes the health-check test. This plan and the engineering
baseline report are new documentation created after the inventory snapshot;
both must also be preserved and included when staging is later authorized.

The worktree must remain intact. In particular, the five backend-root
`file*` artifacts and all ignored developer data are not cleanup targets.
The four filenames below contain the Windows-safe private-use character
U+F03A after `file` (Git's quoted path output renders those names as
`file\357\200\272...`):

- `backend/file` — 0 bytes.
- `backend/file<U+F03A>insights_tests_db` — 507,904 bytes.
- `backend/file<U+F03A>password_reset_tests` — 196,608 bytes.
- `backend/file<U+F03A>tests_db` — 196,608 bytes.
- `backend/file<U+F03A>tests_db_ml` — 196,608 bytes.

## 2. Tracked modified source to preserve

These are already tracked by Git but modified in the worktree. Preserve every
change and review individual hunks before staging; do not stage entire files
blindly where Prompt 17–22 edits overlap.

### CI, status, and backend configuration

- `.github/workflows/ci.yml`
- `BASELINE_VERIFICATION.md`
- `DEVELOPMENT_STATUS.md`
- `backend/.env.example`
- `backend/pyproject.toml`
- `backend/scripts/demo_seed.py`

### Existing migration, API, and application wiring

- `backend/alembic/versions/e6f168c90ff8_add_progress_percent_to_uploads.py`
- `backend/app/api/__init__.py`
- `backend/app/api/billing.py`
- `backend/app/api/health.py`
- `backend/app/api/insights.py`
- `backend/app/api/meters.py`
- `backend/app/api/recommendations.py`
- `backend/app/api/scheduling.py`
- `backend/app/api/tariffs.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/middleware.py`
- `backend/app/tasks.py`

### Models, schemas, and services

- `backend/app/ml/forecast_evaluation.py`
- `backend/app/models/__init__.py`
- `backend/app/models/meter.py`
- `backend/app/models/reading.py`
- `backend/app/models/tariff.py`
- `backend/app/schemas/billing.py`
- `backend/app/schemas/insights.py`
- `backend/app/schemas/meter.py`
- `backend/app/schemas/reading.py`
- `backend/app/schemas/recommendation.py`
- `backend/app/schemas/scheduling.py`
- `backend/app/schemas/tariff.py`
- `backend/app/schemas/usage.py`
- `backend/app/services/ai_assistant.py`
- `backend/app/services/anomaly_detector.py`
- `backend/app/services/forecasting.py`
- `backend/app/services/nem12_importer.py`
- `backend/app/services/nem12_parser.py`
- `backend/app/services/recommendation_engine.py`
- `backend/app/services/scheduling_optimizer.py`
- `backend/app/services/tariff.py`
- `backend/app/services/usage_analyzer.py`

### Backend tests and fixture

- `backend/tests/fixtures/scheduling_v1.json`
- `backend/tests/test_anomaly_detector.py`
- `backend/tests/test_billing.py`
- `backend/tests/test_forecast_evaluation.py`
- `backend/tests/test_forecasting.py`
- `backend/tests/test_insights_endpoints.py`
- `backend/tests/test_migrations.py`
- `backend/tests/test_nem12_parser.py`
- `backend/tests/test_recommendation_engine.py`
- `backend/tests/test_scheduling_contract.py`
- `backend/tests/test_scheduling_optimizer.py`
- `backend/tests/test_upload.py`
- `backend/tests/test_usage_analyzer.py`
- `backend/tests/test_vertical_slice.py`

### Mobile application

- `mobile/app/(auth)/forgot-password.tsx`
- `mobile/app/(auth)/login.tsx`
- `mobile/app/(tabs)/index.tsx`
- `mobile/app/(tabs)/recommendations.tsx`
- `mobile/app/(tabs)/usage.tsx`
- `mobile/app/legal/terms.tsx`
- `mobile/app/onboarding.tsx`
- `mobile/app/scheduling.tsx`
- `mobile/app/tariff-setup.tsx`
- `mobile/app/upload.tsx`
- `mobile/components/BillComparison.tsx`
- `mobile/package-lock.json`
- `mobile/package.json`
- `mobile/services/api.ts`
- `mobile/stores/index.ts`

## 3. Untracked implementation, fixtures, and documentation to preserve

These 47 paths are not generated Graphify output or the backend-root test
artifacts. They are candidate source and must not be silently omitted.

### Migrations and implementation

- `backend/alembic/versions/a7b8c9d0e1f2_add_interval_provenance.py`
- `backend/alembic/versions/b8c9d0e1f2_add_nem12_source_coordinates.py`
- `backend/alembic/versions/c9d0e1f2a3b4_add_immutable_tariff_revisions.py`
- `backend/alembic/versions/d1e2f3a4b5c6_add_external_weather_context.py`
- `backend/app/api/context.py`
- `backend/app/data/__init__.py`
- `backend/app/data/aer_retailer_uris_2026_01.json`
- `backend/app/models/external_data.py`
- `backend/app/schemas/aer_prd.py`
- `backend/app/schemas/external_data.py`
- `backend/app/services/aer_prd.py`
- `backend/app/services/calculation_evidence.py`
- `backend/app/services/interval_quality.py`
- `backend/app/services/open_meteo.py`
- `backend/app/services/scheduling_baseline.py`

### Stage 1 specifications and acceptance evidence

- `backend/docs/stage1/AEMO_NEM12_COMPLIANCE_MATRIX.md`
- `backend/docs/stage1/AER_PRODUCT_REFERENCE_DATA.md`
- `backend/docs/stage1/EXTERNAL_DATA_INTEGRATION_DESIGN.md`
- `backend/docs/stage1/EXTERNAL_PROVIDER_SOURCE_MATRIX.md`
- `backend/docs/stage1/METRICS_AND_DATA_QUALITY_SPEC.md`
- `backend/docs/stage1/PHASE2_IMPLEMENTATION_BACKLOG.md`
- `backend/docs/stage1/PROMPT17_MIGRATION_COMPATIBILITY.md`
- `backend/docs/stage1/PROMPT18_ACCEPTANCE.md`
- `backend/docs/stage1/PROMPT18_MIGRATION_COMPATIBILITY.md`
- `backend/docs/stage1/PROMPT19_ACCEPTANCE.md`
- `backend/docs/stage1/PROMPT20B_STABILITY_REPORT.md`
- `backend/docs/stage1/PROMPT20C_NATIVE_FAULT_REPORT.md`
- `backend/docs/stage1/PROMPT20_ACCEPTANCE.md`
- `backend/docs/stage1/PROMPT21_ACCEPTANCE.md`
- `backend/docs/stage1/PROMPT21_FORECAST_EVALUATION.md`
- `backend/docs/stage1/PROMPT22_ACCEPTANCE.md`
- `backend/docs/stage1/RECOMMENDATION_EVIDENCE_CONTRACT.md`
- `backend/docs/stage1/STAGE1_CAPABILITY_MATRIX.md`
- `backend/docs/stage1/STAGE1_END_TO_END_TEST_REPORT.md`
- `backend/docs/stage1/STAGE1_RELEASE_READINESS.md`
- `backend/docs/stage1/STAGE1_REQUIREMENTS.md`
- `backend/docs/stage1/STAGE1_TEST_MATRIX.md`

### Lock, tests, fixtures, and mobile

- `backend/requirements-dev.lock`
- `backend/tests/fixtures/external/open_meteo_forecast_api_v1.json`
- `backend/tests/fixtures/metering/aemo_mdff_v2_7_interval_records.json`
- `backend/tests/fixtures/metering/prompt17_interval_quality_v1.json`
- `backend/tests/test_aer_prd.py`
- `backend/tests/test_external_data.py`
- `backend/tests/test_health.py`
- `backend/tests/test_interval_quality.py`
- `mobile/components/WeatherGridContext.tsx`
- `mobile/eslint.config.js`

Also include the Prompt 23 reports:

- `STAGE1_SOURCE_CHECKPOINT_PLAN.md`
- `PROMPT23_ENGINEERING_BASELINE.md`

## 4. Generated, machine-local, and sensitive exclusions

Exclude these from a source checkpoint while preserving them in place:

- 601 Graphify outputs under `graphify-out/`, `backend/graphify-out/`,
  `backend/app/graphify-out/`, and `backend/docs/demo/graphify-out/`.
- The five exact backend-root `file*` artifacts enumerated above. Their names
  and sizes are consistent with test-created SQLite artifacts, not
  application source; do not delete or stage them.
- Local `.env` files, including ignored `backend/.env`; never stage credentials.
- Local databases such as ignored `gridsense.db`, SQLite files, and any
  developer/demo database.
- Python environments (`.venv/`, `.venv311/`, `backend/.venv/`), caches,
  `node_modules/`, Expo output (`dist/`, `.expo/`), coverage, and build output.
- Re-generable model artifacts (`*.pkl`), logs, and machine-local research
  template archives.
- `mobile/expo-env.d.ts`, intentionally excluded by Expo's generated
  `mobile/.gitignore` entry; do not edit or stage it.

`backend/app/data/aer_retailer_uris_2026_01.json`, the new migration files,
test fixtures, and Stage 1 documentation are genuine source and are not
excluded by the active ignore rules. The sample-data ignore entry in the root
`.gitignore` is commented out, not an active exclusion. No accidental ignore
of these identified implementation paths was found.

Credential review found no confirmed real credential in the proposed source
set. This report intentionally contains no credential values. The test-only
CI secret is not a production secret.

## 5. Unresolved source and documentation discrepancies

- The full Prompt 17 acceptance report is not present in the worktree. The
  available Prompt 17 record is `PROMPT17_MIGRATION_COMPATIBILITY.md`; the
  later Prompt 22 report also notes this gap.
- Prompt 17–22 implementation is distributed across unstaged changes and
  untracked source, so a plain tracked-file diff is not a complete source
  checkpoint. All 47 untracked source paths above must be explicitly
  considered.
- Five backend-root `file*` artifacts remain untracked. They look like test
  database outputs from legacy SQLite URL handling, but their origin is not
  sufficiently verified to delete or rename them.
- Historical sections in `BASELINE_VERIFICATION.md` and
  `DEVELOPMENT_STATUS.md` contain older test/tooling status. The Prompt 23
  append-only updates supersede those statements for the current gate; retain
  the old records as historical evidence rather than rewriting them.
- The recorded Git HEAD does not include any of the current staged-for-review
  implementation; no commit is authorized or recommended until the user has
  reviewed the exact hunk-level staging list.

## 6. Migration and active-import inventory

`alembic history --verbose` reports one continuous chain with no missing
revision:

`0001_initial_schema` -> `0002_schedule_execution` ->
`e6f168c90ff8` -> `a1b2c3d4e5f6` -> `c3d4e5f6a7b8` ->
`d4e5f6a7b8c9` -> `e5f6a7b8c9d0` -> `f6a7b8c9d0e1` ->
`a7b8c9d0e1f2` -> `b8c9d0e1f2` -> `c9d0e1f2a3b4` ->
`d1e2f3a4b5c6` (head).

The four new migration files are listed above and are required source, not
generated output. A PostgreSQL 16 upgrade-to-head, downgrade-to-base, and
re-upgrade-to-head cycle passed after correcting the existing downgrade to
use `sa.DateTime()`. The SQLite migration tests also pass. No migration
revision is absent from the source checkpoint.

The implementation wiring audit confirmed:

- `context_router` is imported and included by the active FastAPI application.
- The AER reference-data service is used by tariff routes.
- Interval eligibility is used by billing and usage analysis.
- Scheduling baseline eligibility is used by the active scheduling route.
- Calculation evidence is used by recommendations and scheduling.
- External weather models and schemas are used by the weather service and
  context route.

## 7. Recommended future staging/commit structure

No staging has been performed. After explicit authorization, use a reviewed
path list and stage by coherent changes, not by broad `git add .`:

1. **Backend contracts and persisted source provenance** — API, models,
   schemas, services, AER data, and all migration revisions; include the
   corresponding metering, tariff, external-data, recommendation, and
   scheduling tests/fixtures.
2. **Mobile integration and local quality tooling** — the listed mobile
   screens/services/stores, weather context, ESLint config, package manifest,
   and lockfile; include the clean-install and web/type/lint results.
3. **Reproducible engineering gates** — `backend/pyproject.toml`,
   `backend/requirements-dev.lock`, the CI workflow, portable migration
   downgrade, and relevant migration/health regression tests.
4. **Acceptance and status evidence** — Prompt 17–22 Stage 1 reports,
   `BASELINE_VERIFICATION.md`, `DEVELOPMENT_STATUS.md`, and the two Prompt 23
   reports.

These are review groupings only. Some tracked files contain changes from
multiple prompts; inspect and stage individual hunks if a commit boundary
requires it. Do not stage the generated artifacts, local configuration,
databases, environments, caches, or credentials. Do not commit or push without
the user's approval.

## Prompt 23A source checkpoint supplement — 2 November 2026

The repository remains on `main` at
`d789f9814da9955db1c63ced921a95379dd08495`. At the latest recorded snapshot,
the worktree had **103 tracked modified paths, 657 untracked paths, and zero
staged paths**. These counts include pre-existing Prompt 17–23 work and
generated/local files; they are not a source-only manifest. Do not stage from
these counts or use `git add .`.

### Additional Prompt 23A changes to preserve

- `ENGINEERING_DEFECT_REGISTER.md`
- `PROMPT23A_STABILIZATION_REPORT.md`
- `BASELINE_VERIFICATION.md`
- `DEVELOPMENT_STATUS.md`
- `STAGE1_SOURCE_CHECKPOINT_PLAN.md`
- Backend Ruff corrections in existing `backend/app/**` and
  `backend/tests/**` files; review exact hunks rather than replacing entire
  files because they contain changes from earlier prompts.
- Test-isolation corrections in `backend/tests/test_auth.py`,
  `backend/tests/test_insights_endpoints.py`, `backend/tests/test_ml.py`, and
  `backend/tests/test_password_reset.py`.
- Mobile modal focus correction in `mobile/app/(tabs)/automation.tsx`.
- Compatible mobile dependency changes in `mobile/package.json` and
  `mobile/package-lock.json`, plus `mobile/eslint.config.js` where not already
  included in the earlier untracked-source inventory.

The precise set is the output of a fresh `git diff --name-only` plus reviewed
untracked source paths, not the list above alone. The 601 Graphify files,
backend-root `file*` artifacts, ignored developer databases and credentials,
Python environments, caches, `node_modules`, and Expo build outputs remain
excluded.

### SQLite test-path finding and data-preservation limitation

The Prompt 23A focused audit found four tests using fixed URI-style SQLite
URLs. A controlled reproduction in a new temporary directory showed that the
legacy URL created a disk file in its working directory despite the `uri`
connection argument. The four fixtures now use unique per-test databases
under `tmp_path`, dispose their engines, and restore global overrides where
applicable. The focused run passed 23 tests; metadata for the pre-existing
backend-root `file*` artifacts did not change during that focused run.

However, at least one earlier test execution occurred before this correction,
and no artifact hashes or snapshots were recorded before that execution.
Whether existing artifact contents changed cannot be determined. Preserve
all five artifacts exactly as found; do not delete, rewrite, or infer that
they are disposable based on their names. A trusted owner-held backup is
needed for any content comparison or restoration decision. This limitation
is recorded as D23A-004 in
[ENGINEERING_DEFECT_REGISTER.md](ENGINEERING_DEFECT_REGISTER.md).

### Gate and staging decision

Backend Ruff, focused fixture tests, the Windows/Linux backend assertions,
mobile lint/typecheck/Expo compatibility/export, and prior disposable
PostgreSQL/Redis evidence are recorded in
[PROMPT23A_STABILIZATION_REPORT.md](PROMPT23A_STABILIZATION_REPORT.md).
Windows native stability, five production high-severity npm advisories,
browser verification of the modal focus lifecycle, artifact-preservation
certainty, and hosted CI remain blockers. This is a proposal only: nothing
was staged, committed, or pushed. Prompt 24 should not begin.

## Prompt 23B refreshed inventory and exact candidate manifest

This refreshed inventory supersedes the older 70-modified/653-untracked
snapshot above. It was taken on branch `main` at
`d789f9814da9955db1c63ced921a95379dd08495`. After adding the Prompt 23B
report, the expected counts are 106 tracked modified paths, 659 untracked
paths, 53 untracked source/documentation candidates, 601 generated Graphify
files, five preserved backend-root artifacts, and zero staged paths. No
commit, reset, cleanup, or push was performed. Recount before any later
staging; these totals are a review aid, not permission to stage.

### Exact tracked modified paths to preserve (106)

```text
.github/workflows/ci.yml
BASELINE_VERIFICATION.md
DEVELOPMENT_STATUS.md
backend/.env.example
backend/alembic/versions/e6f168c90ff8_add_progress_percent_to_uploads.py
backend/app/api/__init__.py
backend/app/api/auth.py
backend/app/api/automation.py
backend/app/api/billing.py
backend/app/api/chat.py
backend/app/api/health.py
backend/app/api/insights.py
backend/app/api/meters.py
backend/app/api/notifications.py
backend/app/api/notifications_new.py
backend/app/api/recommendations.py
backend/app/api/scheduling.py
backend/app/api/tariffs.py
backend/app/api/usage.py
backend/app/config.py
backend/app/main.py
backend/app/middleware.py
backend/app/ml/cli.py
backend/app/ml/etl.py
backend/app/ml/forecast_evaluation.py
backend/app/ml/predict.py
backend/app/ml/train.py
backend/app/models/__init__.py
backend/app/models/aggregate.py
backend/app/models/automation.py
backend/app/models/chat.py
backend/app/models/meter.py
backend/app/models/ml_training.py
backend/app/models/notification.py
backend/app/models/reading.py
backend/app/models/tariff.py
backend/app/models/user.py
backend/app/schemas/automation.py
backend/app/schemas/billing.py
backend/app/schemas/chat.py
backend/app/schemas/insights.py
backend/app/schemas/meter.py
backend/app/schemas/reading.py
backend/app/schemas/recommendation.py
backend/app/schemas/scheduling.py
backend/app/schemas/tariff.py
backend/app/schemas/usage.py
backend/app/services/ai_assistant.py
backend/app/services/anomaly_detector.py
backend/app/services/auth.py
backend/app/services/automation_provider.py
backend/app/services/chat_service.py
backend/app/services/forecasting.py
backend/app/services/nem12_importer.py
backend/app/services/nem12_parser.py
backend/app/services/notification_service.py
backend/app/services/rag_engine.py
backend/app/services/recommendation_engine.py
backend/app/services/scheduling_optimizer.py
backend/app/services/tariff.py
backend/app/services/usage_analyzer.py
backend/app/tasks.py
backend/pyproject.toml
backend/scripts/demo_seed.py
backend/tests/conftest.py
backend/tests/fixtures/scheduling_v1.json
backend/tests/test_anomaly_detector.py
backend/tests/test_auth.py
backend/tests/test_billing.py
backend/tests/test_forecast_evaluation.py
backend/tests/test_forecasting.py
backend/tests/test_insights_endpoints.py
backend/tests/test_migrations.py
backend/tests/test_ml.py
backend/tests/test_nem12_parser.py
backend/tests/test_password_reset.py
backend/tests/test_recommendation_engine.py
backend/tests/test_scheduling_contract.py
backend/tests/test_scheduling_optimizer.py
backend/tests/test_tariff.py
backend/tests/test_upload.py
backend/tests/test_usage_analyzer.py
backend/tests/test_vertical_slice.py
mobile/app.json
mobile/app/(auth)/forgot-password.tsx
mobile/app/(auth)/login.tsx
mobile/app/(tabs)/_layout.tsx
mobile/app/(tabs)/automation.tsx
mobile/app/(tabs)/chat.tsx
mobile/app/(tabs)/index.tsx
mobile/app/(tabs)/recommendations.tsx
mobile/app/(tabs)/usage.tsx
mobile/app/_layout.tsx
mobile/app/legal/terms.tsx
mobile/app/onboarding.tsx
mobile/app/scheduling.tsx
mobile/app/tariff-setup.tsx
mobile/app/upload.tsx
mobile/components/BillComparison.tsx
mobile/components/OfflineBanner.tsx
mobile/package-lock.json
mobile/package.json
mobile/services/api.ts
mobile/services/errorHandler.ts
mobile/stores/index.ts
mobile/tsconfig.json
```

### Exact untracked source/documentation candidates to preserve (53)

```text
ENGINEERING_DEFECT_REGISTER.md
PROMPT23A_STABILIZATION_REPORT.md
PROMPT23B_NATIVE_STABILITY_REPORT.md
PROMPT23_ENGINEERING_BASELINE.md
STAGE1_SOURCE_CHECKPOINT_PLAN.md
backend/alembic/versions/a7b8c9d0e1f2_add_interval_provenance.py
backend/alembic/versions/b8c9d0e1f2_add_nem12_source_coordinates.py
backend/alembic/versions/c9d0e1f2a3b4_add_immutable_tariff_revisions.py
backend/alembic/versions/d1e2f3a4b5c6_add_external_weather_context.py
backend/app/api/context.py
backend/app/data/__init__.py
backend/app/data/aer_retailer_uris_2026_01.json
backend/app/models/external_data.py
backend/app/schemas/aer_prd.py
backend/app/schemas/external_data.py
backend/app/services/aer_prd.py
backend/app/services/calculation_evidence.py
backend/app/services/interval_quality.py
backend/app/services/open_meteo.py
backend/app/services/scheduling_baseline.py
backend/docs/stage1/AEMO_NEM12_COMPLIANCE_MATRIX.md
backend/docs/stage1/AER_PRODUCT_REFERENCE_DATA.md
backend/docs/stage1/EXTERNAL_DATA_INTEGRATION_DESIGN.md
backend/docs/stage1/EXTERNAL_PROVIDER_SOURCE_MATRIX.md
backend/docs/stage1/METRICS_AND_DATA_QUALITY_SPEC.md
backend/docs/stage1/PHASE2_IMPLEMENTATION_BACKLOG.md
backend/docs/stage1/PROMPT17_MIGRATION_COMPATIBILITY.md
backend/docs/stage1/PROMPT18_ACCEPTANCE.md
backend/docs/stage1/PROMPT18_MIGRATION_COMPATIBILITY.md
backend/docs/stage1/PROMPT19_ACCEPTANCE.md
backend/docs/stage1/PROMPT20_ACCEPTANCE.md
backend/docs/stage1/PROMPT20B_STABILITY_REPORT.md
backend/docs/stage1/PROMPT20C_NATIVE_FAULT_REPORT.md
backend/docs/stage1/PROMPT21_ACCEPTANCE.md
backend/docs/stage1/PROMPT21_FORECAST_EVALUATION.md
backend/docs/stage1/PROMPT22_ACCEPTANCE.md
backend/docs/stage1/RECOMMENDATION_EVIDENCE_CONTRACT.md
backend/docs/stage1/STAGE1_CAPABILITY_MATRIX.md
backend/docs/stage1/STAGE1_END_TO_END_TEST_REPORT.md
backend/docs/stage1/STAGE1_RELEASE_READINESS.md
backend/docs/stage1/STAGE1_REQUIREMENTS.md
backend/docs/stage1/STAGE1_TEST_MATRIX.md
backend/requirements-dev.lock
backend/scripts/run_native_pytest.py
backend/tests/fixtures/external/open_meteo_forecast_api_v1.json
backend/tests/fixtures/metering/aemo_mdff_v2_7_interval_records.json
backend/tests/fixtures/metering/prompt17_interval_quality_v1.json
backend/tests/test_aer_prd.py
backend/tests/test_external_data.py
backend/tests/test_health.py
backend/tests/test_interval_quality.py
mobile/components/WeatherGridContext.tsx
mobile/eslint.config.js
```

### Exclusions, completeness, and staging structure

- Preserve but exclude all 601 Graphify-generated files under the four
  `graphify-out` trees, and preserve but exclude the five pre-existing
  `backend/file*` artifacts. Do not inspect, delete, rename, or restore the
  five artifacts without a trusted owner-held snapshot.
- Exclude ignored `.env` files, developer databases (`gridsense.db` and
  `backend/gridsense.db`), model binaries, coverage output, caches, Python
  environments, `mobile/node_modules/`, `mobile/.expo/`, `mobile/dist/`,
  generated Expo files, logs, and the ignored journal-template folder. Keep
  each item in place. The current ignored-path enumeration returned 85,944
  paths; category names are listed above rather than reproducing
  machine-local paths.
- A bounded credential-pattern scan covered exactly the 159 paths in the
  candidate manifest. It reported zero matches and no credential values were
  printed. This is not a guarantee against every secret format. `.env` and
  developer data are outside the candidate set; `backend/.env.example`
  contains templates, not deployment secrets.
- The four new Alembic revisions are present in the candidate manifest. A
  read-only `alembic heads`/`history --verbose` inspection found one head,
  `d1e2f3a4b5c6`, with a complete 12-revision chain from `0001_initial_schema`.
  The new `context_router` is imported in `backend/app/api/__init__.py` and
  included by `backend/app/main.py` under the configured API prefix.
- The isolated Linux test copy used only `app/`, `alembic/`, `tests/`,
  `scripts/`, `pyproject.toml`, `requirements-dev.lock`, and `alembic.ini`;
  it excluded `.env`, Graphify, caches, and the backend-root artifacts.
  Three locked full suites passed there. This is not a clean Git checkout
  reproduction, and the full 159-path source checkpoint has not yet been
  staged or reproduced from a clean checkout.
- If staging is later approved, review the exact tracked/untracked paths and
  diffs first. Recommended logical commits are: backend source/migrations/
  fixtures/tests; mobile SDK/lint/accessibility and lockfile; CI/version-lock
  updates; then acceptance/status documentation. This plan authorizes no
  staging, commit, or push.

## Mobile SDK 58 modernization supplement

The later mobile upgrade adds or updates source that must be included in any
future reviewed source checkpoint:

- `mobile/package.json` and `mobile/package-lock.json`
- `mobile/app.json` and `mobile/tsconfig.json`
- `mobile/app/(tabs)/_layout.tsx`
- `mobile/app/(tabs)/automation.tsx`
- `mobile/app/(tabs)/chat.tsx`
- `mobile/app/(tabs)/recommendations.tsx`
- `mobile/app/onboarding.tsx`
- `mobile/app/upload.tsx`
- `mobile/components/OfflineBanner.tsx`
- `mobile/components/WeatherGridContext.tsx`
- `mobile/services/api.ts`
- Updated dependency/security and test evidence in
  `ENGINEERING_DEFECT_REGISTER.md`, `PROMPT23A_STABILIZATION_REPORT.md`,
  `BASELINE_VERIFICATION.md`, and `DEVELOPMENT_STATUS.md`

These are source/configuration changes, not Expo-generated artifacts. Keep
`mobile/node_modules/`, `mobile/.expo/`, `mobile/dist/`, and other build
outputs excluded. The tree remains dirty and the original source-inventory
counts above are historical; regenerate and review the exact manifest before
any authorized staging. Nothing was staged, committed, or pushed. Prompt 24 should not begin.

## Prompt 23C fresh exact source inventory — 2 November 2026

The fresh inventory was generated with
`git status --porcelain=v1 -z --untracked-files=all` at
`main` / `d789f9814da9955db1c63ced921a95379dd08495`. It records **106 tracked
modified paths**, **55 untracked source/documentation candidates**, **601
Graphify-generated paths**, **five legacy `backend/file*` artifacts**, and
**zero staged paths**. Thus the current source-candidate set is **161 paths**.
The old 70/47 and 159-path counts elsewhere in this document are historical
snapshots; this section is the current path manifest.

The exact tracked modified paths are:

```text
.github/workflows/ci.yml
BASELINE_VERIFICATION.md
DEVELOPMENT_STATUS.md
backend/.env.example
backend/alembic/versions/e6f168c90ff8_add_progress_percent_to_uploads.py
backend/app/api/__init__.py
backend/app/api/auth.py
backend/app/api/automation.py
backend/app/api/billing.py
backend/app/api/chat.py
backend/app/api/health.py
backend/app/api/insights.py
backend/app/api/meters.py
backend/app/api/notifications.py
backend/app/api/notifications_new.py
backend/app/api/recommendations.py
backend/app/api/scheduling.py
backend/app/api/tariffs.py
backend/app/api/usage.py
backend/app/config.py
backend/app/main.py
backend/app/middleware.py
backend/app/ml/cli.py
backend/app/ml/etl.py
backend/app/ml/forecast_evaluation.py
backend/app/ml/predict.py
backend/app/ml/train.py
backend/app/models/__init__.py
backend/app/models/aggregate.py
backend/app/models/automation.py
backend/app/models/chat.py
backend/app/models/meter.py
backend/app/models/ml_training.py
backend/app/models/notification.py
backend/app/models/reading.py
backend/app/models/tariff.py
backend/app/models/user.py
backend/app/schemas/automation.py
backend/app/schemas/billing.py
backend/app/schemas/chat.py
backend/app/schemas/insights.py
backend/app/schemas/meter.py
backend/app/schemas/reading.py
backend/app/schemas/recommendation.py
backend/app/schemas/scheduling.py
backend/app/schemas/tariff.py
backend/app/schemas/usage.py
backend/app/services/ai_assistant.py
backend/app/services/anomaly_detector.py
backend/app/services/auth.py
backend/app/services/automation_provider.py
backend/app/services/chat_service.py
backend/app/services/forecasting.py
backend/app/services/nem12_importer.py
backend/app/services/nem12_parser.py
backend/app/services/notification_service.py
backend/app/services/rag_engine.py
backend/app/services/recommendation_engine.py
backend/app/services/scheduling_optimizer.py
backend/app/services/tariff.py
backend/app/services/usage_analyzer.py
backend/app/tasks.py
backend/pyproject.toml
backend/scripts/demo_seed.py
backend/tests/conftest.py
backend/tests/fixtures/scheduling_v1.json
backend/tests/test_anomaly_detector.py
backend/tests/test_auth.py
backend/tests/test_billing.py
backend/tests/test_forecast_evaluation.py
backend/tests/test_forecasting.py
backend/tests/test_insights_endpoints.py
backend/tests/test_migrations.py
backend/tests/test_ml.py
backend/tests/test_nem12_parser.py
backend/tests/test_password_reset.py
backend/tests/test_recommendation_engine.py
backend/tests/test_scheduling_contract.py
backend/tests/test_scheduling_optimizer.py
backend/tests/test_tariff.py
backend/tests/test_upload.py
backend/tests/test_usage_analyzer.py
backend/tests/test_vertical_slice.py
mobile/app.json
mobile/app/(auth)/forgot-password.tsx
mobile/app/(auth)/login.tsx
mobile/app/(tabs)/_layout.tsx
mobile/app/(tabs)/automation.tsx
mobile/app/(tabs)/chat.tsx
mobile/app/(tabs)/index.tsx
mobile/app/(tabs)/recommendations.tsx
mobile/app/(tabs)/usage.tsx
mobile/app/_layout.tsx
mobile/app/legal/terms.tsx
mobile/app/onboarding.tsx
mobile/app/scheduling.tsx
mobile/app/tariff-setup.tsx
mobile/app/upload.tsx
mobile/components/BillComparison.tsx
mobile/components/OfflineBanner.tsx
mobile/package-lock.json
mobile/package.json
mobile/services/api.ts
mobile/services/errorHandler.ts
mobile/stores/index.ts
mobile/tsconfig.json
```

The exact untracked source/documentation candidates are:

```text
ENGINEERING_DEFECT_REGISTER.md
PROMPT23A_STABILIZATION_REPORT.md
PROMPT23B_NATIVE_STABILITY_REPORT.md
PROMPT23_ENGINEERING_BASELINE.md
STAGE1_SOURCE_CHECKPOINT_PLAN.md
backend/alembic/versions/a7b8c9d0e1f2_add_interval_provenance.py
backend/alembic/versions/b8c9d0e1f2_add_nem12_source_coordinates.py
backend/alembic/versions/c9d0e1f2a3b4_add_immutable_tariff_revisions.py
backend/alembic/versions/d1e2f3a4b5c6_add_external_weather_context.py
backend/app/api/context.py
backend/app/data/__init__.py
backend/app/data/aer_retailer_uris_2026_01.json
backend/app/models/external_data.py
backend/app/schemas/aer_prd.py
backend/app/schemas/external_data.py
backend/app/services/aer_prd.py
backend/app/services/calculation_evidence.py
backend/app/services/interval_quality.py
backend/app/services/open_meteo.py
backend/app/services/scheduling_baseline.py
backend/docs/stage1/AEMO_NEM12_COMPLIANCE_MATRIX.md
backend/docs/stage1/AER_PRODUCT_REFERENCE_DATA.md
backend/docs/stage1/EXTERNAL_DATA_INTEGRATION_DESIGN.md
backend/docs/stage1/EXTERNAL_PROVIDER_SOURCE_MATRIX.md
backend/docs/stage1/METRICS_AND_DATA_QUALITY_SPEC.md
backend/docs/stage1/PHASE2_IMPLEMENTATION_BACKLOG.md
backend/docs/stage1/PROMPT17_MIGRATION_COMPATIBILITY.md
backend/docs/stage1/PROMPT18_ACCEPTANCE.md
backend/docs/stage1/PROMPT18_MIGRATION_COMPATIBILITY.md
backend/docs/stage1/PROMPT19_ACCEPTANCE.md
backend/docs/stage1/PROMPT20B_STABILITY_REPORT.md
backend/docs/stage1/PROMPT20C_NATIVE_FAULT_REPORT.md
backend/docs/stage1/PROMPT20_ACCEPTANCE.md
backend/docs/stage1/PROMPT21_ACCEPTANCE.md
backend/docs/stage1/PROMPT21_FORECAST_EVALUATION.md
backend/docs/stage1/PROMPT22_ACCEPTANCE.md
backend/docs/stage1/PROMPT23C_LIFECYCLE_INVESTIGATION.md
backend/docs/stage1/RECOMMENDATION_EVIDENCE_CONTRACT.md
backend/docs/stage1/STAGE1_CAPABILITY_MATRIX.md
backend/docs/stage1/STAGE1_END_TO_END_TEST_REPORT.md
backend/docs/stage1/STAGE1_RELEASE_READINESS.md
backend/docs/stage1/STAGE1_REQUIREMENTS.md
backend/docs/stage1/STAGE1_TEST_MATRIX.md
backend/requirements-dev.lock
backend/scripts/pytest_lifecycle_instrumentation.py
backend/scripts/run_native_pytest.py
backend/tests/fixtures/external/open_meteo_forecast_api_v1.json
backend/tests/fixtures/metering/aemo_mdff_v2_7_interval_records.json
backend/tests/fixtures/metering/prompt17_interval_quality_v1.json
backend/tests/test_aer_prd.py
backend/tests/test_external_data.py
backend/tests/test_health.py
backend/tests/test_interval_quality.py
mobile/components/WeatherGridContext.tsx
mobile/eslint.config.js
```

The five `backend/file*` artifacts and all Graphify-generated files remain
preserved but excluded. Test databases, native diagnostics, A/B variants,
the web export, and service logs are outside the repository in disposable
session-state paths. This inventory does not include ignored developer
databases, local `.env`, or generated build output.

The changed-path list is exact for this worktree snapshot, not an instruction
to stage all paths. Several tracked files contain changes from multiple
prompts and require hunk-level review. The previous credential-pattern scan
covered a prior 159-path candidate set; it was not rerun over this expanded
161-path set. The sanitized backend copy used for focused experiments is not
a clean reproduction of all 161 candidates. No clean Git clone, staging,
commit, or push was performed.

## 8. Prompt 23D refreshed inventory and clean-copy evidence

This addendum supersedes the earlier snapshot counts above. At the Prompt
23D inventory:

- Branch / HEAD: `main` /
  `d789f9814da9955db1c63ced921a95379dd08495`.
- Index: **0 staged paths**.
- Tracked modified paths: **106**.
- Untracked paths: **676**, consisting of **615 generated Graphify paths**,
  **5 preserved `backend/file*` artifacts**, and **56 source/documentation
  candidates**.
- Exact source checkpoint candidate manifest: **162 paths** (106 tracked
  modified + 56 untracked source/documentation candidates).
- No source file, developer database, legacy artifact, or generated
  Graphify output was staged, committed, pushed, reset, cleaned, or deleted.

The 615 Graphify files remain in place and are excluded from the candidate
manifest. The five legacy files remain untouched and excluded; their
historical content/provenance remains unresolved. The local research archive,
local environment files, caches, virtual environments, databases, and
generated mobile output are also excluded.

### Exact tracked modified paths (106)

```text
.github/workflows/ci.yml
BASELINE_VERIFICATION.md
DEVELOPMENT_STATUS.md
backend/.env.example
backend/alembic/versions/e6f168c90ff8_add_progress_percent_to_uploads.py
backend/app/api/__init__.py
backend/app/api/auth.py
backend/app/api/automation.py
backend/app/api/billing.py
backend/app/api/chat.py
backend/app/api/health.py
backend/app/api/insights.py
backend/app/api/meters.py
backend/app/api/notifications.py
backend/app/api/notifications_new.py
backend/app/api/recommendations.py
backend/app/api/scheduling.py
backend/app/api/tariffs.py
backend/app/api/usage.py
backend/app/config.py
backend/app/main.py
backend/app/middleware.py
backend/app/ml/cli.py
backend/app/ml/etl.py
backend/app/ml/forecast_evaluation.py
backend/app/ml/predict.py
backend/app/ml/train.py
backend/app/models/__init__.py
backend/app/models/aggregate.py
backend/app/models/automation.py
backend/app/models/chat.py
backend/app/models/meter.py
backend/app/models/ml_training.py
backend/app/models/notification.py
backend/app/models/reading.py
backend/app/models/tariff.py
backend/app/models/user.py
backend/app/schemas/automation.py
backend/app/schemas/billing.py
backend/app/schemas/chat.py
backend/app/schemas/insights.py
backend/app/schemas/meter.py
backend/app/schemas/reading.py
backend/app/schemas/recommendation.py
backend/app/schemas/scheduling.py
backend/app/schemas/tariff.py
backend/app/schemas/usage.py
backend/app/services/ai_assistant.py
backend/app/services/anomaly_detector.py
backend/app/services/auth.py
backend/app/services/automation_provider.py
backend/app/services/chat_service.py
backend/app/services/forecasting.py
backend/app/services/nem12_importer.py
backend/app/services/nem12_parser.py
backend/app/services/notification_service.py
backend/app/services/rag_engine.py
backend/app/services/recommendation_engine.py
backend/app/services/scheduling_optimizer.py
backend/app/services/tariff.py
backend/app/services/usage_analyzer.py
backend/app/tasks.py
backend/pyproject.toml
backend/scripts/demo_seed.py
backend/tests/conftest.py
backend/tests/fixtures/scheduling_v1.json
backend/tests/test_anomaly_detector.py
backend/tests/test_auth.py
backend/tests/test_billing.py
backend/tests/test_forecast_evaluation.py
backend/tests/test_forecasting.py
backend/tests/test_insights_endpoints.py
backend/tests/test_migrations.py
backend/tests/test_ml.py
backend/tests/test_nem12_parser.py
backend/tests/test_password_reset.py
backend/tests/test_recommendation_engine.py
backend/tests/test_scheduling_contract.py
backend/tests/test_scheduling_optimizer.py
backend/tests/test_tariff.py
backend/tests/test_upload.py
backend/tests/test_usage_analyzer.py
backend/tests/test_vertical_slice.py
mobile/app.json
mobile/app/(auth)/forgot-password.tsx
mobile/app/(auth)/login.tsx
mobile/app/(tabs)/_layout.tsx
mobile/app/(tabs)/automation.tsx
mobile/app/(tabs)/chat.tsx
mobile/app/(tabs)/index.tsx
mobile/app/(tabs)/recommendations.tsx
mobile/app/(tabs)/usage.tsx
mobile/app/_layout.tsx
mobile/app/legal/terms.tsx
mobile/app/onboarding.tsx
mobile/app/scheduling.tsx
mobile/app/tariff-setup.tsx
mobile/app/upload.tsx
mobile/components/BillComparison.tsx
mobile/components/OfflineBanner.tsx
mobile/package-lock.json
mobile/package.json
mobile/services/api.ts
mobile/services/errorHandler.ts
mobile/stores/index.ts
mobile/tsconfig.json
```

### Exact untracked source/documentation candidates (56)

```text
ENGINEERING_DEFECT_REGISTER.md
PROMPT23A_STABILIZATION_REPORT.md
PROMPT23B_NATIVE_STABILITY_REPORT.md
PROMPT23_ENGINEERING_BASELINE.md
STAGE1_SOURCE_CHECKPOINT_PLAN.md
backend/alembic/versions/a7b8c9d0e1f2_add_interval_provenance.py
backend/alembic/versions/b8c9d0e1f2_add_nem12_source_coordinates.py
backend/alembic/versions/c9d0e1f2a3b4_add_immutable_tariff_revisions.py
backend/alembic/versions/d1e2f3a4b5c6_add_external_weather_context.py
backend/app/api/context.py
backend/app/data/__init__.py
backend/app/data/aer_retailer_uris_2026_01.json
backend/app/models/external_data.py
backend/app/schemas/aer_prd.py
backend/app/schemas/external_data.py
backend/app/services/aer_prd.py
backend/app/services/calculation_evidence.py
backend/app/services/interval_quality.py
backend/app/services/open_meteo.py
backend/app/services/scheduling_baseline.py
backend/docs/stage1/AEMO_NEM12_COMPLIANCE_MATRIX.md
backend/docs/stage1/AER_PRODUCT_REFERENCE_DATA.md
backend/docs/stage1/EXTERNAL_DATA_INTEGRATION_DESIGN.md
backend/docs/stage1/EXTERNAL_PROVIDER_SOURCE_MATRIX.md
backend/docs/stage1/METRICS_AND_DATA_QUALITY_SPEC.md
backend/docs/stage1/PHASE2_IMPLEMENTATION_BACKLOG.md
backend/docs/stage1/PROMPT17_MIGRATION_COMPATIBILITY.md
backend/docs/stage1/PROMPT18_ACCEPTANCE.md
backend/docs/stage1/PROMPT18_MIGRATION_COMPATIBILITY.md
backend/docs/stage1/PROMPT19_ACCEPTANCE.md
backend/docs/stage1/PROMPT20B_STABILITY_REPORT.md
backend/docs/stage1/PROMPT20C_NATIVE_FAULT_REPORT.md
backend/docs/stage1/PROMPT20_ACCEPTANCE.md
backend/docs/stage1/PROMPT21_ACCEPTANCE.md
backend/docs/stage1/PROMPT21_FORECAST_EVALUATION.md
backend/docs/stage1/PROMPT22_ACCEPTANCE.md
backend/docs/stage1/PROMPT23C_LIFECYCLE_INVESTIGATION.md
backend/docs/stage1/PROMPT23D_FULL_SUITE_COMPARISON.md
backend/docs/stage1/RECOMMENDATION_EVIDENCE_CONTRACT.md
backend/docs/stage1/STAGE1_CAPABILITY_MATRIX.md
backend/docs/stage1/STAGE1_END_TO_END_TEST_REPORT.md
backend/docs/stage1/STAGE1_RELEASE_READINESS.md
backend/docs/stage1/STAGE1_REQUIREMENTS.md
backend/docs/stage1/STAGE1_TEST_MATRIX.md
backend/requirements-dev.lock
backend/scripts/pytest_lifecycle_instrumentation.py
backend/scripts/run_native_pytest.py
backend/tests/fixtures/external/open_meteo_forecast_api_v1.json
backend/tests/fixtures/metering/aemo_mdff_v2_7_interval_records.json
backend/tests/fixtures/metering/prompt17_interval_quality_v1.json
backend/tests/test_aer_prd.py
backend/tests/test_external_data.py
backend/tests/test_health.py
backend/tests/test_interval_quality.py
mobile/components/WeatherGridContext.tsx
mobile/eslint.config.js
```

The source-only copy was created in a disposable temporary directory outside
the repository from the full worktree, not from HEAD alone. It included 405
files before the new Prompt 23D report was copied into it; the final
source-only snapshot contained 406 files. It excluded Graphify output, all
five legacy artifacts, `.env`, caches, local databases, the virtual
environment, `node_modules`, and the local research archive. The backend
lock hash and mobile package-lock hash matched the source worktree exactly.
Ruff, the 265-test backend suite, SQLite migration round trip, mobile clean
install, lint, TypeScript, Expo Doctor, web export, and audits were executed
from that copy. This verifies a source-only local reproduction, not hosted CI
or a fresh Git clone.

The source list is a review manifest, not authorization to stage. Tracked
files still require hunk-level review because changes span multiple prompts.
The Prompt 23D evidence report records the full test fingerprint, A/B
results, diagnostics, and remaining blockers. No commit or push is
authorized by this plan.

## Prompt 23E source checkpoint manifest

- Git: HEAD `d789f98`. `git status`: 829 entries (114 modified, 715 untracked).
- Include (kept source set): 188 untracked and modified paths, plus tracked files. A clean copy of 316 files reproduced the SQLite suite (275 passed, exit 0).
  - Includes `backend/app`, `backend/tests` (including `tests/integration`), `backend/alembic`, `backend/scripts`, `backend/docs/stage1`, `backend/pyproject.toml`, `backend/requirements-dev.lock`, `backend/.env.example`, `mobile/` source and config, `.github/workflows`, and the root stabilisation reports.
- Exclude: Graphify output (`graphify-out/`, `backend/graphify-out/`, `backend/docs/demo/graphify-out/`), legacy `backend/file*` artifacts (5 entries with Windows-invalid names), SQLite and PostgreSQL developer data, `.env` secrets, caches, `.venv*`, `node_modules`, and `mobile/dist`.
- Retained as evidence, not source: `files/prompt23e/`.
- Secret-pattern scan over the kept set: no credentials found. Matches were test placeholders only.
- Proposed checkpoint is human-reviewable. Staging, commit, and push are NOT performed and need explicit approval.
- Blockers before a checkpoint: pip-audit gate passes only through 4 documented chromadb exceptions (owner unassigned; 0 fixes published upstream), Windows SQLite native fault (BLOCKED, recurred in 1 of 4 runs), hosted CI NOT VERIFIED, python-jose to PyJWT auth change awaiting sign-off.
- Security source changes this pass: `backend/app/services/auth.py`, `backend/pyproject.toml`, `backend/requirements-dev.lock`, `backend/tests/test_jwt_security.py`, `backend/tests/test_chromadb_exposure.py`, `.github/workflows/ci.yml`, `backend/docs/stage1/PROMPT23E_SECURITY_REMEDIATION.md`.
- Source-manifest refresh: NOT performed in this pass. The manifest count from the previous pass (316 files) is stale and must be regenerated before any checkpoint.
- Clean-copy verification: the Linux container ran the full backend suite and integration suite from a copy of `backend/` (`/work`), so the backend reproduces from the source copy.

## Prompt 23E-Security source checkpoint (superseded by section 0 and section 9)

- Superseded: the 314/678 counts below are historical. The current manifest is 322 included / 706 excluded (section 0).
- Manifest: 314 included, 678 excluded (615 Graphify, 5 legacy `backend/file*`, 58 `files/` evidence). 0 unaccounted. Supersedes the 316-file count above.
- Lists: `files/prompt23e-security/checkpoint/included-files.txt`, `excluded-files.json`, `manifest.json`.
- Clean copy of the 314 files: no missing files. Ruff, 331 passed / 24 skipped, and 355 passed / 0 skipped with restricted PostgreSQL.
- Secret scan over the 314-file set: 22 hits reviewed, none live.
- Git: nothing staged, committed, pushed, reset, or deleted. Staging needs explicit approval.
- Blockers before a checkpoint: ChromaDB exceptions are PROPOSED, not accepted; JWT sign-off pending; hosted CI NOT VERIFIED; Windows SQLite BLOCKED.

## 9. Manifest-only staging instructions (prepared, NOT executed)

Do not run these until the user gives explicit Git authorization.

Two sets must be kept distinct:

- **Source snapshot:** 322 files in `included-files.txt` (128 tracked unchanged, 114 tracked modified, 80 untracked). This is the verification and clean-copy set.
- **Commit delta:** 194 paths (114 modified + 80 untracked). Git does not stage unchanged tracked files, so the staged set is compared against this delta, never against all 322 entries.

Preflight (read-only):

1. `git rev-parse HEAD` must return `d789f9814da9955db1c63ced921a95379dd08495`, or the change in HEAD must be reviewed first.
2. `git diff --cached --name-only` must be empty before staging.
3. Confirm the manifest hashes against a fresh clean copy (322 files, 0 mismatches).
4. Confirm `files/prompt23e-security/checkpoint/expected-commit-delta.txt` has 194 lines and matches the live `git status` (194 of 194).

Staging (requires explicit authorization):

5. Stage only the reviewed delta by pathspec, never by directory: `git --literal-pathspecs add --pathspec-from-file=files/prompt23e-security/checkpoint/expected-commit-delta.txt`. Do not run `git reset` unless the index is found non-empty and the user approves it.
6. Compare the staged set: `git diff --cached --name-only` must equal the 194-line delta exactly. Any missing path is an unstaged intended change; any extra path is a failure to unstage with `git restore --staged -- <path>`.
7. Exclusion check on the staged set: no path matching `graphify-out/`, `backend/file*`, `files/`, `*.sqlite3`, `*.db`, `*.log`, `.env` (other than `.env.example`), `.venv*`, `node_modules/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.claude/`, `dist/`, `build/`, or `.expo/`.
8. Run Gitleaks on the staged candidate with the `.gitleaksignore` fingerprint policy, using normal failure semantics (exit 0 expected). Review `git diff --cached --stat`.

Commit (requires separate authorization; include the Co-authored-by trailer):

9. `git commit -m "<message>" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"`

Checkpoint readiness is not release readiness. ChromaDB risk acceptances remain PROPOSED; the release security gate remains red for the 9 unaccepted findings; hosted CI remains NOT VERIFIED; Windows SQLite remains an unsupported configuration.
