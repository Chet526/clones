"""Time-zone intelligence for GeoBrief LE (PRD Module E).

Timestamp handling is one of the most important parts of the product, so
this module is deliberately conservative:

* The original timestamp string is always preserved by the caller.
* Values are parsed into a normalized UTC instant.
* A separate display timestamp is produced in the chosen display zone.
* When the source zone cannot be determined with confidence, the record is
  flagged as time-zone uncertain rather than silently guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import parser as date_parser

_EPOCH_RE = re.compile(r"^-?\d{9,13}$")
# An explicit offset or Z/UTC marker means the instant is unambiguous.
_HAS_OFFSET_RE = re.compile(r"(?:[zZ]|[+-]\d{2}:?\d{2})\s*$")
_HAS_UTC_WORD_RE = re.compile(r"\b(utc|gmt|zulu)\b", re.IGNORECASE)


@dataclass
class ParsedTimestamp:
    """Outcome of parsing a single timestamp value."""

    utc: Optional[datetime]
    display: Optional[datetime]
    display_timezone: str
    uncertain: bool
    warning: Optional[str] = None


def _parse_epoch(text: str) -> Optional[datetime]:
    """Parse a Unix epoch value in seconds or milliseconds."""
    try:
        number = int(text)
    except ValueError:
        return None
    # 13 digits -> milliseconds; 10 digits -> seconds.
    if abs(number) >= 10**12:
        number = number / 1000.0
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def resolve_display_zone(name: Optional[str]) -> ZoneInfo:
    """Resolve a display time-zone name, defaulting to UTC when unknown."""
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo("UTC")


def parse_timestamp(
    raw: Optional[str],
    display_timezone: str = "UTC",
    assume_source_timezone: Optional[str] = None,
) -> ParsedTimestamp:
    """Parse a raw timestamp string into UTC + display representations.

    Parameters
    ----------
    raw:
        The original timestamp text from the source row.
    display_timezone:
        IANA zone name the investigator wants to *see* times in.
    assume_source_timezone:
        Optional IANA zone to assume when the source value is naive (no
        offset). When ``None`` and the value is naive, the result is marked
        uncertain and UTC is assumed as a safe, explicit default.
    """
    display_zone = resolve_display_zone(display_timezone)

    if raw is None or str(raw).strip() == "":
        return ParsedTimestamp(
            utc=None,
            display=None,
            display_timezone=display_timezone,
            uncertain=False,
            warning="Missing timestamp.",
        )

    text = str(raw).strip()

    # Epoch integers are always UTC by definition — unambiguous.
    if _EPOCH_RE.match(text):
        dt_utc = _parse_epoch(text)
        if dt_utc is None:
            return ParsedTimestamp(
                None, None, display_timezone, True, "Unparseable epoch value."
            )
        return ParsedTimestamp(
            utc=dt_utc,
            display=dt_utc.astimezone(display_zone),
            display_timezone=display_timezone,
            uncertain=False,
        )

    try:
        parsed = date_parser.parse(text)
    except (ValueError, OverflowError, TypeError):
        return ParsedTimestamp(
            utc=None,
            display=None,
            display_timezone=display_timezone,
            uncertain=True,
            warning=f"Could not understand timestamp '{text}'.",
        )

    uncertain = False
    warning: Optional[str] = None

    if parsed.tzinfo is not None:
        # Value carried an explicit offset/zone — unambiguous instant.
        dt_utc = parsed.astimezone(timezone.utc)
    else:
        has_marker = bool(
            _HAS_OFFSET_RE.search(text) or _HAS_UTC_WORD_RE.search(text)
        )
        if assume_source_timezone:
            source_zone = resolve_display_zone(assume_source_timezone)
            dt_utc = parsed.replace(tzinfo=source_zone).astimezone(
                timezone.utc
            )
        elif has_marker:
            dt_utc = parsed.replace(tzinfo=timezone.utc)
        else:
            # Naive value and no guidance: assume UTC but flag as uncertain
            # so the investigator confirms rather than trusting a guess.
            dt_utc = parsed.replace(tzinfo=timezone.utc)
            uncertain = True
            warning = (
                "Timestamp had no time-zone information; assumed UTC. "
                "Please confirm the source time zone."
            )

    return ParsedTimestamp(
        utc=dt_utc,
        display=dt_utc.astimezone(display_zone),
        display_timezone=display_timezone,
        uncertain=uncertain,
        warning=warning,
    )


def isoformat(dt: Optional[datetime]) -> Optional[str]:
    """ISO-8601 string for a datetime, or ``None``."""
    return dt.isoformat() if dt is not None else None
