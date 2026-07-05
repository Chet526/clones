// POST /api/get-license { "session_id": "cs_..." }
// Exchanges a paid Stripe Checkout Session for a signed GeoBrief license key.
// Requires an authenticated account session; the signed-in email must match the
// checkout customer email. This prevents license retrieval via leaked session
// IDs in URLs/logs/screenshots.
//
// Key scheme (must match src/geobrief/licensing.py):
//   GBLE.<b64url(json payload, sorted keys, no spaces)>.<b64url(HMAC-SHA256(secret, payload_b64))>
"use strict";

const crypto = require("node:crypto");
const { getSupabaseUser, upsertAccountProfile } = require("./_account");

const GRACE_SECONDS = 7 * 24 * 3600; // 7 days past period end
const FALLBACK_TTL_SECONDS = 35 * 24 * 3600; // no subscription info

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return json(405, { error: "Method not allowed" });
  }
  const secretKey = process.env.STRIPE_SECRET_KEY;
  const licenseSecret = process.env.GEOBRIEF_LICENSE_SECRET;
  if (!secretKey || !licenseSecret) {
    return json(503, { error: "License delivery is not configured yet." });
  }
  const auth = await getSupabaseUser(event);
  if (auth.error) return auth.error;

  let sessionId = "";
  try {
    sessionId = String(JSON.parse(event.body || "{}").session_id || "");
  } catch {
    return json(400, { error: "Invalid JSON body." });
  }
  if (!/^cs_[A-Za-z0-9_]+$/.test(sessionId)) {
    return json(400, { error: "Missing or invalid session_id." });
  }

  const session = await stripeGet(secretKey, `checkout/sessions/${sessionId}`);
  if (!session || session.error) {
    return json(404, { error: "Checkout session not found." });
  }
  if (session.payment_status !== "paid") {
    return json(402, { error: "Payment has not completed for this session." });
  }

  const metadataUserId = String(session?.metadata?.supabase_user_id || "").trim();
  if (metadataUserId && metadataUserId !== String(auth.user.id || "").trim()) {
    return json(403, {
      error: "Signed-in account does not match the checkout session owner.",
    });
  }

  let sessionEmail =
    (session.customer_details && session.customer_details.email) ||
    session.customer_email ||
    "";
  if (!sessionEmail && typeof session.customer === "string") {
    const customer = await stripeGet(secretKey, `customers/${session.customer}`);
    sessionEmail = (customer && customer.email) || "";
  }
  const signedInEmail = String(auth.user.email || "").trim().toLowerCase();
  if (!sessionEmail || sessionEmail.trim().toLowerCase() !== signedInEmail) {
    return json(403, {
      error:
        "Signed-in account email does not match this checkout session.",
    });
  }

  const plan = (session.metadata && session.metadata.plan) || "";
  if (plan !== "standard" && plan !== "pro") {
    return json(500, { error: "Session is missing plan information." });
  }

  // Anchor expiry to the subscription's current period when available.
  let exp = Math.floor(Date.now() / 1000) + FALLBACK_TTL_SECONDS;
  let subscriptionStatus = "active";
  let currentPeriodEndIso = null;
  if (typeof session.subscription === "string") {
    const sub = await stripeGet(secretKey, `subscriptions/${session.subscription}`);
    if (sub && !sub.error) {
      if (sub.status !== "active" && sub.status !== "trialing") {
        return json(402, { error: "This subscription is no longer active." });
      }
      subscriptionStatus = sub.status || "active";
      if (sub.current_period_end) {
        exp = Number(sub.current_period_end) + GRACE_SECONDS;
        currentPeriodEndIso = new Date(Number(sub.current_period_end) * 1000).toISOString();
      }
    }
  }

  const email = sessionEmail || undefined;
  await upsertAccountProfile(auth.user, {
    stripe_customer_id: typeof session.customer === "string" ? session.customer : null,
    plan,
    subscription_status: subscriptionStatus,
    current_period_end: currentPeriodEndIso,
  });

  const key = generateLicenseKey({ plan, email, exp }, licenseSecret);
  return json(200, {
    license_key: key,
    plan,
    email: email || null,
    expires_at: exp,
  });
};

function generateLicenseKey({ plan, email, exp }, secret) {
  // Keys must be inserted in sorted order to match Python's sort_keys=True.
  const payload = {};
  if (email) payload.email = email;
  if (exp !== undefined) payload.exp = Math.floor(exp);
  payload.plan = plan;
  const payloadB64 = b64url(Buffer.from(JSON.stringify(payload), "utf-8"));
  const sig = b64url(
    crypto.createHmac("sha256", secret).update(payloadB64, "ascii").digest()
  );
  return `GBLE.${payloadB64}.${sig}`;
}

function b64url(buffer) {
  return buffer.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function stripeGet(secretKey, path) {
  try {
    const response = await fetch(`https://api.stripe.com/v1/${path}`, {
      headers: { Authorization: `Bearer ${secretKey}` },
    });
    return await response.json();
  } catch (err) {
    console.error("Stripe API error:", err);
    return null;
  }
}

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

// Exported for cross-language compatibility tests against licensing.py.
exports.generateLicenseKey = generateLicenseKey;
