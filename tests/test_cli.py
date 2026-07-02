"""Tests for the ``python -m geobrief ask`` CLI command."""

from geobrief.__main__ import main
from conftest import SAMPLE_DIR

SAMPLE = SAMPLE_DIR / "sample_locations.csv"


def test_ask_command_runs_locally(capsys):
    code = main(
        ["ask", str(SAMPLE), "summarize the movement", "--tz",
         "America/Chicago"]
    )
    assert code == 0
    out = capsys.readouterr()
    assert out.out.strip()
    # The mandatory verification disclaimer must always be printed.
    assert "verify before use" in out.out


def test_ask_command_missing_file():
    code = main(["ask", "does_not_exist.csv", "explain this data"])
    assert code == 2
