"""Tests for column detection."""

import pandas as pd

from geobrief.detection import Confidence, detect_columns


def test_detects_standard_headers():
    df = pd.DataFrame(
        {
            "latitude": ["41.88", "41.89"],
            "longitude": ["-87.62", "-87.63"],
            "timestamp": ["2024-03-01T08:00:00Z", "2024-03-01T09:00:00Z"],
            "accuracy_m": ["10", "20"],
        }
    )
    result = detect_columns(df)
    assert result.mapping.latitude == "latitude"
    assert result.mapping.longitude == "longitude"
    assert result.mapping.timestamp == "timestamp"
    assert result.mapping.accuracy == "accuracy_m"
    assert result.confidence["latitude"] == Confidence.HIGH
    assert result.confidence["longitude"] == Confidence.HIGH


def test_detects_abbreviated_headers():
    df = pd.DataFrame(
        {
            "lat": ["41.88", "41.89"],
            "lng": ["-87.62", "-87.63"],
            "event_time": ["2024-03-01T08:00:00Z", "2024-03-01T09:00:00Z"],
        }
    )
    result = detect_columns(df)
    assert result.mapping.latitude == "lat"
    assert result.mapping.longitude == "lng"
    assert result.mapping.timestamp == "event_time"


def test_detects_by_content_when_headers_unhelpful():
    df = pd.DataFrame(
        {
            "col_a": ["41.88", "41.89", "41.90"],
            "col_b": ["-87.62", "-87.63", "-87.64"],
            "col_c": ["x", "y", "z"],
        }
    )
    result = detect_columns(df)
    # Column A holds values only valid as latitude/longitude; B is broader.
    assert result.mapping.latitude in {"col_a", "col_b"}
    assert result.mapping.longitude in {"col_a", "col_b"}
    assert result.mapping.latitude != result.mapping.longitude


def test_missing_coordinates_produce_warning():
    df = pd.DataFrame({"name": ["a"], "note": ["b"]})
    result = detect_columns(df)
    assert result.mapping.latitude is None
    assert result.confidence["latitude"] == Confidence.UNKNOWN
    assert any("latitude" in w for w in result.warnings)
