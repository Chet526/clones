"use strict";

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

function getBearerToken(event) {
  const auth = event.headers.authorization || event.headers.Authorization || "";
  if (!auth.toLowerCase().startsWith("bearer ")) return null;
  return auth.slice(7).trim() || null;
}

function supabaseConfig() {
  const supabaseUrl = process.env.SUPABASE_URL;
  const anonKey = process.env.SUPABASE_ANON_KEY;
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  return { supabaseUrl, anonKey, serviceRoleKey };
}

async function supabaseAdminRequest(path, { method = "GET", body, prefer } = {}) {
  const { supabaseUrl, serviceRoleKey } = supabaseConfig();
  if (!supabaseUrl || !serviceRoleKey) {
    return { ok: false, status: 503, data: { error: "Supabase admin is not configured." } };
  }
  const preferValue =
    body && prefer
      ? `return=representation,${prefer}`
      : body
        ? "return=representation"
        : undefined;
  const response = await fetch(`${supabaseUrl}${path}`, {
    method,
    headers: {
      apikey: serviceRoleKey,
      Authorization: `Bearer ${serviceRoleKey}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(preferValue ? { Prefer: preferValue } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  return { ok: response.ok, status: response.status, data };
}

async function getAccountProfile(userId) {
  const response = await supabaseAdminRequest(
    `/rest/v1/account_profiles?user_id=eq.${encodeURIComponent(userId)}&select=*`
  );
  if (!response.ok) return null;
  const rows = Array.isArray(response.data) ? response.data : [];
  return rows[0] || null;
}

async function upsertAccountProfile(user, patch) {
  const payload = {
    user_id: user.id,
    email: user.email,
    ...patch,
  };
  await supabaseAdminRequest(
    "/rest/v1/account_profiles?on_conflict=user_id",
    {
      method: "POST",
      body: payload,
      prefer: "resolution=merge-duplicates",
    }
  );
}

async function getSupabaseUser(event) {
  const { supabaseUrl, anonKey } = supabaseConfig();
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

async function maybeSupabaseUser(event) {
  const auth = await getSupabaseUser(event);
  if (auth.error) return null;
  return auth.user;
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

async function getStripeCustomer(secretKey, customerId) {
  if (!customerId) return null;
  const customer = await stripeRequest(secretKey, `customers/${customerId}`);
  return customer && !customer.error ? customer : null;
}

async function findCustomersByEmail(secretKey, email) {
  const data = await stripeRequest(
    secretKey,
    `customers?email=${encodeURIComponent(email)}&limit=10`
  );
  return Array.isArray(data?.data) ? data.data : [];
}

async function resolveStripeCustomerForUser(secretKey, user) {
  const profile = await getAccountProfile(user.id);
  if (profile?.stripe_customer_id) {
    const customer = await getStripeCustomer(secretKey, profile.stripe_customer_id);
    if (customer) {
      return { customer, profile, source: "profile" };
    }
  }

  const matches = await findCustomersByEmail(secretKey, user.email);
  if (matches.length === 0) {
    return { customer: null, profile, source: "none" };
  }
  if (matches.length > 1) {
    return { error: "multiple_customers", profile, matches };
  }

  const customer = matches[0];
  await upsertAccountProfile(user, { stripe_customer_id: customer.id });
  return { customer, profile, source: "email" };
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
  maybeSupabaseUser,
  stripeRequest,
  getStripeCustomer,
  findCustomersByEmail,
  resolveStripeCustomerForUser,
  getSubscriptions,
  getAccountProfile,
  upsertAccountProfile,
  mapPlanFromSubscription,
};
