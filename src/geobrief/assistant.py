"""Investigator AI assistant for GeoBrief LE (PRD Section 11 — AI Features).

The assistant helps an investigator make sense of already-processed location
records. It answers plain-English questions such as "explain this data",
"what is missing?", "summarize the movement", or "what should I filter?".

Design goals, driven by the PRD:

* **AI assists, it never decides.** The assistant explains processed records,
  drafts summaries, and points at gaps. It must not invent facts, determine
  guilt or probable cause, hide warnings, or alter data. Every answer carries
  the required verification disclaimer (see :data:`DISCLAIMER`).
* **Local-first / privacy-safe.** Case data is *not* sent to any cloud service
  by default. The assistant works fully offline with a deterministic,
  rule-based responder built from the processing summary. A remote model
  (OpenRouter) is only used when the investigator explicitly configures an API
  key — which, per the environment, is supplied later through the CLI/env.
* **Config through env / CLI later.** All remote settings are read from
  environment variables so no code change is needed to enable the model.

The context handed to the assistant is *aggregate* (counts, time range,
missing fields, a movement summary and a small sample of points) rather than
the full raw record set, keeping any optional external transmission minimal.
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = [
    "DISCLAIMER",
    "AssistantConfig",
    "AssistantError",
    "Assistant",
    "build_context",
]

# PRD Section 11: every AI output must carry this verification notice.
DISCLAIMER = (
    "Draft language generated from processed records. "
    "Investigator must verify before use."
)

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "openrouter/auto"


class AssistantError(RuntimeError):
    """Raised when a remote assistant request cannot be completed."""


def _env_flag(name: str) -> Optional[bool]:
    """Parse a boolean-ish environment variable, or ``None`` if unset."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class AssistantConfig:
    """Settings for the assistant, typically populated from the environment.

    The remote model is only used when :attr:`enabled` is true, which requires
    an API key. Without a key the assistant runs entirely locally.
    """

    api_key: Optional[str] = None
    model: str = _DEFAULT_MODEL
    base_url: str = _DEFAULT_BASE_URL
    temperature: float = 0.2
    max_tokens: int = 700
    timeout: float = 30.0
    # Explicit override; when None, availability follows presence of api_key.
    enabled_override: Optional[bool] = None

    @property
    def enabled(self) -> bool:
        """True when a remote model should be used for answers."""
        if self.enabled_override is not None:
            return self.enabled_override and bool(self.api_key)
        return bool(self.api_key)

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "AssistantConfig":
        """Build a config from environment variables.

        Recognised variables (all optional; supplied later via CLI/env):

        * ``OPENROUTER_API_KEY`` — API key; enables the remote model.
        * ``OPENROUTER_MODEL`` — model slug (default ``openrouter/auto``).
        * ``OPENROUTER_BASE_URL`` — API base URL.
        * ``GEOBRIEF_ASSISTANT_ENABLED`` — force the remote model on/off.
        * ``GEOBRIEF_ASSISTANT_TEMPERATURE`` / ``_MAX_TOKENS`` /
          ``_TIMEOUT`` — model tuning.
        """
        source = os.environ if env is None else env

        def _get(name: str) -> Optional[str]:
            value = source.get(name)
            if value is None:
                return None
            value = value.strip()
            return value or None

        def _float(name: str, default: float) -> float:
            raw = _get(name)
            if raw is None:
                return default
            try:
                return float(raw)
            except ValueError:
                return default

        def _int(name: str, default: int) -> int:
            raw = _get(name)
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        # _env_flag reads os.environ; honour a provided env mapping too.
        override = None
        flag_raw = source.get("GEOBRIEF_ASSISTANT_ENABLED")
        if flag_raw is not None and flag_raw.strip() != "":
            override = flag_raw.strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            api_key=_get("OPENROUTER_API_KEY"),
            model=_get("OPENROUTER_MODEL") or _DEFAULT_MODEL,
            base_url=_get("OPENROUTER_BASE_URL") or _DEFAULT_BASE_URL,
            temperature=_float("GEOBRIEF_ASSISTANT_TEMPERATURE", 0.2),
            max_tokens=_int("GEOBRIEF_ASSISTANT_MAX_TOKENS", 700),
            timeout=_float("GEOBRIEF_ASSISTANT_TIMEOUT", 30.0),
            enabled_override=override,
        )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    radius = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def _movement_summary(features: list[dict]) -> dict[str, Any]:
    """Derive an aggregate movement picture from GeoJSON point features."""
    points = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        props = feature.get("properties") or {}
        points.append(
            {
                "lat": lat,
                "lon": lon,
                "utc": props.get("normalized_timestamp_utc"),
                "display": props.get("display_timestamp"),
            }
        )

    if not points:
        return {"mappable_points": 0}

    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    bbox = {
        "min_lat": min(lats),
        "max_lat": max(lats),
        "min_lon": min(lons),
        "max_lon": max(lons),
    }

    ordered = sorted(
        [p for p in points if p["utc"]], key=lambda p: p["utc"]
    )
    total_km = 0.0
    for a, b in zip(ordered, ordered[1:]):
        total_km += _haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])

    distinct_days = sorted(
        {p["utc"][:10] for p in points if p["utc"] and len(p["utc"]) >= 10}
    )

    summary: dict[str, Any] = {
        "mappable_points": len(points),
        "bounding_box": bbox,
        "approx_path_length_km": round(total_km, 3),
        "distinct_days_utc": distinct_days,
        "ordered_points_with_time": len(ordered),
    }
    if ordered:
        summary["first_point"] = ordered[0]
        summary["last_point"] = ordered[-1]
    return summary


def build_context(
    summary: dict, geojson: Optional[dict] = None, *, sample_size: int = 8
) -> dict[str, Any]:
    """Build a compact, privacy-aware analysis context for the assistant.

    ``summary`` is a :meth:`ProcessingResult.summary` mapping and ``geojson``
    is the matching :meth:`ProcessingResult.geojson` FeatureCollection. The
    returned context contains aggregates (counts, time range, missing fields,
    a movement summary) plus a small sample of points — never the full record
    set — so any optional external call stays minimal.
    """
    features = []
    if geojson:
        features = list(geojson.get("features") or [])

    detected = summary.get("detected_columns") or {}
    missing_fields = [name for name, col in detected.items() if not col]

    counts = summary.get("record_counts") or {}

    sample = []
    for feature in features[:sample_size]:
        props = (feature.get("properties") or {})
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or [None, None]
        sample.append(
            {
                "latitude": coords[1] if len(coords) > 1 else None,
                "longitude": coords[0] if coords else None,
                "display_timestamp": props.get("display_timestamp"),
                "normalized_timestamp_utc": props.get(
                    "normalized_timestamp_utc"
                ),
                "accuracy_radius": props.get("accuracy_radius"),
                "validation_status": props.get("validation_status"),
            }
        )

    return {
        "product": summary.get("product", "GeoBrief LE"),
        "source_file": summary.get("source_file", {}),
        "display_timezone": summary.get("display_timezone"),
        "detected_columns": detected,
        "detection_confidence": summary.get("detection_confidence", {}),
        "missing_fields": missing_fields,
        "record_counts": counts,
        "time_range_utc": summary.get("time_range_utc", {}),
        "warnings": summary.get("warnings", []),
        "plain_english": summary.get("plain_english", ""),
        "movement": _movement_summary(features),
        "sample_points": sample,
    }


# --- System prompt for the remote model ---------------------------------------

_SYSTEM_PROMPT = (
    "You are the GeoBrief LE investigative assistant. You help a law "
    "enforcement investigator understand ALREADY-PROCESSED location records. "
    "You are given an aggregate JSON analysis context. Follow these rules "
    "strictly:\n"
    "- Assist, do not decide. Never determine guilt, probable cause, or make "
    "final legal conclusions.\n"
    "- Never invent facts. Only use what is in the provided context; if "
    "something is unknown, say so.\n"
    "- Never hide warnings or data-quality problems; surface them.\n"
    "- Do not claim to have altered or re-processed the data; you only "
    "explain it.\n"
    "- Be concise, plain-spoken, and neutral. Prefer short paragraphs or "
    "bullet points.\n"
    "- When the context includes 'tool_results', those are exact, locally "
    "computed analysis results (nearest points, time gaps, dwell clusters, "
    "time-window matches, implausible-speed checks). Treat them as ground "
    "truth and cite the source rows they reference.\n"
    "- When asked for report or warrant language, produce factual DRAFT "
    "language only."
)


class Assistant:
    """Answers investigator questions about a processed data set.

    Uses a remote OpenRouter model when configured (an API key is present),
    otherwise falls back to a deterministic local responder so the feature
    works with no network access and no configuration.
    """

    def __init__(self, config: Optional[AssistantConfig] = None) -> None:
        self.config = config or AssistantConfig.from_env()

    # -- Public API -----------------------------------------------------------
    def answer(
        self,
        question: str,
        summary: dict,
        geojson: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Answer ``question`` about the processed data.

        Returns a mapping with the answer text, which backend produced it,
        the mandatory verification disclaimer, any tool results used, and
        ``focus_points`` the map can highlight.
        """
        question = (question or "").strip()
        context = build_context(summary, geojson)

        from .geotools import run_tools

        tool_results = run_tools(question, geojson)
        if tool_results:
            context["tool_results"] = tool_results

        if not question:
            answer_text = self._local_answer("overview", context)
            return self._wrap(
                answer_text,
                backend="local",
                context=context,
                tool_results=tool_results,
            )

        if self.config.enabled:
            try:
                answer_text = self._remote_answer(question, context)
                return self._wrap(
                    answer_text,
                    backend="openrouter",
                    context=context,
                    tool_results=tool_results,
                )
            except AssistantError:
                # Fall back to local rather than failing the investigator.
                answer_text = self._local_answer(question, context)
                return self._wrap(
                    answer_text,
                    backend="local-fallback",
                    context=context,
                    tool_results=tool_results,
                )

        answer_text = self._local_answer(question, context)
        return self._wrap(
            answer_text,
            backend="local",
            context=context,
            tool_results=tool_results,
        )

    @staticmethod
    def _focus_points(tool_results: dict[str, Any]) -> list[dict[str, Any]]:
        """Coordinates the UI can highlight for the tool results used."""
        focus: list[dict[str, Any]] = []

        def add(lat, lon, label):
            if lat is None or lon is None:
                return
            focus.append({"latitude": lat, "longitude": lon, "label": label})

        near = tool_results.get("nearest_points") or {}
        for point in near.get("points", []):
            add(
                point["latitude"],
                point["longitude"],
                f"{point['distance_m']} m away (row {point['source_row']})",
            )
        for cluster in (tool_results.get("dwell_locations") or {}).get(
            "clusters", []
        ):
            add(
                cluster["latitude"],
                cluster["longitude"],
                f"Dwell: {cluster['point_count']} points",
            )
        for gap in (tool_results.get("time_gaps") or {}).get("gaps", [])[:3]:
            add(
                gap["from"]["latitude"],
                gap["from"]["longitude"],
                f"Gap starts here ({gap['gap_human']})",
            )
        for point in (tool_results.get("points_in_window") or {}).get(
            "points", []
        ):
            add(
                point["latitude"],
                point["longitude"],
                f"In window (row {point['source_row']})",
            )
        for jump in (tool_results.get("speed_check") or {}).get(
            "flagged", []
        )[:3]:
            add(
                jump["to"]["latitude"],
                jump["to"]["longitude"],
                f"Implausible jump ({jump['speed_kmh']} km/h)",
            )
        return focus[:25]

    def _wrap(
        self,
        answer_text: str,
        *,
        backend: str,
        context: dict,
        tool_results: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        tool_results = tool_results or {}
        return {
            "answer": answer_text.strip(),
            "backend": backend,
            "model": self.config.model if backend == "openrouter" else None,
            "disclaimer": DISCLAIMER,
            "tools_used": sorted(tool_results.keys()),
            "focus_points": self._focus_points(tool_results),
        }

    # -- Remote (OpenRouter) --------------------------------------------------
    def _remote_answer(self, question: str, context: dict) -> str:
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Analysis context (JSON):\n"
                        + json.dumps(context, ensure_ascii=False)
                        + "\n\nInvestigator question: "
                        + question
                    ),
                },
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": "Bearer " + (self.config.api_key or ""),
            "Content-Type": "application/json",
            # Optional attribution headers recommended by OpenRouter.
            "HTTP-Referer": "https://github.com/geobrief-le",
            "X-Title": "GeoBrief LE",
        }
        request = urllib.request.Request(
            url, data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - network
            detail = exc.read().decode("utf-8", "replace") if exc.fp else ""
            raise AssistantError(
                f"OpenRouter request failed ({exc.code}): {detail[:300]}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:  # pragma: no cover
            raise AssistantError(f"OpenRouter request failed: {exc}") from exc

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AssistantError(
                "OpenRouter returned an unexpected response shape."
            ) from exc

    # -- Local deterministic responder ---------------------------------------
    def _local_answer(self, question: str, context: dict) -> str:
        tool_results = context.get("tool_results") or {}
        if tool_results:
            return self._local_tools(tool_results)
        intent = self._classify(question)
        if intent == "missing":
            return self._local_missing(context)
        if intent == "movement":
            return self._local_movement(context)
        if intent == "time":
            return self._local_time(context)
        if intent == "filter":
            return self._local_filter(context)
        return self._local_overview(context)

    @staticmethod
    def _local_tools(tool_results: dict[str, Any]) -> str:
        """Format deterministic tool output as a plain-English answer."""
        lines: list[str] = []

        near = tool_results.get("nearest_points")
        if near:
            target = near["target"]
            lines.append(
                f"Points nearest to ({target['latitude']}, "
                f"{target['longitude']})"
                + (
                    f" within {near['radius_m']:.0f} m"
                    if near.get("radius_m")
                    else ""
                )
                + f" — {near['matches']} match(es):"
            )
            for point in near["points"]:
                lines.append(
                    f"- {point['distance_m']} m away at "
                    f"({point['latitude']:.5f}, {point['longitude']:.5f}), "
                    f"{point.get('time_display') or point.get('time_utc') or 'no time'} "
                    f"(source row {point['source_row']})"
                )

        gaps = tool_results.get("time_gaps")
        if gaps:
            if gaps["gaps"]:
                lines.append("Largest gaps between consecutive points:")
                for gap in gaps["gaps"]:
                    lines.append(
                        f"- {gap['gap_human']} gap from "
                        f"{gap['from']['time_utc']} to {gap['to']['time_utc']} "
                        f"({gap['distance_m']} m apart; rows "
                        f"{gap['from']['source_row']}→{gap['to']['source_row']})"
                    )
            else:
                lines.append(
                    "No time gaps could be measured (fewer than two "
                    "time-stamped points)."
                )

        dwell = tool_results.get("dwell_locations")
        if dwell:
            if dwell["clusters"]:
                lines.append(
                    f"Locations where points cluster (within "
                    f"{dwell['radius_m']:.0f} m, at least "
                    f"{dwell['min_points']} points):"
                )
                for cluster in dwell["clusters"]:
                    span = (
                        f", seen {cluster['first_seen_utc']} → "
                        f"{cluster['last_seen_utc']} ({cluster['span_human']})"
                        if cluster.get("first_seen_utc")
                        else ""
                    )
                    lines.append(
                        f"- ({cluster['latitude']}, {cluster['longitude']}): "
                        f"{cluster['point_count']} points{span}"
                    )
            else:
                lines.append(
                    "No dwell clusters found with the default settings "
                    "(3+ points within 150 m)."
                )

        window = tool_results.get("points_in_window")
        if window:
            w = window["window"]
            lines.append(
                f"{window['matches']} point(s) between {w['start_utc']} and "
                f"{w['end_utc']} (UTC)."
            )
            for point in window["points"]:
                lines.append(
                    f"- ({point['latitude']:.5f}, {point['longitude']:.5f}) "
                    f"at {point['time_utc']} (source row {point['source_row']})"
                )

        speed = tool_results.get("speed_check")
        if speed:
            if speed["flagged"]:
                lines.append(
                    f"Consecutive jumps implying more than "
                    f"{speed['threshold_kmh']:.0f} km/h (possible data "
                    "problems, not real travel):"
                )
                for jump in speed["flagged"]:
                    lines.append(
                        f"- {jump['speed_kmh']} km/h: {jump['distance_m']} m "
                        f"in {jump['seconds']} s (rows "
                        f"{jump['from']['source_row']}→{jump['to']['source_row']})"
                    )
            else:
                lines.append(
                    "No implausible-speed jumps found between consecutive "
                    "time-stamped points."
                )

        lines.append(
            "I highlighted the relevant points on the map. Verify each "
            "finding against the source rows listed."
        )
        return "\n".join(lines)

    @staticmethod
    def _classify(question: str) -> str:
        q = question.lower()

        def has(*words: str) -> bool:
            return any(w in q for w in words)

        if has("missing", "gap", "absent", "field", "column", "incomplete"):
            return "missing"
        if has(
            "move", "movement", "travel", "distance", "route", "path", "trip",
            "far", "location", "where",
        ):
            return "movement"
        if has("time", "when", "timezone", "time zone", "date", "hour"):
            return "time"
        if has("filter", "suggest", "narrow", "focus", "exclude", "clean"):
            return "filter"
        return "overview"

    @staticmethod
    def _fmt_counts(context: dict) -> dict:
        return context.get("record_counts") or {}

    def _local_overview(self, context: dict) -> str:
        counts = self._fmt_counts(context)
        lines = [context.get("plain_english", "").strip()]
        total = counts.get("total")
        if total is not None:
            lines.append(
                f"- Total records: {total}; mappable points: "
                f"{counts.get('mappable', 0)}; valid: "
                f"{counts.get('valid', 0)}; skipped or flagged: "
                f"{counts.get('skipped_or_flagged', 0)}."
            )
        by_status = counts.get("by_status") or {}
        if by_status:
            breakdown = ", ".join(
                f"{k}: {v}" for k, v in sorted(by_status.items())
            )
            lines.append(f"- Status breakdown: {breakdown}.")
        warnings = context.get("warnings") or []
        if warnings:
            lines.append(
                "- Warnings you should not ignore: "
                + " ".join(str(w) for w in warnings)
            )
        lines.append(
            "You can ask me to explain what is missing, summarize the "
            "movement, explain the time zones, or suggest filters."
        )
        return "\n".join(part for part in lines if part)

    def _local_missing(self, context: dict) -> str:
        missing = context.get("missing_fields") or []
        counts = self._fmt_counts(context)
        by_status = counts.get("by_status") or {}
        lines = []
        if missing:
            lines.append(
                "These expected fields were not detected in the source file: "
                + ", ".join(missing)
                + ". Confirm whether the original data included them under a "
                "different column name."
            )
        else:
            lines.append(
                "All core fields (latitude, longitude, timestamp, accuracy) "
                "were detected."
            )
        gap_statuses = {
            "missing_coordinate": "rows with no usable coordinates",
            "missing_timestamp": "rows with no timestamp",
            "invalid_coordinate": "rows whose coordinates could not be parsed",
            "timezone_uncertain": "rows with an uncertain time zone",
        }
        found = [
            f"{count} {label}"
            for key, label in gap_statuses.items()
            if (count := by_status.get(key))
        ]
        if found:
            lines.append("Data gaps found: " + "; ".join(found) + ".")
        lines.append(
            "No rows were deleted — every flagged row is kept in the cleaned "
            "spreadsheet for your review."
        )
        return "\n".join(lines)

    def _local_movement(self, context: dict) -> str:
        movement = context.get("movement") or {}
        n = movement.get("mappable_points", 0)
        if not n:
            return (
                "There are no mappable points, so I cannot describe any "
                "movement. Check the missing-coordinate warnings first."
            )
        lines = [f"There are {n} mappable points."]
        days = movement.get("distinct_days_utc") or []
        if days:
            lines.append(
                f"They span {len(days)} distinct day(s) (UTC): "
                + ", ".join(days[:10])
                + ("…" if len(days) > 10 else "")
                + "."
            )
        bbox = movement.get("bounding_box")
        if bbox:
            lines.append(
                "Bounding box: latitude "
                f"{bbox['min_lat']:.5f}..{bbox['max_lat']:.5f}, longitude "
                f"{bbox['min_lon']:.5f}..{bbox['max_lon']:.5f}."
            )
        path = movement.get("approx_path_length_km")
        ordered = movement.get("ordered_points_with_time", 0)
        if path is not None and ordered > 1:
            lines.append(
                f"Connecting the {ordered} time-stamped points in "
                f"chronological order gives an approximate path length of "
                f"{path:.2f} km (straight lines between consecutive points; "
                "not an actual travelled route)."
            )
        first = movement.get("first_point")
        last = movement.get("last_point")
        if first and last:
            lines.append(
                "Earliest point: "
                f"({first['lat']:.5f}, {first['lon']:.5f}) at "
                f"{first.get('display') or first.get('utc')}. "
                "Latest point: "
                f"({last['lat']:.5f}, {last['lon']:.5f}) at "
                f"{last.get('display') or last.get('utc')}."
            )
        return "\n".join(lines)

    def _local_time(self, context: dict) -> str:
        time_range = context.get("time_range_utc") or {}
        tz = context.get("display_timezone") or "UTC"
        first = time_range.get("first")
        last = time_range.get("last")
        lines = []
        if first and last:
            lines.append(
                f"Timestamps range from {first} to {last} (UTC)."
            )
        else:
            lines.append("No usable timestamps were found in the records.")
        lines.append(
            f"Times are being displayed in {tz}. The original values were "
            "normalized to UTC first, then converted to the display time "
            "zone, so comparisons across records are consistent."
        )
        counts = self._fmt_counts(context)
        uncertain = (counts.get("by_status") or {}).get("timezone_uncertain")
        if uncertain:
            lines.append(
                f"{uncertain} row(s) had an uncertain time zone — verify the "
                "source's local time before relying on those times."
            )
        return "\n".join(lines)

    def _local_filter(self, context: dict) -> str:
        counts = self._fmt_counts(context)
        by_status = counts.get("by_status") or {}
        suggestions = []
        mapping = {
            "low_accuracy": (
                "Filter out or flag low-accuracy points if you need precise "
                "positions."
            ),
            "duplicate": (
                "Collapse duplicate points to de-clutter the map and timeline."
            ),
            "possible_latlon_reversal": (
                "Review possible latitude/longitude reversals before trusting "
                "those locations."
            ),
            "timezone_uncertain": (
                "Isolate time-zone-uncertain rows and confirm their local "
                "time."
            ),
            "invalid_coordinate": (
                "Exclude invalid-coordinate rows from the map, but keep them "
                "in the report."
            ),
        }
        for key, text in mapping.items():
            if by_status.get(key):
                suggestions.append(f"- {text} ({by_status[key]} row(s))")
        if not suggestions:
            suggestions.append(
                "- The data looks clean; you could still filter by date range "
                "or by a geographic area of interest to focus the map."
            )
        header = (
            "Suggested filters based on what I found (you decide what to "
            "apply):"
        )
        return header + "\n" + "\n".join(suggestions)
