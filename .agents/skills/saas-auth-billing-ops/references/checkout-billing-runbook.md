# Checkout and Billing Runbook

1. Confirm plan id requested by client and mapped price/payment link.
2. Validate checkout endpoint response and Stripe session/link creation.
3. Confirm customer record for account email.
4. Confirm active subscription status and current period end.
5. Reconcile entitlement mapping to application plan.
6. If mismatch persists, log event ids and apply corrective sync path.
