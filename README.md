# GeoBrief LE

**Turn location records into maps, timelines, and reports.**

GeoBrief LE is a local-first tool that helps investigators turn confusing
location records (spreadsheets, provider returns, phone/app records) into a
cleaned data set, a map, and report-ready outputs — without needing GIS
training or advanced spreadsheet skills.

> This repository implements the **Phase 1 prototype** and the **Phase 2
> MVP features** from the [product requirements document](docs/PRD.md). See
> the roadmap in the PRD for what comes next.

## What it does

Upload location records in almost any common format — **CSV, TSV/TXT, Excel,
JSON, GeoJSON, KML/KMZ (Google Earth), GPX, or a ZIP of any of these** — and
GeoBrief LE will:

- **Hash the original file** (SHA-256) for evidence integrity — the source
  file is only read, never altered.
- **Auto-detect** latitude, longitude, timestamp, and accuracy columns, with a
  confidence level for each — and let you **manually map columns** when
  detection is wrong or unsure.
- **Clean and validate** every row: parse coordinates, normalize timestamps to
  UTC, convert to a display time zone, and flag missing, invalid, duplicate,
  low-accuracy, reversed, or time-zone-uncertain points — **without ever
  deleting rows**.
- **Produce outputs**: an interactive map with a **date/time filter** and
  **street / satellite / hybrid views**, a cleaned spreadsheet (CSV), a JSON
  processing summary, map-ready GeoJSON, a **Google Earth KML file**, and a
  **PDF processing report** with hashes, counts, warnings, and a time-zone
  statement.
- **Keep a case workspace**: create local cases, register imported files
  (originals preserved byte-for-byte), record exports, and maintain a
  **tamper-evident audit log** (SHA-256 hash chain).
- **Training mode**: practice the whole workflow on bundled fake data — every
  training output is clearly watermarked.

## Requirements

- Python 3.10+

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .            # or: pip install -r requirements.txt
```

### Public install channel (current)

The storefront currently points to the **source install** channel:

```bash
python -m pip install "git+https://github.com/Chet526/clones.git@51fa5e730266bf1552347a99c8c8bf97cf2617dd"
```

This pin is an immutable commit SHA for reproducible installs. Update it only
through the documented release process in
[`docs/GO_LIVE_RUNBOOK.md`](docs/GO_LIVE_RUNBOOK.md).

PyPI publishing is optional and can be added later as a separate release
channel.

### Or run with Docker

```bash
cp .env.example .env        # fill in what you need (all values optional)
docker compose up --build   # serves http://localhost:8000, data on a volume
```

All configuration is by environment variable — see [.env.example](.env.example)
for the complete annotated list. Never commit a real `.env`.

### Self-host API access control (recommended)

When the server is reachable beyond localhost, enable API token auth:

```bash
export GEOBRIEF_API_AUTH_MODE=token
export GEOBRIEF_API_TOKEN="<long-random-token>"
```

In `token` mode, protected `/api/*` endpoints require either:

* `Authorization: Bearer <token>`, or
* `x-api-key: <token>`

Stripe webhooks (`/api/billing/webhook`) remain signature-authenticated via
`STRIPE_WEBHOOK_SECRET` and do not require the API token.

## Use it — web app (guided wizard)

```bash
python -m geobrief serve
```

Then open <http://127.0.0.1:8000> and follow the wizard: choose a file (or
click **Practice with sample data** for training mode), confirm the detected
columns, pick a display time zone, and click **Process file**. You can
optionally attach the upload to a case. Your data never leaves your machine.

## Use it — command line

```bash
python -m geobrief process sample_data/sample_locations.csv \
    --tz America/Chicago --out ./out
```

This writes `*_cleaned.csv`, `*_summary.json`, `*_points.geojson`, `*.kml`
(Google Earth), and `*_report.pdf` next to the input (or into `--out`).
Add `--training` to watermark all outputs as practice data.

### Case workspace and audit log

```bash
python -m geobrief case create --number 24-001234 \
    --agency "Example PD" --investigator "Det. Smith"
python -m geobrief case list
python -m geobrief process records.csv --case 1 --tz America/Chicago
python -m geobrief case audit 1     # prints the log and verifies the hash chain
```

Cases live in a local SQLite database under `~/.geobrief` (override with
`GEOBRIEF_HOME`). Imported originals are stored byte-for-byte and every
import, hash, processing run, and export is written to a tamper-evident
audit chain.

## Ask the AI assistant

An investigator assistant lives in a side panel of the web app (click
**✦ Assistant**) and is also available from the command line:

```bash
python -m geobrief ask sample_data/sample_locations.csv "summarize the movement" \
    --tz America/Chicago
```

Try questions like *"explain this data"*, *"what is missing?"*, *"summarize the
movement"*, *"explain the time zones"*, or *"suggest filters"*.

The assistant also has **local analysis tools** it runs automatically when a
question calls for them — entirely on your machine — and highlights its
findings on the map:

| Tool | Ask something like |
| --- | --- |
| Nearest points | "what points are near 41.8837, -87.6319 within 500 m?" |
| Time gaps | "are there any gaps in the data?" |
| Dwell locations | "where did the device stay the longest?" |
| Time window | "which points are between 2024-03-01T08:00 and 2024-03-01T12:00?" |
| Impossible jumps | "any impossible jumps or speed problems?" |

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

For the most capable assistant we recommend setting
`OPENROUTER_MODEL=anthropic/claude-sonnet-4` (strong reasoning at a moderate
price); the default `openrouter/auto` lets OpenRouter route each request.

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

### License keys (offline unlock)

Customers who buy on the storefront receive a **signed license key** that
unlocks their plan offline — no account, no phone-home:

```bash
export GEOBRIEF_LICENSE_KEY="GBLE...."        # from the post-checkout page
export GEOBRIEF_LICENSE_SECRET="<product signing secret>"
python -m geobrief serve
```

Keys are `GBLE.<payload>.<signature>` — a URL-safe base64 JSON payload
(`plan`, optional `email`, optional `exp` unix expiry) signed with
HMAC-SHA256 over the encoded payload. Verification lives in
[`geobrief/licensing.py`](src/geobrief/licensing.py); the storefront issues
keys with the identical scheme from a Netlify Function. Entitlement
resolution order: active Stripe subscription → valid license key →
`GEOBRIEF_PLAN`.

### Storefront (Netlify)

Netlify hosts the marketing site + checkout only — the product itself runs on
the customer's machine. The site lives in [site/public](site/public) with two
serverless functions in [site/functions](site/functions):

* `create-checkout` — starts checkout for a plan using either:
  * preset Stripe Payment Links (`STRIPE_PAYMENT_LINK_STANDARD` / `_PRO`), or
  * dynamically-created Stripe Checkout Sessions (`STRIPE_SECRET_KEY` +
    `STRIPE_PRICE_STANDARD` / `_PRO`).
* `get-license` — exchanges a paid checkout session for a signed license key
  whose expiry tracks the subscription's billing period (+7 days grace).
  Requires a valid Supabase bearer token and enforces that the signed-in
  account email matches the checkout email.
* `account-config`, `account-me`, `account-portal` — passwordless account
  login + subscription lookup + Stripe billing portal for SaaS users.

Deploy:

```bash
netlify login
netlify init                          # link/create the site
netlify env:set GEOBRIEF_LICENSE_SECRET "$(openssl rand -hex 32)"
netlify deploy --prod
```

Then choose one checkout mode:

1. Stripe preset Payment Links (fastest to launch; no server-side Checkout Session creation):

```bash
netlify env:set STRIPE_PAYMENT_LINK_STANDARD https://buy.stripe.com/...
netlify env:set STRIPE_PAYMENT_LINK_PRO https://buy.stripe.com/...
netlify deploy --prod
```

2. Stripe Checkout Sessions (current default backend flow):

```bash
netlify env:set STRIPE_SECRET_KEY sk_test_...
netlify env:set STRIPE_PRICE_STANDARD price_...
netlify env:set STRIPE_PRICE_PRO price_...
netlify deploy --prod
```

In Stripe (test mode first): create two Products with recurring monthly Prices
($9.99 / $14.99) dedicated to GeoBrief.

### SaaS accounts and login

If you want customer accounts, enable `/account.html` with Supabase Auth
(passwordless magic links):

```bash
netlify env:set SUPABASE_URL https://<project>.supabase.co
netlify env:set SUPABASE_ANON_KEY <anon-public-key>
netlify env:set SUPABASE_SERVICE_ROLE_KEY <service-role-secret>
netlify env:set STRIPE_BILLING_PORTAL_RETURN_URL https://geobrief-le.netlify.app/account.html
netlify deploy --prod
```

How account management works:

* User signs in on `/account.html` with email magic link.
* Backend verifies the Supabase access token.
* Backend resolves Stripe customer from canonical `account_profiles.stripe_customer_id`.
* If no canonical id exists yet, backend performs guarded email lookup:
  exactly one match is accepted and persisted; multiple matches return a
  conflict for manual support resolution.
* Backend opens Stripe Billing Portal for upgrades/cancellations/payment updates.
* License retrieval on `/success.html` requires sign-in and same-email match
  before issuing a key.

This gives you SaaS-style account access **without building a custom account DB
first**. A custom database becomes necessary only when you need team workspaces,
RBAC, internal analytics, or app-owned profile/settings data.

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