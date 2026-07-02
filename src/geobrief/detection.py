"""Column detection for GeoBrief LE (PRD Module B).

Given a raw string DataFrame, work out which columns most likely hold the
latitude, longitude, timestamp and accuracy-radius values. Detection uses
two signals:

1. Header-name hints (e.g. a column called "lat" is probably latitude).
2. Value content (does the column actually parse as coordinates/dates?).

Both signals are combined into a confidence level so the wizard can decide
whether to auto-proceed or ask the user to confirm (PRD Module C / K).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd
from dateutil import parser as date_parser

from .models import ColumnMapping

# Header-name hints. Ordered by specificity so more specific names win.
_LAT_HINTS = ("latitude", "lat", "lat_wgs84", "y")
_LON_HINTS = ("longitude", "long", "lon", "lng", "lon_wgs84", "x")
_TIME_HINTS = (
    "timestamp",
    "datetime",
    "date_time",
    "date/time",
    "time",
    "date",
    "event_time",
    "utc",
    "occurred_at",
    "captured_at",
)
_ACC_HINTS = (
    "accuracy",
    "accuracy_radius",
    "acc",
    "radius",
    "uncertainty",
    "horizontal_accuracy",
    "hdop",
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass
class DetectionResult:
    mapping: ColumnMapping
    confidence: dict[str, Confidence]
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "mapping": self.mapping.to_dict(),
            "confidence": {k: v.value for k, v in self.confidence.items()},
            "warnings": list(self.warnings),
        }


def _normalize_header(name: str) -> str:
    return _NON_ALNUM.sub("_", str(name).strip().lower()).strip("_")


def _header_score(normalized: str, hints: tuple[str, ...]) -> float:
    """Score how well a normalized header matches a set of hints."""
    for index, hint in enumerate(hints):
        if normalized == hint:
            # Exact match: best hints score highest.
            return 1.0 - index * 0.02
    for index, hint in enumerate(hints):
        # Word-boundary-ish containment, e.g. "device_lat" contains "lat".
        if hint in normalized.split("_") or normalized.endswith("_" + hint):
            return 0.7 - index * 0.02
    return 0.0


def _numeric_fraction(series: pd.Series, lo: float, hi: float) -> float:
    """Fraction of non-empty values that parse as floats within [lo, hi]."""
    values = [v for v in series if str(v).strip() != ""]
    if not values:
        return 0.0
    ok = 0
    for value in values:
        try:
            num = float(str(value).strip())
        except (TypeError, ValueError):
            continue
        if lo <= num <= hi:
            ok += 1
    return ok / len(values)


def _datetime_fraction(series: pd.Series, sample: int = 50) -> float:
    """Fraction of a sample of non-empty values that parse as dates."""
    values = [v for v in series if str(v).strip() != ""][:sample]
    if not values:
        return 0.0
    ok = 0
    for value in values:
        text = str(value).strip()
        try:
            # Pure integers are treated as possible epoch timestamps.
            if re.fullmatch(r"-?\d{9,13}", text):
                ok += 1
                continue
            date_parser.parse(text)
            ok += 1
        except (ValueError, OverflowError, TypeError):
            continue
    return ok / len(values)


def _combine(header: float, content: float) -> Confidence:
    score = 0.6 * header + 0.4 * content
    if header > 0 and content >= 0.6:
        return Confidence.HIGH
    if score >= 0.5:
        return Confidence.MEDIUM
    if score > 0:
        return Confidence.LOW
    return Confidence.UNKNOWN


def _best_column(
    df: pd.DataFrame,
    hints: tuple[str, ...],
    content_fn,
    exclude: Optional[set[str]] = None,
) -> tuple[Optional[str], float, float]:
    """Pick the column that best matches the hints + content function."""
    exclude = exclude or set()
    best_col: Optional[str] = None
    best_total = 0.0
    best_header = 0.0
    best_content = 0.0
    for col in df.columns:
        if col in exclude:
            continue
        header = _header_score(_normalize_header(col), hints)
        content = content_fn(df[col])
        total = 0.6 * header + 0.4 * content
        if total > best_total:
            best_total = total
            best_col = col
            best_header = header
            best_content = content
    return best_col, best_header, best_content


def detect_columns(df: pd.DataFrame) -> DetectionResult:
    """Detect coordinate, timestamp and accuracy columns in a DataFrame."""
    warnings: list[str] = []
    confidence: dict[str, Confidence] = {}

    def lat_content(s):
        return _numeric_fraction(s, -90, 90)

    def lon_content(s):
        return _numeric_fraction(s, -180, 180)

    lat_col, lat_h, lat_c = _best_column(df, _LAT_HINTS, lat_content)
    lon_col, lon_h, lon_c = _best_column(df, _LON_HINTS, lon_content)

    # Avoid picking the same column for both latitude and longitude. Keep the
    # one with the stronger header hint and re-pick the other from remaining
    # columns so two distinct coordinate columns are chosen.
    if lat_col is not None and lat_col == lon_col:
        if lon_h > lat_h:
            lon_col_kept = lon_col
            lat_col, lat_h, lat_c = _best_column(
                df, _LAT_HINTS, lat_content, exclude={lon_col_kept}
            )
        else:
            lat_col_kept = lat_col
            lon_col, lon_h, lon_c = _best_column(
                df, _LON_HINTS, lon_content, exclude={lat_col_kept}
            )
        warnings.append(
            "Latitude and longitude were hard to tell apart; please confirm "
            "the correct columns."
        )

    time_col, time_h, time_c = _best_column(df, _TIME_HINTS, _datetime_fraction)
    acc_col, acc_h, acc_c = _best_column(
        df, _ACC_HINTS, lambda s: _numeric_fraction(s, 0, 1_000_000)
    )

    confidence["latitude"] = (
        _combine(lat_h, lat_c) if lat_col else Confidence.UNKNOWN
    )
    confidence["longitude"] = (
        _combine(lon_h, lon_c) if lon_col else Confidence.UNKNOWN
    )
    confidence["timestamp"] = (
        _combine(time_h, time_c) if time_col else Confidence.UNKNOWN
    )
    confidence["accuracy"] = (
        _combine(acc_h, acc_c) if acc_col else Confidence.UNKNOWN
    )

    for field_name, col in (
        ("latitude", lat_col),
        ("longitude", lon_col),
    ):
        if col is None:
            warnings.append(
                f"Could not confidently find a {field_name} column. "
                "Please map it manually."
            )
    if time_col is None:
        warnings.append(
            "Could not find a date/time column. Points will map without "
            "time-based features until you map one."
        )

    mapping = ColumnMapping(
        latitude=lat_col,
        longitude=lon_col,
        timestamp=time_col,
        accuracy=acc_col,
    )
    return DetectionResult(
        mapping=mapping, confidence=confidence, warnings=warnings
    )
