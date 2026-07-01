"""Subscription plans and feature entitlements for GeoBrief LE.

GeoBrief LE is offered on two monthly plans:

* **Standard — $9.99/month.** The core workflow: upload a file, clean and
  validate the records, view them on a map, and download the cleaned CSV,
  JSON summary, and GeoJSON.
* **Pro — $14.99/month.** Everything in Standard *plus* the investigator AI
  assistant, which answers plain-English questions about the processed data.

The AI assistant is the paid upsell: it is only available on the Pro plan.
Feature access is expressed through *entitlements* — named capabilities that a
plan grants. The rest of the application asks
:func:`plan_allows` / :meth:`Plan.allows` instead of hard-coding plan names, so
new plans or features can be added in one place.

The active plan is read from the ``GEOBRIEF_PLAN`` environment variable and
defaults to Standard, matching the entry-level price point. Pricing is stored
in integer cents to avoid floating-point rounding surprises.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "Feature",
    "Plan",
    "PLANS",
    "DEFAULT_PLAN_ID",
    "PLAN_ENV_VAR",
    "get_plan",
    "current_plan",
    "current_plan_id",
    "plan_allows",
    "upgrade_target",
    "format_price",
]

# Environment variable that selects the active plan.
PLAN_ENV_VAR = "GEOBRIEF_PLAN"

# Entitlement identifiers. Kept as plain strings so payloads stay JSON-friendly.
class Feature:
    """Named capabilities a plan can grant."""

    CORE_PROCESSING = "core_processing"
    AI_ASSISTANT = "ai_assistant"


@dataclass(frozen=True)
class Plan:
    """A subscription tier: its price and the features it unlocks."""

    id: str
    name: str
    price_cents: int
    tagline: str
    features: frozenset = field(default_factory=frozenset)
    highlights: tuple = ()

    @property
    def price_dollars(self) -> float:
        """Monthly price as a float in dollars (e.g. ``9.99``)."""
        return self.price_cents / 100

    @property
    def price_display(self) -> str:
        """Human-readable monthly price, e.g. ``"$9.99/month"``."""
        return f"{format_price(self.price_cents)}/month"

    def allows(self, feature: str) -> bool:
        """True when this plan grants ``feature``."""
        return feature in self.features

    def to_dict(self, *, current: bool = False) -> dict:
        """JSON-serialisable view of the plan for the API/front-end."""
        return {
            "id": self.id,
            "name": self.name,
            "price_cents": self.price_cents,
            "price_dollars": round(self.price_dollars, 2),
            "price_display": self.price_display,
            "tagline": self.tagline,
            "features": sorted(self.features),
            "highlights": list(self.highlights),
            "current": current,
        }


def format_price(cents: int) -> str:
    """Format a price in integer cents as a dollar string, e.g. ``"$9.99"``."""
    return f"${cents / 100:,.2f}"


# The plan catalogue. Order is presentation order (cheapest first).
_STANDARD = Plan(
    id="standard",
    name="Standard",
    price_cents=999,
    tagline="Everything you need to turn location records into maps and reports.",
    features=frozenset({Feature.CORE_PROCESSING}),
    highlights=(
        "Upload CSV or Excel location records",
        "Automatic cleaning, validation, and SHA-256 hashing",
        "Interactive map with accuracy circles",
        "Download cleaned CSV, JSON summary, and GeoJSON",
    ),
)

_PRO = Plan(
    id="pro",
    name="Pro",
    price_cents=1499,
    tagline="Everything in Standard, plus the investigator AI assistant.",
    features=frozenset({Feature.CORE_PROCESSING, Feature.AI_ASSISTANT}),
    highlights=(
        "Everything in Standard",
        "Investigator AI assistant to explain and summarize your data",
        "Ask plain-English questions about movement, gaps, and time zones",
        "Local-first answers by default; optional hosted model",
    ),
)

PLANS: tuple = (_STANDARD, _PRO)

DEFAULT_PLAN_ID = _STANDARD.id

_PLANS_BY_ID = {plan.id: plan for plan in PLANS}


def get_plan(plan_id: Optional[str]) -> Plan:
    """Return the plan for ``plan_id``, falling back to the default plan.

    Lookup is case-insensitive and tolerant of surrounding whitespace so an
    unset or malformed ``GEOBRIEF_PLAN`` value degrades gracefully to Standard
    rather than raising.
    """
    if plan_id is None:
        return _PLANS_BY_ID[DEFAULT_PLAN_ID]
    normalized = plan_id.strip().lower()
    return _PLANS_BY_ID.get(normalized, _PLANS_BY_ID[DEFAULT_PLAN_ID])


def current_plan(env: Optional[dict] = None) -> Plan:
    """Return the active plan, selected by the ``GEOBRIEF_PLAN`` env var."""
    source = os.environ if env is None else env
    return get_plan(source.get(PLAN_ENV_VAR))


def current_plan_id(env: Optional[dict] = None) -> str:
    """Return the id of the active plan."""
    return current_plan(env).id


def plan_allows(feature: str, env: Optional[dict] = None) -> bool:
    """True when the active plan grants ``feature``."""
    return current_plan(env).allows(feature)


def upgrade_target(feature: str) -> Optional[Plan]:
    """Return the cheapest plan that grants ``feature``, if any.

    Used to build upsell messaging that points at the right plan to buy.
    """
    candidates = [plan for plan in PLANS if plan.allows(feature)]
    if not candidates:
        return None
    return min(candidates, key=lambda plan: plan.price_cents)
