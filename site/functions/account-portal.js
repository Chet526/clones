"use strict";

const {
  json,
  getSupabaseUser,
  resolveStripeCustomerForUser,
  stripeRequest,
} = require("./_account");

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return json(405, { error: "Method not allowed" });
  }
  const auth = await getSupabaseUser(event);
  if (auth.error) return auth.error;

  const secretKey = process.env.STRIPE_SECRET_KEY;
  if (!secretKey) {
    return json(503, { error: "Billing is not configured yet." });
  }

  const resolved = await resolveStripeCustomerForUser(secretKey, auth.user);
  if (resolved.error === "multiple_customers") {
    return json(409, {
      error:
        "Multiple billing customers match this email. Contact support to merge records.",
    });
  }

  const customer = resolved.customer;
  if (!customer) {
    return json(404, {
      error: "No Stripe customer found for this account email yet.",
    });
  }

  const returnUrl =
    process.env.STRIPE_BILLING_PORTAL_RETURN_URL ||
    `${process.env.URL || `https://${event.headers.host}`}/account.html`;

  const params = new URLSearchParams({
    customer: customer.id,
    return_url: returnUrl,
  });

  const portal = await stripeRequest(secretKey, "billing_portal/sessions", params);
  if (!portal?.url) {
    return json(502, { error: "Could not create billing portal session." });
  }
  return json(200, { url: portal.url });
};
