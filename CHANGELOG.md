# Changelog

All notable changes to GeoBrief LE are documented here.

## 0.3.0 - 2026-07-05

### Added
- PRD Supervisor autonomous governance mode with mandatory double-check review.
- Launch checklist at docs/LAUNCH_CHECKLIST.md.
- Netlify function tests (Node test runner) for checkout/account/license baseline behavior.
- Repository trust artifacts: SECURITY policy and go-live runbook.

### Changed
- Pipeline summary/runtime version aligned to 0.3.0.
- Storefront install command now points to working source install channel.
- Netlify response security headers hardened.
- Supabase browser SDK pinned with SRI integrity on account/success pages.
- Terms and Privacy pages updated for law-enforcement use constraints, misuse policy, and explicit support/security contacts.

### Security
- Added optional self-host API token guardrails for protected endpoints via GEOBRIEF_API_AUTH_MODE=token and GEOBRIEF_API_TOKEN.
- Added CI dependency vulnerability gate with pip-audit.
