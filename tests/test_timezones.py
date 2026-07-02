"""Tests for time-zone intelligence."""

from datetime import timezone

from geobrief.timezones import parse_timestamp


def test_iso_with_z_is_utc_and_certain():
    result = parse_timestamp("2024-03-01T08:15:00Z", "America/Chicago")
    assert result.utc.tzinfo == timezone.utc
    assert result.utc.hour == 8
    assert result.uncertain is False
    # Central Standard Time is UTC-6 in March (before DST) -> 02:15.
    assert result.display.hour == 2
    assert result.display_timezone == "America/Chicago"


def test_epoch_seconds_parsed_as_utc():
    # 1709295600 == 2024-03-01T12:20:00Z
    result = parse_timestamp("1709295600", "UTC")
    assert result.uncertain is False
    assert result.utc.year == 2024
    assert result.utc.hour == 12
    assert result.utc.minute == 20


def test_epoch_milliseconds_parsed():
    result = parse_timestamp("1709295600000", "UTC")
    assert result.utc.hour == 12
    assert result.utc.minute == 20


def test_naive_timestamp_is_uncertain():
    result = parse_timestamp("2024-03-01 08:15:00", "UTC")
    assert result.uncertain is True
    assert result.warning is not None
    assert result.utc.hour == 8  # assumed UTC as explicit default


def test_naive_with_assumed_source_zone_converts():
    result = parse_timestamp(
        "2024-03-01 08:15:00",
        display_timezone="UTC",
        assume_source_timezone="America/Chicago",
    )
    # 08:15 CST (UTC-6) -> 14:15 UTC
    assert result.utc.hour == 14
    assert result.uncertain is False


def test_empty_timestamp_returns_none():
    result = parse_timestamp("", "UTC")
    assert result.utc is None
    assert result.uncertain is False


def test_unparseable_timestamp_flagged():
    result = parse_timestamp("definitely not a date", "UTC")
    assert result.utc is None
    assert result.uncertain is True
