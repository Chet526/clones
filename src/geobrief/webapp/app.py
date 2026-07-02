"""FastAPI web application for GeoBrief LE (local-first Phase 1 UI).

Runs on the investigator's own machine. Uploaded files are processed in
memory and the original bytes are hashed but never written or altered by
default. No data leaves the machine.
"""

from __future__ import annotations

import base64
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..assistant import Assistant, AssistantConfig
from ..billing import BillingError, BillingService, effective_plan
from ..ingest import UnsupportedFileTypeError
from ..kml import build_kml
from ..pipeline import __version__, process_bytes
from ..report import build_pdf_report
from ..store import CaseStore
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


class CaseCreateRequest(BaseModel):
    """Request to create a new local case workspace."""

    case_number: str
    agency: str = ""
    investigator: str = ""
    offense_type: str = ""
    notes: str = ""


@app.get("/api/cases")
def list_cases() -> dict:
    """List local case workspaces."""
    with CaseStore() as store:
        return {"cases": store.list_cases()}


@app.post("/api/cases")
def create_case(request: CaseCreateRequest) -> JSONResponse:
    """Create a new local case workspace."""
    try:
        with CaseStore() as store:
            case = store.create_case(
                request.case_number,
                agency=request.agency,
                investigator=request.investigator,
                offense_type=request.offense_type,
                notes=request.notes,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(case, status_code=201)


@app.get("/api/cases/{case_id}")
def case_detail(case_id: int) -> dict:
    """A case with its source files and exports."""
    with CaseStore() as store:
        try:
            case = store.get_case(case_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "case": case,
            "source_files": store.list_source_files(case_id),
            "exports": store.list_exports(case_id),
        }


@app.get("/api/cases/{case_id}/audit")
def case_audit(case_id: int) -> dict:
    """A case's tamper-evident audit log."""
    with CaseStore() as store:
        try:
            store.get_case(case_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "events": store.audit_log(case_id),
            "chain_intact": store.verify_audit_chain(case_id),
        }


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

    stem = Path(file.filename or "upload").stem
    export_names = [
        f"{stem}_cleaned.csv",
        f"{stem}_summary.json",
        f"{stem}_points.geojson",
        f"{stem}.kml",
    ]

    recorded_case = None
    if case_id.strip():
        try:
            case_id_int = int(case_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="case_id must be a number."
            ) from exc
        with CaseStore() as store:
            try:
                store.add_source_file(
                    case_id_int, file.filename or "upload", data
                )
            except KeyError as exc:
                raise HTTPException(
                    status_code=404, detail=str(exc)
                ) from exc
            store.log_event(
                case_id_int,
                "file_processed",
                {
                    "filename": file.filename or "upload",
                    "sha256": result.sha256,
                    "display_timezone": result.display_timezone,
                    "total_records": result.total_records,
                },
            )
            for export_type, name in zip(
                ("cleaned_csv", "summary_json", "geojson", "kml"),
                export_names,
            ):
                store.record_export(case_id_int, export_type, name)
            recorded_case = case_id_int

    return JSONResponse(
        {
            "summary": result.summary(),
            "geojson": result.geojson(),
            "cleaned_csv": result.cleaned_csv(),
            "summary_json": result.summary_json(),
            "kml": build_kml(result),
            "report_pdf_base64": base64.b64encode(
                build_pdf_report(result, exports=export_names)
            ).decode("ascii"),
            "case_id": recorded_case,
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
