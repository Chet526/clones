# GeoBrief LE Launch Checklist

Started: 2026-07-05
Branch: copilot/upload-prd

## 1) Distribution and Install Path
- [x] Storefront install command points to a working source install path.
- [x] Decide final customer distribution channel:
  - [x] Source install from immutable Git commit (`51fa5e730266bf1552347a99c8c8bf97cf2617dd`) (current launch channel).
  - [ ] Publish package to PyPI (optional future channel).
  - [ ] Provide signed installer artifacts (wheel/binary bundles) per release.
- [x] Add release-channel note to storefront and README (stable vs dev/source install).

## 2) Version and Release Consistency
- [x] Runtime version in processing summary matches project version (`0.3.0`).
- [x] Add a single-source release process (tag + changelog + artifact naming).

## 3) Security Hardening (Storefront + Functions)
- [x] Netlify response security headers configured (`CSP`, `HSTS`, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`).
- [x] API responses use `Cache-Control: no-store` and defensive headers.
- [x] Supabase browser SDK pinned to exact version with SRI integrity.
- [x] Add explicit self-host deployment guardrails for unauthenticated `/api/*` endpoints:
  - [x] Require auth at reverse proxy for any internet-exposed deployment.
  - [x] Add app-level auth mode for non-localhost deployment (`GEOBRIEF_API_AUTH_MODE=token`, `GEOBRIEF_API_TOKEN`).

## 4) Billing and Account Reliability
- [x] Add automated Node tests for Netlify functions (checkout/account/license method and checkout-path smoke coverage).
- [x] Run Netlify function tests in CI.
- [x] Expand function tests to include full mocked auth + Stripe lifecycle:
  - [x] `get-license` success and ownership mismatch paths
  - [x] `account-me` profile sync conflict paths
  - [x] `account-portal` successful portal creation path

## 5) Legal and Commercial Policy
- [x] Update Terms to explicitly enforce law-enforcement-only usage and prohibited misuse.
- [x] Add explicit suspension/termination language for policy violations.
- [x] Add customer-facing support contact and incident/security reporting path.

## 6) QA Gate (Per Release)
- [x] Python test suite passes.
- [x] Front-end syntax checks pass (web app + storefront scripts, CI-enforced).
- [x] Dependency vulnerability scan (`pip-audit`) passes.
- [x] Add CI job for dependency scan and fail on vulnerabilities.

## 7) Release Operations
- [x] Add repository release trust artifacts:
  - [x] `LICENSE` (commercial)
  - [x] `SECURITY.md`
  - [x] `CHANGELOG.md`
- [x] Define go-live runbook (rollback, key rotation, billing outage handling).

## Latest Check Run (2026-07-05)
- `node --test site/functions/tests/functions.test.cjs` -> pass (11/11)
- `node --check src/geobrief/webapp/static/app.js` -> pass
- `node --check site/public/app.js` -> pass
- `/workspaces/clones/.venv/bin/python -m pytest -q` -> pass
- `pip-audit -r requirements.txt` -> pass (no known vulnerabilities)
