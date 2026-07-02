"""Tests for multi-format file intake (PRD Module B, Phase 2 file types)."""

import io
import json
import zipfile

import pytest

from geobrief.ingest import (
    UnsupportedFileTypeError,
    read_dataframe_from_bytes,
)
from geobrief.pipeline import process_bytes

KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Stop 1</name>
      <TimeStamp><when>2024-03-01T08:00:00Z</when></TimeStamp>
      <Point><coordinates>-87.6298,41.8781,0</coordinates></Point>
    </Placemark>
    <Placemark>
      <name>Stop 2</name>
      <TimeStamp><when>2024-03-01T09:30:00Z</when></TimeStamp>
      <Point><coordinates>-87.6100,41.8850,0</coordinates></Point>
    </Placemark>
    <Placemark><name>No coords</name></Placemark>
  </Document>
</kml>
"""

GPX = b"""<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
  <trk><trkseg>
    <trkpt lat="41.8781" lon="-87.6298">
      <ele>180.0</ele><time>2024-03-01T08:00:00Z</time>
    </trkpt>
    <trkpt lat="41.8850" lon="-87.6100">
      <time>2024-03-01T09:30:00Z</time>
    </trkpt>
  </trkseg></trk>
</gpx>
"""

GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-87.6298, 41.8781]},
            "properties": {"timestamp": "2024-03-01T08:00:00Z", "accuracy": 12},
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[0, 0], [1, 1]],
            },
            "properties": {},
        },
    ],
}


def test_unsupported_extension_raises():
    with pytest.raises(UnsupportedFileTypeError):
        read_dataframe_from_bytes(b"x", "letter.docx")


def test_tsv_and_pipe_delimited_text():
    tsv = b"latitude\tlongitude\ttimestamp\n41.88\t-87.62\t2024-03-01T08:00:00Z\n"
    df = read_dataframe_from_bytes(tsv, "records.tsv")
    assert list(df.columns) == ["latitude", "longitude", "timestamp"]

    piped = b"latitude|longitude|timestamp\n41.88|-87.62|2024-03-01T08:00:00Z\n"
    df2 = read_dataframe_from_bytes(piped, "records.txt")
    assert list(df2.columns) == ["latitude", "longitude", "timestamp"]
    assert df2.iloc[0]["latitude"] == "41.88"


def test_json_array_of_records():
    payload = json.dumps(
        [
            {"lat": 41.88, "lon": -87.62, "time": "2024-03-01T08:00:00Z"},
            {"lat": 41.89, "lon": -87.61, "time": "2024-03-01T09:00:00Z"},
        ]
    ).encode()
    result = process_bytes(payload, "records.json")
    assert result.total_records == 2
    assert len(result.mappable_records) == 2


def test_json_nested_container_and_objects():
    payload = json.dumps(
        {
            "export_info": {"source": "provider"},
            "locations": [
                {
                    "location": {"latitude": 41.88, "longitude": -87.62},
                    "timestamp": "2024-03-01T08:00:00Z",
                }
            ],
        }
    ).encode()
    df = read_dataframe_from_bytes(payload, "provider.json")
    assert "location_latitude" in df.columns
    result = process_bytes(payload, "provider.json")
    assert len(result.mappable_records) == 1


def test_geojson_points_only():
    payload = json.dumps(GEOJSON).encode()
    result = process_bytes(payload, "points.geojson")
    # LineString feature is skipped; one point remains.
    assert result.total_records == 1
    record = result.mappable_records[0]
    assert record.latitude == pytest.approx(41.8781)
    assert record.longitude == pytest.approx(-87.6298)


def test_kml_placemarks():
    result = process_bytes(KML, "route.kml")
    assert len(result.mappable_records) == 2
    first, last = result.time_range_utc()
    assert first is not None and "2024-03-01" in first


def test_kmz_archive():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("doc.kml", KML)
    result = process_bytes(buffer.getvalue(), "route.kmz")
    assert len(result.mappable_records) == 2


def test_gpx_trackpoints():
    result = process_bytes(GPX, "track.gpx")
    assert len(result.mappable_records) == 2
    assert result.records[0].accuracy_radius is None


def test_zip_prefers_csv_inside():
    csv_data = b"latitude,longitude\n41.88,-87.62\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", b"about this export")
        archive.writestr("data/points.csv", csv_data)
    df = read_dataframe_from_bytes(buffer.getvalue(), "export.zip")
    assert list(df.columns) == ["latitude", "longitude"]


def test_zip_without_supported_files_errors():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("image.png", b"\x89PNG")
    with pytest.raises(ValueError):
        read_dataframe_from_bytes(buffer.getvalue(), "export.zip")


def test_bad_json_reports_clear_error():
    with pytest.raises(ValueError):
        read_dataframe_from_bytes(b"{not json", "broken.json")
