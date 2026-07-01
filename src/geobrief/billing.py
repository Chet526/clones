"""Real billing for GeoBrief LE via Stripe subscriptions.

This module turns the plan catalogue in :mod:`geobrief.subscription` into a
working paid product:

* **Stripe Checkout** — :meth:`BillingService.create_checkout_session` starts a
  hosted subscription checkout for a plan and returns the URL to redirect the
  customer to.
* **Signed webhooks** — :meth:`BillingService.construct_event` verifies the
  ``Stripe-Signature`` header (HMAC-SHA256, constant-time compare, replay
  window) *before* the payload is trusted, and :meth:`BillingService.apply_event`
  updates local subscription state from ``checkout.session.completed`` and
  ``customer.subscription.*`` events.
* **Entitlement resolution** — :meth:`BillingService.active_plan_id` reads the
  persisted subscription state so the rest of the app can gate features on a
  *real, paid* subscription. :func:`effective_plan` layers this over the
  ``GEOBRIEF_PLAN`` env fallback used for local development.

Design choices:

* **No new dependencies.** All HTTP and signature work uses the standard
  library (``urllib``, ``hmac``, ``hashlib``), matching the style of
  :mod:`geobrief.assistant`. The Stripe secret key is only ever used
  server-side and is never logged or returned to the client.
* **Single-node persistence.** Subscription state is stored in a JSON file
  (``GEOBRIEF_BILLING_STORE``) with atomic writes. Events are applied
  idempotently keyed by Stripe subscription id, so redelivered webhooks are
  safe. For a multi-node deployment, swap :class:`BillingStore` for a shared
  database with the same interface.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from .subscription import PLANS, Plan, get_plan

__all__ = [
    "BillingConfig",
    "BillingStore",
    "BillingService",
    "BillingError",
    "SignatureVerificationError",
    "effective_plan",
    "ACTIVE_STATUSES",
]

_DEFAULT_API_BASE = "https://api.stripe.com"
_DEFAULT_STORE_PATH = os.path.join("~", ".geobrief", "billing.json")
# Default replay tolerance for webhook timestamps (5 minutes), matching Stripe.
_DEFAULT_WEBHOOK_TOLERANCE = 300

# Stripe subscription statuses that grant access to a plan's features.
ACTIVE_STATUSES = frozenset({"active", "trialing", "past_due"})


class BillingError(RuntimeError):
    """Raised when a billing operation cannot be completed."""


class SignatureVerificationError(BillingError):
    """Raised when a webhook signature fails verification."""


def _get(source: dict, name: str) -> Optional[str]:
    value = source.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


@dataclass
class BillingConfig:
    """Stripe settings, typically populated from the environment.

    Billing is only *configured* when a secret key is present. Without it,
    checkout is unavailable and the app falls back to the ``GEOBRIEF_PLAN``
    env var for entitlements (useful for local development and self-hosting).
    """

    secret_key: Optional[str] = None
    webhook_secret: Optional[str] = None
    # Map of plan id -> Stripe recurring Price id.
    price_ids: dict = field(default_factory=dict)
    success_url: str = "http://localhost:8000/?checkout=success"
    cancel_url: str = "http://localhost:8000/?checkout=cancelled"
    api_base: str = _DEFAULT_API_BASE
    store_path: str = _DEFAULT_STORE_PATH
    timeout: float = 30.0
    webhook_tolerance: int = _DEFAULT_WEBHOOK_TOLERANCE

    @property
    def configured(self) -> bool:
        """True when a Stripe secret key is available for API calls."""
        return bool(self.secret_key)

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "BillingConfig":
        """Build a config from environment variables.

        Recognised variables (all optional):

        * ``STRIPE_SECRET_KEY`` — secret API key; enables checkout.
        * ``STRIPE_WEBHOOK_SECRET`` — signing secret for webhook verification.
        * ``STRIPE_PRICE_STANDARD`` / ``STRIPE_PRICE_PRO`` — Stripe Price ids
          for each plan (any additional plan uses ``STRIPE_PRICE_<ID>``).
        * ``STRIPE_SUCCESS_URL`` / ``STRIPE_CANCEL_URL`` — post-checkout URLs.
        * ``STRIPE_API_BASE`` — API base URL (override for testing).
        * ``GEOBRIEF_BILLING_STORE`` — path to the subscription state file.
        * ``STRIPE_WEBHOOK_TOLERANCE`` — webhook replay window, seconds.
        """
        source = os.environ if env is None else env

        price_ids: dict = {}
        for plan in PLANS:
            value = _get(source, f"STRIPE_PRICE_{plan.id.upper()}")
            if value:
                price_ids[plan.id] = value

        def _int(name: str, default: int) -> int:
            raw = _get(source, name)
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        return cls(
            secret_key=_get(source, "STRIPE_SECRET_KEY"),
            webhook_secret=_get(source, "STRIPE_WEBHOOK_SECRET"),
            price_ids=price_ids,
            success_url=_get(source, "STRIPE_SUCCESS_URL")
            or cls.success_url,
            cancel_url=_get(source, "STRIPE_CANCEL_URL") or cls.cancel_url,
            api_base=_get(source, "STRIPE_API_BASE") or _DEFAULT_API_BASE,
            store_path=_get(source, "GEOBRIEF_BILLING_STORE")
            or _DEFAULT_STORE_PATH,
            webhook_tolerance=_int(
                "STRIPE_WEBHOOK_TOLERANCE", _DEFAULT_WEBHOOK_TOLERANCE
            ),
        )

    def price_id_for(self, plan_id: str) -> Optional[str]:
        """Return the Stripe Price id configured for ``plan_id``."""
        return self.price_ids.get(plan_id)

    def plan_id_for_price(self, price_id: str) -> Optional[str]:
        """Reverse lookup: which plan a Stripe Price id maps to."""
        for plan_id, configured in self.price_ids.items():
            if configured == price_id:
                return plan_id
        return None


class BillingStore:
    """Atomic JSON-file persistence for subscription state.

    State shape::

        {"subscriptions": {"<sub_id>": {"status": ..., "plan": ...,
                                        "customer": ..., "updated": ...}}}

    The file is read fresh on each access so webhook updates written by one
    process are visible to others, and written atomically via a temp file +
    ``os.replace`` so a crash never leaves a partially written file.
    """

    def __init__(self, path: str) -> None:
        self.path = os.path.expanduser(path)
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (FileNotFoundError, ValueError):
            return {"subscriptions": {}}
        if not isinstance(data, dict):
            return {"subscriptions": {}}
        data.setdefault("subscriptions", {})
        return data

    def _write(self, data: dict) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=directory or None, prefix=".billing-", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def upsert_subscription(
        self,
        subscription_id: str,
        *,
        status: str,
        plan_id: Optional[str],
        customer: Optional[str] = None,
    ) -> None:
        """Insert or update a subscription record (idempotent)."""
        with self._lock:
            data = self._read()
            record = data["subscriptions"].get(subscription_id, {})
            record["status"] = status
            if plan_id is not None:
                record["plan"] = plan_id
            if customer is not None:
                record["customer"] = customer
            record["updated"] = int(time.time())
            data["subscriptions"][subscription_id] = record
            self._write(data)

    def active_plan_id(self) -> Optional[str]:
        """Return the highest-tier plan among active subscriptions, if any."""
        data = self._read()
        best: Optional[Plan] = None
        for record in data["subscriptions"].values():
            if record.get("status") not in ACTIVE_STATUSES:
                continue
            plan_id = record.get("plan")
            if not plan_id:
                continue
            plan = get_plan(plan_id)
            if best is None or plan.price_cents > best.price_cents:
                best = plan
        return best.id if best else None

    def snapshot(self) -> dict:
        """Return a copy of the stored subscriptions (for status/debug)."""
        return self._read()["subscriptions"]


class BillingService:
    """Coordinates Stripe API calls, webhook verification, and local state."""

    def __init__(
        self,
        config: Optional[BillingConfig] = None,
        store: Optional[BillingStore] = None,
    ) -> None:
        self.config = config or BillingConfig.from_env()
        self.store = store or BillingStore(self.config.store_path)

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "BillingService":
        return cls(BillingConfig.from_env(env))

    # -- Entitlements --------------------------------------------------------
    def active_plan_id(self) -> Optional[str]:
        """Plan id granted by a real active subscription, or ``None``."""
        return self.store.active_plan_id()

    # -- Checkout ------------------------------------------------------------
    def create_checkout_session(self, plan_id: str) -> dict:
        """Create a Stripe Checkout Session for ``plan_id``.

        Returns the Stripe session object (including its ``url``). Raises
        :class:`BillingError` when billing is not configured or the plan has
        no Stripe Price id.
        """
        if not self.config.configured:
            raise BillingError(
                "Billing is not configured. Set STRIPE_SECRET_KEY."
            )
        plan = get_plan(plan_id)
        price_id = self.config.price_id_for(plan.id)
        if not price_id:
            raise BillingError(
                f"No Stripe price configured for the {plan.name} plan. "
                f"Set STRIPE_PRICE_{plan.id.upper()}."
            )

        params = {
            "mode": "subscription",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "success_url": self.config.success_url,
            "cancel_url": self.config.cancel_url,
            # Carry the plan on both the session and the created subscription
            # so webhooks can resolve the plan without an extra API round-trip.
            "client_reference_id": plan.id,
            "metadata[plan]": plan.id,
            "subscription_data[metadata][plan]": plan.id,
        }
        return self._api_post("/v1/checkout/sessions", params)

    def _api_post(self, path: str, params: dict) -> dict:
        url = self.config.api_base.rstrip("/") + path
        data = urllib.parse.urlencode(params).encode("utf-8")
        headers = {
            "Authorization": "Bearer " + (self.config.secret_key or ""),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        request = urllib.request.Request(
            url, data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - network
            detail = exc.read().decode("utf-8", "replace") if exc.fp else ""
            raise BillingError(
                f"Stripe request failed ({exc.code}): {detail[:300]}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:  # pragma: no cover - network
            raise BillingError(f"Stripe request failed: {exc}") from exc

    # -- Webhooks ------------------------------------------------------------
    def construct_event(
        self,
        payload: bytes,
        signature_header: Optional[str],
        *,
        now: Optional[int] = None,
    ) -> dict:
        """Verify the Stripe signature and return the parsed event.

        Implements Stripe's scheme: the signed payload is
        ``"{timestamp}.{raw_body}"`` and the header carries ``t=`` and one or
        more ``v1=`` HMAC-SHA256 hex digests. Comparison is constant-time and
        the timestamp must be within the configured tolerance to resist
        replay. Raises :class:`SignatureVerificationError` on any mismatch.
        """
        secret = self.config.webhook_secret
        if not secret:
            raise SignatureVerificationError(
                "Webhook secret is not configured (STRIPE_WEBHOOK_SECRET)."
            )
        if not signature_header:
            raise SignatureVerificationError("Missing Stripe-Signature header.")

        timestamp, signatures = _parse_signature_header(signature_header)
        if timestamp is None or not signatures:
            raise SignatureVerificationError(
                "Malformed Stripe-Signature header."
            )

        signed_payload = str(timestamp).encode("utf-8") + b"." + payload
        expected = hmac.new(
            secret.encode("utf-8"), signed_payload, hashlib.sha256
        ).hexdigest()
        if not any(
            hmac.compare_digest(expected, candidate) for candidate in signatures
        ):
            raise SignatureVerificationError("Signature mismatch.")

        current = int(time.time()) if now is None else now
        if abs(current - timestamp) > self.config.webhook_tolerance:
            raise SignatureVerificationError(
                "Timestamp outside the tolerance window."
            )

        try:
            event = json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise SignatureVerificationError("Payload is not valid JSON.") from exc
        if not isinstance(event, dict):
            raise SignatureVerificationError("Unexpected event shape.")
        return event

    def apply_event(self, event: dict) -> Optional[str]:
        """Update stored subscription state from a verified event.

        Handles ``checkout.session.completed`` and ``customer.subscription.*``.
        Returns the affected subscription id, or ``None`` when the event is
        not relevant. Safe to call repeatedly (idempotent).
        """
        event_type = event.get("type", "")
        obj = (event.get("data") or {}).get("object") or {}

        if event_type == "checkout.session.completed":
            if obj.get("mode") != "subscription":
                return None
            subscription_id = obj.get("subscription")
            if not subscription_id:
                return None
            plan_id = (obj.get("metadata") or {}).get("plan") or obj.get(
                "client_reference_id"
            )
            self.store.upsert_subscription(
                subscription_id,
                status="active",
                plan_id=plan_id,
                customer=obj.get("customer"),
            )
            return subscription_id

        if event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            subscription_id = obj.get("id")
            if not subscription_id:
                return None
            status = (
                "canceled"
                if event_type == "customer.subscription.deleted"
                else obj.get("status", "canceled")
            )
            plan_id = self._plan_from_subscription(obj)
            self.store.upsert_subscription(
                subscription_id,
                status=status,
                plan_id=plan_id,
                customer=obj.get("customer"),
            )
            return subscription_id

        return None

    def _plan_from_subscription(self, subscription: dict) -> Optional[str]:
        """Resolve a plan id from a Stripe subscription object."""
        metadata = subscription.get("metadata") or {}
        if metadata.get("plan"):
            return metadata["plan"]
        items = (subscription.get("items") or {}).get("data") or []
        for item in items:
            price = (item or {}).get("price") or {}
            price_id = price.get("id")
            if price_id:
                mapped = self.config.plan_id_for_price(price_id)
                if mapped:
                    return mapped
        return None


def effective_plan(env: Optional[dict] = None) -> Plan:
    """Return the plan the app should enforce right now.

    Prefers a real active Stripe subscription; when there is none (or billing
    is not configured), falls back to the ``GEOBRIEF_PLAN`` env selection used
    for local development and self-hosting.
    """
    # Imported lazily to keep the module import graph shallow and avoid any
    # import-time coupling with the web layer.
    from .subscription import current_plan

    service = BillingService.from_env(env)
    plan_id = service.active_plan_id()
    if plan_id:
        return get_plan(plan_id)
    return current_plan(env)


def _parse_signature_header(header: str):
    """Parse a ``Stripe-Signature`` header into (timestamp, [v1 digests])."""
    timestamp: Optional[int] = None
    signatures: list = []
    for part in header.split(","):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                return None, []
        elif key == "v1":
            signatures.append(value)
    return timestamp, signatures
