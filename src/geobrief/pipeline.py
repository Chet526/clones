"""Processing pipeline for GeoBrief LE (PRD Phase 1 / Module I).

Orchestrates the full Phase 1 flow for a single file:

    read -> hash -> detect columns -> clean/validate -> summarise -> export

and produces a cleaned CSV, a JSON processing summary, and map-ready GeoJSON.
The original file bytes are never modified.
"""

from __future__ import annotations

import io
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import pandas as pd

from .cleaning import CleaningOptions, clean_dataframe
from .detection import DetectionResult, detect_columns
from .hashing import sha256_bytes
from .ingest import read_dataframe_from_bytes
from .models import LocationRecord, ValidationStatus

__version__ = "0.1.0"


@dataclass
class ProcessingResult:
    """Everything produced by processing one source file."""

    filename: str
    sha256: str
    file_size: int
    processed_at: str
    detection: DetectionResult
    records: list[LocationRecord]
    display_timezone: str
    warnings: list[str] = field(default_factory=list)

    # --- Derived summary values -----------------------------------------
    @property
    def total_records(self) -> int:
        return len(self.records)

    @property
    def mappable_records(self) -> list[LocationRecord]:
        return [r for r in self.records if r.is_mappable]

    @property
    def valid_count(self) -> int:
        return sum(
            1
            for r in self.records
            if r.validation_status == ValidationStatus.VALID
        )

    @property
    def status_counts(self) -> dict[str, int]:
        counter = Counter(r.validation_status.value for r in self.records)
        return dict(counter)

    def time_range_utc(self) -> tuple[Optional[str], Optional[str]]:
        stamps = [
            r.normalized_timestamp_utc
            for r in self.records
            if r.normalized_timestamp_utc is not None
        ]
        if not stamps:
            return None, None
        return min(stamps), max(stamps)

    # --- Exports ---------------------------------------------------------
    def summary(self) -> dict:
        """Human/machine-readable processing summary (PRD Module I)."""
        first, last = self.time_range_utc()
        mappable = self.mappable_records
        return {
            "product": "GeoBrief LE",
            "version": __version__,
            "source_file": {
                "filename": self.filename,
                "sha256": self.sha256,
                "file_size_bytes": self.file_size,
            },
            "processed_at": self.processed_at,
            "display_timezone": self.display_timezone,
            "detected_columns": self.detection.mapping.to_dict(),
            "detection_confidence": {
                k: v.value for k, v in self.detection.confidence.items()
            },
            "record_counts": {
                "total": self.total_records,
                "valid": self.valid_count,
                "mappable": len(mappable),
                "skipped_or_flagged": self.total_records - len(mappable),
                "by_status": self.status_counts,
            },
            "time_range_utc": {"first": first, "last": last},
            "warnings": list(self.warnings) + list(self.detection.warnings),
            "plain_english": self._plain_english_summary(),
        }

    def _plain_english_summary(self) -> str:
        mappable = len(self.mappable_records)
        flagged = self.total_records - mappable
        parts = [
            f"I found {self.total_records} records. "
            f"{mappable} have usable coordinates."
        ]
        if flagged:
            parts.append(
                f"{flagged} rows had missing, invalid, or flagged location "
                "data and are listed in this report."
            )
        first, last = self.time_range_utc()
        if first and last:
            parts.append(
                f"Timestamps range from {first} to {last} (UTC), shown in "
                f"{self.display_timezone}."
            )
        return " ".join(parts)

    def summary_json(self, indent: int = 2) -> str:
        return json.dumps(self.summary(), indent=indent)

    def cleaned_dataframe(self) -> pd.DataFrame:
        """Cleaned, traceable records as a DataFrame for CSV export."""
        return pd.DataFrame([r.to_dict() for r in self.records])

    def cleaned_csv(self) -> str:
        buffer = io.StringIO()
        self.cleaned_dataframe().to_csv(buffer, index=False)
        return buffer.getvalue()

    def geojson(self) -> dict:
        """Map-ready GeoJSON FeatureCollection of mappable points."""
        features = []
        for record in self.mappable_records:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        # GeoJSON is [longitude, latitude].
                        "coordinates": [record.longitude, record.latitude],
                    },
                    "properties": {
                        "record_id": record.record_id,
                        "source_row_number": record.source_row_number,
                        "display_timestamp": record.display_timestamp,
                        "normalized_timestamp_utc": (
                            record.normalized_timestamp_utc
                        ),
                        "accuracy_radius": record.accuracy_radius,
                        "validation_status": record.validation_status.value,
                        "warnings": record.warnings,
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}


def process_dataframe(
    df: pd.DataFrame,
    *,
    filename: str,
    raw_bytes: bytes,
    display_timezone: str = "UTC",
    assume_source_timezone: Optional[str] = None,
    mapping_override=None,
) -> ProcessingResult:
    """Run detection + cleaning on an already-loaded DataFrame."""
    detection = detect_columns(df)
    mapping = mapping_override or detection.mapping

    warnings: list[str] = []
    if mapping.latitude is None or mapping.longitude is None:
        warnings.append(
            "Latitude and/or longitude columns are not mapped; no points can "
            "be plotted until they are provided."
        )

    options = CleaningOptions(
        display_timezone=display_timezone,
        assume_source_timezone=assume_source_timezone,
    )
    records = clean_dataframe(df, mapping, options)

    return ProcessingResult(
        filename=filename,
        sha256=sha256_bytes(raw_bytes),
        file_size=len(raw_bytes),
        processed_at=datetime.now(timezone.utc).isoformat(),
        detection=detection,
        records=records,
        display_timezone=display_timezone,
        warnings=warnings,
    )


def process_bytes(
    data: bytes,
    filename: str,
    *,
    display_timezone: str = "UTC",
    assume_source_timezone: Optional[str] = None,
) -> ProcessingResult:
    """Process raw uploaded bytes end to end."""
    df = read_dataframe_from_bytes(data, filename)
    return process_dataframe(
        df,
        filename=filename,
        raw_bytes=data,
        display_timezone=display_timezone,
        assume_source_timezone=assume_source_timezone,
    )


def process_file(
    path: Union[str, Path],
    *,
    display_timezone: str = "UTC",
    assume_source_timezone: Optional[str] = None,
) -> ProcessingResult:
    """Process a file from disk end to end (original file is only read)."""
    path = Path(path)
    data = path.read_bytes()
    return process_bytes(
        data,
        path.name,
        display_timezone=display_timezone,
        assume_source_timezone=assume_source_timezone,
    )
