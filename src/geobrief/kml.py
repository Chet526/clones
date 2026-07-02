"""Google Earth KML/KMZ export for GeoBrief LE (PRD Module H).

Builds an original, plain KML document from a :class:`ProcessingResult`:

- a "Location points" folder with one placemark per mappable record,
  including timestamps, source row, coordinates, accuracy, and warnings;
- an "Accuracy circles" folder approximating each accuracy radius;
- a "Movement path" folder with a chronological path line;
- document-level export metadata (source file, SHA-256, counts,
  time-zone statement).

Only the Python standard library is used. KMZ is simply the KML document
zipped as ``doc.kml``.
"""

from __future__ import annotations

import io
import math
import zipfile
from typing import TYPE_CHECKING, Optional
from xml.sax.saxutils import escape

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .models import LocationRecord
    from .pipeline import ProcessingResult

EARTH_RADIUS_M = 6_371_000.0
CIRCLE_SEGMENTS = 36

_STYLES = """\
  <Style id="pointStyle">
    <IconStyle>
      <color>ff2f6fdd</color>
      <scale>1.0</scale>
      <Icon>
        <href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href>
      </Icon>
    </IconStyle>
    <LabelStyle><scale>0.7</scale></LabelStyle>
  </Style>
  <Style id="flaggedPointStyle">
    <IconStyle>
      <color>ff2f2fdd</color>
      <scale>1.0</scale>
      <Icon>
        <href>http://maps.google.com/mapfiles/kml/shapes/caution.png</href>
      </Icon>
    </IconStyle>
    <LabelStyle><scale>0.7</scale></LabelStyle>
  </Style>
  <Style id="pathStyle">
    <LineStyle>
      <color>b3dd6f2f</color>
      <width>3</width>
    </LineStyle>
  </Style>
  <Style id="accuracyStyle">
    <LineStyle>
      <color>802f6fdd</color>
      <width>1</width>
    </LineStyle>
    <PolyStyle>
      <color>262f6fdd</color>
    </PolyStyle>
  </Style>"""


def _circle_coordinates(
    latitude: float,
    longitude: float,
    radius_m: float,
    segments: int = CIRCLE_SEGMENTS,
) -> str:
    """Approximate a circle on the ground as a KML coordinate ring."""
    lat_rad = math.radians(latitude)
    d_lat = math.degrees(radius_m / EARTH_RADIUS_M)
    # Guard against division blow-up near the poles.
    cos_lat = max(math.cos(lat_rad), 1e-6)
    d_lon = d_lat / cos_lat

    points = []
    for i in range(segments + 1):  # +1 closes the ring
        angle = 2.0 * math.pi * i / segments
        lat_i = latitude + d_lat * math.sin(angle)
        lon_i = longitude + d_lon * math.cos(angle)
        points.append(f"{lon_i:.7f},{lat_i:.7f},0")
    return " ".join(points)


def _record_description(record: "LocationRecord", filename: str) -> str:
    """Plain-language placemark description (PRD Module F popup fields)."""
    rows = [
        ("Original time", record.original_timestamp),
        ("Time (UTC)", record.normalized_timestamp_utc),
        (
            f"Time ({record.display_timezone})"
            if record.display_timezone
            else "Displayed time",
            record.display_timestamp,
        ),
        ("Source file", filename),
        ("Source row", str(record.source_row_number)),
        (
            "Coordinates",
            f"{record.latitude}, {record.longitude}"
            if record.latitude is not None and record.longitude is not None
            else None,
        ),
        (
            "Accuracy radius",
            f"{record.accuracy_radius} m"
            if record.accuracy_radius is not None
            else None,
        ),
        ("Validation", record.validation_status.value),
    ]
    lines = [
        f"{escape(label)}: {escape(str(value))}"
        for label, value in rows
        if value is not None
    ]
    for warning in record.warnings:
        lines.append(f"Warning: {escape(warning)}")
    return "<br/>".join(lines)


def _timestamp_element(record: "LocationRecord") -> str:
    if not record.normalized_timestamp_utc:
        return ""
    when = escape(record.normalized_timestamp_utc)
    return f"<TimeStamp><when>{when}</when></TimeStamp>"


def _point_placemark(record: "LocationRecord", filename: str) -> str:
    from .models import ValidationStatus

    name = (
        record.display_timestamp
        or record.normalized_timestamp_utc
        or f"Row {record.source_row_number}"
    )
    style = (
        "#pointStyle"
        if record.validation_status == ValidationStatus.VALID
        else "#flaggedPointStyle"
    )
    return (
        "      <Placemark>\n"
        f"        <name>{escape(name)}</name>\n"
        f"        <styleUrl>{style}</styleUrl>\n"
        f"        {_timestamp_element(record)}\n"
        "        <description><![CDATA["
        f"{_record_description(record, filename)}]]></description>\n"
        "        <Point><coordinates>"
        f"{record.longitude},{record.latitude},0"
        "</coordinates></Point>\n"
        "      </Placemark>"
    )


def _accuracy_placemark(record: "LocationRecord") -> Optional[str]:
    if (
        record.accuracy_radius is None
        or record.accuracy_radius <= 0
        or record.latitude is None
        or record.longitude is None
    ):
        return None
    ring = _circle_coordinates(
        record.latitude, record.longitude, record.accuracy_radius
    )
    return (
        "      <Placemark>\n"
        f"        <name>Accuracy ~{record.accuracy_radius:g} m "
        f"(row {record.source_row_number})</name>\n"
        "        <styleUrl>#accuracyStyle</styleUrl>\n"
        "        <Polygon><outerBoundaryIs><LinearRing><coordinates>"
        f"{ring}"
        "</coordinates></LinearRing></outerBoundaryIs></Polygon>\n"
        "      </Placemark>"
    )


def _chronological(records: list["LocationRecord"]) -> list["LocationRecord"]:
    timestamped = [r for r in records if r.normalized_timestamp_utc]
    return sorted(timestamped, key=lambda r: r.normalized_timestamp_utc)


def _path_placemark(records: list["LocationRecord"]) -> Optional[str]:
    ordered = _chronological(records)
    if len(ordered) < 2:
        return None
    coords = " ".join(
        f"{r.longitude},{r.latitude},0" for r in ordered
    )
    return (
        "      <Placemark>\n"
        "        <name>Movement path (chronological)</name>\n"
        "        <styleUrl>#pathStyle</styleUrl>\n"
        "        <LineString><tessellate>1</tessellate><coordinates>"
        f"{coords}"
        "</coordinates></LineString>\n"
        "      </Placemark>"
    )


def _document_description(result: "ProcessingResult") -> str:
    summary = result.summary()
    counts = summary["record_counts"]
    first, last = result.time_range_utc()
    lines = []
    if result.training_mode:
        from .training import TRAINING_NOTICE

        lines.append(escape(TRAINING_NOTICE))
    lines += [
        "GeoBrief LE export.",
        f"Source file: {escape(result.filename)}",
        f"SHA-256: {escape(result.sha256)}",
        f"Processed at: {escape(result.processed_at)}",
        f"Total records: {counts['total']}",
        f"Mapped points: {counts['mappable']}",
        f"Skipped or flagged rows: {counts['skipped_or_flagged']}",
        (
            "Times shown in "
            f"{escape(result.display_timezone)}; original and UTC values are "
            "preserved in each point."
        ),
    ]
    if first and last:
        lines.append(
            f"Time range (UTC): {escape(first)} to {escape(last)}"
        )
    for warning in summary["warnings"]:
        lines.append(f"Warning: {escape(warning)}")
    lines.append(
        "Draft output generated from processed records. "
        "Investigator must verify before use."
    )
    return "<br/>".join(lines)


def build_kml(result: "ProcessingResult") -> str:
    """Render a complete KML document for the processing result."""
    mappable = result.mappable_records
    filename = result.filename

    point_placemarks = "\n".join(
        _point_placemark(r, filename) for r in mappable
    )
    accuracy_placemarks = "\n".join(
        p for r in mappable if (p := _accuracy_placemark(r)) is not None
    )
    path_placemark = _path_placemark(mappable)

    folders = [
        (
            "    <Folder>\n"
            "      <name>Location points</name>\n"
            f"{point_placemarks}\n"
            "    </Folder>"
        )
    ]
    if accuracy_placemarks:
        folders.append(
            "    <Folder>\n"
            "      <name>Accuracy circles</name>\n"
            "      <visibility>0</visibility>\n"
            f"{accuracy_placemarks}\n"
            "    </Folder>"
        )
    if path_placemark:
        folders.append(
            "    <Folder>\n"
            "      <name>Movement path</name>\n"
            f"{path_placemark}\n"
            "    </Folder>"
        )

    folders_xml = "\n".join(folders)
    doc_name = (
        f"TRAINING — GeoBrief LE — {filename}"
        if result.training_mode
        else f"GeoBrief LE — {filename}"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "  <Document>\n"
        f"    <name>{escape(doc_name)}</name>\n"
        "    <description><![CDATA["
        f"{_document_description(result)}]]></description>\n"
        f"{_STYLES}\n"
        f"{folders_xml}\n"
        "  </Document>\n"
        "</kml>\n"
    )


def build_kmz(result: "ProcessingResult") -> bytes:
    """Render the KML document zipped as a ``.kmz`` archive."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", build_kml(result))
    return buffer.getvalue()
