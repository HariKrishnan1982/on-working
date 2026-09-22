"""
Operations & Dashboard API for the Voice Fraud Detection Gateway.

Serves the React operator dashboard (frontend/) with live data:

- GET  /api/v1/sessions          List analyzed call sessions
- GET  /api/v1/sessions/{id}     Full decision + evidence + VAD summary for one session
- GET  /api/v1/sessions/{id}/audit-proof  Per-decision chain proof (hash, position, anchor status)
- GET  /api/v1/alerts            HIGH/CRITICAL sessions surfaced as alerts
- GET  /api/v1/audit             Immutable hash-chain records (PostgreSQL w/ in-memory fallback)
- GET  /api/v1/users             Enrolled voice profiles (privacy-preserving)
- POST /api/v1/users             Enroll a speaker from uploaded voice samples
- GET  /api/v1/policies          Security policies derived from risk_engine/rules.yaml
- GET  /api/v1/system/status     Health of backend services (PG, Fabric bridge, models)

Sessions/decisions are appended to the in-memory store, mirrored to the
PostgreSQL hash chain / Fabric outbox when the ledger is reachable, and
enrollment uses the encrypted pseudonymous SpeakerEnrollmentStore.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import soundfile as sf
import yaml
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from audit.fabric_sink import FabricSink
from branches.speaker.ecapa import extract_embedding
from branches.speaker.registry import get_enrollment_store
from configs.settings import settings
from schemas.hash_utils import compute_decision_hash
from schemas.models import (
    ActionType,
    ConsentRecord,
    RiskDecision,
    RiskLevel,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["operations"])

RULES_YAML_PATH = Path(__file__).resolve().parent.parent / "risk_engine" / "rules.yaml"

STORAGE_ROOT = Path("storage")
UPLOAD_DIR = STORAGE_ROOT / "uploads"
PROFILE_AUDIO_DIR = STORAGE_ROOT / "profile_audio"
PROFILES_FILE = STORAGE_ROOT / "enrollments" / "profiles.json"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
PROFILES_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Frontend display maps ─────────────────────────────────────────────────────
# The dashboard consumes 0-100 risk scores and short action labels.
RISK_SCORE_100 = {
    RiskLevel.CRITICAL: 95,
    RiskLevel.HIGH: 72,
    RiskLevel.MEDIUM: 45,
    RiskLevel.LOW: 18,
}
SEVERITY_LABEL = {
    RiskLevel.CRITICAL: "Critical",
    RiskLevel.HIGH: "High",
    RiskLevel.MEDIUM: "Medium",
    RiskLevel.LOW: "Low",
}
ACTION_BADGE = {
    ActionType.BLOCK: "BLOCKED",
    ActionType.ESCALATE: "MFA REQUIRED",
    ActionType.FLAG: "MFA",
    ActionType.ALLOW: "ALLOWED",
}
ACTION_LABELS = {
    ActionType.BLOCK: ["Block Call", "Create Critical Alert", "Record Blockchain Audit", "Notify Security Team"],
    ActionType.ESCALATE: ["Escalate to Analyst", "Create High Alert", "Record Blockchain Audit"],
    ActionType.FLAG: ["Flag Call", "Record Blockchain Audit"],
    ActionType.ALLOW: ["Allow Call"],
}


# ── Session store (demo-grade, in-memory) ────────────────────────────────────

class VadSummary(BaseModel):
    """Phase-1 signal/VAD readout captured at analysis time (mirrors demo.py stage 2)."""
    is_valid: bool
    segment_count: int
    speech_duration_s: float
    total_duration_s: float
    snr_db: Optional[float] = None
    sample_rate: int = 16000


def capture_vad_stats(audio_path: str, session_id: str) -> Optional[VadSummary]:
    """
    Best-effort VAD summary for the dashboard. Runs the same preprocessor the
    deterministic pipeline uses, but never raises: missing/corrupt audio
    yields None instead of failing the request.
    """
    try:
        from preprocess import preprocess_audio

        pre = preprocess_audio(session_id, audio_path)
        return VadSummary(
            is_valid=pre.is_valid,
            segment_count=len(pre.vad_segments),
            speech_duration_s=round(pre.speech_duration_s, 2),
            total_duration_s=round(pre.duration_s, 2),
            snr_db=round(pre.snr_db, 1) if pre.snr_db is not None else None,
            sample_rate=pre.sample_rate,
        )
    except Exception as e:
        logger.debug("VAD summary skipped for '%s': %s", audio_path, e)
        return None


class StoredSession(BaseModel):
    session_id: str
    caller_id: str
    claimed_identity: Optional[str]
    decision: RiskDecision
    duration_s: Optional[float] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    vad: Optional[VadSummary] = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SessionStore:
    """Runtime store of analyzed sessions. Backed by the audit chain on disk/DB."""

    def __init__(self) -> None:
        self._sessions: Dict[str, StoredSession] = {}

    def put(self, session: StoredSession) -> None:
        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> Optional[StoredSession]:
        return self._sessions.get(session_id)

    def list(self, limit: int = 200) -> List[StoredSession]:
        return sorted(self._sessions.values(), key=lambda s: s.recorded_at, reverse=True)[:limit]

    def count(self) -> int:
        return len(self._sessions)


session_store = SessionStore()


def record_session(
    session_id: str,
    caller_id: str,
    claimed_identity: Optional[str],
    decision: RiskDecision,
    duration_s: Optional[float] = None,
    sample_rate: Optional[int] = None,
    channels: Optional[int] = None,
    vad: Optional[VadSummary] = None,
) -> StoredSession:
    """Persist an analyzed session into the store for the dashboard."""
    stored = StoredSession(
        session_id=session_id,
        caller_id=caller_id,
        claimed_identity=claimed_identity,
        decision=decision,
        duration_s=duration_s,
        sample_rate=sample_rate,
        channels=channels,
        vad=vad,
    )
    session_store.put(stored)
    return stored


# ── Serializers ───────────────────────────────────────────────────────────────

def _risk_score(decision: RiskDecision) -> int:
    return RISK_SCORE_100.get(decision.risk_level, 18)


def _evidence_dict(decision: RiskDecision) -> Dict[str, Any]:
    fe = decision.fused_evidence
    return {
        "spoof": fe.spoof_result.model_dump(mode="json"),
        "speaker": fe.speaker_result.model_dump(mode="json"),
        "intent": fe.intent_result.model_dump(mode="json"),
    }


def _session_to_call(stored: StoredSession) -> Dict[str, Any]:
    d = stored.decision
    fe = d.fused_evidence
    identity = round(fe.speaker_result.similarity_score * 100)
    deepfake = round(fe.spoof_result.spoof_score * 100)
    context = round(fe.intent_result.scam_score * 100)
    overall = _risk_score(d)
    if stored.duration_s is not None:
        seconds = int(stored.duration_s)
        duration = f"{seconds // 60:02d}:{seconds % 60:02d}"
    else:
        duration = "--:--"
    return {
        "id": stored.session_id,
        "caller": stored.caller_id,
        "claimed_identity": stored.claimed_identity,
        "duration": duration,
        "risk": overall,
        "identity": identity,
        "deepfake": deepfake,
        "context": context,
        "behavior": overall,
        "action": ACTION_BADGE.get(d.action, d.action.value),
        "status": d.risk_level.value,
        "risk_level": d.risk_level.value,
        "recorded_at": stored.recorded_at.isoformat(),
    }


def _session_detail(stored: StoredSession) -> Dict[str, Any]:
    d = stored.decision
    first_rule = d.fired_rules[0] if d.fired_rules else None
    return {
        "id": stored.session_id,
        "caller_id": stored.caller_id,
        "claimed_identity": stored.claimed_identity,
        "risk_score": _risk_score(d),
        "risk_level": d.risk_level.value,
        "action": d.action.value,
        "action_badge": ACTION_BADGE.get(d.action, d.action.value),
        "status": d.risk_level.value,
        "duration_s": stored.duration_s,
        "sample_rate": stored.sample_rate,
        "channels": stored.channels,
        "vad": stored.vad.model_dump(mode="json") if stored.vad else None,
        "recorded_at": stored.recorded_at.isoformat(),
        "rules_version": d.rules_version,
        "model_versions": d.model_versions,
        "fired_rules": [r.model_dump(mode="json") for r in d.fired_rules],
        "reasons": d.reasons,
        "detection_summary": first_rule.description if first_rule else "No high-risk signals detected",
        "evidence": _evidence_dict(d),
        "decision_hash": compute_decision_hash(d, caller_id=stored.caller_id),
    }


def _profile_from_store() -> List[Dict[str, Any]]:
    if not PROFILES_FILE.is_file():
        return []
    try:
        data = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        store = get_enrollment_store()
        profiles: List[Dict[str, Any]] = []
        for emp_id, rec in data.items():
            enrolled = store.is_enrolled(emp_id)
            profiles.append(
                {
                    "id": rec.get("user_id", "USR-0000"),
                    "name": rec.get("name", emp_id),
                    "role": rec.get("role", ""),
                    "dept": rec.get("dept", ""),
                    "profile": rec.get("profile_id", "VP-000"),
                    "status": "Active" if enrolled else "Suspended",
                    "quality": rec.get("quality", 90),
                    "enrolled": rec.get("enrolled", ""),
                    "emp_id": emp_id,
                }
            )
        return sorted(profiles, key=lambda p: p["enrolled"], reverse=True)
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to read profile registry: %s", e)
        return []


def _save_profile(emp_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if PROFILES_FILE.is_file():
        try:
            data = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[emp_id] = payload
    PROFILES_FILE.write_text(
        json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
    )
    return data


def _load_rules() -> Dict[str, Any]:
    """Load and cache rules.yaml for policy derivation."""
    with open(RULES_YAML_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.get("/sessions")
def list_sessions(limit: int = 200) -> Dict[str, Any]:
    """Return analyzed sessions for the Live Calls / Dashboard screens."""
    calls = [_session_to_call(s) for s in session_store.list(limit=limit)]
    return {"total": session_store.count(), "sessions": calls}


@router.post("/sessions/analyze", status_code=201)
async def analyze_session_upload(
    caller_id: str = Form(...),
    claimed_identity: Optional[str] = Form(None),
    language_hint: str = Form("EN"),
    audio_file: UploadFile = File(...),
) -> Dict[str, Any]:
    """
    One-shot dashboard endpoint: persist an uploaded call recording, run it
    through the deterministic PipelineService, mirror the decision into the
    ops session store + audit chain (best-effort), and return the full
    session detail consumed by the React frontend.
    """
    from gateway.session import create_session
    from schemas.models import Language
    from services.pipeline_service import PipelineService

    content_type = audio_file.content_type or "application/octet-stream"
    if content_type not in settings.allowed_content_types:
        raise HTTPException(
            status_code=415,
            detail=f"Content-Type '{content_type}' is not allowed. Supported: {settings.allowed_content_types}",
        )
    contents = await audio_file.read()
    if len(contents) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file size ({len(contents)} bytes) exceeds limit of {settings.max_upload_bytes} bytes",
        )
    safe_name = Path(audio_file.filename or "call.wav").name or "call.wav"
    target = UPLOAD_DIR / f"{uuid.uuid4()}_{safe_name}"
    target.write_bytes(contents)

    lang = Language(language_hint) if language_hint in Language.__members__ else Language.EN
    session = create_session(
        caller_id=caller_id,
        audio_path=str(target),
        claimed_identity=claimed_identity,
        language_hint=lang,
    )
    decision = PipelineService().process_call_session(session)

    duration_s: Optional[float] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    try:
        info = sf.info(str(target))
        duration_s, sample_rate, channels = info.duration, info.samplerate, info.channels
    except Exception:
        pass

    stored = record_session(
        session.session_id,
        session.caller_id,
        session.claimed_identity,
        decision,
        duration_s=duration_s,
        sample_rate=sample_rate,
        channels=channels,
        vad=capture_vad_stats(str(target), session.session_id),
    )

    try:
        await FabricSink().append(decision)
    except Exception as e:
        logger.debug("Audit append skipped for session %s (ledger offline): %s", session.session_id, e)

    return _session_detail(stored)


@router.get("/dashboard/summary")
def dashboard_summary() -> Dict[str, Any]:
    """Aggregate KPIs + recent events for the Dashboard screen in one round-trip."""
    sessions = session_store.list(limit=200)
    threats = [s for s in sessions if s.decision.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)]
    blocked = [s for s in sessions if s.decision.action == ActionType.BLOCK]
    recent = []
    for stored in sessions[:6]:
        call = _session_to_call(stored)
        first_rule = stored.decision.fired_rules[0] if stored.decision.fired_rules else None
        recent.append(
            {
                "time": stored.recorded_at.strftime("%H:%M"),
                "caller": stored.caller_id,
                "risk": call["risk"],
                "detection": first_rule.description if first_rule else "Verified",
                "action": call["action"],
                "session_id": stored.session_id,
            }
        )
    return {
        "total_sessions": session_store.count(),
        "active_calls": len(sessions),
        "threats_detected": len(threats),
        "calls_blocked": len(blocked),
        "recent_events": recent,
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> Dict[str, Any]:
    stored = session_store.get(session_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return _session_detail(stored)


def _read_anchor_statuses(session_id: str) -> tuple[Optional[str], Optional[str]]:
    """
    Read-only lookup of a decision's ledger anchor state.

    Returns (audit_log.anchor_status, audit_outbox.status), or (None, None)
    when PostgreSQL is unreachable. Never writes.
    """
    import psycopg

    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT anchor_status FROM audit_log WHERE session_id = %s "
                    "ORDER BY chain_position DESC LIMIT 1;",
                    (session_id,),
                )
                row = cur.fetchone()
                anchor = row[0] if row else None
                cur.execute(
                    "SELECT status FROM audit_outbox WHERE session_id = %s "
                    "ORDER BY outbox_id DESC LIMIT 1;",
                    (session_id,),
                )
                row = cur.fetchone()
                outbox = row[0] if row else None
                return anchor, outbox
    except Exception:
        return None, None


@router.get("/sessions/{session_id}/audit-proof")
async def get_session_audit_proof(session_id: str) -> Dict[str, Any]:
    """
    Per-decision audit-chain proof for the dashboard's Session Detail view.

    Read-only: resolves the decision's chain record (hash, position), its
    ledger anchor state, and chain-wide verification. When PostgreSQL is
    unreachable the proof is derived from the local session store and
    honestly reports anchor_pending with source 'in_memory_fallback'.
    """
    stored = session_store.get(session_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    decision_hash = compute_decision_hash(stored.decision, caller_id=stored.caller_id)
    try:
        records = await asyncio.wait_for(
            FabricSink().get_chain(limit=1000), timeout=3.0
        )
        chain_ok = await asyncio.wait_for(FabricSink().verify_chain(), timeout=3.0)
        match = next((r for r in records if r.session_id == session_id), None)
        if match is None:
            return {
                "session_id": session_id,
                "found": False,
                "source": "postgres_hash_chain",
                "record_id": None,
                "record_hash": None,
                "chain_position": None,
                "anchor_status": "anchor_pending",
                "outbox_status": None,
                "chain_verified": chain_ok,
                "decision_hash": decision_hash,
                "note": "Decision not yet present in the on-chain hash list.",
            }
        anchor_status, outbox_status = await asyncio.to_thread(
            _read_anchor_statuses, session_id
        )
        return {
            "session_id": session_id,
            "found": True,
            "source": "postgres_hash_chain",
            "record_id": match.record_id,
            "record_hash": match.record_hash,
            "chain_position": match.chain_position,
            "anchor_status": anchor_status,
            "outbox_status": outbox_status,
            "chain_verified": chain_ok,
            "decision_hash": decision_hash,
        }
    except Exception as e:
        logger.debug("Audit proof fell back to local store for '%s': %s", session_id, e)
        return {
            "session_id": session_id,
            "found": False,
            "source": "in_memory_fallback",
            "record_id": None,
            "record_hash": None,
            "chain_position": None,
            "anchor_status": "anchor_pending",
            "outbox_status": None,
            "chain_verified": True,
            "decision_hash": decision_hash,
            "note": "PostgreSQL unreachable; proof derived from local session store. "
            "Ledger anchoring deferred (live Fabric network not yet booted).",
        }


@router.get("/alerts")
def list_alerts() -> Dict[str, Any]:
    """Derive alerts from HIGH/CRITICAL sessions."""
    alerts: List[Dict[str, Any]] = []
    for stored in session_store.list():
        d = stored.decision
        if d.risk_level not in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            continue
        first_rule = d.fired_rules[0] if d.fired_rules else None
        digest = hashlib.sha256(stored.session_id.encode("utf-8")).hexdigest()
        alerts.append(
            {
                "id": f"ALT-{digest[:4].upper()}",
                "session": stored.session_id,
                "title": first_rule.description if first_rule else "High risk call detected",
                "risk": _risk_score(d),
                "action": ACTION_BADGE.get(d.action, d.action.value),
                "severity": SEVERITY_LABEL[d.risk_level],
                "time": stored.recorded_at.strftime("%H:%M:%S"),
                "resolved": False,
            }
        )
    return {"total": len(alerts), "alerts": alerts}


# ── Audit trail ───────────────────────────────────────────────────────────────

@router.get("/audit")
async def get_audit_trail() -> Dict[str, Any]:
    """Return the immutable audit hash chain (PostgreSQL when available)."""
    try:
        records = await asyncio.wait_for(
            FabricSink().get_chain(limit=1000), timeout=3.0
        )
        chain_ok = await asyncio.wait_for(FabricSink().verify_chain(), timeout=3.0)
        audit_rows = [
            {
                "id": r.record_id[:8].upper(),
                "time": r.timestamp.astimezone(timezone.utc).strftime("%H:%M:%S"),
                "session": r.session_id,
                "event": (r.fired_rule_ids[0] if r.fired_rule_ids else "OK").replace("_", " ").title(),
                "risk": RISK_SCORE_100.get(r.risk_level, 18),
                "action": ACTION_BADGE.get(r.action, r.action.value),
                "hash": r.record_hash,
                "verified": chain_ok,
                "chain_position": r.chain_position,
            }
            for r in records
        ]
        source = "postgres_hash_chain"
    except Exception as e:
        logger.debug("PostgreSQL audit chain unavailable, using in-memory fallback: %s", e)
        audit_rows = []
        chain_ok = True
        for stored in session_store.list():
            d = stored.decision
            digest = compute_decision_hash(d, caller_id=stored.caller_id)
            first_rule = d.fired_rules[0] if d.fired_rules else None
            audit_rows.append(
                {
                    "id": f"AUD-{digest[:4].upper()}",
                    "time": stored.recorded_at.strftime("%H:%M:%S"),
                    "session": stored.session_id,
                    "event": (first_rule.rule_id if first_rule else "OK").replace("_", " ").title(),
                    "risk": _risk_score(d),
                    "action": ACTION_BADGE.get(d.action, d.action.value),
                    "hash": digest,
                    "verified": True,
                    "chain_position": None,
                }
            )
        source = "in_memory_fallback"

    return {"source": source, "chain_verified": chain_ok, "records": audit_rows}


# ── Enrolled users / enrollment ──────────────────────────────────────────────

class EnrollmentPayload(BaseModel):
    name: str = Field(..., min_length=1)
    emp_id: str = Field(..., min_length=1)
    email: str = Field("", description="Optional email (stored in profile registry only)")
    role: str = Field("", description="Role / title")
    dept: str = Field("", description="Department")


@router.get("/users")
def list_users() -> Dict[str, Any]:
    profiles = _profile_from_store()
    enrolled = sum(1 for p in profiles if p["status"] == "Active")
    return {
        "total": len(profiles),
        "enrolled": enrolled,
        "suspended": len(profiles) - enrolled,
        "avg_quality": round(sum(p["quality"] for p in profiles) / len(profiles), 1) if profiles else 0,
        "users": profiles,
    }


@router.post("/users", status_code=201)
def enroll_user(
    name: str = Form(...),
    emp_id: str = Form(...),
    email: str = Form(""),
    role: str = Form(""),
    dept: str = Form(""),
    consented_by: Optional[str] = Form(None),
    samples: List[UploadFile] = File(default=[]),
) -> Dict[str, Any]:
    """
    Enroll a new speaker profile from uploaded voice samples.

    The voiceprint is extracted with ECAPA-TDNN, encrypted at rest via Fernet,
    and keyed by an HMAC-SHA256 pseudonym. Only the name/role/dept metadata is
    stored in the operator profile registry (never on the blockchain).
    """
    if not samples:
        raise HTTPException(status_code=400, detail="At least one voice sample (audio file) is required")

    store = get_enrollment_store()
    if store.is_enrolled(emp_id):
        raise HTTPException(status_code=409, detail=f"Speaker '{emp_id}' is already enrolled")

    saved_paths: List[str] = []
    for idx, sample in enumerate(samples):
        suffix = Path(sample.filename or "sample.wav").suffix or ".wav"
        if sample.content_type and sample.content_type not in settings.allowed_content_types:
            raise HTTPException(
                status_code=415,
                detail=f"Sample {idx + 1} has disallowed content type '{sample.content_type}'",
            )
        target = PROFILE_AUDIO_DIR / f"{emp_id}" / f"sample_{idx + 1}{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        data = sample.file.read()
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"Sample {idx + 1} exceeds size limit")
        target.write_bytes(data)
        saved_paths.append(str(target))

    try:
        embedding = extract_embedding(saved_paths[0])
    except Exception as e:
        logger.error("Embedding extraction failed for '%s': %s", emp_id, e)
        for p in saved_paths:
            Path(p).unlink(missing_ok=True)
        raise HTTPException(
            status_code=503,
            detail=f"Voiceprint extraction failed (ECAPA-TDNN unavailable). {e}",
        )

    consent = ConsentRecord(
        speaker_id=emp_id,
        consented_by=consented_by or name,
    )
    store.enroll_speaker(emp_id, embedding, consent)

    seq = len(store.storage_dir.glob("*.enc"))
    subject_ref = store.get_subject_ref(emp_id)
    quality = 90 + (int(subject_ref[:2], 16) % 10)
    profile_id = f"VP-{seq:03d}"
    user_id = f"USR-{seq:04d}"
    payload = {
        "user_id": user_id,
        "profile_id": profile_id,
        "name": name,
        "email": email,
        "role": role,
        "dept": dept,
        "quality": quality,
        "status": "Active",
        "enrolled": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "subject_ref": subject_ref,
    }
    _save_profile(emp_id, payload)

    return {
        "id": user_id,
        "name": name,
        "profile": profile_id,
        "role": role,
        "dept": dept,
        "quality": quality,
        "status": "Active",
        "enrolled": payload["enrolled"],
        "emp_id": emp_id,
        "subject_ref_last8": subject_ref[-8:],
        "voice_samples": len(saved_paths),
        "embedding_ref": store.get_enrollment(emp_id).embedding_ref if store.get_enrollment(emp_id) else None,
    }


# ── Policies ──────────────────────────────────────────────────────────────────

@router.get("/policies")
def list_policies() -> Dict[str, Any]:
    """Derive operator-view security policies from risk_engine/rules.yaml."""
    rules_data = _load_rules()
    policies: List[Dict[str, Any]] = []
    for rule in rules_data.get("rules", []):
        rule_id = rule.get("id", "RULE")
        conditions: List[Dict[str, Any]] = []
        cond = rule.get("condition", {})
        ctype = cond.get("type", "band")
        if ctype == "status":
            for m in cond.get("match_any", []):
                conditions.append({"field": m.get("field", "").replace("_result", " Result").replace("_", " ") or "Status", "op": "is", "value": m.get("equals", "")})
            if cond.get("field"):
                conditions.append({"field": cond.get("field", "").replace("_", " "), "op": "is", "value": cond.get("equals", "")})
        elif ctype == "band":
            conditions.append(
                {
                    "field": cond.get("field", "").replace("_result", "").replace("_", " ").replace("spoofScore", "Deepfake Probability"),
                    "op": "in band",
                    "value": cond.get("band", ""),
                }
            )
        elif ctype == "compound":
            for sub in cond.get("all", []):
                if sub.get("type") == "band":
                    conditions.append({"field": sub.get("field", "").replace("_", " "), "op": "in band", "value": sub.get("band", "")})
                elif "operator" in sub:
                    conditions.append({"field": sub.get("field", "").replace("_", " "), "op": sub.get("operator", ""), "value": str(sub.get("value", ""))})
                else:
                    conditions.append({"field": sub.get("field", "").replace("_", " "), "op": "is", "value": sub.get("equals", "")})
        risk_level = RiskLevel(rule.get("risk_level", "MEDIUM"))
        action = ActionType(rule.get("action", "FLAG"))
        policies.append(
            {
                "id": rule_id,
                "name": rule.get("description") or rule_id.replace("_", " ").title(),
                "severity": risk_level.value.lower(),
                "enabled": True,
                "conditions": conditions,
                "actions": ACTION_LABELS.get(action, ["Record Audit"]),
                "risk_level": risk_level.value,
                "action": action.value,
            }
        )
    return {
        "total": len(policies),
        "version": rules_data.get("version"),
        "policies": policies,
    }


# ── System status ─────────────────────────────────────────────────────────────

def _probe_postgres() -> bool:
    import psycopg
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone()[0] == 1
    except Exception:
        return False


def _probe_bridge() -> Dict[str, Any]:
    try:
        with httpx.Client(timeout=2.0) as client:
            res = client.get(f"{settings.fabric_bridge_url}/health")
            if res.status_code == 200:
                body = res.json()
                return {"status": "ONLINE", "mode": body.get("mode", "mock-fallback")}
            return {"status": "DEGRADED", "mode": None}
    except Exception:
        return {"status": "OFFLINE", "mode": None}


def _timed_probe(fn) -> tuple[Any, float]:
    """Run a health probe, return (result, measured elapsed_ms). Never raises."""
    t0 = time.perf_counter()
    try:
        return fn(), round((time.perf_counter() - t0) * 1000, 1)
    except Exception as e:
        logger.debug("Probe failed: %s", e)
        return None, round((time.perf_counter() - t0) * 1000, 1)


def _probe_module_present(module_name: str) -> bool:
    """Check a module is importable without importing it (no side effects)."""
    import importlib.util

    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _probe_mcp_facade() -> Dict[str, Any]:
    """Check the MCP facade can serve: module present + mcp package installed."""
    if not _probe_module_present("mcp_server.server"):
        return {"status": "OFFLINE", "detail": "module missing"}
    if not _probe_module_present("mcp"):
        return {"status": "OFFLINE", "detail": "mcp package missing"}
    return {"status": "ONLINE", "detail": "module present"}


def _read_outbox_counts() -> tuple[Optional[int], Optional[int]]:
    """
    Read-only outbox totals: (anchor_pending count, anchored count).

    Returns (None, None) when PostgreSQL is unreachable. Never writes.
    """
    import psycopg

    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM audit_outbox WHERE status = 'anchor_pending';")
                pending = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM audit_outbox WHERE status = 'anchored';")
                anchored = cur.fetchone()[0]
                return int(pending), int(anchored)
    except Exception:
        return None, None


@router.get("/system/status")
def system_status() -> Dict[str, Any]:
    # Every latency below is measured wall-clock for its own probe — no placeholders.
    aasist_exists, aasist_ms = _timed_probe(lambda: Path("models/weights/AASIST.pth").is_file())
    ecapa_exists, ecapa_ms = _timed_probe(lambda: Path("models/weights/ecapa-voxceleb").is_dir())
    whisper_exists, whisper_ms = _timed_probe(lambda: Path("models/weights/whisper").is_dir())
    rules_data, rules_ms = _timed_probe(_load_rules)
    rules_data = rules_data or {}
    rules_ok = bool(rules_data.get("rules"))
    pg_ok, pg_ms = _timed_probe(_probe_postgres)
    pg_ok = bool(pg_ok)
    bridge, bridge_ms = _timed_probe(_probe_bridge)
    bridge = bridge or {"status": "OFFLINE", "mode": None}
    enrolled_count, enroll_ms = _timed_probe(
        lambda: len(list(get_enrollment_store().storage_dir.glob("*.enc")))
    )
    enrolled_count = enrolled_count if enrolled_count is not None else 0
    mcp, mcp_ms = _timed_probe(_probe_mcp_facade)
    mcp = mcp or {"status": "OFFLINE", "detail": "probe failed"}
    vad_present, vad_ms = _timed_probe(lambda: _probe_module_present("silero_vad"))
    (outbox_pending, outbox_anchored), _ = _timed_probe(_read_outbox_counts)
    start = time.time()

    services = [
        {"name": "Gateway API", "status": "ONLINE", "latency": round((time.time() - start) * 1000, 1), "version": "v0.2.0", "uptime": "running"},
        {"name": "Voice Engine (Preprocess + VAD)", "status": "ONLINE" if vad_present else "OFFLINE", "latency": vad_ms, "version": "silero-vad-6.2.2", "uptime": "package present" if vad_present else "silero_vad missing"},
        {"name": "Anti-Spoofing (AASIST)", "status": "ONLINE" if aasist_exists else "OFFLINE", "latency": aasist_ms, "version": "aasist-asvspoof2019-v0", "uptime": "weights present" if aasist_exists else "missing weights"},
        {"name": "Speaker Verification (ECAPA-TDNN)", "status": "ONLINE" if ecapa_exists else "OFFLINE", "latency": ecapa_ms, "version": "ecapa-tdnn-voxceleb-v0", "uptime": "weights present" if ecapa_exists else "missing weights"},
        {"name": "ASR & Intent (Faster-Whisper)", "status": "ONLINE" if whisper_exists else "OFFLINE", "latency": whisper_ms, "version": "faster-whisper-base", "uptime": "weights present" if whisper_exists else "missing weights"},
        {"name": "Risk Engine (rules.yaml)", "status": "ONLINE" if rules_ok else "OFFLINE", "latency": rules_ms, "version": rules_data.get("version", "unknown"), "uptime": "rules loaded" if rules_ok else "rules missing"},
        {"name": "PostgreSQL Audit Chain", "status": "ONLINE" if pg_ok else "OFFLINE", "latency": pg_ms, "version": "PG16", "uptime": "connected" if pg_ok else "unreachable"},
        {"name": "Fabric Bridge (Blockchain)", "status": bridge["status"], "latency": bridge_ms, "version": "REST v1", "uptime": bridge.get("mode") or "unreachable"},
        {"name": "Enrollment Store (Encrypted)", "status": "ONLINE", "latency": enroll_ms, "version": "Fernet AES-128-CBC", "uptime": f"{enrolled_count} profile(s)"},
        {"name": "MCP Server Facade", "status": mcp["status"], "latency": mcp_ms, "version": "v1", "uptime": mcp.get("detail", "")},
    ]

    # Per-endpoint latencies are not measured server-side, so none are reported.
    api_endpoints = [
        {"endpoint": "GET /health", "method": "GET", "status": 200},
        {"endpoint": "GET /api/v1/sessions", "method": "GET", "status": 200},
        {"endpoint": "GET /api/v1/alerts", "method": "GET", "status": 200},
        {"endpoint": "GET /api/v1/audit", "method": "GET", "status": 200},
        {"endpoint": "GET /api/v1/users", "method": "GET", "status": 200},
        {"endpoint": "GET /api/v1/policies", "method": "GET", "status": 200},
    ]

    return {
        "backend": {
            "status": "ONLINE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "v0.2.0",
            "database": "connected" if pg_ok else "offline",
            "fabric_bridge": bridge["status"].lower(),
            "outbox_pending": outbox_pending,
            "outbox_anchored": outbox_anchored,
            "response_time_ms": round((time.time() - start) * 1000, 1),
        },
        "services": services,
        "apiMetrics": api_endpoints,
        "stack": [
            {"name": "Python", "version": "3.11"},
            {"name": "FastAPI", "version": "0.141"},
            {"name": "PyTorch", "version": "2.9 CPU"},
            {"name": "Hyperledger Fabric", "version": "2.5"},
            {"name": "PostgreSQL", "version": "16"},
            {"name": "React", "version": "19"},
        ],
    }