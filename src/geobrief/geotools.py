"""Deterministic geo-analysis tools for the investigator assistant.

Each tool takes the mappable GeoJSON point features the client already
holds and returns plain-data results. The assistant runs these locally —
no data leaves the machine — and uses the results to answer questions,
optionally passing them as extra context to the hosted model.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any, Optional


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_008.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def _parse_utc(stamp: Optional[str]) -> Optional[datetime]:
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _points(features: list[dict]) -> list[dict[str, Any]]:
    """Normalize GeoJSON features into simple point dicts."""
    points = []
    for feature in features or []:
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            continue
        props = feature.get("properties") or {}
        utc = props.get("normalized_timestamp_utc")
        points.append(
            {
                "lat": coords[1],
                "lon": coords[0],
                "utc": utc,
                "when": _parse_utc(utc),
                "display": props.get("display_timestamp"),
                "row": props.get("source_row_number"),
                "accuracy": props.get("accuracy_radius"),
                "status": props.get("validation_status"),
            }
        )
    return points


def _public(point: dict[str, Any]) -> dict[str, Any]:
    return {
        "latitude": point["lat"],
        "longitude": point["lon"],
        "time_utc": point["utc"],
        "time_display": point["display"],
        "source_row": point["row"],
        "accuracy_radius": point["accuracy"],
    }


# --- Tools --------------------------------------------------------------------

def nearest_points(
    features: list[dict],
    latitude: float,
    longitude: float,
    *,
    radius_m: Optional[float] = None,
    top: int = 5,
) -> dict[str, Any]:
    """Points closest to a coordinate, optionally within a radius."""
    ranked = []
    for point in _points(features):
        distance = _haversine_m(latitude, longitude, point["lat"], point["lon"])
        if radius_m is not None and distance > radius_m:
            continue
        entry = _public(point)
        entry["distance_m"] = round(distance, 1)
        ranked.append(entry)
    ranked.sort(key=lambda e: e["distance_m"])
    return {
        "tool": "nearest_points",
        "target": {"latitude": latitude, "longitude": longitude},
        "radius_m": radius_m,
        "matches": len(ranked),
        "points": ranked[:top],
    }


def time_gaps(features: list[dict], *, top: int = 5) -> dict[str, Any]:
    """Largest gaps between consecutive time-stamped points."""
    timed = sorted(
        [p for p in _points(features) if p["when"]], key=lambda p: p["when"]
    )
    gaps = []
    for a, b in zip(timed, timed[1:]):
        seconds = (b["when"] - a["when"]).total_seconds()
        if seconds <= 0:
            continue
        gaps.append(
            {
                "gap_seconds": int(seconds),
                "gap_human": _human_duration(seconds),
                "from": _public(a),
                "to": _public(b),
                "distance_m": round(
                    _haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]), 1
                ),
            }
        )
    gaps.sort(key=lambda g: g["gap_seconds"], reverse=True)
    return {
        "tool": "time_gaps",
        "timed_points": len(timed),
        "gaps": gaps[:top],
    }


def dwell_locations(
    features: list[dict],
    *,
    radius_m: float = 150.0,
    min_points: int = 3,
    top: int = 5,
) -> dict[str, Any]:
    """Places where multiple points cluster (possible stays/stops).

    Simple greedy clustering: walk points, join each to the first cluster
    whose centroid is within ``radius_m``; report clusters with at least
    ``min_points`` members.
    """
    clusters: list[dict[str, Any]] = []
    for point in _points(features):
        placed = False
        for cluster in clusters:
            if (
                _haversine_m(
                    cluster["lat"], cluster["lon"], point["lat"], point["lon"]
                )
                <= radius_m
            ):
                members = cluster["members"]
                members.append(point)
                cluster["lat"] = sum(m["lat"] for m in members) / len(members)
                cluster["lon"] = sum(m["lon"] for m in members) / len(members)
                placed = True
                break
        if not placed:
            clusters.append(
                {"lat": point["lat"], "lon": point["lon"], "members": [point]}
            )

    dwells = []
    for cluster in clusters:
        members = cluster["members"]
        if len(members) < min_points:
            continue
        times = sorted([m["when"] for m in members if m["when"]])
        entry: dict[str, Any] = {
            "latitude": round(cluster["lat"], 6),
            "longitude": round(cluster["lon"], 6),
            "point_count": len(members),
            "source_rows": [m["row"] for m in members][:20],
        }
        if times:
            entry["first_seen_utc"] = times[0].isoformat()
            entry["last_seen_utc"] = times[-1].isoformat()
            entry["span_human"] = _human_duration(
                (times[-1] - times[0]).total_seconds()
            )
        dwells.append(entry)
    dwells.sort(key=lambda d: d["point_count"], reverse=True)
    return {
        "tool": "dwell_locations",
        "radius_m": radius_m,
        "min_points": min_points,
        "clusters": dwells[:top],
    }


def points_in_window(
    features: list[dict], start_utc: str, end_utc: str, *, top: int = 10
) -> dict[str, Any]:
    """Points whose UTC timestamp falls inside [start, end]."""
    start = _parse_utc(start_utc)
    end = _parse_utc(end_utc)
    if start is None or end is None:
        return {
            "tool": "points_in_window",
            "error": "Could not parse the start or end time.",
        }
    if end < start:
        start, end = end, start
    inside = [
        p for p in _points(features) if p["when"] and start <= p["when"] <= end
    ]
    inside.sort(key=lambda p: p["when"])
    return {
        "tool": "points_in_window",
        "window": {"start_utc": start.isoformat(), "end_utc": end.isoformat()},
        "matches": len(inside),
        "points": [_public(p) for p in inside[:top]],
    }


def speed_check(
    features: list[dict], *, max_kmh: float = 200.0, top: int = 5
) -> dict[str, Any]:
    """Consecutive jumps implying an implausible speed (data-quality check)."""
    timed = sorted(
        [p for p in _points(features) if p["when"]], key=lambda p: p["when"]
    )
    flagged = []
    for a, b in zip(timed, timed[1:]):
        seconds = (b["when"] - a["when"]).total_seconds()
        if seconds <= 0:
            continue
        meters = _haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
        kmh = (meters / 1000.0) / (seconds / 3600.0)
        if kmh > max_kmh:
            flagged.append(
                {
                    "speed_kmh": round(kmh, 1),
                    "distance_m": round(meters, 1),
                    "seconds": int(seconds),
                    "from": _public(a),
                    "to": _public(b),
                }
            )
    flagged.sort(key=lambda f: f["speed_kmh"], reverse=True)
    return {
        "tool": "speed_check",
        "threshold_kmh": max_kmh,
        "flagged": flagged[:top],
    }


def _human_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


# --- Question-driven dispatch ---------------------------------------------------

_COORD_RE = re.compile(
    r"(-?\d{1,3}\.\d+)\s*[, ]\s*(-?\d{1,3}\.\d+)"
)
_WINDOW_RE = re.compile(
    r"between\s+(\S+(?:[T ]\S+)?)\s+and\s+(\S+(?:[T ]\S+)?)", re.IGNORECASE
)


def run_tools(question: str, geojson: Optional[dict]) -> dict[str, Any]:
    """Run whichever analysis tools the question calls for.

    Returns a mapping of tool name -> result. Empty when no tool applies
    or there are no features to analyse.
    """
    features = list((geojson or {}).get("features") or [])
    if not features:
        return {}
    q = (question or "").lower()
    results: dict[str, Any] = {}

    coord = _COORD_RE.search(question or "")
    if coord and any(w in q for w in ("near", "close", "around", "within", "at ")):
        lat, lon = float(coord.group(1)), float(coord.group(2))
        radius = None
        radius_match = re.search(r"within\s+(\d+(?:\.\d+)?)\s*(m|km|meter|mile)", q)
        if radius_match:
            value = float(radius_match.group(1))
            unit = radius_match.group(2)
            radius = value * {"m": 1, "meter": 1, "km": 1000, "mile": 1609.34}[unit]
        results["nearest_points"] = nearest_points(
            features, lat, lon, radius_m=radius
        )

    if any(w in q for w in ("gap", "gaps", "silence", "dark period", "missing time")):
        results["time_gaps"] = time_gaps(features)

    if any(
        w in q
        for w in ("dwell", "stay", "stayed", "stopped", "stops", "linger",
                  "frequent", "common location", "important location")
    ):
        results["dwell_locations"] = dwell_locations(features)

    window = _WINDOW_RE.search(question or "")
    if window and any(w in q for w in ("point", "record", "where", "during", "window")):
        result = points_in_window(features, window.group(1), window.group(2))
        if "error" not in result:
            results["points_in_window"] = result

    if any(w in q for w in ("speed", "impossible", "teleport", "jump", "plausib")):
        results["speed_check"] = speed_check(features)

    return results
