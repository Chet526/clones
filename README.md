# GeoBrief LE

**Turn location records into maps, timelines, and reports.**

GeoBrief LE is a local-first tool that helps investigators turn confusing
location records (spreadsheets, provider returns, phone/app records) into a
cleaned data set, a map, and report-ready outputs — without needing GIS
training or advanced spreadsheet skills.

> This repository currently implements the **Phase 1 prototype** from the
> [product requirements document](docs/PRD.md). See the roadmap in the PRD for
> what comes next.

## What Phase 1 does

Upload a CSV or Excel file and GeoBrief LE will:

- **Hash the original file** (SHA-256) for evidence integrity — the source
  file is only read, never altered.
- **Auto-detect** latitude, longitude, timestamp, and accuracy columns, with a
  confidence level for each.
- **Clean and validate** every row: parse coordinates, normalize timestamps to
  UTC, convert to a display time zone, and flag missing, invalid, duplicate,
  low-accuracy, reversed, or time-zone-uncertain points — **without ever
  deleting rows**.
- **Produce outputs**: an interactive map, a cleaned spreadsheet (CSV), a JSON
  processing summary, and map-ready GeoJSON.

## Requirements

- Python 3.10+

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .            # or: pip install -r requirements.txt
```

## Use it — web app (guided wizard)

```bash
python -m geobrief serve
```

Then open <http://127.0.0.1:8000>, choose a file, pick a display time zone,
and click **Process file**. Your data never leaves your machine.

## Use it — command line

```bash
python -m geobrief process sample_data/sample_locations.csv \
    --tz America/Chicago --out ./out
```

This writes `*_cleaned.csv`, `*_summary.json`, and `*_points.geojson` next to
the input (or into `--out`).

## Ask the AI assistant

An investigator assistant helps you make sense of the processed data — in the
web app (Step 5, "Ask the assistant") or from the command line:

```bash
python -m geobrief ask sample_data/sample_locations.csv "summarize the movement" \
    --tz America/Chicago
```

Try questions like *"explain this data"*, *"what is missing?"*, *"summarize the
movement"*, *"explain the time zones"*, or *"suggest filters"*.

> **The AI assistant is a Pro-plan feature.** See [Plans & pricing](#plans--pricing).
> In the web app the assistant endpoints require the Pro plan; the Standard
> plan shows an upgrade prompt instead.

**Local-first by default.** With no configuration the assistant answers
entirely on your machine from the processing summary — nothing leaves the
computer. To enable a hosted model via [OpenRouter](https://openrouter.ai),
set these environment variables (they can be supplied later, no code change
needed):

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | API key; enables the hosted model | *(unset → local)* |
| `OPENROUTER_MODEL` | Model slug | `openrouter/auto` |
| `OPENROUTER_BASE_URL` | API base URL | `https://openrouter.ai/api/v1` |
| `GEOBRIEF_ASSISTANT_ENABLED` | Force the hosted model on/off | follows key |

When a key is set, only an **aggregate** analysis context (counts, time range,
missing fields, a movement summary, and a small sample of points) is sent —
never the full record set. Every answer carries the notice: *"Draft language
generated from processed records. Investigator must verify before use."* The
assistant assists, it never decides.

## Plans &amp; pricing

GeoBrief LE is offered on two monthly plans:

| Plan | Price | Includes |
| --- | --- | --- |
| **Standard** | **$9.99/month** | Core workflow: upload, clean & validate, SHA-256 hashing, interactive map, and CSV / JSON / GeoJSON downloads |
| **Pro** | **$14.99/month** | Everything in Standard **plus** the investigator AI assistant |

The **investigator AI assistant is the Pro upsell** — it is only available on
the Pro plan. The active plan is selected with the `GEOBRIEF_PLAN` environment
variable (`standard` by default):

```bash
GEOBRIEF_PLAN=pro python -m geobrief serve   # unlock the AI assistant
```

The web app shows both plans (Step "Plans & pricing"), marks the active plan,
and exposes them at `GET /api/plans`. When the assistant is requested on the
Standard plan, `GET /api/assistant/status` and `POST /api/assistant` return
`402 Payment Required` with an upgrade prompt.

### Real billing (Stripe)

For a live product, entitlements come from real Stripe subscriptions instead of
`GEOBRIEF_PLAN`. Create two recurring **Prices** in Stripe (one per plan) and
configure the server with these environment variables:

| Variable | Purpose |
| --- | --- |
| `STRIPE_SECRET_KEY` | Secret API key; enables Checkout. |
| `STRIPE_WEBHOOK_SECRET` | Signing secret used to verify webhook events. |
| `STRIPE_PRICE_STANDARD` | Stripe Price id for the $9.99 Standard plan. |
| `STRIPE_PRICE_PRO` | Stripe Price id for the $14.99 Pro plan. |
| `STRIPE_SUCCESS_URL` / `STRIPE_CANCEL_URL` | Post-checkout redirect URLs. |
| `GEOBRIEF_BILLING_STORE` | Path to the subscription-state JSON file. |

Endpoints:

* `POST /api/billing/checkout` `{ "plan": "pro" }` → creates a Stripe Checkout
  Session and returns its `url`; the pricing UI redirects the customer there.
* `POST /api/billing/webhook` → receives Stripe events. The `Stripe-Signature`
  header is verified (HMAC-SHA256, constant-time compare, replay window) before
  the payload is trusted; `checkout.session.completed` and
  `customer.subscription.*` events update the active plan.
* `GET /api/billing/status` → reports whether billing is configured and the
  currently entitled plan.

Point a Stripe webhook endpoint at `/api/billing/webhook` (the signing secret
it gives you is `STRIPE_WEBHOOK_SECRET`). When a subscription is active the
plan is resolved from Stripe; with no active subscription the server falls back
to `GEOBRIEF_PLAN` (defaulting to Standard) for local development. The secret
key is only used server-side and is never sent to the browser. No extra Python
dependency is added — Stripe calls and signature verification use the standard
library.

## Use it — as a library

```python
from geobrief import process_file

result = process_file("records.csv", display_timezone="America/Chicago")
print(result.summary()["plain_english"])
result.cleaned_csv()   # cleaned spreadsheet as text
result.geojson()       # map-ready points
result.summary_json()  # processing report
```

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

## Project layout

```
src/geobrief/
  hashing.py     SHA-256 evidence hashing
  ingest.py      CSV / XLSX / XLS intake (values preserved as text)
  detection.py   coordinate / timestamp / accuracy column detection
  timezones.py   timestamp parsing + UTC/display conversion
  cleaning.py    cleaning & validation engine
  pipeline.py    orchestration + summary / CSV / GeoJSON exports
  assistant.py   investigator AI assistant (OpenRouter + local fallback)
  subscription.py plans, pricing, and feature entitlements (AI = Pro)
  billing.py     Stripe checkout, signed webhooks, subscription state
  webapp/        local FastAPI app + guided UI (Leaflet map)
docs/PRD.md      full product requirements document
sample_data/     example input file
tests/           unit + end-to-end tests
```

## Notes on scope

Phase 1 intentionally excludes case accounts, cloud collaboration, provider
parser templates, PDF exhibits, and the legal-process guide. Those are later
phases in the [PRD](docs/PRD.md). Draft outputs must always be verified by the
investigator before use.