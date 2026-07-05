# GeoBrief LE Launch Checklist

Started: 2026-07-05
Branch: copilot/upload-prd

Priority policy:
- [BLOCKER] must be complete before market launch.
- [CONDITIONAL-BLOCKER] must be complete when its condition applies.
- [OPTIONAL] may remain open without blocking launch.
- Conditional reverse-proxy scope: applies only to internet-exposed self-host investigator-data APIs, not Netlify storefront billing/account endpoints.

## 1) Distribution and Install Path
- [x] [BLOCKER] Storefront install command points to a working source install path.
- [x] [BLOCKER] Decide final customer distribution channel:
  - [x] [BLOCKER] Source install from immutable Git commit (`52b31ec530c2a81c6647da7b5bf7f99cd03a4475`) (current launch channel).
  - [ ] [OPTIONAL] Publish package to PyPI (optional future channel).
  - [ ] [OPTIONAL] Provide signed installer artifacts (wheel/binary bundles) per release.
- [x] [BLOCKER] Add release-channel note to storefront and README (stable vs dev/source install).

## 2) Version and Release Consistency
- [x] [BLOCKER] Runtime version in processing summary matches project version (`0.3.0`).
- [x] [BLOCKER] Add a single-source release process (tag + changelog + artifact naming).

## 3) Security Hardening (Storefront + Functions)
- [x] [BLOCKER] Netlify response security headers configured (`CSP`, `HSTS`, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`).
- [x] [BLOCKER] API responses use `Cache-Control: no-store` and defensive headers.
- [x] [BLOCKER] Supabase browser SDK pinned to exact version with SRI integrity.
- [x] [BLOCKER] Add explicit self-host deployment guardrails for unauthenticated `/api/*` endpoints:
  - [x] [CONDITIONAL-BLOCKER: internet-exposed deployment only] Require auth at reverse proxy in front of `/api/*`.
  - [x] [BLOCKER] Add app-level auth mode for non-localhost deployment (`GEOBRIEF_API_AUTH_MODE=token`, `GEOBRIEF_API_TOKEN`).

## 4) Billing and Account Reliability
- [x] [BLOCKER] Add automated Node tests for Netlify functions (checkout/account/license method and checkout-path smoke coverage).
- [x] [BLOCKER] Run Netlify function tests in CI.
- [x] [BLOCKER] Expand function tests to include full mocked auth + Stripe lifecycle:
  - [x] `get-license` success and ownership mismatch paths
  - [x] `account-me` profile sync conflict paths
  - [x] `account-portal` successful portal creation path

## 5) Legal and Commercial Policy
- [x] [BLOCKER] Update Terms to explicitly enforce law-enforcement-only usage and prohibited misuse.
- [x] [BLOCKER] Add explicit suspension/termination language for policy violations.
- [x] [BLOCKER] Add customer-facing support contact and incident/security reporting path.

## 6) QA Gate (Per Release)
- [x] [BLOCKER] Python test suite passes.
- [x] [BLOCKER] Front-end syntax checks pass (web app + storefront scripts, CI-enforced).
- [x] [BLOCKER] Dependency vulnerability scan (`pip-audit`) passes.
- [x] [BLOCKER] Add CI job for dependency scan and fail on vulnerabilities.
- [x] [BLOCKER] GitHub CI run is green for the launch-governance commit (record run URL/ID).

## 7) Release Operations
- [x] [BLOCKER] Add repository release trust artifacts:
  - [x] `LICENSE` (commercial)
  - [x] `SECURITY.md`
  - [x] `CHANGELOG.md`
- [x] [BLOCKER] Define go-live runbook (rollback, key rotation, billing outage handling).

## 8) Release Provenance Evidence
- [x] [BLOCKER] Annotated tag created for launch governance snapshot: `v0.3.0-launch-r2`.
- [x] [BLOCKER] Customer install references are pinned to immutable commit `52b31ec530c2a81c6647da7b5bf7f99cd03a4475` and documented in README/storefront.
- [x] [BLOCKER] Install references in customer docs point to the same immutable commit.
- [x] [CONDITIONAL-BLOCKER: internet-exposed deployment only] Reverse-proxy auth evidence is recorded in `docs/DEPLOYMENT_EVIDENCE.md`.
- [x] [BLOCKER] Provenance verification commands are defined in the go-live runbook and executed during release.

## Latest Check Run (2026-07-05)
- `node --test site/functions/tests/functions.test.cjs` -> pass (11/11)
- `node --check src/geobrief/webapp/static/app.js` -> pass
- `node --check site/public/app.js` -> pass
- `/workspaces/clones/.venv/bin/python -m pytest -q` -> pass
- `pip-audit -r requirements.txt` -> pass (no known vulnerabilities)
