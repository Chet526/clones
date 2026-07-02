"""Training mode support (PRD Module N).

Training mode lets an investigator practice the full workflow on clearly
fake, bundled sample data. Outputs produced in training mode carry a
watermark so a practice map or report can never be mistaken for real
evidence.
"""

from __future__ import annotations

from pathlib import Path

TRAINING_NOTICE = (
    "TRAINING MODE — practice data, not real evidence. "
    "Do not use in a report or court filing."
)

TRAINING_SAMPLE_FILENAME = "training_sample.csv"
_DATA_DIR = Path(__file__).parent / "data"


def training_sample_bytes() -> bytes:
    """The bundled, clearly fake practice file."""
    return (_DATA_DIR / TRAINING_SAMPLE_FILENAME).read_bytes()
