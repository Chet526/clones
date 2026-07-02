"""Basic Processing Report PDF generator (PRD Module I, report type 1).

Renders an investigator-ready PDF from a :class:`ProcessingResult`:
source file details with SHA-256 hash, record counts, time range,
time-zone statement, warnings, and the list of produced exports.
Every report carries the draft-output disclaimer.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .pipeline import ProcessingResult

DISCLAIMER = (
    "Draft output generated from processed records. "
    "Investigator must verify before use."
)

_STATUS_LABELS = {
    "valid": "Valid",
    "missing_coordinate": "Missing coordinate",
    "missing_timestamp": "Missing timestamp",
    "invalid_coordinate": "Invalid coordinate",
    "low_accuracy": "Low accuracy",
    "duplicate": "Duplicate",
    "timezone_uncertain": "Time-zone uncertain",
    "possible_latlon_reversal": "Possible lat/long reversal",
    "excluded_from_map": "Excluded from map",
}


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": base["Title"],
        "heading": base["Heading2"],
        "body": base["BodyText"],
        "mono": ParagraphStyle(
            "mono", parent=base["BodyText"], fontName="Courier", fontSize=8
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer",
            parent=base["BodyText"],
            textColor=colors.HexColor("#7a5b00"),
            fontSize=9,
        ),
    }


def _kv_table(rows: list[tuple[str, object]], styles) -> Table:
    data = [
        [
            Paragraph(f"<b>{escape(label)}</b>", styles["body"]),
            Paragraph(escape(str(value)), styles["mono"]),
        ]
        for label, value in rows
    ]
    table = Table(data, colWidths=[1.9 * inch, 4.6 * inch])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8cdd5")),
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor("#eef1f5"),
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _timezone_statement(result: "ProcessingResult") -> str:
    return (
        "Timestamps were normalized to UTC during processing. Times in this "
        f"report and its exports are shown in {result.display_timezone}. "
        "The original timestamp values from the source file are preserved "
        "unchanged in the cleaned spreadsheet."
    )


def build_pdf_report(
    result: "ProcessingResult",
    exports: Optional[list[str]] = None,
) -> bytes:
    """Render the Basic Processing Report as PDF bytes.

    ``exports`` optionally lists filenames of outputs generated alongside
    this report so the report can enumerate them (PRD Module I).
    """
    styles = _styles()
    summary = result.summary()
    counts = summary["record_counts"]
    first, last = result.time_range_utc()

    story = [
        Paragraph("GeoBrief LE — Processing Report", styles["title"]),
        Paragraph(
            f"Generated {escape(result.processed_at)} · "
            f"GeoBrief LE version {escape(summary['version'])}",
            styles["body"],
        ),
        Spacer(1, 10),
        Paragraph(escape(summary["plain_english"]), styles["body"]),
        Spacer(1, 6),
        Paragraph("Source file", styles["heading"]),
        _kv_table(
            [
                ("Filename", result.filename),
                ("File size", f"{result.file_size} bytes"),
                ("SHA-256", result.sha256),
                ("Processed at", result.processed_at),
            ],
            styles,
        ),
        Spacer(1, 6),
        Paragraph("Record counts", styles["heading"]),
        _kv_table(
            [
                ("Total records", counts["total"]),
                ("Valid records", counts["valid"]),
                ("Mappable points", counts["mappable"]),
                ("Skipped or flagged", counts["skipped_or_flagged"]),
            ]
            + [
                (_STATUS_LABELS.get(status, status), count)
                for status, count in sorted(counts["by_status"].items())
            ],
            styles,
        ),
        Spacer(1, 6),
        Paragraph("Time range and time zones", styles["heading"]),
        _kv_table(
            [
                ("First timestamp (UTC)", first or "None found"),
                ("Last timestamp (UTC)", last or "None found"),
                ("Display time zone", result.display_timezone),
            ],
            styles,
        ),
        Paragraph(escape(_timezone_statement(result)), styles["body"]),
        Spacer(1, 6),
        Paragraph("Warnings", styles["heading"]),
    ]

    warnings = summary["warnings"]
    if warnings:
        for warning in warnings:
            story.append(
                Paragraph(f"• {escape(warning)}", styles["body"])
            )
    else:
        story.append(Paragraph("No warnings.", styles["body"]))

    story.append(Spacer(1, 6))
    story.append(Paragraph("Exports produced", styles["heading"]))
    if exports:
        for name in exports:
            story.append(Paragraph(f"• {escape(name)}", styles["body"]))
    else:
        story.append(
            Paragraph(
                "No additional export files were recorded.", styles["body"]
            )
        )

    story.append(Spacer(1, 14))
    story.append(Paragraph(escape(DISCLAIMER), styles["disclaimer"]))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title="GeoBrief LE — Processing Report",
        author="GeoBrief LE",
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
    )
    doc.build(story)
    return buffer.getvalue()
