"use strict";

const {
  json,
  getSupabaseUser,
  resolveStripeCustomerForUser,
  getSubscriptions,
  getAccountProfile,
  upsertAccountProfile,
  mapPlanFromSubscription,
} = require("./_account");

exports.handler = async (event) => {
  if (event.httpMethod !== "GET") {
    return json(405, { error: "Method not allowed" });
  }
  const auth = await getSupabaseUser(event);
  if (auth.error) return auth.error;

  const user = auth.user;
  const secretKey = process.env.STRIPE_SECRET_KEY;
  if (!secretKey) {
    return json(503, { error: "Billing is not configured yet." });
  }

  const resolved = await resolveStripeCustomerForUser(secretKey, user);
  if (resolved.error === "multiple_customers") {
    return json(409, {
      error:
        "Multiple billing customers match this email. Contact support to merge records.",
    });
  }

  const customer = resolved.customer;
  if (!customer) {
    const profile = await getAccountProfile(user.id);
    return json(200, {
      email: user.email,
      customer_id: null,
      subscription: null,
      plan: profile?.plan || "standard",
      has_billing_account: false,
    });
  }

  const subscriptions = await getSubscriptions(secretKey, customer.id);
  const active = subscriptions.find((s) =>
    ["active", "trialing", "past_due"].includes(s.status)
  ) || null;

  const currentProfile = await getAccountProfile(user.id);
  const resolvedPlan = active ? mapPlanFromSubscription(active) : null;
  const plan = resolvedPlan || currentProfile?.plan || "standard";
  const periodEndIso =
    active && active.current_period_end
      ? new Date(active.current_period_end * 1000).toISOString()
      : null;

  await upsertAccountProfile(user, {
    stripe_customer_id: customer.id,
    plan,
    subscription_status: active ? active.status : "inactive",
    current_period_end: periodEndIso,
  });

  return json(200, {
    email: user.email,
    customer_id: customer.id,
    has_billing_account: true,
    subscription: active
      ? {
          id: active.id,
          status: active.status,
          cancel_at_period_end: Boolean(active.cancel_at_period_end),
          current_period_end: active.current_period_end || null,
        }
      : null,
    plan,
  });
};
