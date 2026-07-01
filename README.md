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