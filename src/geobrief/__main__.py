"""Command-line interface for GeoBrief LE.

Usage:
    python -m geobrief process INPUT.csv [--tz America/Chicago] [--out DIR]
                               [--case CASE_ID]
    python -m geobrief ask INPUT.csv "what is missing?" [--tz ...]
    python -m geobrief case create --number 24-001 [--agency ...] [...]
    python -m geobrief case list
    python -m geobrief case audit CASE_ID
    python -m geobrief serve [--host 127.0.0.1] [--port 8000]

The ``process`` command reads a file, hashes it, cleans and validates the
records, and writes a cleaned CSV, a JSON summary, map-ready GeoJSON, and a
Google Earth KML file to an output directory. With ``--case`` the source
file, exports, and processing events are also recorded in the local case
workspace. The ``ask`` command answers a plain-English question
about the data using the investigator AI assistant. The original file is
never modified.
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
    kml_path = out_dir / f"{stem}.kml"
    report_path = out_dir / f"{stem}_report.pdf"

    cleaned_path.write_text(result.cleaned_csv(), encoding="utf-8")
    summary_path.write_text(result.summary_json(), encoding="utf-8")
    import json

    geojson_path.write_text(
        json.dumps(result.geojson(), indent=2), encoding="utf-8"
    )
    from .kml import build_kml

    kml_path.write_text(build_kml(result), encoding="utf-8")
    from .report import build_pdf_report

    report_path.write_bytes(
        build_pdf_report(
            result,
            exports=[
                cleaned_path.name,
                summary_path.name,
                geojson_path.name,
                kml_path.name,
            ],
        )
    )

    if args.case is not None:
        from .store import CaseStore

        with CaseStore() as store:
            store.add_source_file(
                args.case, input_path.name, input_path.read_bytes()
            )
            store.log_event(
                args.case,
                "file_processed",
                {
                    "filename": input_path.name,
                    "sha256": result.sha256,
                    "display_timezone": args.tz,
                    "total_records": result.total_records,
                },
            )
            for export_type, path in (
                ("cleaned_csv", cleaned_path),
                ("summary_json", summary_path),
                ("geojson", geojson_path),
                ("kml", kml_path),
                ("pdf_report", report_path),
            ):
                store.record_export(args.case, export_type, path.name)
        print(f"Recorded in case {args.case}.")

    print(result.summary()["plain_english"])
    print(f"SHA-256: {result.sha256}")
    print(f"Cleaned spreadsheet: {cleaned_path}")
    print(f"Processing summary:  {summary_path}")
    print(f"Map points (GeoJSON): {geojson_path}")
    print(f"Google Earth file:   {kml_path}")
    print(f"PDF report:          {report_path}")
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    from .assistant import Assistant

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        return 2

    result = process_file(
        input_path,
        display_timezone=args.tz,
        assume_source_timezone=args.assume_tz,
    )
    answer = Assistant().answer(
        args.question, result.summary(), result.geojson()
    )

    print(answer["answer"])
    print()
    print(answer["disclaimer"])
    if answer["backend"] != "openrouter":
        print(
            "\n(Answered locally. Set OPENROUTER_API_KEY to enable the "
            "AI model.)",
            file=sys.stderr,
        )
    return 0


def _cmd_case(args: argparse.Namespace) -> int:
    import json

    from .store import CaseStore

    with CaseStore() as store:
        if args.case_command == "create":
            case = store.create_case(
                args.number,
                agency=args.agency,
                investigator=args.investigator,
                offense_type=args.offense,
                notes=args.notes,
            )
            print(
                f"Created case {case['case_id']} "
                f"(number {case['case_number']})."
            )
        elif args.case_command == "list":
            cases = store.list_cases()
            if not cases:
                print("No cases yet. Create one with: geobrief case create")
            for case in cases:
                print(
                    f"[{case['case_id']}] {case['case_number']} "
                    f"— {case['agency'] or 'no agency'} "
                    f"— {case['investigator'] or 'no investigator'} "
                    f"({case['status']})"
                )
        elif args.case_command == "audit":
            events = store.audit_log(args.case_id)
            intact = store.verify_audit_chain(args.case_id)
            for event in events:
                details = json.dumps(event["event_details"], sort_keys=True)
                print(
                    f"{event['timestamp']} {event['event_type']} {details}"
                )
            print(
                "Audit chain: "
                + ("intact" if intact else "TAMPERED — hashes do not match")
            )
            if not intact:
                return 1
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
    p_process.add_argument(
        "--case",
        type=int,
        default=None,
        help="Case ID to record this file and its exports under.",
    )
    p_process.set_defaults(func=_cmd_process)

    p_ask = sub.add_parser(
        "ask",
        help="Ask the investigator AI assistant about a file's data.",
    )
    p_ask.add_argument("input", help="Path to the source file.")
    p_ask.add_argument(
        "question",
        help='Question, e.g. "summarize the movement" or "what is missing?".',
    )
    p_ask.add_argument(
        "--tz",
        default="UTC",
        help="Display time zone (IANA name, e.g. America/Chicago).",
    )
    p_ask.add_argument(
        "--assume-tz",
        default=None,
        help="Assume this source time zone for naive timestamps.",
    )
    p_ask.set_defaults(func=_cmd_ask)

    p_case = sub.add_parser("case", help="Manage local case workspaces.")
    case_sub = p_case.add_subparsers(dest="case_command", required=True)

    p_case_create = case_sub.add_parser("create", help="Create a new case.")
    p_case_create.add_argument(
        "--number", required=True, help="Case number, e.g. 24-001234."
    )
    p_case_create.add_argument("--agency", default="", help="Agency name.")
    p_case_create.add_argument(
        "--investigator", default="", help="Investigator name."
    )
    p_case_create.add_argument(
        "--offense", default="", help="Offense type."
    )
    p_case_create.add_argument("--notes", default="", help="Case notes.")
    p_case_create.set_defaults(func=_cmd_case)

    p_case_list = case_sub.add_parser("list", help="List cases.")
    p_case_list.set_defaults(func=_cmd_case)

    p_case_audit = case_sub.add_parser(
        "audit", help="Print a case's audit log and verify its integrity."
    )
    p_case_audit.add_argument("case_id", type=int)
    p_case_audit.set_defaults(func=_cmd_case)

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
