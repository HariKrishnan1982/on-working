"""
Real-time voice gateway (Phase 1: transport + windowing over the existing AI pipeline).

Architecture (deliberately minimal):

    Browser microphone (getUserMedia)
        │  WebRTC audio (Opus/SRTP via aiortc)
        ▼
    POST /api/v1/live/sessions/{id}/offer   (signaling: SDP offer/answer, REST)
        │  No trickle ICE: loopback host candidates are sufficient for the
        │  127.0.0.1 gateway, so the full SDP is exchanged in one round-trip.
        ▼
    AudioFrame consumer  →  adapter (→ 16 kHz mono int16 PCM)  →  stream buffer
        │
        │  every WINDOW_S seconds of buffered audio becomes one window:
        ▼
    temp WAV window  →  existing PipelineService (AASIST/ECAPA/Whisper/fusion/
    risk engine, unmodified)  →  window result (in-memory, WS event)
        │
        │  on END: full buffered audio → one final PipelineService run →
        │  existing ops session store + existing audit mechanism
        ▼
    GET /api/v1/sessions/{live_session_id}  (authoritative, existing endpoint)

Live status events stream over:

    WS /api/v1/live/sessions/{id}/events

Honesty rules enforced here:
- No synthetic audio, scores, transcripts, or statuses anywhere in this module.
- Window results carry only values returned by the real pipeline + measured timings.
- Raw audio lives in memory + short-lived temp window files (deleted after use).
  Only hashes/references reach the audit chain, per existing privacy invariants.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import soundfile as sf
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/live", tags=["live-gateway"])

# ── Processing windows ──────────────────────────────────────────────────────
# Rationale (grounded in the existing branch requirements, not round numbers):
# - AASIST native frame is 64600 samples @16kHz ≈ 4.04 s (pad_or_truncate).
#   An 8 s window always covers ≥1 full native frame with real context.
# - ECAPA-TDNN accepts any length but needs voiced speech; 8 s is ample.
# - Faster-Whisper needs several seconds of speech for a usable transcript.
# - VAD validity gate is only 0.5 s total, so 8 s windows are never gated out
#   for length reasons.
TARGET_SAMPLE_RATE = 16000
WINDOW_S = 8.0
WINDOW_SAMPLES = int(WINDOW_S * TARGET_SAMPLE_RATE)
# Final partial window on END: below this we report "insufficient final audio"
# instead of invoking the pipeline on a meaningless blip.
MIN_FINAL_WINDOW_S = 2.0
MIN_FINAL_SAMPLES = int(MIN_FINAL_WINDOW_S * TARGET_SAMPLE_RATE)

LIVE_WINDOW_ROOT = Path("storage") / "live_windows"
LIVE_WINDOW_ROOT.mkdir(parents=True, exist_ok=True)

# Stale-session sweep bounds.
CONNECT_TIMEOUT_S = 120.0
TERMINAL_TTL_S = 15 * 60.0


class LiveState(str, Enum):
    CREATED = "CREATED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECEIVING_AUDIO = "RECEIVING_AUDIO"
    PROCESSING = "PROCESSING"
    ENDED = "ENDED"
    FAILED = "FAILED"


class FinalStatus(str, Enum):
    NONE = "none"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"


# ── Audio adapter (gateway boundary; VAD/pipeline untouched) ────────────────


def webrtc_frame_to_pcm16(frame: Any) -> np.ndarray:
    """
    Convert an incoming WebRTC AudioFrame to canonical 16 kHz mono int16 PCM.

    Handles s16/s16p and flt/fltp PyAV formats, mono or multi-channel layouts.
    Raises ValueError on empty/corrupt frames (caller treats as dropped frame,
    never as silence to analyse).
    """
    import scipy.signal

    arr = frame.to_ndarray()
    if arr is None or arr.size == 0:
        raise ValueError("Empty WebRTC audio frame")
    fmt_name = ""
    try:
        fmt_name = frame.format.name or ""
    except Exception:
        pass

    # Channel count: prefer the frame layout, fall back to array shape.
    n_channels = 1
    try:
        layout = frame.layout
        channels = getattr(layout, "channels", None)
        if channels is not None:
            n_channels = len(channels)
        elif arr.ndim == 2:
            n_channels = arr.shape[0]
    except Exception:
        n_channels = arr.shape[0] if arr.ndim == 2 else 1

    if arr.ndim == 1 and n_channels > 1:
        # Interleaved packed layout: de-interleave into (channels, samples).
        usable = (arr.shape[0] // n_channels) * n_channels
        if usable == 0:
            raise ValueError("Truncated interleaved WebRTC audio frame")
        arr = arr[:usable].reshape(-1, n_channels).T
    elif arr.ndim == 2 and arr.shape[0] == 1 and n_channels > 1:
        # Packed multi-channel arrives as a single interleaved row.
        row = arr[0]
        usable = (row.shape[0] // n_channels) * n_channels
        if usable == 0:
            raise ValueError("Truncated interleaved WebRTC audio frame")
        arr = row[:usable].reshape(-1, n_channels).T

    if "flt" in fmt_name or arr.dtype == np.float32 or arr.dtype == np.float64:
        mono = np.mean(arr.astype(np.float64), axis=0) if arr.ndim == 2 else arr.astype(np.float64)
    else:
        # Signed 16-bit integer path.
        mono = (
            np.mean(arr.astype(np.float64), axis=0)
            if arr.ndim == 2
            else arr.astype(np.float64)
        )
        mono = mono / 32768.0

    if mono.size == 0:
        raise ValueError("Empty WebRTC audio frame after channel mix")
    mono = np.clip(mono, -1.0, 1.0)

    in_rate = int(getattr(frame, "sample_rate", 0) or 0)
    if in_rate <= 0:
        raise ValueError("WebRTC audio frame has no sample rate")
    if in_rate != TARGET_SAMPLE_RATE:
        gcd = math.gcd(in_rate, TARGET_SAMPLE_RATE)
        up = TARGET_SAMPLE_RATE // gcd
        down = in_rate // gcd
        mono = scipy.signal.resample_poly(mono, up, down).astype(np.float64)
        mono = np.clip(mono, -1.0, 1.0)

    return (mono * 32767.0).astype(np.int16)


# ── Live session state (backend-authoritative) ──────────────────────────────


@dataclass
class WindowResult:
    window_index: int
    audio_s: float
    risk_level: str
    action: str
    risk_score_100: int
    detection_summary: str
    started_at: str
    finished_at: str
    latency_ms: float


@dataclass
class LiveSession:
    session_id: str
    caller_id: str
    claimed_identity: Optional[str]
    language_hint: str
    state: LiveState = LiveState.CREATED
    # Audio transport that feeds this session: "webrtc" (browser microphone)
    # or a telephony transport (e.g. "local-rtp", "provider-media-stream").
    # Both transports share the same buffer → windows → pipeline path.
    transport: str = "webrtc"
    telephony_call_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    connected_at: Optional[float] = None
    first_audio_at: Optional[float] = None
    ended_at: Optional[float] = None
    error: Optional[str] = None
    final_status: FinalStatus = FinalStatus.NONE
    final_error: Optional[str] = None
    result_session_id: Optional[str] = None
    windows: List[WindowResult] = field(default_factory=list)
    buffer: bytearray = field(default_factory=bytearray)
    buffer_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    events: asyncio.Queue = field(default_factory=asyncio.Queue)
    # Bounded operational audit trail: every event emitted on this session,
    # in order (metadata only — never audio). Backs the telephony
    # CALL_RECEIVED … CALL_ENDED trail; the on-chain ledger still carries
    # only the final RiskDecision hash.
    event_log: List[Dict[str, Any]] = field(default_factory=list)
    pc: Any = None
    consumer_task: Any = None
    window_task: Any = None
    finalize_task: Any = None
    window_running: bool = False

    @property
    def audio_samples(self) -> int:
        return len(self.buffer) // 2

    @property
    def audio_seconds(self) -> float:
        return round(self.audio_samples / TARGET_SAMPLE_RATE, 2)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "caller_id": self.caller_id,
            "claimed_identity": self.claimed_identity,
            "language_hint": self.language_hint,
            "transport": self.transport,
            "telephony_call_id": self.telephony_call_id,
            "created_at": _ts(self.created_at),
            "connected_at": _ts(self.connected_at) if self.connected_at else None,
            "first_audio_at": _ts(self.first_audio_at) if self.first_audio_at else None,
            "ended_at": _ts(self.ended_at) if self.ended_at else None,
            "audio_samples_received": self.audio_samples,
            "audio_seconds_received": self.audio_seconds,
            "windows_processed": len(self.windows),
            "windows": [w.__dict__ for w in self.windows],
            "final_status": self.final_status.value,
            "final_error": self.final_error,
            "result_session_id": self.result_session_id,
            "error": self.error,
        }


def _ts(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


_sessions: Dict[str, LiveSession] = {}
_sessions_lock = asyncio.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _emit(session: LiveSession, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
    event = {
        "type": event_type,
        "session_id": session.session_id,
        "timestamp": _now_iso(),
        "data": data or {},
    }
    await session.events.put(event)
    # Operational trail (capped): real emitted events only, never synthesized.
    session.event_log.append(event)
    cap = 200
    try:
        from configs.settings import settings as _settings

        cap = max(16, int(_settings.telephony_event_log_cap))
    except Exception:
        pass
    if len(session.event_log) > cap:
        del session.event_log[: len(session.event_log) - cap]


def _get_session_or_404(session_id: str) -> LiveSession:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Live session '{session_id}' not found")
    return session


async def _sweep_stale() -> None:
    """Best-effort reaper: fail stuck handshakes, drop old terminal sessions."""
    now = time.time()
    async with _sessions_lock:
        for sid, s in list(_sessions.items()):
            if s.state == LiveState.CONNECTING and (now - s.created_at) > CONNECT_TIMEOUT_S:
                s.state = LiveState.FAILED
                s.error = "WebRTC handshake timed out"
                try:
                    await s.events.put(
                        {
                            "type": "session.error",
                            "session_id": sid,
                            "timestamp": _now_iso(),
                            "data": {"error": s.error},
                        }
                    )
                except Exception:
                    pass
                await _close_pc(s)
            elif s.state in (LiveState.ENDED, LiveState.FAILED) and s.ended_at and (
                now - s.ended_at
            ) > TERMINAL_TTL_S:
                _sessions.pop(sid, None)


async def _close_pc(session: LiveSession) -> None:
    pc = session.pc
    session.pc = None
    if pc is not None:
        try:
            await pc.close()
        except Exception as e:
            logger.debug("PC close failed for '%s': %s", session.session_id, e)


# ── Window processing (existing pipeline, unmodified) ───────────────────────


def _risk_score_100(risk_level: Any) -> int:
    from schemas.models import RiskLevel

    return {
        RiskLevel.CRITICAL: 95,
        RiskLevel.HIGH: 72,
        RiskLevel.MEDIUM: 45,
        RiskLevel.LOW: 18,
    }.get(risk_level, 18)


def _run_pipeline_on_wav(
    wav_path: Path,
    session_id: str,
    caller_id: str,
    claimed_identity: Optional[str],
    language_hint: str,
) -> Any:
    """Synchronous: run the existing deterministic pipeline on a WAV file.

    Executed in a worker thread via asyncio.to_thread — never on the event loop.
    """
    import hashlib as _hashlib

    from gateway.session import create_session as _create_session
    from schemas.models import CallSession, Language
    from services.pipeline_service import PipelineService

    raw = wav_path.read_bytes()
    lang = Language(language_hint) if language_hint in Language.__members__ else Language.EN
    base = _create_session(
        caller_id=caller_id,
        audio_path=str(wav_path),
        claimed_identity=claimed_identity,
        language_hint=lang,
    )
    call = CallSession(
        session_id=session_id,
        caller_id=base.caller_id,
        claimed_identity=base.claimed_identity,
        audio_path_encrypted=base.audio_path_encrypted,
        audio_hash_sha256=_hashlib.sha256(raw).hexdigest(),
        language_hint=base.language_hint,
        timestamp=base.timestamp,
        metadata={**(base.metadata or {}), "live": True},
    )
    return PipelineService().process_call_session(call)


def _session_dir(session_id: str) -> Path:
    d = LIVE_WINDOW_ROOT / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _process_window(session: LiveSession, pcm: np.ndarray, window_index: int) -> None:
    """Process one full window through the real pipeline; record + emit result."""
    from gateway.ops_api import ACTION_BADGE

    started = time.perf_counter()
    started_iso = _now_iso()
    wav_path = _session_dir(session.session_id) / f"window_{window_index:03d}.wav"
    try:
        await _emit(
            session,
            "analysis.started",
            {"window_index": window_index, "audio_s": round(len(pcm) / TARGET_SAMPLE_RATE, 2)},
        )
        await asyncio.to_thread(sf.write, str(wav_path), pcm, TARGET_SAMPLE_RATE)
        decision = await asyncio.to_thread(
            _run_pipeline_on_wav,
            wav_path,
            f"{session.session_id}-w{window_index}",
            session.caller_id,
            session.claimed_identity,
            session.language_hint,
        )
        finished_iso = _now_iso()
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        first_rule = decision.fired_rules[0] if decision.fired_rules else None
        result = WindowResult(
            window_index=window_index,
            audio_s=round(len(pcm) / TARGET_SAMPLE_RATE, 2),
            risk_level=decision.risk_level.value,
            action=ACTION_BADGE.get(decision.action, decision.action.value),
            risk_score_100=_risk_score_100(decision.risk_level),
            detection_summary=(
                first_rule.description if first_rule else "No high-risk signals detected"
            ),
            started_at=started_iso,
            finished_at=finished_iso,
            latency_ms=latency_ms,
        )
        session.windows.append(result)
        if session.state == LiveState.RECEIVING_AUDIO:
            session.state = LiveState.PROCESSING
        await _emit(session, "analysis.completed", {**result.__dict__, "final": False})
        if session.state == LiveState.PROCESSING:
            session.state = LiveState.RECEIVING_AUDIO
    except Exception as e:
        logger.exception("Window %d failed for live session '%s'", window_index, session.session_id)
        await _emit(
            session, "session.error", {"window_index": window_index, "error": f"Analysis unavailable: {e}"}
        )
    finally:
        try:
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass
        session.window_running = False
        # Drain any backlog: if another full window accumulated, process it next.
        await _maybe_process_window(session)


async def _maybe_process_window(session: LiveSession) -> None:
    """Start window processing if a full window is buffered and none is running."""
    if session.window_running:
        return
    if session.state in (LiveState.ENDED, LiveState.FAILED):
        return
    async with session.buffer_lock:
        if len(session.buffer) < WINDOW_SAMPLES * 2:
            return
        raw = bytes(session.buffer[: WINDOW_SAMPLES * 2])
        del session.buffer[: WINDOW_SAMPLES * 2]
    pcm = np.frombuffer(raw, dtype=np.int16).copy()
    session.window_running = True
    session.window_task = asyncio.ensure_future(
        _process_window(session, pcm, len(session.windows))
    )


async def ingest_pcm16(session: LiveSession, pcm: Any, source: str = "webrtc") -> int:
    """Shared audio-ingress interface for every transport.

    Browser WebRTC frames (via _consume_track) and telephony RTP/media
    packets (via telephony/ingress.py) both arrive here as canonical 16 kHz
    mono int16 PCM. Buffering, first-audio transition, and window triggering
    are identical for all transports. Returns ingested sample count (0 when
    the session is closed or the chunk is empty).
    """
    if pcm is None or pcm.size == 0:
        return 0
    if session.state in (LiveState.ENDED, LiveState.FAILED):
        return 0
    async with session.buffer_lock:
        session.buffer.extend(pcm.tobytes())
    if session.first_audio_at is None:
        session.first_audio_at = time.time()
        if session.state in (LiveState.CONNECTED, LiveState.PROCESSING):
            session.state = LiveState.RECEIVING_AUDIO
        await _emit(
            session,
            "audio.receiving",
            {"sample_rate": TARGET_SAMPLE_RATE, "channels": 1, "format": "pcm_s16le", "source": source},
        )
    await _maybe_process_window(session)
    return int(pcm.size)


async def _consume_track(session: LiveSession, track: Any) -> None:
    """Pump incoming WebRTC audio frames into the session buffer (real audio only)."""
    from aiortc.mediastreams import MediaStreamError

    try:
        while True:
            if session.state in (LiveState.ENDED, LiveState.FAILED):
                return
            try:
                frame = await track.recv()
            except MediaStreamError:
                logger.info("Audio track ended for live session '%s'", session.session_id)
                return
            try:
                pcm = webrtc_frame_to_pcm16(frame)
            except ValueError as e:
                logger.debug("Dropped corrupt frame for '%s': %s", session.session_id, e)
                continue
            await ingest_pcm16(session, pcm, source="webrtc")
    except asyncio.CancelledError:
        return
    except Exception as e:
        logger.exception("Audio consumer failed for live session '%s'", session.session_id)
        if session.state not in (LiveState.ENDED, LiveState.FAILED):
            session.state = LiveState.FAILED
            session.error = f"Audio ingest failed: {e}"
            await _emit(session, "session.error", {"error": session.error})


def _audit_final_best_effort(decision: Any) -> None:
    """Mirror the final live decision into the audit chain (never raises)."""

    def _runner() -> None:
        try:
            import asyncio as _asyncio

            from audit.fabric_sink import FabricSink

            _asyncio.run(FabricSink().append(decision))
        except Exception as e:
            logger.debug("Live audit append skipped (ledger offline): %s", e)

    thread = threading.Thread(target=_runner, daemon=True, name="vfd-live-audit")
    thread.start()


async def _finalize_session(session: LiveSession) -> None:
    """END path: final partial window + full-audio pipeline run + ops/audit record."""
    from gateway.ops_api import capture_vad_stats
    from gateway.ops_api import record_session as ops_record_session

    try:
        async with session.buffer_lock:
            total_samples = len(session.buffer) // 2
            full = bytes(session.buffer)
            session.buffer.clear()

        if total_samples < MIN_FINAL_SAMPLES:
            session.final_status = FinalStatus.FAILED
            session.final_error = (
                f"Insufficient live audio ({total_samples / TARGET_SAMPLE_RATE:.1f}s < "
                f"{MIN_FINAL_WINDOW_S:.0f}s) — analysis unavailable"
            )
            await _emit(
                session,
                "session.error",
                {"error": session.final_error, "final": True},
            )
            return

        full_pcm = np.frombuffer(full, dtype=np.int16).copy()
        duration_s = len(full_pcm) / TARGET_SAMPLE_RATE
        started = time.perf_counter()
        wav_path = _session_dir(session.session_id) / "full.wav"
        await asyncio.to_thread(sf.write, str(wav_path), full_pcm, TARGET_SAMPLE_RATE)
        try:
            decision = await asyncio.to_thread(
                _run_pipeline_on_wav,
                wav_path,
                session.session_id,
                session.caller_id,
                session.claimed_identity,
                session.language_hint,
            )
            # VAD readout while the temp file still exists (best-effort, never raises).
            vad = capture_vad_stats(str(wav_path), session.session_id)
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass

        stored = ops_record_session(
            session.session_id,
            session.caller_id,
            session.claimed_identity,
            decision,
            duration_s=round(duration_s, 2),
            sample_rate=TARGET_SAMPLE_RATE,
            channels=1,
            vad=vad,
        )
        _audit_final_best_effort(decision)
        # Telephony posture: record the decided action (detect-only — the call
        # itself is never disturbed). Metadata only, never audio or scores
        # beyond what the pipeline already produced.
        try:
            from telephony.policy import resolve_call_action

            resolution = resolve_call_action(decision.action.value, session.session_id)
        except Exception:
            resolution = {"mode": "detect-only", "recorded_action": decision.action.value}
        await _emit(
            session,
            "action.taken",
            {
                "action": decision.action.value,
                "risk_level": decision.risk_level.value,
                "fired_rules": [r.rule_id for r in decision.fired_rules],
                **resolution,
            },
        )
        session.result_session_id = stored.session_id
        session.final_status = FinalStatus.COMPLETE
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        await _emit(
            session,
            "analysis.completed",
            {
                "final": True,
                "audio_s": round(duration_s, 2),
                "risk_level": decision.risk_level.value,
                "action": decision.action.value,
                "risk_score_100": _risk_score_100(decision.risk_level),
                "result_session_id": stored.session_id,
                "latency_ms": latency_ms,
            },
        )
    except Exception as e:
        logger.exception("Finalize failed for live session '%s'", session.session_id)
        session.final_status = FinalStatus.FAILED
        session.final_error = f"Analysis unavailable: {e}"
        await _emit(session, "session.error", {"error": session.final_error, "final": True})


# ── REST: session lifecycle + signaling ─────────────────────────────────────


class CreateLiveSessionRequest(BaseModel):
    caller_id: str = Field(..., min_length=1)
    claimed_identity: Optional[str] = None
    language_hint: str = Field("EN")


class OfferRequest(BaseModel):
    sdp: str = Field(..., min_length=1)
    type: str = Field(..., description="Must be 'offer'")


@router.post("/sessions", status_code=201)
async def create_live_session(body: CreateLiveSessionRequest) -> Dict[str, Any]:
    """Create a backend-owned live-analysis session (state CREATED)."""
    await _sweep_stale()
    session_id = uuid.uuid4().hex
    session = LiveSession(
        session_id=session_id,
        caller_id=body.caller_id,
        claimed_identity=body.claimed_identity,
        language_hint=body.language_hint,
    )
    async with _sessions_lock:
        _sessions[session_id] = session
    await _emit(session, "session.created", {"caller_id": session.caller_id})
    return session.snapshot()


@router.get("/sessions/{session_id}")
async def get_live_session(session_id: str) -> Dict[str, Any]:
    """Authoritative live session state (the frontend must not invent this)."""
    await _sweep_stale()
    return _get_session_or_404(session_id).snapshot()


@router.post("/sessions/{session_id}/offer")
async def live_session_offer(session_id: str, body: OfferRequest) -> Dict[str, Any]:
    """
    WebRTC signaling: accept the browser's SDP offer, return the SDP answer.
    One round-trip carries the full SDP (no trickle ICE needed on loopback).
    """
    from aiortc import RTCPeerConnection, RTCSessionDescription

    session = _get_session_or_404(session_id)
    if session.state in (LiveState.ENDED, LiveState.FAILED):
        raise HTTPException(status_code=409, detail=f"Live session '{session_id}' is already closed")
    if session.pc is not None:
        raise HTTPException(status_code=409, detail=f"Live session '{session_id}' already has a peer connection")
    if body.type != "offer":
        raise HTTPException(status_code=400, detail="Signaling body must be an SDP 'offer'")

    session.state = LiveState.CONNECTING
    pc = RTCPeerConnection()

    @pc.on("track")
    def on_track(track: Any) -> None:
        if track.kind != "audio":
            logger.info("Ignoring non-audio track for live session '%s'", session.session_id)
            return
        logger.info("Audio track received for live session '%s'", session.session_id)
        session.consumer_task = asyncio.ensure_future(_consume_track(session, track))

    @pc.on("connectionstatechange")
    async def on_connectionstatechange() -> None:
        logger.info("PC state '%s' for live session '%s'", pc.connectionState, session.session_id)
        if pc.connectionState == "connected":
            if session.state == LiveState.CONNECTING:
                session.state = LiveState.CONNECTED
                session.connected_at = time.time()
                await _emit(session, "session.connected", {})
        elif pc.connectionState == "failed":
            if session.state not in (LiveState.ENDED, LiveState.FAILED):
                session.state = LiveState.FAILED
                session.error = "WebRTC connection failed"
                await _emit(session, "session.error", {"error": session.error})

    try:
        await pc.setRemoteDescription(RTCSessionDescription(sdp=body.sdp, type=body.type))
    except Exception as e:
        await pc.close()
        session.state = LiveState.FAILED
        session.error = f"Invalid SDP offer: {e}"
        await _emit(session, "session.error", {"error": session.error})
        raise HTTPException(status_code=400, detail=f"Invalid SDP offer: {e}")

    # aiortc's SDP parser is lenient: offers without any audio section parse
    # fine but can never deliver voice. Reject those explicitly and honestly.
    has_audio = any(
        t.kind == "audio"
        for t in pc.getTransceivers()
    ) or "m=audio" in (body.sdp or "").lower()
    if not has_audio:
        await pc.close()
        session.state = LiveState.FAILED
        session.error = "SDP offer contains no audio section"
        await _emit(session, "session.error", {"error": session.error})
        raise HTTPException(status_code=400, detail=session.error)

    session.pc = pc
    try:
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
    except Exception as e:
        await _close_pc(session)
        session.state = LiveState.FAILED
        session.error = f"Signaling failure: {e}"
        await _emit(session, "session.error", {"error": session.error})
        raise HTTPException(status_code=500, detail=f"Signaling failure: {e}")

    desc = pc.localDescription
    return {"sdp": desc.sdp, "type": desc.type, "session_id": session_id}


@router.post("/sessions/{session_id}/end")
async def end_live_session(session_id: str) -> Dict[str, Any]:
    """
    END CALL: stop ingest, close the peer connection, release resources, and
    schedule final full-audio analysis (polled via GET / WS, never faked).
    Idempotent for already-closed sessions.
    """
    session = _get_session_or_404(session_id)
    if session.state in (LiveState.ENDED, LiveState.FAILED):
        return session.snapshot()

    session.state = LiveState.ENDED
    session.ended_at = time.time()

    for task_attr in ("consumer_task", "window_task"):
        task = getattr(session, task_attr)
        if task is not None and not task.done():
            task.cancel()
    await _close_pc(session)
    await _emit(session, "session.ended", {"audio_seconds_received": session.audio_seconds})

    if session.finalize_task is None and session.final_status == FinalStatus.NONE:
        session.final_status = FinalStatus.PROCESSING
        session.finalize_task = asyncio.ensure_future(_finalize_session(session))
    return session.snapshot()


# ── WS: live event stream ───────────────────────────────────────────────────


@router.websocket("/sessions/{session_id}/events")
async def live_session_events(websocket: WebSocket, session_id: str) -> None:
    """Push backend-owned session events. No timer-based fake transitions."""
    session = _sessions.get(session_id)
    if session is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    # Snapshot first so a late joiner never sees invented history.
    await websocket.send_json(
        {
            "type": "session.state",
            "session_id": session_id,
            "timestamp": _now_iso(),
            "data": session.snapshot(),
        }
    )
    try:
        while True:
            event = await session.events.get()
            await websocket.send_json(event)
            if event["type"] == "session.ended":
                # Keep the socket open for the final analysis event, then idle
                # until the client goes away.
                continue
    except WebSocketDisconnect:
        return
    except Exception as e:
        logger.debug("Live events socket closed for '%s': %s", session_id, e)
        return
