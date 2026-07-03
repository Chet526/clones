"""Shared pytest fixtures and path setup for GeoBrief LE tests."""

import sys
from pathlib import Path

import pytest

# Make the src/ layout importable without an editable install.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "sample_data"

# Environment variables that could leak real billing/assistant config into a
# test run. Cleared by default so tests are deterministic and never contact a
# real Stripe/OpenRouter account.
_ISOLATED_ENV_VARS = (
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_STANDARD",
    "STRIPE_PRICE_PRO",
    "STRIPE_SUCCESS_URL",
    "STRIPE_CANCEL_URL",
    "STRIPE_API_BASE",
    "STRIPE_WEBHOOK_TOLERANCE",
    "GEOBRIEF_PLAN",
    "GEOBRIEF_LICENSE_KEY",
    "GEOBRIEF_LICENSE_SECRET",
)


@pytest.fixture(autouse=True)
def isolated_billing_env(tmp_path, monkeypatch):
    """Point billing state at a temp file and clear real billing config.

    Keeps every test hermetic: the subscription store starts empty and no
    Stripe/plan environment from the host process bleeds into assertions.
    """
    for name in _ISOLATED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(
        "GEOBRIEF_BILLING_STORE", str(tmp_path / "billing.json")
    )
    monkeypatch.setenv("GEOBRIEF_HOME", str(tmp_path / "geobrief_home"))
    yield

