"""Tests for the FastAPI web application."""

import io

import pytest
from fastapi.testclient import TestClient

from geobrief.billing import BillingStore
from geobrief.subscription import PLAN_ENV_VAR
from geobrief.webapp.app import app

client = TestClient(app)


@pytest.fixture()
def pro_plan(monkeypatch):
    """Activate the Pro plan so assistant endpoints are unlocked."""
    monkeypatch.setenv(PLAN_ENV_VAR, "pro")


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_index_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "GeoBrief LE" in response.text


def test_process_endpoint():
    csv = (
        "latitude,longitude,timestamp,accuracy_m\n"
        "41.88,-87.62,2024-03-01T08:00:00Z,10\n"
        ",,2024-03-01T09:00:00Z,\n"
    )
    files = {"file": ("records.csv", io.BytesIO(csv.encode()), "text/csv")}
    response = client.post(
        "/api/process",
        files=files,
        data={"display_timezone": "America/Chicago"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["record_counts"]["total"] == 2
    assert body["summary"]["record_counts"]["mappable"] == 1
    assert len(body["geojson"]["features"]) == 1
    assert "validation_status" in body["cleaned_csv"]


def test_unsupported_file_type_rejected():
    files = {"file": ("notes.docx", io.BytesIO(b"hello"), "text/plain")}
    response = client.post("/api/process", files=files)
    assert response.status_code == 400


def test_empty_file_rejected():
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    response = client.post("/api/process", files=files)
    assert response.status_code == 400


def test_detect_endpoint_reports_columns_and_mapping():
    csv = (
        "the_lat,the_long,when,radius_m\n"
        "41.88,-87.62,2024-03-01T08:00:00Z,10\n"
    )
    files = {"file": ("records.csv", io.BytesIO(csv.encode()), "text/csv")}
    response = client.post("/api/detect", files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["the_lat", "the_long", "when", "radius_m"]
    assert body["row_count"] == 1
    assert body["detection"]["mapping"]["latitude"] == "the_lat"
    assert set(body["detection"]["confidence"]) == {
        "latitude",
        "longitude",
        "timestamp",
        "accuracy",
    }


def test_detect_rejects_unsupported_type():
    files = {"file": ("notes.docx", io.BytesIO(b"hello"), "text/plain")}
    response = client.post("/api/detect", files=files)
    assert response.status_code == 400


def test_process_with_manual_column_mapping():
    # Column names give detection nothing to work with; the manual mapping
    # must make the rows mappable anyway.
    csv = (
        "a,b,c\n"
        "41.88,-87.62,2024-03-01T08:00:00Z\n"
        "41.90,-87.63,2024-03-01T12:00:00Z\n"
    )
    files = {"file": ("odd.csv", io.BytesIO(csv.encode()), "text/csv")}
    response = client.post(
        "/api/process",
        files=files,
        data={
            "latitude_column": "a",
            "longitude_column": "b",
            "timestamp_column": "c",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["record_counts"]["mappable"] == 2
    assert len(body["geojson"]["features"]) == 2


def _process_sample():
    csv = (
        "latitude,longitude,timestamp,accuracy_m\n"
        "41.88,-87.62,2024-03-01T08:00:00Z,10\n"
        "41.90,-87.63,2024-03-01T12:00:00Z,15\n"
    )
    files = {"file": ("records.csv", io.BytesIO(csv.encode()), "text/csv")}
    response = client.post(
        "/api/process",
        files=files,
        data={"display_timezone": "America/Chicago"},
    )
    assert response.status_code == 200
    return response.json()


def test_assistant_status_defaults_to_local(pro_plan):
    response = client.get("/api/assistant/status")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["backend"] in {"local", "openrouter"}
    assert "enabled" in body


def test_assistant_answers_from_processed_data(pro_plan):
    processed = _process_sample()
    response = client.post(
        "/api/assistant",
        json={
            "question": "summarize the movement",
            "summary": processed["summary"],
            "geojson": processed["geojson"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["disclaimer"]
    assert body["backend"].startswith("local")


def test_assistant_requires_summary(pro_plan):
    response = client.post(
        "/api/assistant", json={"question": "hi", "summary": {}}
    )
    assert response.status_code == 400


def test_plans_endpoint_lists_both_tiers():
    response = client.get("/api/plans")
    assert response.status_code == 200
    body = response.json()
    ids = {plan["id"]: plan for plan in body["plans"]}
    assert ids["standard"]["price_display"] == "$9.99/month"
    assert ids["pro"]["price_display"] == "$14.99/month"


def test_plans_marks_current_plan(monkeypatch):
    monkeypatch.setenv(PLAN_ENV_VAR, "pro")
    body = client.get("/api/plans").json()
    assert body["current_plan"] == "pro"
    current = [plan for plan in body["plans"] if plan["current"]]
    assert [plan["id"] for plan in current] == ["pro"]


def test_assistant_status_paywalled_on_standard(monkeypatch):
    monkeypatch.setenv(PLAN_ENV_VAR, "standard")
    response = client.get("/api/assistant/status")
    assert response.status_code == 402
    body = response.json()
    assert body["available"] is False
    assert body["required_plan"]["id"] == "pro"


def test_assistant_endpoint_paywalled_on_standard(monkeypatch):
    monkeypatch.setenv(PLAN_ENV_VAR, "standard")
    processed = _process_sample()
    response = client.post(
        "/api/assistant",
        json={
            "question": "summarize the movement",
            "summary": processed["summary"],
            "geojson": processed["geojson"],
        },
    )
    assert response.status_code == 402
    assert response.json()["required_plan"]["price_display"] == "$14.99/month"


def test_billing_status_reports_disabled_by_default():
    body = client.get("/api/billing/status").json()
    assert body["billing_enabled"] is False
    assert body["active_subscription"] is False


def test_checkout_unavailable_without_config():
    response = client.post("/api/billing/checkout", json={"plan": "pro"})
    assert response.status_code == 503


def test_active_subscription_unlocks_assistant(monkeypatch, tmp_path):
    # An active Pro subscription in the billing store should unlock the
    # assistant even without GEOBRIEF_PLAN set.
    store_path = str(tmp_path / "billing.json")
    monkeypatch.setenv("GEOBRIEF_BILLING_STORE", store_path)
    BillingStore(store_path).upsert_subscription(
        "sub_1", status="active", plan_id="pro"
    )
    processed = _process_sample()
    response = client.post(
        "/api/assistant",
        json={
            "question": "summarize the movement",
            "summary": processed["summary"],
            "geojson": processed["geojson"],
        },
    )
    assert response.status_code == 200
    assert response.json()["answer"]


def test_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    response = client.post(
        "/api/billing/webhook",
        content=b'{"type": "ping"}',
        headers={"stripe-signature": "t=1,v1=deadbeef"},
    )
    assert response.status_code == 400
