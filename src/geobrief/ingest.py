"""File intake for GeoBrief LE (PRD Module B).

Phase 1 supports CSV, XLSX and XLS. Files are read as *text* (dtype=str)
so the original values are preserved exactly and never coerced/altered
during load — cleaning happens later and keeps the originals intact.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Union

import pandas as pd

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


class UnsupportedFileTypeError(ValueError):
    """Raised when a file extension is not supported in Phase 1."""


def _read_csv(source: Union[str, Path, io.BytesIO]) -> pd.DataFrame:
    # keep_default_na=False so empty cells stay as "" rather than NaN,
    # which keeps original values faithful and avoids float coercion.
    return pd.read_csv(
        source,
        dtype=str,
        keep_default_na=False,
        skip_blank_lines=False,
    )


def _read_excel(source: Union[str, Path, io.BytesIO]) -> pd.DataFrame:
    return pd.read_excel(source, dtype=str, keep_default_na=False)


def read_dataframe(path: Union[str, Path]) -> pd.DataFrame:
    """Read a supported file from disk into a string DataFrame."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{ext}'. Phase 1 supports: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )
    if ext == ".csv":
        return _read_csv(path)
    return _read_excel(path)


def read_dataframe_from_bytes(data: bytes, filename: str) -> pd.DataFrame:
    """Read a supported file from an in-memory bytes buffer (uploads)."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{ext}'. Phase 1 supports: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS))
        )
    buffer = io.BytesIO(data)
    if ext == ".csv":
        return _read_csv(buffer)
    return _read_excel(buffer)
