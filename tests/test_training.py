"""Tests for training mode (PRD Module N)."""

import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

from geobrief.kml import build_kml
from geobrief.pipeline import process_bytes
from geobrief.report import build_pdf_report
from geobrief.training import TRAINING_NOTICE, training_sample_bytes
from geobrief.webapp.app import app

CSV_DATA = b"lat,lon,time\n33.4,-112.0,2024-03-01T12:00:00Z\n"


def test_training_sample_is_bundled_and_readable():
    data = training_sample_bytes()
    result = process_bytes(data, "training_sample.csv", training=True)
    assert result.total_records > 0
    assert result.training_mode is True


def test_summary_carries_training_watermark():
    result = process_bytes(CSV_DATA, "trip.csv", training=True)
    summary = result.summary()
    assert summary["training_mode"] is True
    assert summary["plain_english"].startswith("TRAINING MODE")


def test_summary_defaults_to_non_training():
    result = process_bytes(CSV_DATA, "trip.csv")
    summary = result.summary()
    assert summary["training_mode"] is False
    assert "TRAINING" not in summary["plain_english"]


def test_kml_is_watermarked_in_training_mode():
    result = process_bytes(CSV_DATA, "trip.csv", training=True)
    kml = build_kml(result)
    ET.fromstring(kml)  # still well-formed
    assert TRAINING_NOTICE in kml
    assert "TRAINING — GeoBrief LE" in kml


def test_pdf_is_watermarked_in_training_mode():
    import base64
    import re
    import zlib

    result = process_bytes(CSV_DATA, "trip.csv", training=True)
    pdf = build_pdf_report(result)
    assert pdf.startswith(b"%PDF-")
    chunks = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        data = match.group(1).strip()
        try:
            chunks.append(
                zlib.decompress(base64.a85decode(data, adobe=True)).decode(
                    "latin-1", "replace"
                )
            )
        except Exception:
            continue
    assert "TRAINING MODE" in "\n".join(chunks)


def test_web_training_sample_endpoint():
    client = TestClient(app)
    response = client.get("/api/training/sample")
    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "training_sample.csv"
    assert "latitude" in body["csv"]


def test_web_process_accepts_training_flag():
    client = TestClient(app)
    response = client.post(
        "/api/process",
        files={"file": ("trip.csv", CSV_DATA, "text/csv")},
        data={"training": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["training_mode"] is True
    assert TRAINING_NOTICE in body["kml"]


def test_cli_training_flag(tmp_path, capsys):
    from geobrief.__main__ import main

    source = tmp_path / "trip.csv"
    source.write_bytes(CSV_DATA)
    assert (
        main(
            ["process", str(source), "--out", str(tmp_path / "out"), "--training"]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "TRAINING MODE" in out
    kml = (tmp_path / "out" / "trip.kml").read_text(encoding="utf-8")
    assert TRAINING_NOTICE in kml
