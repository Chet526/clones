"""Tests for the case workspace and audit log (PRD Modules A and J)."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from geobrief.hashing import sha256_bytes
from geobrief.store import CaseStore
from geobrief.webapp.app import app

CSV_DATA = b"lat,lon,time\n33.4,-112.0,2024-03-01T12:00:00Z\n"


@pytest.fixture()
def store(tmp_path):
    with CaseStore(tmp_path / "home") as s:
        yield s


def test_create_and_list_cases(store):
    case = store.create_case(
        "24-001",
        agency="Test PD",
        investigator="Det. Smith",
        offense_type="Theft",
    )
    assert case["case_id"] == 1
    assert case["case_number"] == "24-001"
    assert case["status"] == "open"
    assert [c["case_id"] for c in store.list_cases()] == [1]


def test_case_number_is_required(store):
    with pytest.raises(ValueError):
        store.create_case("   ")


def test_get_unknown_case_raises(store):
    with pytest.raises(KeyError):
        store.get_case(99)


def test_source_file_is_preserved_byte_for_byte(store):
    case = store.create_case("24-002")
    record = store.add_source_file(case["case_id"], "trip.csv", CSV_DATA)
    assert record["sha256_hash"] == sha256_bytes(CSV_DATA)
    assert record["file_size"] == len(CSV_DATA)
    stored = open(record["storage_path"], "rb").read()
    assert stored == CSV_DATA


def test_source_file_import_is_audited(store):
    case = store.create_case("24-003")
    store.add_source_file(case["case_id"], "trip.csv", CSV_DATA)
    events = [e["event_type"] for e in store.audit_log(case["case_id"])]
    assert events == ["case_created", "file_imported", "file_hashed"]


def test_exports_are_recorded_and_audited(store):
    case = store.create_case("24-004")
    export = store.record_export(case["case_id"], "kml", "trip.kml")
    assert export["export_type"] == "kml"
    assert store.list_exports(case["case_id"])[0]["filename"] == "trip.kml"
    events = [e["event_type"] for e in store.audit_log(case["case_id"])]
    assert "export_generated" in events


def test_audit_chain_verifies_when_untouched(store):
    case = store.create_case("24-005")
    store.add_source_file(case["case_id"], "trip.csv", CSV_DATA)
    store.record_export(case["case_id"], "kml", "trip.kml")
    assert store.verify_audit_chain(case["case_id"]) is True


def test_audit_chain_detects_tampering(tmp_path):
    home = tmp_path / "home"
    with CaseStore(home) as store:
        case = store.create_case("24-006")
        store.add_source_file(case["case_id"], "trip.csv", CSV_DATA)
        case_id = case["case_id"]

    # Tamper with an event outside the normal API.
    conn = sqlite3.connect(str(home / "geobrief.db"))
    conn.execute(
        "UPDATE audit_events SET event_details = '{\"filename\": \"fake\"}' "
        "WHERE event_type = 'file_imported'"
    )
    conn.commit()
    conn.close()

    with CaseStore(home) as store:
        assert store.verify_audit_chain(case_id) is False


def test_web_case_endpoints_roundtrip():
    client = TestClient(app)
    created = client.post(
        "/api/cases",
        json={"case_number": "24-100", "investigator": "Det. Jones"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    listed = client.get("/api/cases").json()["cases"]
    assert [c["case_id"] for c in listed] == [case_id]

    processed = client.post(
        "/api/process",
        files={"file": ("trip.csv", CSV_DATA, "text/csv")},
        data={"display_timezone": "UTC", "case_id": str(case_id)},
    )
    assert processed.status_code == 200
    assert processed.json()["case_id"] == case_id

    detail = client.get(f"/api/cases/{case_id}").json()
    assert len(detail["source_files"]) == 1
    assert detail["source_files"][0]["original_filename"] == "trip.csv"
    assert len(detail["exports"]) == 4

    audit = client.get(f"/api/cases/{case_id}/audit").json()
    assert audit["chain_intact"] is True
    types = [e["event_type"] for e in audit["events"]]
    assert "case_created" in types
    assert "file_processed" in types


def test_web_process_with_unknown_case_is_404():
    client = TestClient(app)
    response = client.post(
        "/api/process",
        files={"file": ("trip.csv", CSV_DATA, "text/csv")},
        data={"case_id": "42"},
    )
    assert response.status_code == 404


def test_web_case_number_required():
    client = TestClient(app)
    response = client.post("/api/cases", json={"case_number": "  "})
    assert response.status_code == 400


def test_cli_case_create_list_audit(capsys):
    from geobrief.__main__ import main

    assert main(["case", "create", "--number", "24-200"]) == 0
    assert main(["case", "list"]) == 0
    out = capsys.readouterr().out
    assert "24-200" in out
    assert main(["case", "audit", "1"]) == 0
    out = capsys.readouterr().out
    assert "case_created" in out
    assert "intact" in out


def test_cli_process_with_case(tmp_path, capsys):
    from geobrief.__main__ import main

    source = tmp_path / "trip.csv"
    source.write_bytes(CSV_DATA)
    assert main(["case", "create", "--number", "24-300"]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "process",
                str(source),
                "--out",
                str(tmp_path / "out"),
                "--case",
                "1",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Recorded in case 1." in out

    with CaseStore() as store:
        files = store.list_source_files(1)
        assert [f["original_filename"] for f in files] == ["trip.csv"]
        assert len(store.list_exports(1)) == 5
        assert store.verify_audit_chain(1) is True
