// Storefront interactions: start Stripe checkout for the chosen plan.
"use strict";

document.querySelectorAll(".buy").forEach((button) => {
  button.addEventListener("click", async () => {
    const status = document.getElementById("buy-status");
    button.disabled = true;
    status.textContent = "Starting secure checkout…";
    try {
      const response = await fetch("/api/create-checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: button.dataset.plan }),
      });
      const body = await response.json();
      if (response.ok && body.url) {
        window.location.href = body.url;
        return;
      }
      status.textContent = body.error || "Checkout is unavailable right now.";
    } catch {
      status.textContent = "Checkout is unavailable right now. Please try again.";
    }
    button.disabled = false;
  });
});
