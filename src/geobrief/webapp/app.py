"""FastAPI web application for GeoBrief LE (local-first Phase 1 UI).

Runs on the investigator's own machine. Uploaded files are processed in
memory and the original bytes are hashed but never written or altered by
default. No data leaves the machine.
"""

from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..assistant import Assistant, AssistantConfig
from ..billing import BillingError, BillingService, effective_plan
from ..detection import detect_columns
from ..ingest import UnsupportedFileTypeError, read_dataframe_from_bytes
from ..kml import build_kml, build_kmz
from ..models import ColumnMapping
from ..pipeline import __version__, process_bytes
from ..report import build_pdf_report
from ..store import CaseStore
from ..training import TRAINING_SAMPLE_FILENAME, training_sample_bytes
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


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "favicon.svg", media_type="image/svg+xml"
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "product": "GeoBrief LE", "version": __version__}


def _api_auth_mode() -> str:
    """Runtime API auth mode for self-host deployments.

    Supported values:
    - ``off`` (default): no API token required.
    - ``token``: require bearer token or x-api-key for protected endpoints.
    """

    return os.environ.get("GEOBRIEF_API_AUTH_MODE", "off").strip().lower()


def _require_api_auth(request: Request) -> None:
    """Optional API token gate for non-localhost deployments.

    By default the local-first app is open on localhost. When self-hosting on
    a reachable interface, set ``GEOBRIEF_API_AUTH_MODE=token`` and provide
    ``GEOBRIEF_API_TOKEN`` to require authentication on protected routes.
    """

    mode = _api_auth_mode()
    if mode in {"", "off", "none", "disabled"}:
        return
    if mode != "token":
        raise HTTPException(
            status_code=500,
            detail=(
                "Unsupported GEOBRIEF_API_AUTH_MODE. "
                "Use 'off' or 'token'."
            ),
        )

    expected = os.environ.get("GEOBRIEF_API_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=(
                "API auth mode is 'token' but GEOBRIEF_API_TOKEN is not "
                "configured."
            ),
        )

    auth_header = request.headers.get("authorization", "")
    presented = ""
    if auth_header.lower().startswith("bearer "):
        presented = auth_header[7:].strip()
    if not presented:
        presented = request.headers.get("x-api-key", "").strip()

    if not presented or not secrets.compare_digest(presented, expected):
        raise HTTPException(
            status_code=401,
            detail=(
                "Unauthorized. Provide a valid bearer token or x-api-key."
            ),
        )


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


@app.get("/api/plans", dependencies=[Depends(_require_api_auth)])
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


@app.get("/api/cases", dependencies=[Depends(_require_api_auth)])
def list_cases() -> dict:
    """List local case workspaces."""
    with CaseStore() as store:
        return {"cases": store.list_cases()}


@app.post("/api/cases", dependencies=[Depends(_require_api_auth)])
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


@app.get("/api/cases/{case_id}", dependencies=[Depends(_require_api_auth)])
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


@app.get(
    "/api/cases/{case_id}/audit", dependencies=[Depends(_require_api_auth)]
)
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


@app.get("/api/billing/status", dependencies=[Depends(_require_api_auth)])
def billing_status() -> dict:
    """Report whether real billing is configured and the active plan."""
    service = BillingService.from_env()
    active = effective_plan()
    return {
        "billing_enabled": service.config.configured,
        "current_plan": active.id,
        "active_subscription": service.active_plan_id() is not None,
    }


@app.post("/api/billing/checkout", dependencies=[Depends(_require_api_auth)])
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


@app.post("/api/detect", dependencies=[Depends(_require_api_auth)])
async def detect(file: UploadFile = File(...)) -> JSONResponse:
    """Inspect an uploaded file: list its columns and detected mapping.

    Lets the wizard show "confirm detected columns" before processing, so
    the user can correct the mapping when detection is wrong or unsure.
    """
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty.")
    try:
        df = read_dataframe_from_bytes(data, file.filename or "upload")
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - surfaced to the user
        raise HTTPException(
            status_code=400, detail=f"Could not read file: {exc}"
        ) from exc
    detection = detect_columns(df)
    return JSONResponse(
        {
            "columns": [str(c) for c in df.columns],
            "row_count": int(len(df)),
            "detection": detection.to_dict(),
        }
    )


def _mapping_override(
    latitude: str, longitude: str, timestamp: str, accuracy: str
) -> ColumnMapping | None:
    """Build a manual mapping when any column override was supplied."""
    values = (latitude, longitude, timestamp, accuracy)
    if not any(v.strip() for v in values):
        return None
    return ColumnMapping(
        latitude=latitude.strip() or None,
        longitude=longitude.strip() or None,
        timestamp=timestamp.strip() or None,
        accuracy=accuracy.strip() or None,
    )


@app.get("/api/training/sample", dependencies=[Depends(_require_api_auth)])
def training_sample() -> JSONResponse:
    """The bundled, clearly fake practice file for training mode."""
    return JSONResponse(
        {
            "filename": TRAINING_SAMPLE_FILENAME,
            "csv": training_sample_bytes().decode("utf-8"),
        }
    )


@app.post("/api/process", dependencies=[Depends(_require_api_auth)])
async def process(
    file: UploadFile = File(...),
    display_timezone: str = Form("UTC"),
    assume_source_timezone: str = Form(""),
    case_id: str = Form(""),
    latitude_column: str = Form(""),
    longitude_column: str = Form(""),
    timestamp_column: str = Form(""),
    accuracy_column: str = Form(""),
    training: str = Form(""),
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
            mapping_override=_mapping_override(
                latitude_column,
                longitude_column,
                timestamp_column,
                accuracy_column,
            ),
            training=training.strip().lower() in {"1", "true", "yes", "on"},
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
            "kmz_base64": base64.b64encode(build_kmz(result)).decode(
                "ascii"
            ),
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


@app.get(
    "/api/assistant/status", dependencies=[Depends(_require_api_auth)]
)
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


@app.post("/api/assistant", dependencies=[Depends(_require_api_auth)])
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
