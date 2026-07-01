"""Internal data models for GeoBrief LE (PRD Module D / Section 13).

These are intentionally lightweight dataclasses/enums so the Phase 1
prototype has no database dependency. Every processed point keeps a link
back to its original source row so nothing is ever silently lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ValidationStatus(str, Enum):
    """Validation outcomes for a single location record (PRD Module D)."""

    VALID = "valid"
    MISSING_COORDINATE = "missing_coordinate"
    MISSING_TIMESTAMP = "missing_timestamp"
    INVALID_COORDINATE = "invalid_coordinate"
    LOW_ACCURACY = "low_accuracy"
    DUPLICATE = "duplicate"
    TIMEZONE_UNCERTAIN = "timezone_uncertain"
    POSSIBLE_LATLON_REVERSAL = "possible_latlon_reversal"
    EXCLUDED_FROM_MAP = "excluded_from_map"


# Statuses that mean the point should not be plotted on the map.
NON_MAPPABLE_STATUSES = frozenset(
    {
        ValidationStatus.MISSING_COORDINATE,
        ValidationStatus.INVALID_COORDINATE,
        ValidationStatus.DUPLICATE,
        ValidationStatus.EXCLUDED_FROM_MAP,
    }
)


@dataclass
class LocationRecord:
    """A single cleaned location record traceable to its source row."""

    record_id: int
    source_row_number: int
    # Original, untouched values as read from the file.
    original_timestamp: Optional[str] = None
    original_latitude: Optional[str] = None
    original_longitude: Optional[str] = None
    # Normalised values produced by the cleaning engine.
    normalized_timestamp_utc: Optional[str] = None
    display_timestamp: Optional[str] = None
    display_timezone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy_radius: Optional[float] = None
    # Validation output.
    validation_status: ValidationStatus = ValidationStatus.VALID
    warnings: list[str] = field(default_factory=list)

    @property
    def is_mappable(self) -> bool:
        """True if this record has coordinates safe to plot on a map."""
        return (
            self.latitude is not None
            and self.longitude is not None
            and self.validation_status not in NON_MAPPABLE_STATUSES
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "source_row_number": self.source_row_number,
            "original_timestamp": self.original_timestamp,
            "original_latitude": self.original_latitude,
            "original_longitude": self.original_longitude,
            "normalized_timestamp_utc": self.normalized_timestamp_utc,
            "display_timestamp": self.display_timestamp,
            "display_timezone": self.display_timezone,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy_radius": self.accuracy_radius,
            "validation_status": self.validation_status.value,
            "warnings": list(self.warnings),
            "is_mappable": self.is_mappable,
        }


@dataclass
class ColumnMapping:
    """Which source columns were used for each detected field."""

    latitude: Optional[str] = None
    longitude: Optional[str] = None
    timestamp: Optional[str] = None
    accuracy: Optional[str] = None

    def to_dict(self) -> dict[str, Optional[str]]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timestamp": self.timestamp,
            "accuracy": self.accuracy,
        }
