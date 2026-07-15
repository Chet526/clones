"""Report export helpers (KML + minimal PDF)."""

from __future__ import annotations

from xml.sax.saxutils import escape


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_basic_pdf(lines: list[str], *, title: str = "GeoBrief LE Report") -> bytes:
    """Create a minimal single-page PDF with plain text lines."""
    text_ops = [
        "BT",
        "/F1 14 Tf",
        "72 760 Td",
        f"({_pdf_escape(title)}) Tj",
        "/F1 10 Tf",
        "0 -22 Td",
    ]
    for line in lines:
        text_ops.append(f"({_pdf_escape(line)}) Tj")
        text_ops.append("0 -14 Td")
    text_ops.append("ET")
    content = "\n".join(text_ops).encode("latin-1", errors="replace")

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n"
        + content
        + b"\nendstream"
    )

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for idx, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{idx} 0 obj\n".encode("ascii"))
        pdf.extend(body)
        pdf.extend(b"\nendobj\n")
    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            "trailer\n"
            f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_start}\n"
            "%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def build_kml(
    features: list[dict], *, name: str = "GeoBrief LE Export", training_mode: bool = False
) -> str:
    """Convert GeoJSON-like features to a simple KML document."""
    placemarks: list[str] = []
    for feature in features:
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})
        coords = geom.get("coordinates") or [None, None]
        lon, lat = coords[0], coords[1]
        if lon is None or lat is None:
            continue
        when = escape(str(props.get("normalized_timestamp_utc") or ""))
        display = escape(str(props.get("display_timestamp") or ""))
        row = escape(str(props.get("source_row_number") or ""))
        status = escape(str(props.get("validation_status") or ""))
        accuracy = props.get("accuracy_radius")
        accuracy_text = "" if accuracy is None else escape(str(accuracy))
        desc = (
            f"<![CDATA[<p><b>Source row:</b> {row}</p>"
            f"<p><b>Display time:</b> {display}</p>"
            f"<p><b>UTC time:</b> {when}</p>"
            f"<p><b>Status:</b> {status}</p>"
            f"<p><b>Accuracy (m):</b> {accuracy_text or '—'}</p>]]>"
        )
        placemarks.append(
            "<Placemark>"
            f"<name>Row {row}</name>"
            f"<description>{desc}</description>"
            + (f"<TimeStamp><when>{when}</when></TimeStamp>" if when else "")
            + "<Point><coordinates>"
            f"{lon},{lat},0"
            "</coordinates></Point>"
            "</Placemark>"
        )

    training_notice = (
        "<description>TRAINING MODE: sample/practice output only.</description>"
        if training_mode
        else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2">'
        "<Document>"
        f"<name>{escape(name)}</name>"
        f"{training_notice}"
        + "".join(placemarks)
        + "</Document></kml>"
    )
