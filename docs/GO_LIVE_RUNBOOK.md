# GeoBrief LE Go-Live Runbook

## 1. Pre-Launch Gates
- Confirm CI green on latest commit.
- Confirm docs/LAUNCH_CHECKLIST.md has no unresolved blocker-priority launch items.
- Optional future-channel items (for example PyPI publishing or signed installers) may remain open if explicitly marked optional.
- Confirm Stripe live-mode products/prices and webhook endpoint are configured.
- Confirm Netlify production env vars are set (Stripe, license secret, Supabase as needed).

## 2. Secrets and Access
- Rotate and store all production secrets in Netlify/env manager.
- Restrict access to service-role keys.
- Never expose service-role keys in browser/client code.
- For any internet-exposed self-host deployment, enforce reverse-proxy auth in front of `/api/*` in addition to app-level token mode.

## 3. Deploy
- Deploy storefront/functions to production.
- Validate endpoints:
  - /api/create-checkout
  - /api/get-license
  - /api/account-config
  - /api/account-me
  - /api/account-portal
- Validate local app startup and health endpoint.

## 4. Smoke Tests
- Complete a full test-mode purchase flow.
- Verify license retrieval and plan unlock behavior.
- Verify account portal session creation.
- Verify webhook signature validation and entitlement updates.

## 5. Monitoring and Incident Response
- Monitor checkout failures, 4xx/5xx trends, and webhook errors.
- For billing incidents:
  - Pause marketing links if checkout is broken.
  - Verify Stripe status and webhook delivery logs.
  - Reconcile entitlement state after fix.
- For security incidents:
  - Rotate exposed keys immediately.
  - Assess impact and notify affected stakeholders.
  - Track remediation and post-incident actions.

## 6. Rollback
- Keep last known good deployment metadata.
- Re-deploy previous stable version if critical failure appears.
- Re-run smoke tests after rollback.

## 7. Single-Source Release Process
- Update version metadata and changelog entries for the release.
- Run release gates: Python tests, function tests, JS syntax checks, and dependency audit.
- Build release artifacts with deterministic naming (`geobrief-<version>-<buildid>`).
- Create an annotated git tag and record the immutable commit SHA.
- Update customer-facing install commands to that commit SHA.
- Publish release notes and deployment metadata, then archive the runbook checklist evidence.

## 8. Post-Launch
- Review support inbox and error telemetry daily for first 7 days.
- Publish patch releases for confirmed defects.
- Update CHANGELOG.md for every production change.
