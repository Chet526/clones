"""Tests for the FastAPI web application."""

import io

from fastapi.testclient import TestClient

from geobrief.webapp.app import app

client = TestClient(app)


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
    files = {"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
    response = client.post("/api/process", files=files)
    assert response.status_code == 400


def test_empty_file_rejected():
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    response = client.post("/api/process", files=files)
    assert response.status_code == 400


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


def test_assistant_status_defaults_to_local():
    response = client.get("/api/assistant/status")
    assert response.status_code == 200
    body = response.json()
    assert body["backend"] in {"local", "openrouter"}
    assert "enabled" in body


def test_assistant_answers_from_processed_data():
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


def test_assistant_requires_summary():
    response = client.post(
        "/api/assistant", json={"question": "hi", "summary": {}}
    )
    assert response.status_code == 400
