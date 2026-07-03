"use strict";

const {
  json,
  getSupabaseUser,
  findCustomerByEmail,
  getSubscriptions,
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

  const customer = await findCustomerByEmail(secretKey, user.email);
  if (!customer) {
    return json(200, {
      email: user.email,
      customer_id: null,
      subscription: null,
      plan: null,
      has_billing_account: false,
    });
  }

  const subscriptions = await getSubscriptions(secretKey, customer.id);
  const active = subscriptions.find((s) =>
    ["active", "trialing", "past_due"].includes(s.status)
  ) || null;

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
    plan: active ? mapPlanFromSubscription(active) : null,
  });
};
