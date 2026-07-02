"""Tests for the investigator AI assistant (local responder + config)."""

from geobrief.assistant import (
    DISCLAIMER,
    Assistant,
    AssistantConfig,
    build_context,
)
from geobrief.pipeline import process_bytes

CSV = (
    "latitude,longitude,timestamp,accuracy_m\n"
    "41.8781,-87.6298,2024-03-01T08:00:00Z,10\n"
    "41.9000,-87.6300,2024-03-01T12:00:00Z,15\n"
    ",,2024-03-01T09:00:00Z,\n"
)


def _result():
    return process_bytes(CSV.encode(), "records.csv",
                         display_timezone="America/Chicago")


def test_config_disabled_without_key():
    config = AssistantConfig.from_env(env={})
    assert config.enabled is False
    assert config.model  # has a default


def test_config_enabled_with_key():
    config = AssistantConfig.from_env(
        env={"OPENROUTER_API_KEY": "sk-test", "OPENROUTER_MODEL": "x/y"}
    )
    assert config.enabled is True
    assert config.model == "x/y"


def test_config_override_off_even_with_key():
    config = AssistantConfig.from_env(
        env={
            "OPENROUTER_API_KEY": "sk-test",
            "GEOBRIEF_ASSISTANT_ENABLED": "false",
        }
    )
    assert config.enabled is False


def test_build_context_reports_missing_and_movement():
    result = _result()
    context = build_context(result.summary(), result.geojson())
    # accuracy present here, but no missing core fields in this sample
    assert context["record_counts"]["total"] == 3
    assert context["movement"]["mappable_points"] == 2
    assert context["movement"]["approx_path_length_km"] > 0
    assert context["missing_fields"] == []


def test_local_answer_has_disclaimer_and_backend():
    result = _result()
    assistant = Assistant(AssistantConfig())  # no key -> local
    answer = assistant.answer("explain this data", result.summary(),
                              result.geojson())
    assert answer["backend"] == "local"
    assert answer["disclaimer"] == DISCLAIMER
    assert answer["answer"]


def test_local_movement_question():
    result = _result()
    answer = Assistant(AssistantConfig()).answer(
        "summarize the movement", result.summary(), result.geojson()
    )
    assert "mappable points" in answer["answer"].lower()
    assert "km" in answer["answer"].lower()


def test_local_missing_question_flags_gap():
    result = _result()
    answer = Assistant(AssistantConfig()).answer(
        "what is missing?", result.summary(), result.geojson()
    )
    # one row has no coordinates -> a data gap should be surfaced
    assert "gap" in answer["answer"].lower() or "no usable" in \
        answer["answer"].lower()


def test_local_time_question_mentions_display_tz():
    result = _result()
    answer = Assistant(AssistantConfig()).answer(
        "explain the time zones", result.summary(), result.geojson()
    )
    assert "America/Chicago" in answer["answer"]


def test_local_filter_question():
    result = _result()
    answer = Assistant(AssistantConfig()).answer(
        "suggest filters", result.summary(), result.geojson()
    )
    assert "filter" in answer["answer"].lower()


def test_empty_question_gives_overview():
    result = _result()
    answer = Assistant(AssistantConfig()).answer(
        "", result.summary(), result.geojson()
    )
    assert answer["answer"]
    assert answer["disclaimer"] == DISCLAIMER


def _fake_response(content):
    import io

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    import json

    body = json.dumps(
        {"choices": [{"message": {"content": content}}]}
    ).encode()
    return FakeResp(body)


def test_remote_answer_used_when_configured(monkeypatch):
    result = _result()
    assistant = Assistant(AssistantConfig(api_key="sk-test", model="a/b"))

    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["auth"] = request.headers["Authorization"]
        captured["url"] = request.full_url
        return _fake_response("Draft movement summary.")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    answer = assistant.answer(
        "summarize movement", result.summary(), result.geojson()
    )
    assert answer["backend"] == "openrouter"
    assert answer["model"] == "a/b"
    assert answer["answer"] == "Draft movement summary."
    assert answer["disclaimer"] == DISCLAIMER
    assert captured["auth"].startswith("Bearer ")
    assert captured["url"].endswith("/chat/completions")


def test_remote_failure_falls_back_to_local(monkeypatch):
    result = _result()
    assistant = Assistant(AssistantConfig(api_key="sk-test"))

    def boom(request, timeout=None):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    answer = assistant.answer(
        "summarize movement", result.summary(), result.geojson()
    )
    assert answer["backend"] == "local-fallback"
    assert answer["answer"]
    assert answer["disclaimer"] == DISCLAIMER
