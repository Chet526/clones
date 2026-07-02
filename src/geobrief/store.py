"""Case workspace and audit log (PRD Modules A and J, Section 13).

A small SQLite-backed store, local by default, that gives every
investigation a case record, registers imported source files (originals
are copied byte-for-byte and never altered), records exports, and keeps
a tamper-evident audit log.

Audit events form a hash chain: every event's ``immutable_hash`` is the
SHA-256 of the previous event's hash plus the event payload, so any
edit or deletion inside the chain is detectable with
:meth:`CaseStore.verify_audit_chain`.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from .hashing import sha256_bytes

DEFAULT_HOME_ENV = "GEOBRIEF_HOME"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number TEXT NOT NULL,
    agency TEXT NOT NULL DEFAULT '',
    investigator TEXT NOT NULL DEFAULT '',
    offense_type TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_files (
    source_file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(case_id),
    original_filename TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    sha256_hash TEXT NOT NULL,
    imported_by TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL,
    storage_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exports (
    export_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(case_id),
    export_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    generated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    audit_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(case_id),
    event_type TEXT NOT NULL,
    event_details TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    immutable_hash TEXT NOT NULL
);
"""

_GENESIS_HASH = "0" * 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_home() -> Path:
    """Directory holding the local case database and original files."""
    env = os.environ.get(DEFAULT_HOME_ENV)
    if env:
        return Path(env)
    return Path.home() / ".geobrief"


class CaseStore:
    """Local SQLite case workspace (cases, source files, exports, audit)."""

    def __init__(self, home: Union[str, Path, None] = None) -> None:
        self.home = Path(home) if home else default_home()
        self.home.mkdir(parents=True, exist_ok=True)
        self.originals_dir = self.home / "originals"
        self.originals_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.home / "geobrief.db"
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "CaseStore":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # --- Cases ------------------------------------------------------------
    def create_case(
        self,
        case_number: str,
        *,
        agency: str = "",
        investigator: str = "",
        offense_type: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        if not case_number.strip():
            raise ValueError("A case number is required.")
        now = _now()
        cursor = self._conn.execute(
            "INSERT INTO cases (case_number, agency, investigator, "
            "offense_type, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                case_number.strip(),
                agency,
                investigator,
                offense_type,
                notes,
                now,
                now,
            ),
        )
        case_id = cursor.lastrowid
        self.log_event(
            case_id,
            "case_created",
            {"case_number": case_number.strip(), "investigator": investigator},
        )
        self._conn.commit()
        return self.get_case(case_id)

    def get_case(self, case_id: int) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"No case with id {case_id}.")
        return dict(row)

    def list_cases(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM cases ORDER BY case_id"
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Source files -----------------------------------------------------
    def add_source_file(
        self,
        case_id: int,
        filename: str,
        data: bytes,
        *,
        imported_by: str = "",
    ) -> dict[str, Any]:
        """Register (and preserve a byte-for-byte copy of) a source file."""
        self.get_case(case_id)  # raises for unknown case
        digest = sha256_bytes(data)
        safe_name = Path(filename).name or "upload"
        storage_path = self.originals_dir / f"{digest[:16]}_{safe_name}"
        if not storage_path.exists():
            # Never overwrite a stored original.
            storage_path.write_bytes(data)
        now = _now()
        cursor = self._conn.execute(
            "INSERT INTO source_files (case_id, original_filename, "
            "file_size, sha256_hash, imported_by, imported_at, storage_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                case_id,
                safe_name,
                len(data),
                digest,
                imported_by,
                now,
                str(storage_path),
            ),
        )
        source_file_id = cursor.lastrowid
        self.log_event(
            case_id,
            "file_imported",
            {
                "source_file_id": source_file_id,
                "filename": safe_name,
                "file_size": len(data),
            },
        )
        self.log_event(
            case_id,
            "file_hashed",
            {"source_file_id": source_file_id, "sha256": digest},
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM source_files WHERE source_file_id = ?",
            (source_file_id,),
        ).fetchone()
        return dict(row)

    def list_source_files(self, case_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM source_files WHERE case_id = ? "
            "ORDER BY source_file_id",
            (case_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Exports ------------------------------------------------------------
    def record_export(
        self, case_id: int, export_type: str, filename: str
    ) -> dict[str, Any]:
        self.get_case(case_id)
        now = _now()
        cursor = self._conn.execute(
            "INSERT INTO exports (case_id, export_type, filename, "
            "generated_at) VALUES (?, ?, ?, ?)",
            (case_id, export_type, filename, now),
        )
        export_id = cursor.lastrowid
        self.log_event(
            case_id,
            "export_generated",
            {
                "export_id": export_id,
                "export_type": export_type,
                "filename": filename,
            },
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM exports WHERE export_id = ?", (export_id,)
        ).fetchone()
        return dict(row)

    def list_exports(self, case_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM exports WHERE case_id = ? ORDER BY export_id",
            (case_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Audit log ----------------------------------------------------------
    def _last_audit_hash(self, case_id: int) -> str:
        row = self._conn.execute(
            "SELECT immutable_hash FROM audit_events WHERE case_id = ? "
            "ORDER BY audit_event_id DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        return row["immutable_hash"] if row else _GENESIS_HASH

    def log_event(
        self,
        case_id: int,
        event_type: str,
        details: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Append a tamper-evident event to the case audit chain."""
        timestamp = _now()
        payload = json.dumps(details or {}, sort_keys=True)
        previous = self._last_audit_hash(case_id)
        immutable_hash = hashlib.sha256(
            f"{previous}|{case_id}|{event_type}|{payload}|{timestamp}".encode()
        ).hexdigest()
        cursor = self._conn.execute(
            "INSERT INTO audit_events (case_id, event_type, event_details, "
            "timestamp, immutable_hash) VALUES (?, ?, ?, ?, ?)",
            (case_id, event_type, payload, timestamp, immutable_hash),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM audit_events WHERE audit_event_id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return self._event_dict(row)

    @staticmethod
    def _event_dict(row: sqlite3.Row) -> dict[str, Any]:
        event = dict(row)
        event["event_details"] = json.loads(event["event_details"])
        return event

    def audit_log(self, case_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM audit_events WHERE case_id = ? "
            "ORDER BY audit_event_id",
            (case_id,),
        ).fetchall()
        return [self._event_dict(r) for r in rows]

    def verify_audit_chain(self, case_id: int) -> bool:
        """Recompute the hash chain; False means the log was tampered with."""
        previous = _GENESIS_HASH
        rows = self._conn.execute(
            "SELECT * FROM audit_events WHERE case_id = ? "
            "ORDER BY audit_event_id",
            (case_id,),
        ).fetchall()
        for row in rows:
            expected = hashlib.sha256(
                f"{previous}|{row['case_id']}|{row['event_type']}|"
                f"{row['event_details']}|{row['timestamp']}".encode()
            ).hexdigest()
            if expected != row["immutable_hash"]:
                return False
            previous = row["immutable_hash"]
        return True
