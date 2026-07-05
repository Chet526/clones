// POST /api/create-checkout  { "plan": "standard" | "pro" }
// Creates a Stripe Checkout Session for a monthly subscription and returns
// its URL. Secrets come from Netlify env vars — never expose them client-side.
"use strict";

const { maybeSupabaseUser } = require("./_account");

const PLAN_PRICE_ENV = {
  standard: "STRIPE_PRICE_STANDARD",
  pro: "STRIPE_PRICE_PRO",
};

const PLAN_LINK_ENV = {
  standard: "STRIPE_PAYMENT_LINK_STANDARD",
  pro: "STRIPE_PAYMENT_LINK_PRO",
};

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return json(405, { error: "Method not allowed" });
  }

  let plan;
  try {
    plan = String(JSON.parse(event.body || "{}").plan || "").toLowerCase();
  } catch {
    return json(400, { error: "Invalid JSON body." });
  }
  const paymentLinkEnv = PLAN_LINK_ENV[plan];
  const paymentLink = paymentLinkEnv && process.env[paymentLinkEnv];
  if (paymentLink) {
    return json(200, { url: paymentLink, mode: "payment_link" });
  }

  const secretKey = process.env.STRIPE_SECRET_KEY;
  if (!secretKey) {
    return json(503, {
      error:
        "Billing is not configured yet (missing STRIPE_SECRET_KEY or payment link env vars).",
    });
  }

  const priceEnv = PLAN_PRICE_ENV[plan];
  const priceId = priceEnv && process.env[priceEnv];
  if (!priceId) {
    return json(400, { error: `Unknown or unconfigured plan: ${plan}` });
  }

  const origin = process.env.URL || `https://${event.headers.host}`;
  const params = new URLSearchParams({
    mode: "subscription",
    "line_items[0][price]": priceId,
    "line_items[0][quantity]": "1",
    success_url: `${origin}/success.html?session_id={CHECKOUT_SESSION_ID}`,
    cancel_url: `${origin}/?checkout=cancelled`,
    "metadata[plan]": plan,
    "subscription_data[metadata][plan]": plan,
  });

  // If checkout is started from a signed-in account, pin Stripe metadata to
  // that identity to make later entitlement reconciliation deterministic.
  const signedInUser = await maybeSupabaseUser(event);
  if (signedInUser?.email) {
    params.set("customer_email", signedInUser.email);
    params.set("metadata[supabase_user_id]", signedInUser.id || "");
    params.set("subscription_data[metadata][supabase_user_id]", signedInUser.id || "");
  }

  const response = await fetch("https://api.stripe.com/v1/checkout/sessions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${secretKey}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: params.toString(),
  });
  const session = await response.json();
  if (!response.ok) {
    console.error("Stripe checkout error:", session.error?.message);
    return json(502, { error: "Could not start checkout. Try again shortly." });
  }
  return json(200, { url: session.url, mode: "checkout_session" });
};

function json(statusCode, body) {
  return {
    statusCode,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "X-Frame-Options": "DENY",
      "Referrer-Policy": "no-referrer",
    },
    body: JSON.stringify(body),
  };
}
