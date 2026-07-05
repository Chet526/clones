# GeoBrief LE Go-Live Runbook

## 1. Pre-Launch Gates
- Confirm CI green on latest launch-governance commit and record run URL/ID in launch evidence.
- A representative supplemental CI run for post-anchor docs-only commits may be recorded for audit continuity; it is optional and does not need to match latest HEAD.
- Confirm docs/LAUNCH_CHECKLIST.md has no unresolved `[BLOCKER]` items.
- Confirm there are no unresolved `[CONDITIONAL-BLOCKER]` items whose conditions are true for the target deployment.
- Items marked `[OPTIONAL]` may remain open without blocking launch.
- Confirm Stripe live-mode products/prices and webhook endpoint are configured.
- Confirm Netlify production env vars are set (Stripe, license secret, Supabase as needed).

## 2. Secrets and Access
- Rotate and store all production secrets in Netlify/env manager.
- Restrict access to service-role keys.
- Never expose service-role keys in browser/client code.
- For any internet-exposed self-host deployment, enforce reverse-proxy auth in front of `/api/*` in addition to app-level token mode.

Scope note:
- The reverse-proxy conditional blocker applies to the self-host investigator-data API served by GeoBrief (`python -m geobrief serve`).
- Netlify storefront endpoints (`/api/create-checkout`, `/api/get-license`, `/api/account-config`, `/api/account-me`, `/api/account-portal`) are commerce/account functions and are evaluated under storefront security controls, not this self-host reverse-proxy condition.

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
- Record the governance snapshot tag for the launch record (`v0.3.0-launch-r2` for this release cycle).
- Set customer-facing install commands to the immutable customer install commit SHA (may differ from the governance snapshot commit when only non-runtime governance artifacts changed afterward, such as release docs or CI workflow policy).
- Publish release notes and deployment metadata, then archive the runbook checklist evidence.
- Record deployment-only control evidence in `docs/DEPLOYMENT_EVIDENCE.md`.

Provenance verification commands (record command + output in deployment evidence):
- `git show-ref --tags <governance_snapshot_tag>`
- `git rev-parse <governance_snapshot_tag>^{}`
- `grep -H "<customer_install_pin_sha>" README.md site/public/index.html docs/LAUNCH_CHECKLIST.md`
- `gh api repos/<owner>/<repo>/actions/runs/<run_id> --jq '{run_id: .id, run_number: .run_number, workflow: .name, head_sha: .head_sha, status: .status, conclusion: .conclusion, html_url: .html_url, run_started_at: .run_started_at, updated_at: .updated_at}'`

## 8. Post-Launch
- Review support inbox and error telemetry daily for first 7 days.
- Publish patch releases for confirmed defects.
- Update CHANGELOG.md for every production change.
