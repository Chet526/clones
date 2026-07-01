"""Command-line interface for GeoBrief LE (Phase 1).

Usage:
    python -m geobrief process INPUT.csv [--tz America/Chicago] [--out DIR]
    python -m geobrief serve [--host 127.0.0.1] [--port 8000]

The ``process`` command reads a file, hashes it, cleans and validates the
records, and writes a cleaned CSV, a JSON summary, and map-ready GeoJSON to
an output directory. The original file is never modified.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import process_file


def _cmd_process(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        return 2

    result = process_file(
        input_path,
        display_timezone=args.tz,
        assume_source_timezone=args.assume_tz,
    )

    out_dir = Path(args.out) if args.out else input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem

    cleaned_path = out_dir / f"{stem}_cleaned.csv"
    summary_path = out_dir / f"{stem}_summary.json"
    geojson_path = out_dir / f"{stem}_points.geojson"

    cleaned_path.write_text(result.cleaned_csv(), encoding="utf-8")
    summary_path.write_text(result.summary_json(), encoding="utf-8")
    import json

    geojson_path.write_text(
        json.dumps(result.geojson(), indent=2), encoding="utf-8"
    )

    print(result.summary()["plain_english"])
    print(f"SHA-256: {result.sha256}")
    print(f"Cleaned spreadsheet: {cleaned_path}")
    print(f"Processing summary:  {summary_path}")
    print(f"Map points (GeoJSON): {geojson_path}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "geobrief.webapp.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="geobrief",
        description="GeoBrief LE — location evidence processor (Phase 1).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_process = sub.add_parser("process", help="Process a CSV/XLSX file.")
    p_process.add_argument("input", help="Path to the source file.")
    p_process.add_argument(
        "--tz",
        default="UTC",
        help="Display time zone (IANA name, e.g. America/Chicago).",
    )
    p_process.add_argument(
        "--assume-tz",
        default=None,
        help="Assume this source time zone for naive timestamps.",
    )
    p_process.add_argument(
        "--out", default=None, help="Output directory for exports."
    )
    p_process.set_defaults(func=_cmd_process)

    p_serve = sub.add_parser("serve", help="Run the local web app.")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
