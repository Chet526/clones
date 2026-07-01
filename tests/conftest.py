"""Shared pytest fixtures and path setup for GeoBrief LE tests."""

import sys
from pathlib import Path

# Make the src/ layout importable without an editable install.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "sample_data"
