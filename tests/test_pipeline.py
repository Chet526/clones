"""End-to-end tests for the processing pipeline."""

import json

from conftest import SAMPLE_DIR

from geobrief.pipeline import process_file


def test_process_sample_file_summary():
    result = process_file(
        SAMPLE_DIR / "sample_locations.csv",
        display_timezone="America/Chicago",
    )
    summary = result.summary()

    # 10 data rows in the sample file.
    assert summary["record_counts"]["total"] == 10
    # SHA-256 hex digest is 64 chars.
    assert len(result.sha256) == 64
    assert summary["detected_columns"]["latitude"] == "latitude"
    assert summary["detected_columns"]["longitude"] == "longitude"

    # There is at least one valid and several flagged rows.
    counts = summary["record_counts"]
    assert counts["mappable"] >= 1
    assert counts["skipped_or_flagged"] >= 1

    by_status = counts["by_status"]
    assert by_status.get("missing_coordinate", 0) >= 1
    assert by_status.get("duplicate", 0) >= 1


def test_summary_json_is_valid_json():
    result = process_file(SAMPLE_DIR / "sample_locations.csv")
    parsed = json.loads(result.summary_json())
    assert parsed["product"] == "GeoBrief LE"
    assert "plain_english" in parsed


def test_geojson_only_contains_mappable_points():
    result = process_file(SAMPLE_DIR / "sample_locations.csv")
    geojson = result.geojson()
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == len(result.mappable_records)
    for feature in geojson["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        assert -180 <= lon <= 180
        assert -90 <= lat <= 90


def test_cleaned_csv_has_all_rows():
    result = process_file(SAMPLE_DIR / "sample_locations.csv")
    csv_text = result.cleaned_csv()
    # Header + 10 data rows.
    lines = [line for line in csv_text.splitlines() if line.strip()]
    assert len(lines) == 11
    assert "validation_status" in lines[0]


def test_kml_export_contains_placemark():
    result = process_file(SAMPLE_DIR / "sample_locations.csv")
    kml = result.kml()
    assert "<kml" in kml
    assert "<Placemark>" in kml


def test_processing_report_pdf_has_pdf_header():
    result = process_file(SAMPLE_DIR / "sample_locations.csv")
    pdf = result.processing_report_pdf()
    assert pdf.startswith(b"%PDF-1.4")
