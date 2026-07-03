"""Tests for offline license keys (licensing.py)."""

import time

import pytest

from geobrief.billing import effective_plan
from geobrief.licensing import (
    LICENSE_KEY_ENV_VAR,
    LICENSE_SECRET_ENV_VAR,
    LicenseError,
    generate_license_key,
    licensed_plan,
    verify_license_key,
)

SECRET = "test-signing-secret"


def test_round_trip_pro_key():
    key = generate_license_key("pro", SECRET, email="buyer@example.com")
    payload = verify_license_key(key, SECRET)
    assert payload == {"plan": "pro", "email": "buyer@example.com"}


def test_key_format_prefix_and_parts():
    key = generate_license_key("standard", SECRET)
    parts = key.split(".")
    assert len(parts) == 3
    assert parts[0] == "GBLE"


def test_wrong_secret_rejected():
    key = generate_license_key("pro", SECRET)
    assert verify_license_key(key, "other-secret") is None


def test_tampered_payload_rejected():
    key = generate_license_key("standard", SECRET)
    prefix, payload_b64, sig = key.split(".")
    # Swap in the payload of a pro key while keeping the standard signature.
    pro_payload = generate_license_key("pro", SECRET).split(".")[1]
    forged = f"{prefix}.{pro_payload}.{sig}"
    assert verify_license_key(forged, SECRET) is None


def test_malformed_keys_rejected():
    for bad in ("", "GBLE", "GBLE.abc", "nope.abc.def", "GBLE.!!.??", "a.b.c.d"):
        assert verify_license_key(bad, SECRET) is None


def test_expired_key_rejected_and_future_ok():
    now = time.time()
    expired = generate_license_key("pro", SECRET, expires_at=int(now - 60))
    valid = generate_license_key("pro", SECRET, expires_at=int(now + 3600))
    assert verify_license_key(expired, SECRET) is None
    assert verify_license_key(valid, SECRET) is not None


def test_unknown_plan_rejected_on_issue():
    with pytest.raises(LicenseError):
        generate_license_key("enterprise", SECRET)


def test_issue_requires_secret():
    with pytest.raises(LicenseError):
        generate_license_key("pro", "")


def test_licensed_plan_from_env():
    key = generate_license_key("pro", SECRET)
    env = {LICENSE_KEY_ENV_VAR: key, LICENSE_SECRET_ENV_VAR: SECRET}
    plan = licensed_plan(env)
    assert plan is not None and plan.id == "pro"
    # Missing secret → no entitlement.
    assert licensed_plan({LICENSE_KEY_ENV_VAR: key}) is None
    assert licensed_plan({}) is None


def test_effective_plan_uses_license_key(monkeypatch):
    key = generate_license_key("pro", SECRET)
    assert effective_plan().id == "standard"
    monkeypatch.setenv(LICENSE_KEY_ENV_VAR, key)
    monkeypatch.setenv(LICENSE_SECRET_ENV_VAR, SECRET)
    assert effective_plan().id == "pro"


def test_env_plan_still_works_without_license(monkeypatch):
    monkeypatch.setenv("GEOBRIEF_PLAN", "pro")
    assert effective_plan().id == "pro"
