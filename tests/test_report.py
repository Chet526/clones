"""Tests for the Basic Processing Report PDF (PRD Module I, type 1)."""

import base64
import re
import zlib

import pytest

from geobrief.pipeline import process_bytes
from geobrief.report import DISCLAIMER, build_pdf_report

CSV_DATA = b"""latitude,longitude,timestamp,accuracy
33.4484,-112.0740,2024-03-01T12:00:00Z,25
33.4500,-112.0700,2024-03-01T12:05:00Z,15
,-112.0600,2024-03-01T12:15:00Z,10
"""


@pytest.fixture()
def result():
    return process_bytes(
        CSV_DATA, "trip.csv", display_timezone="America/Chicago"
    )


def _pdf_text(pdf_bytes: bytes) -> str:
    """Extract text-ish content by decoding the PDF's content streams.

    ReportLab encodes page streams as ASCII85 + Flate by default. Decoding
    them here avoids adding a PDF-parsing dependency; content strings appear
    literally in the decoded streams.
    """
    chunks = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.S):
        data = match.group(1).strip()
        for decode in (
            lambda d: zlib.decompress(base64.a85decode(d, adobe=True)),
            zlib.decompress,
            lambda d: d,
        ):
            try:
                chunks.append(decode(data).decode("latin-1", "replace"))
                break
            except Exception:
                continue
    return "\n".join(chunks)


def test_report_is_a_pdf(result):
    pdf = build_pdf_report(result)
    assert pdf.startswith(b"%PDF-")
    assert b"%%EOF" in pdf


def test_report_includes_hash_and_filename(result):
    text = _pdf_text(build_pdf_report(result))
    assert result.sha256 in text
    assert "trip.csv" in text


def test_report_includes_timezone_statement(result):
    text = _pdf_text(build_pdf_report(result))
    assert "America/Chicago" in text
    assert "UTC" in text


def test_report_includes_disclaimer(result):
    text = _pdf_text(build_pdf_report(result))
    assert "Investigator" in text
    assert "verify" in text
    assert "verify" in DISCLAIMER


def test_report_lists_exports(result):
    text = _pdf_text(
        build_pdf_report(result, exports=["trip_cleaned.csv", "trip.kml"])
    )
    assert "trip_cleaned.csv" in text
    assert "trip.kml" in text


def test_report_handles_no_timestamps():
    data = b"lat,lon\n10.0,20.0\n"
    result = process_bytes(data, "nostamps.csv")
    pdf = build_pdf_report(result)
    assert pdf.startswith(b"%PDF-")
    assert "None found" in _pdf_text(pdf)
