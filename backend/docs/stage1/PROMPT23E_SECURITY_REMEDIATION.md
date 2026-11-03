# Prompt 23E-Security: Backend Dependency Vulnerability Remediation

Status: **PARTIAL** (final sign-off pass). Four ChromaDB advisory IDs are a **PROPOSED RISK ACCEPTANCE**, not a finally approved exception. Hosted CI **NOT VERIFIED**. Windows SQLite native fault **BLOCKED** and explicitly unsupported. Prompt 24 and 23F not started.
No staging, commit, push, reset or deletion has been performed.

## 0. Final closure status (current round)

- **Release gate.** `backend/scripts/security_gate.py` rejects PROPOSED entries, placeholder or missing approvers, missing dates or evidence, expired approvals, and mismatched package, version, scanner or advisory. Covered by 34 synthetic tests in `backend/tests/test_security_gate.py`. On the real outputs it exits 1 with 9 unaccepted ChromaDB findings (pip-audit PYSEC-2026-311, 3813, 3814, 3815; Trivy CVE-2026-45829 and 45833 CRITICAL, CVE-2026-45830 and 45831 HIGH). The gate stays red until an accountable owner approves the exceptions.
- **Trivy.** Scans a staged, SHA256-checked `requirements.txt` copy of `requirements-dev.lock` using `aquasec/trivy:0.66.0` (digest-pinned) with `--list-all-pkgs`. Recognised 158/158 pins. JSON and SARIF are written. The SARIF upload runs even when the policy fails.
- **pip-audit.** Tool environment is hash-locked (`requirements-audit.lock`). Exit 1 on the current ChromaDB findings. Expected.
- **Tests.** Full backend suite on restricted PostgreSQL 16 (role `gs_it_23e`, `-rs`, `--require-hashes`): 389 passed, 0 skipped, exit 0. Includes `test_migrations`.
- **Secret scanning.** Gitleaks is authoritative. The 10 synthetic JWT fixture findings are excluded only by fingerprint in `.gitleaksignore`, not by path. Clean copy exit 0. Negative controls exit 1. The earlier path-wide allowlist was removed.
- **Workflow.** actionlint 1.7.7 with ShellCheck exits 0 after four corrections in `ci.yml` (`{1..30}` loop variable, quoted SSH targets and the curl URL).
- **Manifest.** 321 included, 706 excluded. The 678→681 historical delta is NOT VERIFIED.
- **Windows SQLite.** BLOCKED and explicitly unsupported. Not reopened.
- **Hosted CI.** NOT VERIFIED.

The sections below are the historical record. Where they conflict with this section, this section governs.

## 1. Result summary

| Gate | Result | Evidence |
|---|---|---|
| pip-audit, development lock, before | 85 findings, 15 packages | `files/prompt23e-security/baseline/baseline-dev.json` |
| pip-audit, adopted lock, after | 5 findings, 1 package (chromadb), 4 unique IDs, 0 fixes published | `files/prompt23e-security/post-fix/postfix-major-candidate.json` |
| pip-audit gate with documented exceptions | No known vulnerabilities found, 5 ignored, exit 0 | Docker `python:3.11-slim`, `--require-hashes` |
| JWT migration python-jose to PyJWT | PyJWT verdicts match python-jose on 8 synthetic legacy fixtures; 25 security tests plus 11 legacy-compatibility tests pass (37 in the locked container) | `backend/tests/test_jwt_security.py`; `backend/tests/test_jwt_legacy_compat.py`; `backend/tests/fixtures/auth/legacy_jose_tokens.json` |
| Legacy python-jose token fixtures | 8 synthetic cases; PyJWT verdict matches python-jose on all 8 | `backend/tests/fixtures/auth/legacy_jose_tokens.json` |
| Full backend suite, clean 314-file copy, no PostgreSQL URL | 331 passed, 24 skipped (PostgreSQL tests skip without a URL), exit 0 | `files/prompt23e-security/checkpoint/` (clean-copy run, Section 10) |
| Full backend suite, clean 314-file copy, restricted PostgreSQL | **355 passed, 0 skipped, 0 errors**, exit 0 | Same clean copy, role `gs_it_23e`, DB `gridsense_test_23e` |
| Ruff, backend `app`, `tests`, `scripts` | All checks passed (`--extend-exclude .claude`) | Clean copy, `python:3.11-slim` |
| Full backend suite, Linux (earlier pass) | 320 passed, 24 skipped | `files/prompt23e-security/linux/full-linux-run-1.txt` (pre-JWT-legacy tests) |
| Restricted PostgreSQL integration, Windows (earlier pass) | 35 passed, 0 skipped | `files/prompt23e-security/pg-windows-run-1.txt` (pre-JWT-legacy tests) |
| Restricted PostgreSQL integration, Linux (earlier pass) | 35 passed, 0 skipped | `files/prompt23e-security/linux/pg-linux-run-1.txt` |
| Alembic upgrade, downgrade, re-upgrade | All exit 0; re-upgrade created 21 tables; schema dropped | Disposable schema `gs_mig_*` in `gridsense-it-pg16-23e` |
| Redis/RQ job execution | Job FINISHED, result 5 | `files/prompt23e-security/linux/redis-rq-run-1.txt` |
| Windows native SQLite harness, 4 runs | Run 1, 3, 4 clean; **run 2 flagged** `Native diagnostic: YES`, harness exit 1 | `files/prompt23e-security/windows-native-sqlite-run-{1..4}` |

Security gate: **PARTIAL**. The gate passes only because of the four ChromaDB advisory exceptions in section 4 (audit reports five rows across four IDs; PYSEC-2026-311 is listed twice). Those exceptions are not fixes and are not finally risk-accepted.

## 2. Exact environment

- Adopted lock: `backend/requirements-dev.lock`, SHA256 `6A1DE8A583DA86F7D4EAC08BA9E16C1536D0E0A00C4CDEE2430E7DED8B997069`, 158 pins, universal, `--python-version 3.11`, hash-locked.
- Linux: `python:3.11-slim` (Python 3.11.18), `pip install --require-hashes -r requirements-dev.lock`.
- Windows: isolated uv venv `venvmajor` (outside the repo), same lock.
- pip-audit: 2.10.1.
- PostgreSQL: disposable container `gridsense-it-pg16-23e`, PostgreSQL 16, `127.0.0.1:55433`, no host volume, role `gs_it_23e` (NOSUPERUSER, NOCREATEDB, NOCREATEROLE). The developer container `gridsense-test-pg16-prompt23e` (port 55432) was not touched.
- Credentials were read from the disposable container's environment at run time, passed through process environment variables, and not written to disk or logs.

## 3. Advisory-by-advisory disposition

Each package was categorised as direct or transitive, production or development, and reachable or not.

| Package (baseline) | Before | Disposition | After | Direct or transitive | Reachability | Major upgrade |
|---|---|---|---|---|---|---|
| python-jose | 3.5.0, PYSEC-2026-4298 (no upstream fix) | REMEDIATED by replacement with PyJWT 2.15.1; python-jose removed | not installed | Direct (`pyproject.toml`) | Production: JWT issue and verify in `auth.py` | No, but semantic library change; see section 5 |
| ecdsa, pyasn1, rsa, cryptography, cffi, pycparser | Pulled in by python-jose | NOT APPLICABLE; removed with python-jose | removed | Transitive | Not imported by app code | No |
| aiohttp | vulnerable | REMEDIATED | 3.14.5 | Transitive | Not direct | No |
| certifi | vulnerable | REMEDIATED | 2026.10.23 | Transitive | n/a | No |
| dnspython | vulnerable | REMEDIATED | 2.9.1 | Transitive | n/a | No |
| httpx2 | vulnerable | REMEDIATED | 2.16.0 | Transitive | n/a | No |
| langgraph-sdk | vulnerable | REMEDIATED | 0.4.11 | Transitive | n/a | No |
| multidict | vulnerable | REMEDIATED | 6.9.1 | Transitive | n/a | No |
| opentelemetry-api | vulnerable | REMEDIATED | 1.45.2 | Transitive | n/a | No |
| urllib3 | vulnerable | REMEDIATED | 2.8.0 | Transitive | n/a | No |
| filelock | 12 findings | REMEDIATED | 4.2.6 | Transitive | No direct app import | **Yes** (major) |
| oauthlib | 3 findings | REMEDIATED | 4.0.1 | Transitive | No direct app import | **Yes** (major) |
| pillow | 39 findings | REMEDIATED | 13.0.0 | Transitive, via matplotlib | `forecast_evaluation.py`, `scheduling_experiment.py` use matplotlib PNG output; smoke test passed | **Yes** (major) |
| chromadb | 5 findings, no fix | ACCEPTED EXCEPTION (section 4) | 1.5.9 | Direct (`pyproject.toml` line 29) | In-process `Chroma.from_texts` only; no server, HTTP, persistent client or `trust_remote_code` | No fix exists |

Fix versions for the three major upgrades were established by resolving with floors and no other changes. The full suite passed on the upgraded set. A PNG smoke test for Pillow 13 passed.

## 4. Accepted exceptions (not fixes)

Four IDs are ignored in the gate, and PYSEC-2026-311 is listed twice in the audit output. All are chromadb.

| ID | Affected component | Why it is not reachable in GridSense | Mitigation | Owner | Review date |
|---|---|---|---|---|---|
| PYSEC-2026-311 | chromadb HTTP server, `/api/v2/tenants` | No Chroma server or HTTP client; the app has no `HttpClient` | Guard test `backend/tests/test_chromadb_exposure.py` fails if an HTTP or persistent client, `persist_directory`, `chroma run` or `/api/v2/tenants` appears in app code | Project maintainer — assignment pending | 2026-12-31 (proposed) |
| PYSEC-2026-3813 | SimpleRBACAuthorizationProvider | RBAC authorization provider is server-side and not used | Same guard test | Project maintainer — assignment pending | 2026-12-31 (proposed) |
| PYSEC-2026-3814 | `trust_remote_code` path | Not set anywhere; guard test checks it | Same guard test | Project maintainer — assignment pending | 2026-12-31 (proposed) |
| PYSEC-2026-3815 | Server and tenant path | Same as above | Same guard test | Project maintainer — assignment pending | 2026-12-31 (proposed) |

Approval state: **PROPOSED RISK ACCEPTANCE**. None of these four is finally risk-accepted. Approval requires a named accountable maintainer and a recorded sign-off on the 2026-12-31 review date. The CI ignore list is exactly these four IDs (`ci.yml` lines 303–306). A new, unrelated advisory is not ignored and fails the gate.

Residual risk: if a future change adds a Chroma server, a persistent client or remote code loading, the guard test fails and the exception must be reviewed. Chroma is used only through in-memory `Chroma.from_texts` in `backend/app/services/rag_engine.py`.

## 5. Authentication semantic change (needs your sign-off)

`python-jose` was replaced by `PyJWT` in `backend/app/services/auth.py` and `backend/pyproject.toml`. This is a change to the authentication library, so it is reported here rather than treated as routine.

Parity evidence: `backend/tests/test_jwt_legacy_compat.py` checks PyJWT verdicts against python-jose verdicts recorded in `legacy_jose_tokens.json` (8 synthetic cases, generated by `backend/scripts/generate_legacy_jwt_fixtures.py`). All 8 verdicts match. The earlier "18-case parity script" reference was removed because no such script or evidence exists.

Behaviour notes:

- Algorithm allowlist: unchanged. HS256 accepted; `none` and HS512 rejected.
- Non-string `sub`: **both** libraries reject an integer `sub` in the synthetic legacy fixtures (python-jose raises `JWTClaimsError`; PyJWT raises `InvalidSubjectError`). The earlier statement that python-jose accepted an integer `sub` was wrong and is withdrawn. The migration therefore adds no new rejection for integer-`sub` tokens. The app does not accept numeric `sub` and makes no compatibility exception for it.
- Missing `sub`: python-jose returned `sub: null`; PyJWT path rejects it through the app's `decode_token` check. This is a deliberate tightening and is recorded as a difference.
- Token shapes, access and refresh claim names, expiry handling and 401 responses are unchanged.
- Regression tests: `backend/tests/test_jwt_security.py` (25 cases) covers round trip, refresh rotation, cross-type rejection, expired tokens, tampered signature and payload, wrong secret, `alg none`, HS512, missing or non-string `sub`, malformed input and endpoint 401s on `/api/v1/auth/me`.
- Legacy compatibility: `backend/tests/test_jwt_legacy_compat.py` (11 cases) runs against `backend/tests/fixtures/auth/legacy_jose_tokens.json`, 8 synthetic tokens minted with python-jose 3.5.0 by `backend/scripts/generate_legacy_jwt_fixtures.py` under a non-secret synthetic key label. Verdicts: string-`sub` access and refresh tokens are accepted; access-without-`typ` is accepted; integer `sub`, wrong algorithm, expired and tampered tokens are rejected. The fixture verdicts match between python-jose and PyJWT.

Legacy-token inspection and re-login policy:

- Committed history always issued string `sub` (`str(user.id)` in `backend/app/api/auth.py`). Tokens minted before git history cannot be inspected, so the claim "no such tokens exist" is **not** made.
- Tokens are stateless. There is no server-side session table, so there is no way to enumerate outstanding tokens.
- Bound on exposure: access tokens expire after 7 days and refresh tokens after 30 days. Any token that predates the string-`sub` policy and is still unexpired will receive 401 on use.
- Client behaviour: `mobile/services/api.ts` (around lines 692–748) attempts refresh on 401, then clears tokens and returns the user to sign-in. A stale token therefore results in one re-authentication, with no data loss.
- Policy: no forced global logout is applied. Natural expiry is the bound. If a deliberate global re-login is wanted, rotate `SECRET_KEY`, which invalidates every token. That is an operator decision (Section 9), not something this change performs.


## 6. Native diagnostics and hang

- Windows SQLite native fault: **BLOCKED**. Run 2 of 4 reported `Native diagnostic: YES` ("Windows fatal exception: access violation") with harness exit 1, while pytest itself reported 320 passed. The fault is intermittent. Three clean runs do not fix it. It is not fixed and must not be described as fixed.
- Linux SQLite behaviour is not evidence about the Windows fault.

## 7. CI and policy

- Action pins: all **23** `uses:` references in `.github/workflows/*.yml` are pinned to a 40-character commit SHA, covering **9** distinct actions (checked by pattern and against upstream tags in an earlier pass).
- Security gate: `.github/workflows/ci.yml` security-scan runs `pip-audit --requirement requirements-dev.lock --require-hashes` with exactly four `--ignore-vuln` flags (`PYSEC-2026-311`, `3813`, `3814`, `3815`). It has no `continue-on-error` and no `|| true`. Any other advisory fails the job.
- Same lock: the backend-test jobs install `requirements-dev.lock` with `--require-hashes`, and pip-audit reads the same file, so the audit scans the tested dependency set.
- Local CI-equivalent run (Docker `python:3.11-slim`): pip-audit reports "No known vulnerabilities found, 5 ignored", exit 0. Without the ignores it reports 5 findings across 4 IDs (`files/prompt23e-security/final/pip-audit-post-fix-no-ignores.json`).
- Token permissions: top level `contents: read`; `security-events: write` only on the security job. Deploy jobs use secrets and run only on push to `develop` or `main`, not on pull requests.
- Known gaps (not fixed in this pass):
  - The pip-audit tool itself is installed as `pip install pip-audit==2.10.1` without hashes. Only the audited dependency set is hash-locked.
  - Trivy SARIF upload has no `exit-code` and no `.trivyignore`, so it does not gate.
  - actionlint 1.7.7 reports no structural errors. It reports four pre-existing ShellCheck findings (one SC2034 warning near line 251; SC2086 info near lines 335, 365 and 391). None are in lines changed here, so they are recorded and left alone.
- Secret scan: 22 pattern hits across the proposed file set, all reviewed (values masked). Section 10 lists the disposition.
- **Hosted GitHub Actions: NOT VERIFIED.** No hosted run has been executed for this change.


## 8. Items not completed

- Phase 4 production/development lock split: **not done**. One lock is retained because chromadb, pillow and prophet are reached by the app. Splitting would need a separate verified production environment test. Deferred.
- Mobile checks: not run in this pass. The API contract did not change; only backend auth internals and dependencies changed.
- npm audit: unchanged in this pass; see the existing 14 moderate development-only advisories in `ENGINEERING_DEFECT_REGISTER.md`.
- Hosted CI run: not executed. NOT VERIFIED.
- Trivy gating and hashing the pip-audit tool install: not done (Section 7 gaps).

## 9. Decisions needed from you

1. **Approve the python-jose to PyJWT change** (Section 5). Confirm the re-login policy: natural expiry (access 7 days, refresh 30 days) with no forced logout, or a deliberate `SECRET_KEY` rotation to invalidate every token.
2. **Name the accountable owner** for the four ChromaDB exception IDs. Until then the label is "Project maintainer — assignment pending". Confirm or change the proposed review date of 2026-12-31.
3. **Accept or reject the ChromaDB residual risk** (PROPOSED RISK ACCEPTANCE), or direct a split into a production lock without chromadb.
4. **Trivy gating**: choose whether to add a `.trivyignore` and `exit-code` so the scan gates, or keep it advisory.
5. **Hash-lock the pip-audit tool** install, or accept the current unhashed pin.
6. **Checkpoint**: decide whether to stage this as a work-in-progress checkpoint. Nothing has been staged, committed or pushed.

## 10. Source checkpoint, secret scan and clean-copy reproduction (Task B)

- Manifest: built from the actual worktree by `files/prompt23e-security/checkpoint/build_manifest.py`. HEAD `d789f98`.
  - **314 files included**: 128 tracked and unchanged, 114 tracked and modified, 72 untracked. Binary files are hashed only (27).
  - **Final-candidate update (current round):** 318 included (314 plus the four new JWT, ChromaDB, gate and audit-tool files); 681 excluded: 615 Graphify, 5 legacy `backend/file*`, 61 `files/` evidence.
  - The 678→681 delta is three evidence files that the earlier 58-file count did not include. The stored `excluded-before.json` backup was taken after regeneration, so it cannot identify the three files. The exact three are NOT VERIFIED.
  - **Manifest gap (open):** a reconciliation of the 86 files on disk under `files/` shows 25 diagnostic logs (`stdout.log`, `stderr.log`, `*-harness.out`) that are neither included nor listed as excluded. The earlier "0 unaccounted" statement was incorrect. These logs must be classified by the builder before the candidate is final.
  - 0 tracked files deleted in the worktree.
  - Outputs: `files/prompt23e-security/checkpoint/manifest.json`, `included-files.txt`, `excluded-files.json`.
- Secret scan over the exact 314-file set: 22 pattern hits, reviewed with values masked. Disposition:
  - PostgreSQL DATABASE_URL placeholders with `postgres:postgres` in `ci.yml` (lines 105, 160, 165, 170), `docker-compose.yml` (38, 68), `backend/.env.example`, `backend/README.md`. These are standard local or CI service values, not live secrets.
  - `backend/docs/deployment.md:29` (user `gridsense`): a documentation template. The value does not equal any live container secret.
  - Test-only literals in `backend/tests/integration/test_auth_and_meters.py`, `test_tariffs_billing.py`, `test_upload_journey.py`, `backend/tests/test_rate_limits.py`, and a `gs_test` localhost URL in `test_fixture_guards.py`. Each is labelled a disposable test credential, and none equals a live container secret.
  - Eight synthetic JWT tokens in `legacy_jose_tokens.json`, signed with a non-secret synthetic key label.
  - Live container secrets were not compared against the scanned set in this pass. That check is NOT PERFORMED.
- Clean-copy reproduction: the 314 files were copied to a temporary directory and nothing else. In `python:3.11-slim` the project installed from `requirements-dev.lock` with `--require-hashes`:
  - Ruff (`app tests scripts`, `--extend-exclude .claude`): All checks passed.
  - Full suite with the CI environment (`DEBUG=true`, `SECRET_KEY`, `REDIS_URL`), no PostgreSQL URL: **331 passed, 24 skipped**.
  - Full suite with the restricted PostgreSQL role (`GRIDSENSE_INTEGRATION_DATABASE_URL`, `GRIDSENSE_INTEGRATION_CONFIRM_DATABASE=gridsense_test_23e`, superuser bypass not set): **355 passed, 0 skipped, 0 errors**, 355 collected.
  - Note: the first attempts set `DATABASE_URL` and `GS_IT_URL`, which the integration fixtures do not read. Those runs were discarded and rerun with the correct variable.
  - Environment: `python:3.11-slim` (current 3.11 patch), not the CI pin `3.11.16`. This is an environment difference and is recorded as such.
- Staging diff (read-only `git diff --name-status HEAD`): 114 `M` entries (modified) and 0 deletions. Full stat is in the git output, not in a file.
- Missing files: none. Unexpected generated files: none in the included set.
- Nothing has been staged, committed or pushed.

## 11. Windows SQLite disposition (Task D)

This is a supported-platform decision, not a new native-fault investigation.

| Area | Status | Basis |
|---|---|---|
| PostgreSQL 16, restricted role | **Supported integration gate** | 355 passed, 0 skipped on the clean copy (Linux container). Earlier: 35/35 on Windows and Linux. |
| Linux full backend suite | **Supported CI runtime** | 331 passed and 24 skipped without PostgreSQL. With PostgreSQL, 355 passed and 0 skipped. |
| Windows SQLite tests | **Excluded from supported release gates** | Intermittent native access violation (run 2 of 4, `Native diagnostic: YES`, harness exit 1, while pytest reported 320 passed). The fault is unresolved and no causal fix is verified. |
| Windows PostgreSQL tests | Supported on Windows as a developer check | 35/35 earlier. Not the release gate; Linux is. |

Coverage limits:

- PostgreSQL coverage is **not automatically equivalent** to SQLite behaviour. Differences in dialect, transaction semantics and type handling mean a PostgreSQL pass does not prove SQLite correctness.
- Linux SQLite tests do not reproduce the Windows native fault. A Linux pass is not evidence that Windows SQLite is fixed.

What would retire the Windows limitation:

1. A reproducible minimal case with a stable failure rate, captured with the existing native diagnostic harness.
2. A verified causal fix, shown by repeated runs (not one pass) on Windows.
3. Sign-off that the fix does not change SQLite behaviour on Linux.

Until then the limitation stays documented. Windows SQLite is an explicitly unsupported stability path.

How SQLite regressions would still be detected on Linux:

- The Linux backend job runs the full suite on SQLite, which covers the SQLite code path under the pinned lock.
- Any new SQLite-related regression is caught by that job in CI, subject to hosted CI being run (currently NOT VERIFIED).

## 12. Final gate table (Prompt 23E-Security final sign-off)

| Gate | Result | Evidence |
|---|---|---|
| python-jose to PyJWT migration | **PROPOSED RISK ACCEPTANCE** (sign-off pending, Section 9) | 8 synthetic legacy verdicts match; 37 JWT and legacy tests pass |
| Legacy token compatibility (synthetic fixtures) | **VERIFIED** for the 8 synthetic cases | `test_jwt_legacy_compat.py`, 11 tests |
| Pre-git issued tokens | **NOT VERIFIED**; re-login policy stated in Section 5 | Not inspectable |
| PYSEC-2026-4298 python-jose | **VERIFIED** (removed) | Replaced by PyJWT 2.15.1 |
| ChromaDB PYSEC-2026-311, 3813, 3814, 3815 | **PROPOSED RISK ACCEPTANCE** (owner pending; review 2026-12-31 proposed) | Exact four IDs in `ci.yml` lines 303–306; guard test passes |
| No Chroma server, persistent client or remote code | **VERIFIED** | `test_chromadb_exposure.py`; in-memory use only in `rag_engine.py` |
| Any other pip-audit finding | **VERIFIED** (none; gate fails on new findings) | CI-equivalent run, exit 0, 5 ignored |
| Backend Ruff | **VERIFIED** | Clean copy, `python:3.11-slim` |
| Full suite, clean copy, PostgreSQL restricted | **VERIFIED** 355 passed, 0 skipped | Section 10 |
| Full suite, clean copy, no PostgreSQL | **VERIFIED** 331 passed, 24 skipped (expected skips) | Section 10 |
| Metering safeguards (unknown direction, unverified clock basis) | Retained; covered by the 355-test suite | Regression tests in the suite; see `ENGINEERING_DEFECT_REGISTER.md` |
| GitHub Actions SHA pins | **VERIFIED** (23 of 23 pinned, 9 distinct actions) | Pattern check on `.github/workflows/*.yml` |
| Workflow syntax | **VERIFIED** (actionlint, no structural errors) | Four pre-existing ShellCheck findings noted, not fixed |
| Token permissions and PR secret access | **VERIFIED** (read-only top level; deploy only on push) | `ci.yml` lines 9, 278–280 |
| Trivy scan gating | **VERIFIED** as enforced by `backend/scripts/security_gate.py`; currently FAILS on 4 unapproved ChromaDB CVEs | Section 13 |
| pip-audit tool install hash-locked | **VERIFIED** (`backend/requirements-audit.lock`, pip-audit 2.10.1, `--require-hashes`) | Section 13 |
| Hosted GitHub Actions run | **NOT VERIFIED** | No hosted run executed |
| Windows SQLite native access violation | **BLOCKED**; explicitly unsupported | Section 11 |
| Production lock split | **NOT DONE** (deferred) | Section 8 |
| Secret scan over the 314-file set | **VERIFIED** (22 hits, all reviewed; none live) | Section 10 |
| Source manifest | **PARTIAL**: 319 included, 706 excluded (diagnostic logs now classified as excluded evidence); 678→681 historical delta NOT VERIFIED | Section 10 and 13 |

Overall security sign-off: **PARTIAL**. The four ChromaDB exceptions are proposed and not finally risk-accepted. Hosted CI is NOT VERIFIED. Windows SQLite stays BLOCKED and unsupported.

Evidence directory: `files/prompt23e-security/`.

## 13. Trivy coverage, LangGraph/Mako triage and final gate status (current round)

**Trivy coverage.** Trivy does not recognise `requirements-dev.lock`. The CI security job now copies the lock to an isolated `requirements.txt`, checks its SHA256 against the original, and scans it with `aquasec/trivy:0.66.0` pinned by digest. Trivy recognised 158 of 158 pins. Zero recognised packages is a verification failure.

**Findings triaged:**

| Finding | Identity | Resolution |
|---|---|---|
| CVE-2026-45829 (critical) | PYSEC-2026-311 | Not remediated. Proposed exception |
| CVE-2026-45833 (critical) | PYSEC-2026-3814 | Not remediated. Proposed exception |
| CVE-2026-45830 (high) | PYSEC-2026-3813 | Not remediated. Proposed exception |
| CVE-2026-45831 (high) | PYSEC-2026-3815 | Not remediated. Proposed exception |
| CVE-2026-102991 Mako (GHSA-5639-2j2p-m4mx) | PYSEC-2026-4243, Windows drive-letter path traversal | **REMEDIATED**: mako 1.4.1→1.4.2 |
| CVE-2026-118667 LangGraph (GHSA-3fx2-cqw9-xr3c) | Redirect in RemoteGraph v3 streaming. Authoritative ranges: `langgraph-sdk` 0.4.0–0.4.5 (fixed 0.4.6); `langgraph` 1.2.3–1.2.13 (fixed 1.2.14), exploitable only with a vulnerable SDK | **REMEDIATED**: langgraph 1.2.11→1.2.14 and langgraph-sdk pinned at 0.4.11. Both are outside the affected ranges. The earlier "1.2.3–1.2.14" wording was incorrect. Current Trivy run no longer reports it |

Mapping of the four ChromaDB CVEs was taken from OSV. NVD could not be read directly. The dependency upgrades changed only those two pins (158 pins before and after).

**Source disagreement.** pip-audit (PyPI data) did not flag mako 1.4.1, but OSV and Trivy do. Both sources are recorded.

**Scanner coverage limits.**
- pip-audit scanned 153–154 of 158 pins. Unscanned: async-timeout, colorama, httpx2-jsfetch, tzdata (platform markers) and packaging 26.3 (no marker; cause NOT VERIFIED). Trivy's recognition of all 158 is the coverage evidence.
- Trivy's vulnerability database updates daily, so results are not reproducible across days.
- The lock header comments reference temporary paths (`gs-remediation`). This is a reproducibility caveat.

**Gate behaviour.** `backend/scripts/security_gate.py` fails on any unapproved pip-audit finding. It also fails on any Trivy CRITICAL, HIGH or MEDIUM finding that is not covered by an APPROVED, unexpired entry in `backend/security/risk-acceptances.json`. Current run on real data: **FAIL, 9 unaccepted findings** (5 pip-audit rows, including a duplicate PYSEC-2026-311 row, and 4 Trivy CVEs). A simulated approval with a temporary register passed (exit 0). The temporary register was removed.

**ChromaDB risk-acceptance record (PROPOSED).** Owner: "Project maintainer — approval pending". Review by 2026-12-31. Status: PROPOSED. ChromaDB is used in-memory only (`backend/app/services/rag_engine.py`). Guard test: `backend/tests/test_chromadb_exposure.py`. The gate does not honour a PROPOSED entry.

**Test evidence on the new lock (Linux container, `python:3.11.16-slim`, `--require-hashes`):**
- Affected auth, ChromaDB, billing and NEM12 tests: 125 passed.
- Full suite excluding `tests/integration`: 320 passed.
- PostgreSQL integration suite on the new lock (`requirements-dev.lock`, `--require-hashes`, PostgreSQL 16 disposable container, restricted role): **355 passed**, exit 0. The explicit skip count was not captured separately in this run, so "0 skipped" is provisional until a re-run with `-rs` is recorded.
- Alembic on an isolated disposable schema: upgrade head → downgrade base → upgrade head reached `d1e2f3a4b5c6 (head)`, exit 0. The schema was dropped afterwards.
- Ruff (CI scope `app tests`): passed.

**Secret scanning.**
- Before exclusion: Gitleaks v8.24.2 (digest-pinned) reported 10 findings, all synthetic JWT fixtures: `backend/tests/fixtures/auth/legacy_jose_tokens.json` (lines 3, 8, 18, 28, 38, 47, 56, 65, 74) and `backend/scripts/generate_legacy_jwt_fixtures.py` (line 101).
- Exclusion: `.gitleaks.toml` at repo root has one singular `[allowlist]` with two path regexes for those two files. It skips all rules for these files, not just the JWT and generic-api-key rules. Gitleaks v8.24 ignores the `[[allowlists]]`/`targetRules` form, so rule-level scoping is NOT achieved. Any real secret added to these two files would go undetected. Compensating control: manual review of these files on change.
- After exclusion, on the clean copy of the 319-file set (hashes verified): **no leaks found, exit 0**.
- Negative control: a fake `sk_live_` token appended to a copied `backend/tests/test_auth.py` in the clean copy produced **exit 1**. The control was removed afterwards. The rule ID was not captured in this rerun.
- Fixture signing-key literals were searched across 149 production-scope files (`backend/app`, `backend/scripts`, `backend/tests` non-fixture, `.github`, `docker-compose*.yml`). **0 matches.** `backend/app/config.py` reads the secret from environment settings (lines 15–82).

**Final gate table (current round):**

| Item | Result |
|---|---|
| Trivy findings: ChromaDB CVE-2026-45829, 45833, 45830, 45831 | **PROPOSED RISK ACCEPTANCE** (owner pending) |
| Mako PYSEC-2026-4243 / CVE-2026-102991 | **VERIFIED** remediated (1.4.2) |
| LangGraph GHSA-3fx2-cqw9-xr3c / CVE-2026-118667 | **VERIFIED** remediated (langgraph 1.2.14, sdk 0.4.11, both outside ranges) |
| pip-audit ChromaDB rows (PYSEC-2026-311, 3813, 3814, 3815) | **PROPOSED RISK ACCEPTANCE** (5 rows, 4 IDs; 311 appears twice) |
| Trivy ChromaDB CVEs (45829, 45833, 45830, 45831) | **PROPOSED RISK ACCEPTANCE**; no fixed version (`fixed=none`) |
| Security gate (`security_gate.py`, final run) | **FAIL**, exit 1, 9 unaccepted findings (5 pip-audit rows, 4 Trivy CVEs). Expected until an accountable owner approves |
| pip-audit tool hashed | **VERIFIED** (`requirements-audit.lock`, `--require-hashes`) |
| pip-audit run on the app lock | **VERIFIED** exit 1 as expected (5 ChromaDB rows; no other findings) |
| Trivy scan recognition | **VERIFIED** 158/158 (Trivy 0.66.0, digest-pinned; 4 findings, all ChromaDB) |
| Gitleaks | **VERIFIED** exit 0 on the clean copy after path-scoped exclusion; negative control exit 1 |
| Fixture key in production config | **VERIFIED** not present (0 matches) |
| PostgreSQL integration on new lock | **VERIFIED** 355 passed on PostgreSQL 16 (skip count provisional, see above) |
| Alembic upgrade/downgrade/upgrade on disposable schema | **VERIFIED** to `d1e2f3a4b5c6` |
| actionlint on `ci.yml` | **VERIFIED** no structural errors; exit 1 from shellcheck notes at lines 251, 374, 404, 430 (outside the security job, not fixed) |
| Clean-copy hashes (319 files) | **VERIFIED** 0 mismatches |
| Manifest completeness | **VERIFIED** 319 included, 706 excluded. The 25 `files/` diagnostic logs are now classified as git-ignored evidence. The 678→681 historical delta remains **NOT VERIFIED** |
| Hosted CI | **NOT VERIFIED** |
| Windows SQLite native fault | **BLOCKED**; excluded from release gates; not fixed |
