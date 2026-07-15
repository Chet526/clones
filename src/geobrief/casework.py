"""Case workspace and audit-log storage for local-first operation."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str, *, fallback: str = "case") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return text or fallback


@dataclass
class CaseStore:
    """Filesystem-backed case workspace."""

    root: Path

    @classmethod
    def from_env(cls) -> "CaseStore":
        import os

        configured = os.getenv("GEOBRIEF_CASES_DIR", "").strip()
        if configured:
            root = Path(configured).expanduser()
        else:
            root = Path.home() / ".geobrief" / "cases"
        return cls(root=root)

    def _case_dir(self, case_id: str) -> Path:
        return self.root / case_id

    def _case_file(self, case_id: str) -> Path:
        return self._case_dir(case_id) / "case.json"

    def _audit_file(self, case_id: str) -> Path:
        return self._case_dir(case_id) / "audit.jsonl"

    def create_case(self, metadata: dict[str, Any]) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        case_number = str(metadata.get("case_number", "")).strip()
        agency_name = str(metadata.get("agency_name", "")).strip()
        slug = _slug(case_number or agency_name or "case")
        case_id = f"{slug}-{uuid.uuid4().hex[:8]}"
        case_dir = self._case_dir(case_id)
        case_dir.mkdir(parents=True, exist_ok=False)

        record = {
            "case_id": case_id,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "metadata": {
                "case_number": case_number,
                "agency_name": agency_name,
                "investigator_name": str(
                    metadata.get("investigator_name", "")
                ).strip(),
                "offense_type": str(metadata.get("offense_type", "")).strip(),
                "suspect_identifier": str(
                    metadata.get("suspect_identifier", "")
                ).strip(),
                "victim_identifier": str(
                    metadata.get("victim_identifier", "")
                ).strip(),
                "device_identifiers": str(
                    metadata.get("device_identifiers", "")
                ).strip(),
                "notes": str(metadata.get("notes", "")).strip(),
                "training_mode": bool(metadata.get("training_mode", False)),
            },
        }
        self._case_file(case_id).write_text(
            json.dumps(record, indent=2), encoding="utf-8"
        )
        self.log_event(case_id, "case_created", {"metadata": record["metadata"]})
        return record

    def get_case(self, case_id: str) -> dict[str, Any]:
        path = self._case_file(case_id)
        if not path.exists():
            raise FileNotFoundError(case_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def list_cases(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        out: list[dict[str, Any]] = []
        for child in sorted(self.root.iterdir()):
            if not child.is_dir():
                continue
            case_file = child / "case.json"
            if not case_file.exists():
                continue
            try:
                out.append(json.loads(case_file.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return out

    def log_event(self, case_id: str, event_type: str, details: dict[str, Any]) -> None:
        case = self.get_case(case_id)
        case["updated_at"] = _utc_now()
        self._case_file(case_id).write_text(
            json.dumps(case, indent=2), encoding="utf-8"
        )
        event = {
            "timestamp": _utc_now(),
            "event_type": event_type,
            "details": details,
        }
        audit_path = self._audit_file(case_id)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")

    def read_audit(self, case_id: str) -> list[dict[str, Any]]:
        path = self._audit_file(case_id)
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events
