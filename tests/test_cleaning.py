"""Tests for the cleaning and validation engine."""

import pandas as pd

from geobrief.cleaning import CleaningOptions, clean_dataframe
from geobrief.models import ColumnMapping, ValidationStatus

MAPPING = ColumnMapping(
    latitude="lat",
    longitude="lon",
    timestamp="ts",
    accuracy="acc",
)


def _clean(rows, **kwargs):
    df = pd.DataFrame(rows, dtype=str).fillna("")
    return clean_dataframe(df, MAPPING, CleaningOptions(**kwargs))


def test_valid_row_is_valid_and_mappable():
    records = _clean(
        [{"lat": "41.88", "lon": "-87.62", "ts": "2024-03-01T08:00:00Z", "acc": "10"}]
    )
    assert records[0].validation_status == ValidationStatus.VALID
    assert records[0].is_mappable
    assert records[0].latitude == 41.88
    assert records[0].longitude == -87.62


def test_missing_coordinate_flagged_not_deleted():
    records = _clean([{"lat": "", "lon": "", "ts": "2024-03-01T08:00:00Z", "acc": ""}])
    assert len(records) == 1
    assert records[0].validation_status == ValidationStatus.MISSING_COORDINATE
    assert not records[0].is_mappable


def test_invalid_coordinate_flagged():
    records = _clean([{"lat": "not_a_number", "lon": "-87.6", "ts": "", "acc": ""}])
    assert records[0].validation_status == ValidationStatus.INVALID_COORDINATE
    assert not records[0].is_mappable


def test_out_of_range_without_swap_is_invalid():
    records = _clean([{"lat": "200", "lon": "-87.6", "ts": "", "acc": ""}])
    assert records[0].validation_status == ValidationStatus.INVALID_COORDINATE


def test_latlon_reversal_detected_and_swapped():
    # lat=-120.5 is out of latitude range but valid as longitude; lon=41.88
    # is valid as a latitude -> a likely reversal that can be swapped.
    records = _clean([{"lat": "-120.5", "lon": "41.88", "ts": "", "acc": ""}])
    rec = records[0]
    assert rec.validation_status == ValidationStatus.POSSIBLE_LATLON_REVERSAL
    assert rec.latitude == 41.88
    assert rec.longitude == -120.5
    assert rec.is_mappable


def test_duplicate_detected():
    rows = [
        {"lat": "41.88", "lon": "-87.62", "ts": "2024-03-01T08:00:00Z", "acc": "10"},
        {"lat": "41.88", "lon": "-87.62", "ts": "2024-03-01T08:00:00Z", "acc": "10"},
    ]
    records = _clean(rows)
    assert records[0].validation_status == ValidationStatus.VALID
    assert records[1].validation_status == ValidationStatus.DUPLICATE
    assert not records[1].is_mappable


def test_low_accuracy_flagged():
    records = _clean(
        [{"lat": "41.88", "lon": "-87.62", "ts": "2024-03-01T08:00:00Z", "acc": "5000"}],
        low_accuracy_meters=1000,
    )
    assert records[0].validation_status == ValidationStatus.LOW_ACCURACY
    assert records[0].is_mappable  # still plotted, just flagged


def test_missing_timestamp_still_mappable():
    records = _clean([{"lat": "41.88", "lon": "-87.62", "ts": "", "acc": "10"}])
    assert records[0].validation_status == ValidationStatus.MISSING_TIMESTAMP
    assert records[0].is_mappable


def test_original_values_preserved():
    records = _clean(
        [{"lat": " 41.88 ", "lon": "-87.62", "ts": "2024-03-01T08:00:00Z", "acc": "10"}]
    )
    assert records[0].original_latitude == " 41.88 "
    assert records[0].latitude == 41.88
