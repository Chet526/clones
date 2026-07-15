"""FastAPI web application for GeoBrief LE (local-first Phase 1 UI).

Runs on the investigator's own machine. Uploaded files are processed in
memory and the original bytes are hashed but never written or altered by
default. No data leaves the machine.
"""

from __future__ import annotations

from pathlib import Path
import base64

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..assistant import Assistant, AssistantConfig
from ..billing import BillingError, BillingService, effective_plan
from ..casework import CaseStore
from ..ingest import UnsupportedFileTypeError
from ..pipeline import __version__, process_bytes
from ..models import ColumnMapping
from ..subscription import (
    Feature,
    PLANS,
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


def _plan_allows(feature: str) -> bool:
    """True when the app's currently enforced plan grants ``feature``."""
    return effective_plan().allows(feature)


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
    active = effective_plan()
    billing_configured = BillingService.from_env().config.configured
    return {
        "current_plan": active.id,
        "billing_enabled": billing_configured,
        "plans": [
            plan.to_dict(current=plan.id == active.id) for plan in PLANS
        ],
    }


class CheckoutRequest(BaseModel):
    """Request to start a subscription checkout for a plan."""

    plan: str


@app.get("/api/billing/status")
def billing_status() -> dict:
    """Report whether real billing is configured and the active plan."""
    service = BillingService.from_env()
    active = effective_plan()
    return {
        "billing_enabled": service.config.configured,
        "current_plan": active.id,
        "active_subscription": service.active_plan_id() is not None,
    }


@app.post("/api/billing/checkout")
def billing_checkout(request: CheckoutRequest) -> JSONResponse:
    """Create a Stripe Checkout Session and return its redirect URL."""
    service = BillingService.from_env()
    if not service.config.configured:
        raise HTTPException(
            status_code=503,
            detail="Billing is not configured on this server.",
        )
    try:
        session = service.create_checkout_session(request.plan)
    except BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"id": session.get("id"), "url": session.get("url")})


@app.post("/api/billing/webhook")
async def billing_webhook(request: Request) -> JSONResponse:
    """Receive Stripe webhook events (signature-verified) and apply them."""
    service = BillingService.from_env()
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    try:
        event = service.construct_event(payload, signature)
    except Exception as exc:  # signature/parse failures -> 400, no state change
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    service.apply_event(event)
    return JSONResponse({"received": True})


@app.post("/api/process")
async def process(
    file: UploadFile = File(...),
    display_timezone: str = Form("UTC"),
    assume_source_timezone: str = Form(""),
    case_id: str = Form(""),
    training_mode: bool = Form(False),
    latitude_column: str = Form(""),
    longitude_column: str = Form(""),
    timestamp_column: str = Form(""),
    accuracy_column: str = Form(""),
) -> JSONResponse:
    """Process an uploaded CSV/XLSX file and return summary + map data."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty.")

    try:
        override = ColumnMapping(
            latitude=latitude_column or None,
            longitude=longitude_column or None,
            timestamp=timestamp_column or None,
            accuracy=accuracy_column or None,
        )
        mapping_override = (
            override if any(override.to_dict().values()) else None
        )
        result = process_bytes(
            data,
            file.filename or "upload",
            display_timezone=display_timezone or "UTC",
            assume_source_timezone=assume_source_timezone or None,
            mapping_override=mapping_override,
            case_id=case_id or None,
            training_mode=training_mode,
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - surfaced to the user
        raise HTTPException(
            status_code=400, detail=f"Could not read file: {exc}"
        ) from exc

    if case_id:
        store = CaseStore.from_env()
        try:
            store.log_event(
                case_id,
                "file_processed",
                {
                    "filename": file.filename or "upload",
                    "file_size": len(data),
                    "sha256": result.sha256,
                    "record_counts": result.summary()["record_counts"],
                },
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Case not found.") from exc

    pdf_b64 = base64.b64encode(result.processing_report_pdf()).decode("ascii")
    return JSONResponse(
        {
            "summary": result.summary(),
            "geojson": result.geojson(),
            "cleaned_csv": result.cleaned_csv(),
            "summary_json": result.summary_json(),
            "kml": result.kml(),
            "processing_report_pdf_base64": pdf_b64,
        }
    )


class CaseCreateRequest(BaseModel):
    case_number: str = ""
    agency_name: str = ""
    investigator_name: str = ""
    offense_type: str = ""
    suspect_identifier: str = ""
    victim_identifier: str = ""
    device_identifiers: str = ""
    notes: str = ""
    training_mode: bool = False


@app.get("/api/cases")
def list_cases() -> dict:
    store = CaseStore.from_env()
    return {"cases": store.list_cases()}


@app.post("/api/cases")
def create_case(request: CaseCreateRequest) -> JSONResponse:
    store = CaseStore.from_env()
    created = store.create_case(request.model_dump())
    return JSONResponse(created, status_code=201)


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    store = CaseStore.from_env()
    try:
        return store.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Case not found.") from exc


@app.get("/api/cases/{case_id}/audit")
def case_audit(case_id: str) -> dict:
    store = CaseStore.from_env()
    try:
        store.get_case(case_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Case not found.") from exc
    return {"case_id": case_id, "events": store.read_audit(case_id)}


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
    if not _plan_allows(Feature.AI_ASSISTANT):
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
    if not _plan_allows(Feature.AI_ASSISTANT):
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
