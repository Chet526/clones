---
name: saas-auth-billing-ops
description: 'Use for SaaS account operations: login failures, password resets, magic links, session issues, checkout failures, subscription mismatches, billing portal access, and entitlement drift between auth and Stripe.'
argument-hint: 'User email, symptom, environment, and expected plan'
user-invocable: false
---

# SaaS Auth and Billing Operations

## Purpose
Provide fast, auditable support runbooks for account access and subscription lifecycle issues.

## When To Use
- Password reset or magic-link login problems
- Checkout not starting or failing after payment
- Active subscription not reflected in product entitlements
- Billing portal access and cancellation/reactivation flows

## Triage Workflow
1. Confirm environment (test vs production) and exact user email.
2. Verify auth provider status and redirect URLs.
3. Verify checkout/price configuration and live endpoint responses.
4. Verify Stripe customer + subscription state for the same email.
5. Reconcile entitlement mapping (price -> plan).
6. Document root cause, remediation, and prevention action.

## Standard Runbooks
- [Login and Reset Runbook](./references/login-reset-runbook.md)
- [Checkout and Billing Runbook](./references/checkout-billing-runbook.md)

## Guardrails
- Never request or store plaintext passwords.
- Never expose secret keys in logs or chat responses.
- Use least-privilege keys and environment-scoped checks.
- Separate customer-facing message from internal technical detail.
