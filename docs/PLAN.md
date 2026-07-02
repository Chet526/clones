# GeoBrief LE — Project Status & Completion Plan

_Last updated: 2026-07-02_

This document assesses where the project stands today and lays out a concrete plan to complete it, phase by phase, against the roadmap in [`docs/PRD.md`](https://github.com/Chet526/clones/blob/copilot/upload-prd/docs/PRD.md) (currently on PR #1).

---

## 1. Where we are

### Repository state

| Branch / PR | Contents | Status |
|---|---|---|
| `main` | Empty (README stub only) | Nothing merged yet |
| PR [#1](https://github.com/Chet526/clones/pull/1) (`copilot/upload-prd`) | Full Phase 1 prototype + PRD + extras | Open **draft**, all 82 tests passing |
| PR [#2](https://github.com/Chet526/clones/pull/2) (this branch) | This plan | Open |

**Key takeaway:** all product work lives on PR #1 and is unmerged. Nothing ships until it lands on `main`.

### What is built (verified working on PR #1 — `pip install -e .` + `pytest`: 82/82 pass)

**Phase 1 (Prototype) — ✅ complete**

- CSV/XLSX/XLS upload & ingest (`ingest.py`) — cells preserved as text
- SHA-256 evidence hashing, read-only originals (`hashing.py`)
- Coordinate/timestamp/accuracy column detection with confidence levels (`detection.py`)
- Time-zone intelligence: ISO 8601 / epoch s+ms / naive / offset → UTC + display zone (`timezones.py`)
- Cleaning engine — rows flagged, never dropped; duplicate/reversal/accuracy/tz flags (`cleaning.py`)
- Pipeline producing plain-English summary, cleaned CSV, JSON report, GeoJSON (`pipeline.py`)
- CLI: `process`, `ask`, `serve` (`__main__.py`)
- Local FastAPI web app with Leaflet map, accuracy circles, per-point popups, downloads (`webapp/`)
- Sample data + unit and end-to-end tests

**Built ahead of roadmap (monetization & AI)**

- Two subscription plans (Standard $9.99 / Pro $14.99, `subscription.py`)
- Real Stripe billing: checkout, signature-verified webhooks, JSON subscription store (`billing.py`)
- Investigator AI assistant: local rule-based default, optional OpenRouter model; Pro-gated (`assistant.py`)

### What is **not** built yet (per PRD roadmap)

- Phase 2 (MVP): case workspace, guided wizard w/ manual column mapping, time-zone confirmation step, KML/Google Earth export, PDF processing report, audit log, training mode
- Phase 3 (Beta): provider parsers (Google, Snapchat, Meta, carrier, tower dump), timeline animation, court exhibit builder, agency branding
- Phase 4 (Agency): accounts, RBAC, admin panel, MFA, encrypted case vault, legal-process guide
- Phase 5 (Advanced): live ping, mobile companion, collaboration, cloud-optional mode, SSO, CAD/RMS

---

## 2. Plan for completion

### Milestone 0 — Ship what exists (immediate)

1. **Review and merge PR #1 into `main`.** It is a passing, self-contained Phase 1 prototype; keeping it as an ever-growing draft blocks everything downstream.
2. Mark PR #1 ready-for-review, resolve any review feedback, merge.
3. Add CI (GitHub Actions: `pip install -e .` + `pytest` on push/PR) so future work is gated automatically.
4. Tag `v0.1.0` (Phase 1 prototype).

### Milestone 1 — Phase 2: MVP (`v0.2.0`)

Work items, roughly in dependency order (one focused PR each):

1. **Case workspace** — create/open cases; per-case folder with originals, hashes, outputs (Module A)
2. **Audit log** — append-only per-case log of every ingest/clean/export action (Module J; foundation for court defensibility, so do it early)
3. **Guided wizard + manual column mapping** — confirm/override detected columns and time zone in the web UI before processing (Modules C, E)
4. **KML export** — Google Earth output alongside GeoJSON (Module H)
5. **PDF processing report** — printable report of summary, flags, hashes, methodology (Module I)
6. **Training mode** — bundled sample cases with guided walkthrough (Module N)
7. **Validation warnings surfaced in UI** — expose existing cleaning flags as pre-map confirmations

### Milestone 2 — Phase 3: Beta (`v0.3.0`)

1. **Provider parser framework** (Module K) — pluggable templates, then parsers in order of investigator demand: Google → carrier → Meta → Snapchat → tower dump
2. **Timeline + animation** (Module G)
3. **Court exhibit builder** (Module I extension)
4. **Agency branding** on reports/exhibits

### Milestone 3 — Phase 4: Agency version (`v0.4.0`)

1. User accounts, role-based access, admin panel, MFA (Module O)
2. Encrypted case vault (encryption at rest, PRD §10)
3. Legal-process guide beta (Module L)
4. Parser update system
5. Wire the existing Stripe billing to real account entitlements (today entitlement is env-var based)

### Milestone 4 — Phase 5: Advanced (`v1.0+`)

Live ping module, mobile companion, team collaboration, prosecutor viewer, cloud-optional mode, SSO, CAD/RMS integration, advanced tower/cell analysis — scope each only after Phase 4 is in users' hands.

---

## 3. Working agreements

- **One milestone item per PR**, branched from `main`, with tests; keep the 100%-green suite green.
- Update the PRD if scope decisions change; treat `docs/PRD.md` as the source of truth.
- Local-first and clean-room rules (PRD §2, §10) apply to every feature — no telemetry, originals never modified, everything hash-verified.

## 4. Immediate next actions

1. ☐ Merge PR #1 (unblocks everything)
2. ☐ Add CI workflow
3. ☐ Tag `v0.1.0`
4. ☐ Open tracking issues for the seven Phase 2 work items above
