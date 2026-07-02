"""Evidence-integrity hashing.

Every source file imported into a case is hashed with SHA-256 so its
integrity can be demonstrated later (PRD Goal 3 / Module J). The original
bytes are never modified here; we only read them.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Union

_CHUNK_SIZE = 1024 * 1024  # 1 MiB


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest of an in-memory bytes object."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Union[str, Path]) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks.

    Reading in chunks keeps memory flat for large evidence files.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
