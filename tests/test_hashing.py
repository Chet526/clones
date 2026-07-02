"""Tests for evidence-integrity hashing."""

import hashlib

from geobrief.hashing import sha256_bytes, sha256_file


def test_sha256_bytes_matches_hashlib():
    data = b"location evidence"
    assert sha256_bytes(data) == hashlib.sha256(data).hexdigest()


def test_sha256_file_matches_bytes(tmp_path):
    path = tmp_path / "evidence.csv"
    content = b"lat,lon\n1.0,2.0\n"
    path.write_bytes(content)
    assert sha256_file(path) == sha256_bytes(content)


def test_sha256_empty_file(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_bytes(b"")
    assert sha256_file(path) == hashlib.sha256(b"").hexdigest()
