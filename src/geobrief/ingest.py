"""File intake for GeoBrief LE (PRD Module B).

Reads many evidence formats into a plain string DataFrame so the same
detection + cleaning engine can process all of them:

- CSV / TSV / TXT (delimiter sniffed)
- XLSX / XLS spreadsheets
- JSON (arrays of records, nested record containers)
- GeoJSON (Feature/FeatureCollection points)
- KML / KMZ (Google Earth placemarks)
- GPX (track points, route points, waypoints)
- ZIP (first supported file inside)

Values are kept as *text* (dtype=str) so the original values are preserved
exactly and never coerced/altered during load — cleaning happens later and
keeps the originals intact.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any, Optional, Union
from xml.etree import ElementTree

import pandas as pd

SUPPORTED_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".txt",
    ".xlsx",
    ".xls",
    ".json",
    ".geojson",
    ".kml",
    ".kmz",
    ".gpx",
    ".zip",
}


class UnsupportedFileTypeError(ValueError):
    """Raised when a file extension is not supported."""


def _unsupported(ext: str) -> UnsupportedFileTypeError:
    return UnsupportedFileTypeError(
        f"Unsupported file type '{ext}'. Supported: "
        + ", ".join(sorted(SUPPORTED_EXTENSIONS))
    )


# --- Delimited text -----------------------------------------------------------

def _sniff_delimiter(text: str) -> str:
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _read_delimited(data: bytes, delimiter: Optional[str] = None) -> pd.DataFrame:
    text = data.decode("utf-8-sig", errors="replace")
    sep = delimiter or _sniff_delimiter(text)
    # keep_default_na=False so empty cells stay as "" rather than NaN,
    # which keeps original values faithful and avoids float coercion.
    return pd.read_csv(
        io.StringIO(text),
        dtype=str,
        sep=sep,
        keep_default_na=False,
        skip_blank_lines=False,
        engine="python",
    )


def _read_excel(data: bytes) -> pd.DataFrame:
    return pd.read_excel(io.BytesIO(data), dtype=str, keep_default_na=False)


# --- JSON / GeoJSON -----------------------------------------------------------

def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _rows_to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        raise ValueError("No records were found in the file.")
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    table = {
        col: [_stringify(row.get(col)) for row in rows] for col in columns
    }
    return pd.DataFrame(table, dtype=str)


def _flatten_record(record: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten one level of nesting: {"location": {"lat": 1}} -> location_lat."""
    flat: dict[str, Any] = {}
    for key, value in record.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                flat[f"{name}_{sub_key}"] = (
                    _stringify(sub_value)
                    if isinstance(sub_value, (dict, list))
                    else sub_value
                )
        else:
            flat[name] = value
    return flat


def _geojson_rows(obj: dict[str, Any]) -> list[dict[str, Any]]:
    if obj.get("type") == "Feature":
        features = [obj]
    else:
        features = list(obj.get("features") or [])
    rows = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Point":
            continue
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            continue
        row: dict[str, Any] = {
            "longitude": coords[0],
            "latitude": coords[1],
        }
        if len(coords) > 2:
            row["altitude"] = coords[2]
        for key, value in (feature.get("properties") or {}).items():
            if key not in row:
                row[key] = value
        rows.append(row)
    return rows


def _read_json(data: bytes) -> pd.DataFrame:
    try:
        obj = json.loads(data.decode("utf-8-sig", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse JSON: {exc}") from exc

    if isinstance(obj, dict) and obj.get("type") in {
        "FeatureCollection",
        "Feature",
    }:
        rows = _geojson_rows(obj)
        if not rows:
            raise ValueError(
                "The GeoJSON file contains no point features to map."
            )
        return _rows_to_dataframe([_flatten_record(r) for r in rows])

    records: Optional[list] = None
    if isinstance(obj, list):
        records = obj
    elif isinstance(obj, dict):
        # Common containers: {"records": [...]}, {"data": [...]}, or the
        # first list-of-dicts value found anywhere at the top level.
        for key in ("records", "data", "locations", "items", "results", "rows"):
            value = obj.get(key)
            if isinstance(value, list):
                records = value
                break
        if records is None:
            for value in obj.values():
                if isinstance(value, list) and value and isinstance(
                    value[0], dict
                ):
                    records = value
                    break
    if not records:
        raise ValueError(
            "Could not find a list of records in the JSON file. Expected an "
            "array of objects or a GeoJSON FeatureCollection."
        )
    rows = [
        _flatten_record(r) for r in records if isinstance(r, dict)
    ]
    return _rows_to_dataframe(rows)


# --- KML / KMZ ----------------------------------------------------------------

def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _kml_rows(data: bytes) -> list[dict[str, Any]]:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValueError(f"Could not parse KML: {exc}") from exc

    rows: list[dict[str, Any]] = []
    for element in root.iter():
        if _strip_ns(element.tag) != "Placemark":
            continue
        row: dict[str, Any] = {}
        coords_text = None
        for child in element.iter():
            tag = _strip_ns(child.tag)
            text = (child.text or "").strip()
            if tag == "name" and text and "name" not in row:
                row["name"] = text
            elif tag == "description" and text and "description" not in row:
                row["description"] = text
            elif tag == "when" and text and "timestamp" not in row:
                row["timestamp"] = text
            elif tag == "coordinates" and text and coords_text is None:
                coords_text = text
            elif tag == "Data":
                key = child.get("name")
                value = child.findtext("./{*}value") or child.findtext(
                    "value"
                )
                if key and value is not None:
                    row.setdefault(key, value.strip())
        if not coords_text:
            continue
        # Use the first coordinate tuple (points; first vertex of lines).
        first = coords_text.split()[0]
        parts = first.split(",")
        if len(parts) < 2:
            continue
        row["longitude"] = parts[0]
        row["latitude"] = parts[1]
        if len(parts) > 2:
            row["altitude"] = parts[2]
        rows.append(row)
    return rows


def _read_kml(data: bytes) -> pd.DataFrame:
    rows = _kml_rows(data)
    if not rows:
        raise ValueError("No placemarks with coordinates were found.")
    return _rows_to_dataframe(rows)


def _read_kmz(data: bytes) -> pd.DataFrame:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [
                n for n in archive.namelist() if n.lower().endswith(".kml")
            ]
            if not names:
                raise ValueError("The KMZ archive contains no KML document.")
            # doc.kml first when present, matching Google Earth convention.
            names.sort(key=lambda n: (Path(n).name.lower() != "doc.kml", n))
            return _read_kml(archive.read(names[0]))
    except zipfile.BadZipFile as exc:
        raise ValueError("The KMZ file is not a valid archive.") from exc


# --- GPX ------------------------------------------------------------------------

def _read_gpx(data: bytes) -> pd.DataFrame:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValueError(f"Could not parse GPX: {exc}") from exc

    rows: list[dict[str, Any]] = []
    for element in root.iter():
        tag = _strip_ns(element.tag)
        if tag not in {"trkpt", "rtept", "wpt"}:
            continue
        lat = element.get("lat")
        lon = element.get("lon")
        if lat is None or lon is None:
            continue
        row: dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            "point_type": tag,
        }
        for child in element:
            child_tag = _strip_ns(child.tag)
            text = (child.text or "").strip()
            if child_tag == "time" and text:
                row["timestamp"] = text
            elif child_tag == "ele" and text:
                row["altitude"] = text
            elif child_tag == "name" and text:
                row["name"] = text
        rows.append(row)
    if not rows:
        raise ValueError("No track, route, or way points found in the GPX file.")
    return _rows_to_dataframe(rows)


# --- ZIP -------------------------------------------------------------------------

def _read_zip(data: bytes) -> pd.DataFrame:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if not name.endswith("/")
                and not Path(name).name.startswith(".")
                and Path(name).suffix.lower()
                in (SUPPORTED_EXTENSIONS - {".zip"})
            ]
            if not candidates:
                raise ValueError(
                    "The ZIP archive contains no supported data files."
                )
            # Prefer spreadsheet-like files, then anything else, stable order.
            priority = [".csv", ".tsv", ".xlsx", ".xls", ".json", ".geojson",
                        ".kml", ".kmz", ".gpx", ".txt"]
            candidates.sort(
                key=lambda n: (priority.index(Path(n).suffix.lower()), n)
            )
            inner = candidates[0]
            return read_dataframe_from_bytes(archive.read(inner), inner)
    except zipfile.BadZipFile as exc:
        raise ValueError("The ZIP file is not a valid archive.") from exc


# --- Public API --------------------------------------------------------------------

_READERS = {
    ".csv": lambda data: _read_delimited(data, ","),
    ".tsv": lambda data: _read_delimited(data, "\t"),
    ".txt": _read_delimited,
    ".xlsx": _read_excel,
    ".xls": _read_excel,
    ".json": _read_json,
    ".geojson": _read_json,
    ".kml": _read_kml,
    ".kmz": _read_kmz,
    ".gpx": _read_gpx,
    ".zip": _read_zip,
}


def read_dataframe_from_bytes(data: bytes, filename: str) -> pd.DataFrame:
    """Read a supported file from an in-memory bytes buffer (uploads)."""
    ext = Path(filename).suffix.lower()
    reader = _READERS.get(ext)
    if reader is None:
        raise _unsupported(ext)
    return reader(data)


def read_dataframe(path: Union[str, Path]) -> pd.DataFrame:
    """Read a supported file from disk into a string DataFrame."""
    path = Path(path)
    return read_dataframe_from_bytes(path.read_bytes(), path.name)
