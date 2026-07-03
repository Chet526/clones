"use strict";

let supabaseClient = null;

init().catch((err) => {
  console.error(err);
  setText("status", "Account page is unavailable right now.");
});

async function init() {
  const configRes = await fetch("/api/account-config");
  const config = await configRes.json();
  if (!config.auth_enabled) {
    setText(
      "status",
      "Account login is not configured yet. Please contact support."
    );
    return;
  }

  supabaseClient = window.supabase.createClient(
    config.supabase_url,
    config.supabase_anon_key
  );

  const {
    data: { session },
  } = await supabaseClient.auth.getSession();

  if (!session) {
    setText("status", "Sign in to manage your subscription.");
    show("auth-card");
    bindLogin();
    return;
  }

  await showProfile(session);
}

function bindLogin() {
  const form = document.getElementById("login-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = document.getElementById("email").value.trim();
    if (!email) return;
    setText("login-status", "Sending magic link…");
    const { error } = await supabaseClient.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${location.origin}/account.html` },
    });
    if (error) {
      setText("login-status", error.message || "Could not send magic link.");
      return;
    }
    setText("login-status", "Check your email for the sign-in link.");
  });
}

async function showProfile(session) {
  hide("auth-card");
  show("profile-card");
  setText("status", "Signed in. Loading subscription…");

  const response = await fetch("/api/account-me", {
    headers: { Authorization: `Bearer ${session.access_token}` },
  });
  const body = await response.json();

  if (!response.ok) {
    setText("status", body.error || "Could not load account details.");
    return;
  }

  renderProfile(body);
  setText("status", "");
  bindActions(session.access_token, body);
}

function renderProfile(profile) {
  const plan = profile.plan ? profile.plan.toUpperCase() : "No active plan";
  const sub = profile.subscription;
  const expires = sub?.current_period_end
    ? new Date(sub.current_period_end * 1000).toLocaleString()
    : "n/a";
  const body = document.getElementById("profile-body");
  body.innerHTML = `
    <p><strong>Email:</strong> ${escapeHtml(profile.email)}</p>
    <p><strong>Plan:</strong> ${escapeHtml(plan)}</p>
    <p><strong>Subscription status:</strong> ${escapeHtml(sub?.status || "none")}</p>
    <p><strong>Current period end:</strong> ${escapeHtml(expires)}</p>
  `;
}

function bindActions(accessToken, profile) {
  const portalBtn = document.getElementById("portal-btn");
  const signoutBtn = document.getElementById("signout-btn");

  if (!profile.has_billing_account) {
    portalBtn.disabled = true;
    setText(
      "profile-status",
      "No billing account found for this email yet. Complete checkout first."
    );
  } else {
    portalBtn.addEventListener("click", async () => {
      portalBtn.disabled = true;
      setText("profile-status", "Opening Stripe billing portal…");
      const response = await fetch("/api/account-portal", {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      const body = await response.json();
      if (response.ok && body.url) {
        location.href = body.url;
        return;
      }
      setText(
        "profile-status",
        body.error || "Could not open billing portal right now."
      );
      portalBtn.disabled = false;
    });
  }

  signoutBtn.addEventListener("click", async () => {
    await supabaseClient.auth.signOut();
    location.reload();
  });
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function show(id) {
  const el = document.getElementById(id);
  if (el) el.hidden = false;
}

function hide(id) {
  const el = document.getElementById(id);
  if (el) el.hidden = true;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
