"""Tests for the assistant's deterministic geo-analysis tools."""

import pytest

from geobrief.assistant import Assistant
from geobrief.geotools import (
    dwell_locations,
    nearest_points,
    points_in_window,
    run_tools,
    speed_check,
    time_gaps,
)
from geobrief.pipeline import process_bytes

# Three points near Chicago city hall, one far away, with a 2-day gap.
CSV_DATA = b"""latitude,longitude,timestamp
41.8837,-87.6319,2024-03-01T08:00:00Z
41.8838,-87.6320,2024-03-01T08:20:00Z
41.8836,-87.6318,2024-03-01T08:40:00Z
41.9500,-87.7000,2024-03-03T09:00:00Z
"""


@pytest.fixture()
def features():
    result = process_bytes(CSV_DATA, "trip.csv")
    return result.geojson()["features"]


def test_nearest_points_ranks_by_distance(features):
    out = nearest_points(features, 41.8837, -87.6319, top=3)
    assert out["matches"] == 4
    distances = [p["distance_m"] for p in out["points"]]
    assert distances == sorted(distances)
    assert distances[0] < 20


def test_nearest_points_radius_filters(features):
    out = nearest_points(features, 41.8837, -87.6319, radius_m=500)
    assert out["matches"] == 3  # the far point is excluded


def test_time_gaps_finds_two_day_gap(features):
    out = time_gaps(features)
    assert out["gaps"][0]["gap_seconds"] >= 2 * 86400 - 3600
    assert "d" in out["gaps"][0]["gap_human"]


def test_dwell_locations_clusters_nearby_points(features):
    out = dwell_locations(features, radius_m=150, min_points=3)
    assert len(out["clusters"]) == 1
    assert out["clusters"][0]["point_count"] == 3


def test_points_in_window(features):
    out = points_in_window(
        features, "2024-03-01T08:00:00Z", "2024-03-01T09:00:00Z"
    )
    assert out["matches"] == 3


def test_speed_check_flags_teleport():
    data = (
        b"lat,lon,time\n"
        b"41.88,-87.63,2024-03-01T08:00:00Z\n"
        b"48.85,2.35,2024-03-01T08:10:00Z\n"  # Chicago -> Paris in 10 min
    )
    features = process_bytes(data, "jump.csv").geojson()["features"]
    out = speed_check(features)
    assert out["flagged"]
    assert out["flagged"][0]["speed_kmh"] > 10000


def test_run_tools_dispatches_by_question(features):
    assert "nearest_points" in run_tools(
        "what points are near 41.8837, -87.6319?", {"features": features}
    )
    assert "time_gaps" in run_tools(
        "are there any gaps in the data?", {"features": features}
    )
    assert "dwell_locations" in run_tools(
        "where did the device stay the longest?", {"features": features}
    )
    assert "speed_check" in run_tools(
        "any impossible jumps?", {"features": features}
    )
    assert (
        run_tools("explain this data", {"features": features}) == {}
    )
    assert run_tools("near 1.0, 2.0", None) == {}


def test_assistant_answers_with_tools_and_focus_points():
    result = process_bytes(CSV_DATA, "trip.csv")
    answer = Assistant().answer(
        "which points are near 41.8837, -87.6319 within 500 m?",
        result.summary(),
        result.geojson(),
    )
    assert "tools_used" in answer and "nearest_points" in answer["tools_used"]
    assert answer["focus_points"]
    assert "m away" in answer["answer"]
    assert answer["disclaimer"]


def test_assistant_without_tools_still_answers():
    result = process_bytes(CSV_DATA, "trip.csv")
    answer = Assistant().answer(
        "explain this data", result.summary(), result.geojson()
    )
    assert answer["tools_used"] == []
    assert answer["focus_points"] == []
    assert answer["answer"]
