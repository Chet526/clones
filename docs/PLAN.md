# GeoBrief LE — Project Status & Completion Plan

_Last updated: 2026-07-15_

This document reflects the current repository state and tracks phased delivery against the roadmap in `docs/PRD.md`.

---

## 1. Current status

### Phase 1 (Prototype) — ✅ Completed

Implemented and validated in this repository:

- CSV/XLSX/XLS upload and ingest (`ingest.py`)
- SHA-256 source hashing with read-only originals (`hashing.py`)
- Coordinate/timestamp/accuracy detection (`detection.py`)
- Time parsing and UTC/display timezone normalization (`timezones.py`)
- Cleaning and validation engine with row flagging (no row deletion) (`cleaning.py`)
- Pipeline outputs: plain-English summary, cleaned CSV, JSON report, GeoJSON (`pipeline.py`)
- CLI commands: `process`, `ask`, `serve` (`__main__.py`)
- Local web app for upload, review, map, and downloads (`webapp/`)
- Test suite passing (`pytest`: 82 passed)

Additional capabilities delivered ahead of later roadmap items:

- Subscription plans and feature entitlements (`subscription.py`)
- Stripe checkout + signed webhooks + local subscription state (`billing.py`)
- Investigator AI assistant with local-first behavior and optional OpenRouter (`assistant.py`)

### Phase 1 baseline hardening — ✅ Completed

- GitHub Actions CI at `.github/workflows/ci.yml`
- CI runs on pull requests and pushes to `main`
- Python matrix: 3.10, 3.11, 3.12
- Install step: `python -m pip install -e ".[dev]"`
- Test step: `pytest -v --tb=short`
- Least-privilege workflow permissions: `contents: read`
- Pip cache enabled for faster workflow runs

---

## 2. Three-phase completion path

### Phase 1 — Stabilize baseline (Done)

- [x] Verify project setup and full test pass
- [x] Add and harden CI test workflow
- [x] Update project planning status to current reality

### Phase 2 — MVP completion (Done)

- [x] Case workspace
- [x] Audit log
- [x] Guided wizard improvements (manual mapping + timezone confirmation)
- [x] Validation warnings surfaced in UI
- [x] KML export
- [x] PDF processing report
- [x] Training mode

### Phase 3 — Post-market expansion roadmap

- [ ] Beta scope: provider parser framework/parsers, timeline animation, court exhibit builder, agency branding
- [ ] Agency scope: accounts, RBAC, admin, MFA, encrypted vault, legal-process guide, parser update system
- [ ] Advanced scope: live ping, mobile companion, team collaboration, cloud-optional mode, SSO, CAD/RMS integration

---

## 3. Next actions

1. Keep CI green and stabilize the market MVP.
2. Sequence post-market Phase 3 work by customer demand and risk.
3. Reassess roadmap status after each major expansion release.
