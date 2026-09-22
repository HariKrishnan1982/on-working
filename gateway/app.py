"""
FastAPI Secure Call Gateway.

Features:
- API-Key Authentication (X-API-Key header)
- Upload size and MIME-type enforcement
- Asynchronous Job API (POST /jobs -> 202, GET /jobs/{job_id} -> decision)
- Direct synchronous POST /analyze endpoint
- Background execution via shared PipelineService (independent of any LLM agent)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Security,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

import soundfile as sf

from configs.settings import settings
from gateway.ops_api import record_session, router as ops_router
from gateway.session import create_session
from schemas.models import (
    BranchStatus,
    JobStatus,
    Language,
    RiskDecision,
)
from services.pipeline_service import PipelineService

app = FastAPI(
    title="Voice Fraud Detection Gateway",
    description="Multi-branch voice fraud detection gateway with API key security and async job execution",
    version="0.2.0",
)

# Dashboard (React) runs on the Vite dev server; allow cross-origin reads.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8443",
        "http://127.0.0.1:8443",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Operations / dashboard API consumed by frontend/
app.include_router(ops_router)

pipeline_service = PipelineService()

logger = logging.getLogger(__name__)

# Disk location for persisted multipart uploads so the pipeline can read real audio.
UPLOAD_ROOT = Path("storage") / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

# ── Security & Authentication ────────────────────────────────────────────────

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """Validate X-API-Key against configured secret."""
    if not api_key or api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )
    return api_key


# ── In-Memory Job Store (Backed by DB/Redis in prod) ──────────────────────────

class JobState(BaseModel):
    job_id: str
    status: JobStatus
    caller_id: str
    claimed_identity: Optional[str] = None
    decision: Optional[RiskDecision] = None
    error: Optional[str] = None


jobs_db: dict[str, JobState] = {}


# ── Request Models ────────────────────────────────────────────────────────────


class AnalyzeRequest(BaseModel):
    """Direct analysis request payload."""
    caller_id: str = Field(..., description="Phone number or SIP caller ID")
    audio_path: str = Field(..., description="Path to encrypted audio recording")
    claimed_identity: Optional[str] = Field(None, description="Claimed identity for verification")
    language_hint: str = Field("EN", description="Language hint (EN, HI, TA, TE, ML, KN)")


class JobCreationResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str


# ── Helper for async execution ────────────────────────────────────────────────


def _audio_metadata(audio_path: str) -> tuple[Optional[float], Optional[int], Optional[int]]:
    """Best-effort extraction of duration/rate/channels for the ops session store."""
    try:
        info = sf.info(audio_path)
        return info.duration, info.samplerate, info.channels
    except Exception:
        return None, None, None


def _record_ops_session(session: "CallSession", decision: RiskDecision) -> None:
    """Mirror a pipeline decision into the dashboard ops store (never raises)."""
    try:
        from gateway.ops_api import capture_vad_stats
        from gateway.ops_api import record_session as ops_record_session

        duration_s, sample_rate, channels = _audio_metadata(session.audio_path_encrypted)
        ops_record_session(
            session.session_id,
            session.caller_id,
            session.claimed_identity,
            decision,
            duration_s=duration_s,
            sample_rate=sample_rate,
            channels=channels,
            vad=capture_vad_stats(session.audio_path_encrypted, session.session_id),
        )
    except Exception as e:
        logger.warning("Could not record ops session '%s': %s", session.session_id, e)


def _append_audit_best_effort(decision: RiskDecision) -> None:
    """Append to the PostgreSQL/Fabric audit chain without failing the request.

    Runs in a daemon thread with its own event loop. Never calls
    ``asyncio.run`` on the caller's thread: under ``TestClient``/uvicorn the
    caller may already live inside an anyio portal loop, where a nested
    ``asyncio.run`` deadlocks the process.
    """
    try:
        from audit.fabric_sink import FabricSink

        def _runner() -> None:
            try:
                asyncio.run(FabricSink().append(decision))
            except Exception as e:
                logger.debug("Audit append skipped (ledger offline): %s", e)

        thread = threading.Thread(target=_runner, daemon=True, name="vfd-audit-append")
        thread.start()
    except Exception as e:
        logger.debug("Audit append scheduling failed: %s", e)


def _execute_job_task(job_id: str, caller_id: str, audio_path: str, claimed_identity: Optional[str], language_hint: str):
    try:
        jobs_db[job_id].status = JobStatus.PROCESSING
        lang = Language(language_hint) if language_hint in Language.__members__ else Language.EN
        session = create_session(
            caller_id=caller_id,
            audio_path=audio_path,
            claimed_identity=claimed_identity,
            language_hint=lang,
        )
        decision = pipeline_service.process_call_session(session)
        _record_ops_session(session, decision)
        _append_audit_best_effort(decision)
        jobs_db[job_id].decision = decision
        jobs_db[job_id].status = JobStatus.COMPLETED
    except Exception as e:
        logger.exception("Job '%s' failed: %s", job_id, e)
        jobs_db[job_id].status = JobStatus.FAILED
        jobs_db[job_id].error = str(e)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
def health_check():
    """Unauthenticated health check endpoint."""
    return {"status": "healthy", "service": "voice-fraud-detection"}


@app.post("/analyze", response_model=RiskDecision)
def analyze_call_sync(
    request: AnalyzeRequest,
    _auth: str = Depends(verify_api_key),
):
    """
    Synchronous analysis endpoint. Runs pipeline directly through PipelineService.
    """
    lang = Language(request.language_hint) if request.language_hint in Language.__members__ else Language.EN
    session = create_session(
        caller_id=request.caller_id,
        audio_path=request.audio_path,
        claimed_identity=request.claimed_identity,
        language_hint=lang,
    )
    return _run_analysis(session)


def _run_analysis(session: "CallSession"):
    """Shared decision path: executes pipeline, records the session for ops + audit."""
    decision = pipeline_service.process_call_session(session)
    _record_ops_session(session, decision)
    _append_audit_best_effort(decision)
    return decision


@app.post("/jobs", response_model=JobCreationResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis_job(
    background_tasks: BackgroundTasks,
    caller_id: str = Form(...),
    claimed_identity: Optional[str] = Form(None),
    language_hint: str = Form("EN"),
    audio_file: Optional[UploadFile] = File(None),
    audio_path: Optional[str] = Form(None),
    _auth: str = Depends(verify_api_key),
):
    """
    Asynchronous job endpoint.
    Accepts multipart upload or existing storage path, validates file constraints,
    enqueues analysis in the background, and returns job_id immediately.
    """
    if audio_file is not None:
        # Validate MIME type
        content_type = audio_file.content_type or "application/octet-stream"
        if content_type not in settings.allowed_content_types:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Content-Type '{content_type}' is not allowed. Supported: {settings.allowed_content_types}",
            )

        # Read and enforce max size
        contents = await audio_file.read()
        if len(contents) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Audio file size ({len(contents)} bytes) exceeds limit of {settings.max_upload_bytes} bytes",
            )

        safe_name = Path(audio_file.filename or "upload.wav").name or "upload.wav"
        target_path = UPLOAD_ROOT / f"{uuid.uuid4()}_{safe_name}"
        target_path.write_bytes(contents)
        resolved_audio_path = str(target_path)
    elif audio_path is not None:
        resolved_audio_path = audio_path
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either audio_file upload or audio_path must be provided",
        )

    job_id = str(uuid.uuid4())
    jobs_db[job_id] = JobState(
        job_id=job_id,
        status=JobStatus.PENDING,
        caller_id=caller_id,
        claimed_identity=claimed_identity,
    )

    background_tasks.add_task(
        _execute_job_task,
        job_id,
        caller_id,
        resolved_audio_path,
        claimed_identity,
        language_hint,
    )

    return JobCreationResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="Call analysis job successfully scheduled",
    )


@app.get("/jobs/{job_id}", response_model=JobState)
def get_job_status(
    job_id: str,
    _auth: str = Depends(verify_api_key),
):
    """
    Retrieve status and result of an asynchronous analysis job.
    """
    if job_id not in jobs_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    return jobs_db[job_id]
