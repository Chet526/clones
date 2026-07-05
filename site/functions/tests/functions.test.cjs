"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return body;
    },
  };
}

function load(modulePath) {
  delete require.cache[require.resolve(modulePath)];
  return require(modulePath);
}

function resetEnv() {
  for (const key of [
    "STRIPE_SECRET_KEY",
    "STRIPE_PRICE_STANDARD",
    "STRIPE_PRICE_PRO",
    "STRIPE_PAYMENT_LINK_STANDARD",
    "STRIPE_PAYMENT_LINK_PRO",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "GEOBRIEF_LICENSE_SECRET",
  ]) {
    delete process.env[key];
  }
}

test("create-checkout rejects non-POST methods", async (t) => {
  resetEnv();
  const mod = load("../create-checkout.js");
  const response = await mod.handler({ httpMethod: "GET", headers: {} });

  assert.equal(response.statusCode, 405);
  const body = JSON.parse(response.body);
  assert.match(body.error, /Method not allowed/i);

  t.after(() => resetEnv());
});

test("create-checkout returns configured payment link", async (t) => {
  resetEnv();
  process.env.STRIPE_PAYMENT_LINK_STANDARD = "https://buy.stripe.com/test_link";

  const mod = load("../create-checkout.js");
  const response = await mod.handler({
    httpMethod: "POST",
    headers: { host: "example.com" },
    body: JSON.stringify({ plan: "standard" }),
  });

  assert.equal(response.statusCode, 200);
  const body = JSON.parse(response.body);
  assert.equal(body.mode, "payment_link");
  assert.equal(body.url, "https://buy.stripe.com/test_link");

  t.after(() => resetEnv());
});

test("create-checkout creates Stripe session with plan metadata", async (t) => {
  resetEnv();
  process.env.STRIPE_SECRET_KEY = "sk_test_123";
  process.env.STRIPE_PRICE_PRO = "price_pro_123";

  const originalFetch = global.fetch;
  let fetchCall = null;
  global.fetch = async (url, options) => {
    fetchCall = { url, options };
    return {
      ok: true,
      async json() {
        return { id: "cs_test_123", url: "https://checkout.stripe.com/c/pay/cs_test_123" };
      },
    };
  };

  const mod = load("../create-checkout.js");
  const response = await mod.handler({
    httpMethod: "POST",
    headers: { host: "example.com" },
    body: JSON.stringify({ plan: "pro" }),
  });

  assert.equal(response.statusCode, 200);
  const body = JSON.parse(response.body);
  assert.equal(body.mode, "checkout_session");
  assert.equal(body.url, "https://checkout.stripe.com/c/pay/cs_test_123");

  assert.ok(fetchCall);
  assert.equal(fetchCall.url, "https://api.stripe.com/v1/checkout/sessions");
  const params = new URLSearchParams(fetchCall.options.body);
  assert.equal(params.get("mode"), "subscription");
  assert.equal(params.get("line_items[0][price]"), "price_pro_123");
  assert.equal(params.get("metadata[plan]"), "pro");
  assert.equal(params.get("subscription_data[metadata][plan]"), "pro");

  t.after(() => {
    global.fetch = originalFetch;
    resetEnv();
  });
});

test("account-config reports auth availability based on env", async (t) => {
  resetEnv();
  const mod = load("../account-config.js");

  let response = await mod.handler();
  let body = JSON.parse(response.body);
  assert.equal(body.auth_enabled, false);

  process.env.SUPABASE_URL = "https://example.supabase.co";
  process.env.SUPABASE_ANON_KEY = "anon_key";

  response = await mod.handler();
  body = JSON.parse(response.body);
  assert.equal(body.auth_enabled, true);

  t.after(() => resetEnv());
});

test("account-me rejects non-GET methods", async (t) => {
  resetEnv();
  const mod = load("../account-me.js");
  const response = await mod.handler({ httpMethod: "POST" });

  assert.equal(response.statusCode, 405);
  const body = JSON.parse(response.body);
  assert.match(body.error, /Method not allowed/i);

  t.after(() => resetEnv());
});

test("account-portal rejects non-POST methods", async (t) => {
  resetEnv();
  const mod = load("../account-portal.js");
  const response = await mod.handler({ httpMethod: "GET" });

  assert.equal(response.statusCode, 405);
  const body = JSON.parse(response.body);
  assert.match(body.error, /Method not allowed/i);

  t.after(() => resetEnv());
});

test("get-license rejects non-POST methods", async (t) => {
  resetEnv();
  const mod = load("../get-license.js");
  const response = await mod.handler({ httpMethod: "GET" });

  assert.equal(response.statusCode, 405);
  const body = JSON.parse(response.body);
  assert.match(body.error, /Method not allowed/i);

  t.after(() => resetEnv());
});

test("get-license returns signed key for matching authenticated user", async (t) => {
  resetEnv();
  process.env.STRIPE_SECRET_KEY = "sk_test_123";
  process.env.GEOBRIEF_LICENSE_SECRET = "license_secret_123";
  process.env.SUPABASE_URL = "https://supabase.test";
  process.env.SUPABASE_ANON_KEY = "anon_test";
  process.env.SUPABASE_SERVICE_ROLE_KEY = "service_role_test";

  const originalFetch = global.fetch;
  global.fetch = async (url) => {
    if (url === "https://supabase.test/auth/v1/user") {
      return jsonResponse({ id: "user_1", email: "buyer@example.gov" });
    }
    if (url === "https://api.stripe.com/v1/checkout/sessions/cs_valid123") {
      return jsonResponse({
        payment_status: "paid",
        metadata: { plan: "pro", supabase_user_id: "user_1" },
        customer_details: { email: "buyer@example.gov" },
        customer: "cus_123",
        subscription: "sub_123",
      });
    }
    if (url === "https://api.stripe.com/v1/subscriptions/sub_123") {
      return jsonResponse({
        status: "active",
        current_period_end: 2000000000,
      });
    }
    if (String(url).startsWith("https://supabase.test/rest/v1/account_profiles")) {
      return jsonResponse([]);
    }
    throw new Error(`Unexpected fetch URL: ${url}`);
  };

  const mod = load("../get-license.js");
  const response = await mod.handler({
    httpMethod: "POST",
    headers: {
      authorization: "Bearer session_token",
    },
    body: JSON.stringify({ session_id: "cs_valid123" }),
  });

  assert.equal(response.statusCode, 200);
  const body = JSON.parse(response.body);
  assert.equal(body.plan, "pro");
  assert.equal(body.email, "buyer@example.gov");
  assert.match(body.license_key, /^GBLE\./);

  t.after(() => {
    global.fetch = originalFetch;
    resetEnv();
  });
});

test("get-license blocks session owner mismatch", async (t) => {
  resetEnv();
  process.env.STRIPE_SECRET_KEY = "sk_test_123";
  process.env.GEOBRIEF_LICENSE_SECRET = "license_secret_123";
  process.env.SUPABASE_URL = "https://supabase.test";
  process.env.SUPABASE_ANON_KEY = "anon_test";

  const originalFetch = global.fetch;
  global.fetch = async (url) => {
    if (url === "https://supabase.test/auth/v1/user") {
      return jsonResponse({ id: "user_1", email: "buyer@example.gov" });
    }
    if (url === "https://api.stripe.com/v1/checkout/sessions/cs_mismatch123") {
      return jsonResponse({
        payment_status: "paid",
        metadata: { plan: "pro", supabase_user_id: "user_2" },
        customer_details: { email: "buyer@example.gov" },
      });
    }
    throw new Error(`Unexpected fetch URL: ${url}`);
  };

  const mod = load("../get-license.js");
  const response = await mod.handler({
    httpMethod: "POST",
    headers: {
      authorization: "Bearer session_token",
    },
    body: JSON.stringify({ session_id: "cs_mismatch123" }),
  });

  assert.equal(response.statusCode, 403);
  const body = JSON.parse(response.body);
  assert.match(body.error, /does not match the checkout session owner/i);

  t.after(() => {
    global.fetch = originalFetch;
    resetEnv();
  });
});

test("account-me returns conflict when multiple Stripe customers match", async (t) => {
  resetEnv();
  process.env.SUPABASE_URL = "https://supabase.test";
  process.env.SUPABASE_ANON_KEY = "anon_test";
  process.env.STRIPE_SECRET_KEY = "sk_test_123";

  const originalFetch = global.fetch;
  global.fetch = async (url) => {
    if (url === "https://supabase.test/auth/v1/user") {
      return jsonResponse({ id: "user_1", email: "buyer@example.gov" });
    }
    if (String(url).startsWith("https://supabase.test/rest/v1/account_profiles")) {
      return jsonResponse([]);
    }
    if (String(url).startsWith("https://api.stripe.com/v1/customers?email=")) {
      return jsonResponse({ data: [{ id: "cus_1" }, { id: "cus_2" }] });
    }
    throw new Error(`Unexpected fetch URL: ${url}`);
  };

  const mod = load("../account-me.js");
  const response = await mod.handler({
    httpMethod: "GET",
    headers: {
      authorization: "Bearer session_token",
    },
  });

  assert.equal(response.statusCode, 409);
  const body = JSON.parse(response.body);
  assert.match(body.error, /multiple billing customers/i);

  t.after(() => {
    global.fetch = originalFetch;
    resetEnv();
  });
});

test("account-portal creates billing portal URL for authenticated user", async (t) => {
  resetEnv();
  process.env.SUPABASE_URL = "https://supabase.test";
  process.env.SUPABASE_ANON_KEY = "anon_test";
  process.env.SUPABASE_SERVICE_ROLE_KEY = "service_role_test";
  process.env.STRIPE_SECRET_KEY = "sk_test_123";

  const originalFetch = global.fetch;
  global.fetch = async (url) => {
    if (url === "https://supabase.test/auth/v1/user") {
      return jsonResponse({ id: "user_1", email: "buyer@example.gov" });
    }
    if (String(url).startsWith("https://supabase.test/rest/v1/account_profiles") && String(url).includes("select=*")) {
      return jsonResponse([]);
    }
    if (String(url).startsWith("https://api.stripe.com/v1/customers?email=")) {
      return jsonResponse({ data: [{ id: "cus_123" }] });
    }
    if (String(url).startsWith("https://supabase.test/rest/v1/account_profiles") && String(url).includes("on_conflict=user_id")) {
      return jsonResponse([{ user_id: "user_1", stripe_customer_id: "cus_123" }]);
    }
    if (url === "https://api.stripe.com/v1/billing_portal/sessions") {
      return jsonResponse({ url: "https://billing.stripe.com/p/session_123" });
    }
    throw new Error(`Unexpected fetch URL: ${url}`);
  };

  const mod = load("../account-portal.js");
  const response = await mod.handler({
    httpMethod: "POST",
    headers: {
      authorization: "Bearer session_token",
      host: "example.com",
    },
  });

  assert.equal(response.statusCode, 200);
  const body = JSON.parse(response.body);
  assert.equal(body.url, "https://billing.stripe.com/p/session_123");

  t.after(() => {
    global.fetch = originalFetch;
    resetEnv();
  });
});
