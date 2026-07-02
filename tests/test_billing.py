"""Tests for real billing (Stripe) integration."""

import hashlib
import hmac
import json
import time

import pytest

from geobrief.billing import (
    BillingConfig,
    BillingService,
    BillingStore,
    SignatureVerificationError,
    effective_plan,
)


def _service(tmp_path, **overrides):
    config = BillingConfig(
        secret_key=overrides.get("secret_key"),
        webhook_secret=overrides.get("webhook_secret"),
        price_ids=overrides.get(
            "price_ids", {"standard": "price_std", "pro": "price_pro"}
        ),
        store_path=str(tmp_path / "billing.json"),
        webhook_tolerance=overrides.get("webhook_tolerance", 300),
    )
    return BillingService(config, BillingStore(config.store_path))


def _sign(payload: bytes, secret: str, timestamp: int) -> str:
    signed = f"{timestamp}".encode() + b"." + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


# -- Configuration -----------------------------------------------------------


def test_config_from_env_reads_prices_and_keys():
    env = {
        "STRIPE_SECRET_KEY": "sk_test_123",
        "STRIPE_WEBHOOK_SECRET": "whsec_123",
        "STRIPE_PRICE_STANDARD": "price_std",
        "STRIPE_PRICE_PRO": "price_pro",
    }
    config = BillingConfig.from_env(env)
    assert config.configured is True
    assert config.price_id_for("pro") == "price_pro"
    assert config.plan_id_for_price("price_std") == "standard"


def test_config_not_configured_without_key():
    assert BillingConfig.from_env({}).configured is False


# -- Checkout ----------------------------------------------------------------


def test_checkout_requires_configuration(tmp_path):
    service = _service(tmp_path)  # no secret key
    with pytest.raises(Exception):
        service.create_checkout_session("pro")


def test_checkout_requires_price_for_plan(tmp_path):
    service = _service(tmp_path, secret_key="sk_test", price_ids={})
    with pytest.raises(Exception):
        service.create_checkout_session("pro")


def test_checkout_posts_expected_params(tmp_path, monkeypatch):
    service = _service(tmp_path, secret_key="sk_test")
    captured = {}

    def fake_post(path, params):
        captured["path"] = path
        captured["params"] = params
        return {"id": "cs_test", "url": "https://checkout.stripe.test/cs_test"}

    monkeypatch.setattr(service, "_api_post", fake_post)
    session = service.create_checkout_session("pro")
    assert session["url"] == "https://checkout.stripe.test/cs_test"
    assert captured["path"] == "/v1/checkout/sessions"
    params = captured["params"]
    assert params["mode"] == "subscription"
    assert params["line_items[0][price]"] == "price_pro"
    assert params["metadata[plan]"] == "pro"
    assert params["subscription_data[metadata][plan]"] == "pro"


# -- Webhook signature verification ------------------------------------------


def test_construct_event_accepts_valid_signature(tmp_path):
    service = _service(tmp_path, webhook_secret="whsec_test")
    payload = json.dumps({"type": "ping"}).encode()
    header = _sign(payload, "whsec_test", int(time.time()))
    event = service.construct_event(payload, header)
    assert event["type"] == "ping"


def test_construct_event_rejects_bad_signature(tmp_path):
    service = _service(tmp_path, webhook_secret="whsec_test")
    payload = json.dumps({"type": "ping"}).encode()
    header = _sign(payload, "wrong_secret", int(time.time()))
    with pytest.raises(SignatureVerificationError):
        service.construct_event(payload, header)


def test_construct_event_rejects_replayed_timestamp(tmp_path):
    service = _service(tmp_path, webhook_secret="whsec_test")
    payload = json.dumps({"type": "ping"}).encode()
    old = int(time.time()) - 10_000
    header = _sign(payload, "whsec_test", old)
    with pytest.raises(SignatureVerificationError):
        service.construct_event(payload, header)


def test_construct_event_requires_secret_and_header(tmp_path):
    payload = b"{}"
    no_secret = _service(tmp_path)
    with pytest.raises(SignatureVerificationError):
        no_secret.construct_event(payload, "t=1,v1=abc")
    with_secret = _service(tmp_path, webhook_secret="whsec_test")
    with pytest.raises(SignatureVerificationError):
        with_secret.construct_event(payload, None)


def test_construct_event_rejects_tampered_payload(tmp_path):
    service = _service(tmp_path, webhook_secret="whsec_test")
    payload = json.dumps({"type": "ping"}).encode()
    header = _sign(payload, "whsec_test", int(time.time()))
    tampered = json.dumps({"type": "evil"}).encode()
    with pytest.raises(SignatureVerificationError):
        service.construct_event(tampered, header)


# -- Applying events / entitlements ------------------------------------------


def test_checkout_completed_activates_plan(tmp_path):
    service = _service(tmp_path)
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "mode": "subscription",
                "subscription": "sub_1",
                "customer": "cus_1",
                "metadata": {"plan": "pro"},
            }
        },
    }
    assert service.apply_event(event) == "sub_1"
    assert service.active_plan_id() == "pro"


def test_subscription_deleted_revokes_access(tmp_path):
    service = _service(tmp_path)
    service.apply_event(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "mode": "subscription",
                    "subscription": "sub_1",
                    "metadata": {"plan": "pro"},
                }
            },
        }
    )
    assert service.active_plan_id() == "pro"
    service.apply_event(
        {
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_1", "status": "canceled"}},
        }
    )
    assert service.active_plan_id() is None


def test_subscription_updated_resolves_plan_from_price(tmp_path):
    service = _service(tmp_path)
    event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_2",
                "status": "active",
                "items": {"data": [{"price": {"id": "price_pro"}}]},
            }
        },
    }
    service.apply_event(event)
    assert service.active_plan_id() == "pro"


def test_apply_event_is_idempotent(tmp_path):
    service = _service(tmp_path)
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "mode": "subscription",
                "subscription": "sub_1",
                "metadata": {"plan": "pro"},
            }
        },
    }
    service.apply_event(event)
    service.apply_event(event)
    assert len(service.store.snapshot()) == 1


def test_active_plan_picks_highest_tier(tmp_path):
    service = _service(tmp_path)
    service.store.upsert_subscription(
        "sub_std", status="active", plan_id="standard"
    )
    service.store.upsert_subscription(
        "sub_pro", status="active", plan_id="pro"
    )
    assert service.active_plan_id() == "pro"


def test_effective_plan_prefers_subscription_over_env(tmp_path, monkeypatch):
    store_path = str(tmp_path / "billing.json")
    monkeypatch.setenv("GEOBRIEF_BILLING_STORE", store_path)
    monkeypatch.setenv("GEOBRIEF_PLAN", "standard")
    # No subscription yet -> env fallback.
    assert effective_plan().id == "standard"
    # Record an active Pro subscription -> overrides env.
    BillingStore(store_path).upsert_subscription(
        "sub_1", status="active", plan_id="pro"
    )
    assert effective_plan().id == "pro"
