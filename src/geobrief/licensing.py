"""Offline license keys for GeoBrief LE.

After a customer buys a plan on the storefront, the checkout webhook issues a
signed license key. The locally-installed app verifies the key **offline** —
no network call, no account system — and unlocks the purchased plan.

Key format (three dot-separated parts)::

    GBLE.<payload_b64url>.<signature_b64url>

* ``payload_b64url`` — URL-safe base64 (no padding) of a JSON object:
  ``{"plan": "pro", "email": "buyer@example.com", "exp": 1735689600}``.
  ``email`` is optional; ``exp`` (unix seconds) is optional — omitted means
  the key does not expire.
* ``signature_b64url`` — URL-safe base64 (no padding) of
  ``HMAC-SHA256(secret, payload_b64url)``. The signature covers the encoded
  payload string, so no JSON canonicalisation is needed and the same scheme
  is trivially reproduced in other languages (e.g. the storefront's Node
  webhook function).

Environment variables:

* ``GEOBRIEF_LICENSE_KEY`` — the customer's key.
* ``GEOBRIEF_LICENSE_SECRET`` — the signing secret. Needed both to issue keys
  (storefront) and to verify them (app). Without it, license keys are ignored.

Only the Python standard library is used.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from .subscription import PLANS, Plan, get_plan

__all__ = [
    "LICENSE_KEY_ENV_VAR",
    "LICENSE_SECRET_ENV_VAR",
    "LicenseError",
    "generate_license_key",
    "verify_license_key",
    "licensed_plan",
]

LICENSE_KEY_ENV_VAR = "GEOBRIEF_LICENSE_KEY"
LICENSE_SECRET_ENV_VAR = "GEOBRIEF_LICENSE_SECRET"

_PREFIX = "GBLE"

_VALID_PLAN_IDS = frozenset(plan.id for plan in PLANS)


class LicenseError(ValueError):
    """Raised when a license key cannot be issued or verified."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(payload_b64: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    return _b64url_encode(digest)


def generate_license_key(
    plan_id: str,
    secret: str,
    *,
    email: Optional[str] = None,
    expires_at: Optional[int] = None,
) -> str:
    """Issue a signed license key for ``plan_id``.

    ``expires_at`` is a unix timestamp (seconds); omit for a non-expiring key.
    """
    if not secret:
        raise LicenseError("A signing secret is required to issue license keys.")
    if plan_id not in _VALID_PLAN_IDS:
        raise LicenseError(f"Unknown plan id: {plan_id!r}")
    payload: dict = {"plan": plan_id}
    if email:
        payload["email"] = email
    if expires_at is not None:
        payload["exp"] = int(expires_at)
    payload_b64 = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return f"{_PREFIX}.{payload_b64}.{_sign(payload_b64, secret)}"


def verify_license_key(
    key: str, secret: str, *, now: Optional[float] = None
) -> Optional[dict]:
    """Verify ``key`` and return its payload, or ``None`` when invalid.

    Invalid means: malformed, wrong signature, unknown plan, or expired.
    Verification never raises for bad input — a broken key simply grants
    nothing, and the app falls back to its other entitlement sources.
    """
    if not key or not secret:
        return None
    parts = key.strip().split(".")
    if len(parts) != 3 or parts[0] != _PREFIX:
        return None
    _, payload_b64, signature = parts
    if not hmac.compare_digest(_sign(payload_b64, secret), signature):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("plan") not in _VALID_PLAN_IDS:
        return None
    exp = payload.get("exp")
    if exp is not None:
        try:
            if float(exp) < (time.time() if now is None else now):
                return None
        except (TypeError, ValueError):
            return None
    return payload


def licensed_plan(env: Optional[dict] = None) -> Optional[Plan]:
    """Return the plan unlocked by the environment's license key, if any."""
    import os

    source = os.environ if env is None else env
    key = source.get(LICENSE_KEY_ENV_VAR)
    secret = source.get(LICENSE_SECRET_ENV_VAR)
    payload = verify_license_key(key or "", secret or "")
    if payload is None:
        return None
    return get_plan(payload["plan"])
