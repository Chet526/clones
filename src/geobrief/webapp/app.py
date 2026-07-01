"""FastAPI web application for GeoBrief LE (local-first Phase 1 UI).

Runs on the investigator's own machine. Uploaded files are processed in
memory and the original bytes are hashed but never written or altered by
default. No data leaves the machine.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..ingest import UnsupportedFileTypeError
from ..pipeline import __version__, process_bytes

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="GeoBrief LE",
    description="Local-first investigator location evidence processor.",
    version=__version__,
)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "product": "GeoBrief LE", "version": __version__}


@app.post("/api/process")
async def process(
    file: UploadFile = File(...),
    display_timezone: str = Form("UTC"),
    assume_source_timezone: str = Form(""),
) -> JSONResponse:
    """Process an uploaded CSV/XLSX file and return summary + map data."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty.")

    try:
        result = process_bytes(
            data,
            file.filename or "upload",
            display_timezone=display_timezone or "UTC",
            assume_source_timezone=assume_source_timezone or None,
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - surfaced to the user
        raise HTTPException(
            status_code=400, detail=f"Could not read file: {exc}"
        ) from exc

    return JSONResponse(
        {
            "summary": result.summary(),
            "geojson": result.geojson(),
            "cleaned_csv": result.cleaned_csv(),
            "summary_json": result.summary_json(),
        }
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
