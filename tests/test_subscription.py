"""Tests for subscription plans and feature entitlements."""

from geobrief.subscription import (
    DEFAULT_PLAN_ID,
    PLAN_ENV_VAR,
    Feature,
    current_plan,
    current_plan_id,
    format_price,
    get_plan,
    plan_allows,
    upgrade_target,
)


def test_standard_is_default_and_priced_at_999():
    plan = get_plan(None)
    assert plan.id == DEFAULT_PLAN_ID == "standard"
    assert plan.price_cents == 999
    assert plan.price_dollars == 9.99
    assert plan.price_display == "$9.99/month"


def test_pro_is_priced_at_1499():
    plan = get_plan("pro")
    assert plan.price_cents == 1499
    assert plan.price_display == "$14.99/month"


def test_only_pro_unlocks_the_assistant():
    assert not get_plan("standard").allows(Feature.AI_ASSISTANT)
    assert get_plan("pro").allows(Feature.AI_ASSISTANT)
    # Both plans include the core processing workflow.
    assert get_plan("standard").allows(Feature.CORE_PROCESSING)
    assert get_plan("pro").allows(Feature.CORE_PROCESSING)


def test_unknown_or_malformed_plan_falls_back_to_default():
    assert get_plan("enterprise").id == DEFAULT_PLAN_ID
    assert get_plan("  PRO  ").id == "pro"
    assert get_plan("").id == DEFAULT_PLAN_ID


def test_current_plan_reads_env():
    assert current_plan(env={}).id == "standard"
    assert current_plan(env={PLAN_ENV_VAR: "pro"}).id == "pro"
    assert current_plan_id(env={PLAN_ENV_VAR: "pro"}) == "pro"


def test_plan_allows_reads_env():
    assert not plan_allows(Feature.AI_ASSISTANT, env={})
    assert plan_allows(Feature.AI_ASSISTANT, env={PLAN_ENV_VAR: "pro"})


def test_upgrade_target_points_at_cheapest_plan_with_feature():
    target = upgrade_target(Feature.AI_ASSISTANT)
    assert target is not None
    assert target.id == "pro"
    assert upgrade_target("nonexistent_feature") is None


def test_format_price():
    assert format_price(999) == "$9.99"
    assert format_price(1499) == "$14.99"


def test_plan_to_dict_is_json_friendly():
    data = get_plan("pro").to_dict(current=True)
    assert data["id"] == "pro"
    assert data["price_display"] == "$14.99/month"
    assert data["current"] is True
    assert isinstance(data["features"], list)
    assert Feature.AI_ASSISTANT in data["features"]
