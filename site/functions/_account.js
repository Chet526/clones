"use strict";

function json(statusCode, body) {
  return {
    statusCode,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    body: JSON.stringify(body),
  };
}

function getBearerToken(event) {
  const auth = event.headers.authorization || event.headers.Authorization || "";
  if (!auth.toLowerCase().startsWith("bearer ")) return null;
  return auth.slice(7).trim() || null;
}

async function getSupabaseUser(event) {
  const supabaseUrl = process.env.SUPABASE_URL;
  const anonKey = process.env.SUPABASE_ANON_KEY;
  if (!supabaseUrl || !anonKey) {
    return { error: json(503, { error: "Auth is not configured yet." }) };
  }
  const token = getBearerToken(event);
  if (!token) {
    return { error: json(401, { error: "Missing bearer token." }) };
  }
  const response = await fetch(`${supabaseUrl}/auth/v1/user`, {
    headers: {
      apikey: anonKey,
      Authorization: `Bearer ${token}`,
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || !body?.email) {
    return { error: json(401, { error: "Invalid or expired login session." }) };
  }
  return { user: body };
}

async function stripeRequest(secretKey, path, params = null) {
  const url = `https://api.stripe.com/v1/${path}`;
  const response = await fetch(url, {
    method: params ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${secretKey}`,
      ...(params ? { "Content-Type": "application/x-www-form-urlencoded" } : {}),
    },
    body: params ? params.toString() : undefined,
  });
  return response.json();
}

async function findCustomerByEmail(secretKey, email) {
  const data = await stripeRequest(
    secretKey,
    `customers?email=${encodeURIComponent(email)}&limit=1`
  );
  const list = Array.isArray(data?.data) ? data.data : [];
  return list[0] || null;
}

async function getSubscriptions(secretKey, customerId) {
  const data = await stripeRequest(
    secretKey,
    `subscriptions?customer=${encodeURIComponent(customerId)}&status=all&limit=10`
  );
  return Array.isArray(data?.data) ? data.data : [];
}

function mapPlanFromSubscription(subscription) {
  const standard = process.env.STRIPE_PRICE_STANDARD;
  const pro = process.env.STRIPE_PRICE_PRO;
  const items = subscription?.items?.data || [];
  const priceIds = items.map((item) => item?.price?.id).filter(Boolean);
  if (pro && priceIds.includes(pro)) return "pro";
  if (standard && priceIds.includes(standard)) return "standard";
  return null;
}

module.exports = {
  json,
  getSupabaseUser,
  stripeRequest,
  findCustomerByEmail,
  getSubscriptions,
  mapPlanFromSubscription,
};
