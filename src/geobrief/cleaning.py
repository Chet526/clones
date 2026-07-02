"""Data cleaning and validation engine for GeoBrief LE (PRD Module D).

Converts messy source rows into consistent ``LocationRecord`` objects. Core
guarantees:

* Original values are preserved on every record.
* Cleaned data is traceable to the original source row number.
* Bad rows are flagged, never silently deleted.
* Warnings are attached to records so they can surface in the report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .models import ColumnMapping, LocationRecord, ValidationStatus
from .timezones import isoformat, parse_timestamp

# A point whose accuracy radius exceeds this many metres is "low accuracy"
# and shows a general area rather than an exact location (PRD Module F).
DEFAULT_LOW_ACCURACY_METERS = 1000.0


@dataclass
class CleaningOptions:
    display_timezone: str = "UTC"
    assume_source_timezone: Optional[str] = None
    low_accuracy_meters: float = DEFAULT_LOW_ACCURACY_METERS


def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _valid_lat(value: Optional[float]) -> bool:
    return value is not None and -90.0 <= value <= 90.0


def _valid_lon(value: Optional[float]) -> bool:
    return value is not None and -180.0 <= value <= 180.0


def clean_dataframe(
    df: pd.DataFrame,
    mapping: ColumnMapping,
    options: Optional[CleaningOptions] = None,
) -> list[LocationRecord]:
    """Clean a DataFrame into a list of validated ``LocationRecord``s."""
    options = options or CleaningOptions()
    records: list[LocationRecord] = []
    seen: dict[tuple, int] = {}

    for position, (_, row) in enumerate(df.iterrows()):
        source_row_number = position + 2  # +1 for header, +1 for 1-based

        raw_lat = (
            row[mapping.latitude] if mapping.latitude in df.columns else None
        )
        raw_lon = (
            row[mapping.longitude]
            if mapping.longitude in df.columns
            else None
        )
        raw_time = (
            row[mapping.timestamp]
            if mapping.timestamp and mapping.timestamp in df.columns
            else None
        )
        raw_acc = (
            row[mapping.accuracy]
            if mapping.accuracy and mapping.accuracy in df.columns
            else None
        )

        record = LocationRecord(
            record_id=position + 1,
            source_row_number=source_row_number,
            original_timestamp=None if raw_time is None else str(raw_time),
            original_latitude=None if raw_lat is None else str(raw_lat),
            original_longitude=None if raw_lon is None else str(raw_lon),
        )

        lat = _to_float(raw_lat)
        lon = _to_float(raw_lon)
        accuracy = _to_float(raw_acc)
        record.accuracy_radius = accuracy

        # --- Timestamp handling -----------------------------------------
        parsed = parse_timestamp(
            record.original_timestamp,
            display_timezone=options.display_timezone,
            assume_source_timezone=options.assume_source_timezone,
        )
        record.normalized_timestamp_utc = isoformat(parsed.utc)
        record.display_timestamp = isoformat(parsed.display)
        record.display_timezone = parsed.display_timezone
        if parsed.warning:
            record.warnings.append(parsed.warning)

        # --- Coordinate validation --------------------------------------
        has_lat_text = record.original_latitude not in (None, "")
        has_lon_text = record.original_longitude not in (None, "")

        if not has_lat_text or not has_lon_text:
            record.validation_status = ValidationStatus.MISSING_COORDINATE
            record.warnings.append("Missing latitude or longitude.")
            records.append(record)
            continue

        if lat is None or lon is None:
            record.validation_status = ValidationStatus.INVALID_COORDINATE
            record.warnings.append(
                "Latitude/longitude are not valid numbers."
            )
            records.append(record)
            continue

        lat_ok = _valid_lat(lat)
        lon_ok = _valid_lon(lon)
        reversed_flag = False

        if not lat_ok or not lon_ok:
            # Detect a likely lat/lon reversal: values are out of range for
            # their column but would be valid if swapped.
            if _valid_lat(lon) and _valid_lon(lat) and (not lat_ok):
                record.latitude = lon
                record.longitude = lat
                reversed_flag = True
                record.warnings.append(
                    "Latitude and longitude look reversed; swapped values "
                    "for mapping. Please confirm."
                )
            else:
                record.latitude = lat
                record.longitude = lon
                record.validation_status = (
                    ValidationStatus.INVALID_COORDINATE
                )
                record.warnings.append(
                    "Coordinates are outside the valid range."
                )
                records.append(record)
                continue
        else:
            record.latitude = lat
            record.longitude = lon

        # --- Duplicate detection ----------------------------------------
        key = (
            round(record.latitude, 6),
            round(record.longitude, 6),
            record.normalized_timestamp_utc,
        )
        if key in seen:
            record.validation_status = ValidationStatus.DUPLICATE
            record.warnings.append(
                f"Duplicate of record #{seen[key]} (same time and place)."
            )
            records.append(record)
            continue
        seen[key] = record.record_id

        # --- Quality classification -------------------------------------
        # Add timestamp/accuracy warnings, but never let them overwrite a
        # coordinate-level flag such as a suspected lat/lon reversal.
        if record.normalized_timestamp_utc is None:
            record.warnings.append(
                "No usable timestamp; point maps without time features."
            )
            if not reversed_flag:
                record.validation_status = (
                    ValidationStatus.MISSING_TIMESTAMP
                )
        elif parsed.uncertain and not reversed_flag:
            record.validation_status = ValidationStatus.TIMEZONE_UNCERTAIN
        elif (
            accuracy is not None
            and accuracy > options.low_accuracy_meters
        ):
            record.warnings.append(
                "Large accuracy radius; this shows a general area, not an "
                "exact location."
            )
            if not reversed_flag:
                record.validation_status = ValidationStatus.LOW_ACCURACY

        if reversed_flag:
            record.validation_status = (
                ValidationStatus.POSSIBLE_LATLON_REVERSAL
            )

        records.append(record)

    return records
