"""Tests for the Google Earth KML/KMZ export (PRD Module H)."""

import io
import xml.etree.ElementTree as ET
import zipfile

import pytest

from geobrief.kml import build_kml, build_kmz
from geobrief.pipeline import process_bytes

KML_NS = "{http://www.opengis.net/kml/2.2}"

CSV_DATA = b"""latitude,longitude,timestamp,accuracy
33.4484,-112.0740,2024-03-01T12:00:00Z,25
33.4500,-112.0700,2024-03-01T12:05:00Z,15
33.4520,-112.0650,2024-03-01T12:10:00Z,
,-112.0600,2024-03-01T12:15:00Z,10
"""


@pytest.fixture()
def result():
    return process_bytes(
        CSV_DATA, "trip.csv", display_timezone="America/Phoenix"
    )


@pytest.fixture()
def kml_root(result):
    return ET.fromstring(build_kml(result))


def _folder(root, name):
    for folder in root.iter(f"{KML_NS}Folder"):
        if folder.findtext(f"{KML_NS}name") == name:
            return folder
    return None


def test_kml_is_valid_xml_with_kml_root(kml_root):
    assert kml_root.tag == f"{KML_NS}kml"


def test_one_placemark_per_mappable_record(result, kml_root):
    folder = _folder(kml_root, "Location points")
    placemarks = folder.findall(f"{KML_NS}Placemark")
    assert len(placemarks) == len(result.mappable_records) == 3


def test_placemark_coordinates_are_lon_lat(kml_root):
    folder = _folder(kml_root, "Location points")
    coords = folder.find(
        f"{KML_NS}Placemark/{KML_NS}Point/{KML_NS}coordinates"
    ).text
    lon, lat, _alt = coords.split(",")
    assert float(lon) == pytest.approx(-112.0740)
    assert float(lat) == pytest.approx(33.4484)


def test_placemarks_carry_timestamps(kml_root):
    folder = _folder(kml_root, "Location points")
    whens = [
        el.text
        for el in folder.iter(f"{KML_NS}when")
    ]
    assert len(whens) == 3
    assert all("2024-03-01" in when for when in whens)


def test_placemark_description_includes_source_details(result):
    kml = build_kml(result)
    assert "Source file: trip.csv" in kml
    assert "Source row:" in kml
    assert "Accuracy radius: 25.0 m" in kml


def test_document_metadata_includes_hash_and_counts(result):
    kml = build_kml(result)
    assert result.sha256 in kml
    assert "Total records: 4" in kml
    assert "Mapped points: 3" in kml
    assert "Investigator must verify before use." in kml


def test_accuracy_circles_only_for_records_with_radius(kml_root):
    folder = _folder(kml_root, "Accuracy circles")
    polygons = folder.findall(f"{KML_NS}Placemark")
    assert len(polygons) == 2  # rows with accuracy 25 and 15
    ring = polygons[0].find(
        f"{KML_NS}Polygon/{KML_NS}outerBoundaryIs/{KML_NS}LinearRing/"
        f"{KML_NS}coordinates"
    ).text
    points = ring.split()
    assert len(points) == 37  # 36 segments + closing point
    assert points[0] == points[-1]  # ring is closed


def test_movement_path_present_and_chronological(kml_root):
    folder = _folder(kml_root, "Movement path")
    line = folder.find(
        f"{KML_NS}Placemark/{KML_NS}LineString/{KML_NS}coordinates"
    ).text
    points = line.split()
    assert len(points) == 3
    # First chronological point is the 12:00 record.
    assert points[0].startswith("-112.074,")


def test_no_path_folder_for_single_point():
    data = b"lat,lon,time\n10.0,20.0,2024-01-01T00:00:00Z\n"
    result = process_bytes(data, "one.csv")
    root = ET.fromstring(build_kml(result))
    assert _folder(root, "Movement path") is None
    assert _folder(root, "Location points") is not None


def test_special_characters_are_escaped():
    data = b'lat,lon,time\n10.0,20.0,"<b>&nasty</b>"\n'
    result = process_bytes(data, "we<i>rd & name.csv")
    kml = build_kml(result)
    ET.fromstring(kml)  # must remain well-formed XML


def test_kmz_is_zip_containing_doc_kml(result):
    kmz = build_kmz(result)
    with zipfile.ZipFile(io.BytesIO(kmz)) as archive:
        assert archive.namelist() == ["doc.kml"]
        inner = archive.read("doc.kml").decode("utf-8")
    assert inner == build_kml(result)
