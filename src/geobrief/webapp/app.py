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
from pydantic import BaseModel

from ..assistant import Assistant, AssistantConfig
from ..ingest import UnsupportedFileTypeError
from ..pipeline import __version__, process_bytes
from ..subscription import (
    Feature,
    PLANS,
    current_plan,
    plan_allows,
    upgrade_target,
)

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


def _assistant_upsell() -> dict:
    """Upsell payload describing the plan needed to unlock the assistant."""
    target = upgrade_target(Feature.AI_ASSISTANT)
    return {
        "detail": (
            "The investigator AI assistant is a Pro feature. Upgrade to "
            f"{target.name} ({target.price_display}) to ask questions about "
            "your processed data."
            if target
            else "The investigator AI assistant is not available on your plan."
        ),
        "feature": Feature.AI_ASSISTANT,
        "required_plan": target.to_dict() if target else None,
    }


@app.get("/api/plans")
def plans() -> dict:
    """List the subscription plans and report which one is active."""
    active = current_plan()
    return {
        "current_plan": active.id,
        "plans": [
            plan.to_dict(current=plan.id == active.id) for plan in PLANS
        ],
    }


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


class AssistantRequest(BaseModel):
    """Payload for an investigator question about processed data."""

    question: str = ""
    summary: dict
    geojson: dict | None = None


@app.get("/api/assistant/status")
def assistant_status() -> JSONResponse:
    """Report assistant availability for the active plan.

    The assistant is a Pro-plan feature. When the active plan does not
    include it, respond with ``402 Payment Required`` and an upsell payload
    so the UI can prompt an upgrade. Otherwise report whether the remote
    model is configured (no data leaves the machine on the local backend).
    """
    if not plan_allows(Feature.AI_ASSISTANT):
        payload = _assistant_upsell()
        payload["available"] = False
        return JSONResponse(payload, status_code=402)

    config = AssistantConfig.from_env()
    return JSONResponse(
        {
            "available": True,
            "enabled": config.enabled,
            "model": config.model if config.enabled else None,
            "backend": "openrouter" if config.enabled else "local",
        }
    )


@app.post("/api/assistant")
def assistant(request: AssistantRequest) -> JSONResponse:
    """Answer an investigator question about already-processed data.

    Requires the Pro plan; requests on other plans receive ``402 Payment
    Required`` with an upsell payload. The client sends back the processing
    ``summary`` (and optional ``geojson``) it already holds; the assistant
    builds an aggregate context from them. When no OpenRouter key is
    configured the answer is produced locally and nothing leaves the machine.
    """
    if not plan_allows(Feature.AI_ASSISTANT):
        return JSONResponse(_assistant_upsell(), status_code=402)
    if not request.summary:
        raise HTTPException(
            status_code=400,
            detail="Process a file first, then ask the assistant.",
        )
    result = Assistant().answer(
        request.question, request.summary, request.geojson
    )
    return JSONResponse(result)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
