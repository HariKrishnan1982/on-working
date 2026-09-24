"""
Telephony ingress API (provider-neutral transport boundary).

Endpoints (router prefix /api/v1/telephony):

- GET  /status ................. ingress status: provider configured?,
                                  local RTP listener state. Open (dashboard).
- GET  /calls .................. list telephony sessions (real only). Open.
- GET  /calls/{id} ............. one telephony snapshot. Open.
- POST /calls .................. create a call leg (provider signaling).
                                  Requires X-API-Key.
- POST /calls/{id}/accept ...... accept an INCOMING call. Requires X-API-Key.
- POST /calls/{id}/end ......... hang up (shared finalize + audit). Key.
- POST /webhooks/{provider} .... provider signaling webhook (Twilio
                                  signature-verified). No API key; the
                                  provider signature IS the credential.
- WS   /calls/{id}/media ....... provider media-stream socket (Twilio Media
                                  Streams JSON protocol: connected / start /
                                  media / stop). Bound to an existing call id.
- GET  /calls/{id}/events ....... operational lifecycle trail for one call
                                  (CALL_RECEIVED … CALL_ENDED mapped from real
                                  emitted events; metadata only). Open.
- GET  /ari/status ............... Asterisk ARI controller state. Open.
- POST /ari/connect .............. attach to Asterisk ARI (operator action).
                                  Requires X-API-Key.
- POST /ari/disconnect ........... detach from ARI. Requires X-API-Key.

Security: webhooks without a valid signature are rejected (401) and never
create sessions. Raw caller numbers never appear in responses, events, or
logs — only masked display forms and HMAC pseudonyms. Raw audio is never
logged and never touches the audit chain (decision hashes only, via the
shared live-session finalize path).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Security, WebSocket, WebSocketDisconnect
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from configs.settings import settings
from gateway.rate_limit import limit_telephony_signaling, limit_telephony_webhook
from telephony import sessions as ts
from telephony.asterisk_ari import get_ari_controller
from telephony.audio import RtpError, mulaw_to_pcm16, resample_to_16k
from telephony.ingress import get_local_ingress
from telephony.models import (
    TRANSPORT_ASTERISK_ARI,
    TRANSPORT_LOCAL_RTP,
    TRANSPORT_PROVIDER_STREAM,
    TelephonyState,
)
from telephony.policy import EVENT_TO_AUDIT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telephony", tags=["telephony-ingress"])

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _verify_provider_key(api_key: str | None = Security(_api_key_header)) -> str:
    """Same credential as the main gateway (settings.api_key).

    Kept local to this module so the telephony router never imports
    gateway.app (which itself includes this router).
    """
    from fastapi import status as _status

    if not api_key or api_key != settings.api_key:
        raise HTTPException(
            status_code=_status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )
    return api_key


# ── Status ──────────────────────────────────────────────────────────────────


@router.get("/status")
async def telephony_status() -> Dict[str, Any]:
    """Honest ingress status: what is configured, what is listening."""
    from telephony.ingress import _ingress

    provider = (settings.telephony_provider or "").strip().lower()
    local_running = _ingress is not None and _ingress.running
    return {
        "provider": provider or None,
        "provider_configured": bool(provider and settings.telephony_webhook_secret),
        "ari": get_ari_controller().status(),
        "transports": {
            "local_rtp": {
                "enabled": settings.telephony_local_rtp_enabled,
                "listening": local_running,
                "host": settings.telephony_local_rtp_host,
                "port": _ingress.bound_port
                if local_running and _ingress is not None
                else settings.telephony_local_rtp_port,
            },
            "provider_media_stream": {
                "available": bool(provider and settings.telephony_webhook_secret),
            },
        },
        "timestamp": time.time(),
    }


# ── Call control ────────────────────────────────────────────────────────────


class CreateCallRequest(BaseModel):
    transport: str = Field(TRANSPORT_LOCAL_RTP)
    caller_number: Optional[str] = Field(None, description="Caller number as provided by signaling (stored masked only)")
    called_number: Optional[str] = Field(None)
    claimed_identity: Optional[str] = None
    provider_call_id: Optional[str] = Field(None, description="Provider call SID when known")


@router.post("/calls", status_code=201)
async def create_call(
    body: CreateCallRequest,
    _auth: str = Depends(_verify_provider_key),
    _rate: None = Depends(limit_telephony_signaling),
) -> Dict[str, Any]:
    """Create a call leg on genuine provider signaling (authenticated)."""
    if body.transport == TRANSPORT_LOCAL_RTP:
        if not settings.telephony_local_rtp_enabled:
            raise HTTPException(status_code=503, detail="Local RTP ingress is disabled")
        ingress = await get_local_ingress()
        session = await ts.create_session(
            provider_call_id=body.provider_call_id or f"api-{time.time_ns()}",
            transport=TRANSPORT_LOCAL_RTP,
            caller_raw=body.caller_number,
            called_raw=body.called_number,
            claimed_identity=body.claimed_identity,
        )
        if settings.telephony_auto_accept_local:
            await ts.accept_session(session.session_id)
            session = ts.get_session(session.session_id)
        snap = await ts.snapshot(session)
        snap["rtp"] = {
            "host": ingress.host,
            "port": ingress.bound_port or ingress.port,
            "codecs": ["PCMU/8000", "PCMA/8000"],
        }
        return snap
    if body.transport == TRANSPORT_PROVIDER_STREAM:
        if not ((settings.telephony_provider or "").strip() and settings.telephony_webhook_secret):
            raise HTTPException(status_code=503, detail="No telephony provider configured")
        if not body.provider_call_id:
            raise HTTPException(status_code=400, detail="provider_call_id is required for provider streams")
        session = await ts.create_session(
            provider_call_id=body.provider_call_id,
            transport=TRANSPORT_PROVIDER_STREAM,
            caller_raw=body.caller_number,
            called_raw=body.called_number,
            claimed_identity=body.claimed_identity,
        )
        return await ts.snapshot(session)
    raise HTTPException(status_code=400, detail=f"Unknown transport '{body.transport}'")


@router.get("/calls")
async def list_calls() -> Dict[str, Any]:
    await ts.sweep_stale()
    return {"total": len(ts.list_sessions()), "calls": [await ts.snapshot(s) for s in ts.list_sessions()]}


@router.get("/calls/{session_id}")
async def get_call(session_id: str) -> Dict[str, Any]:
    await ts.sweep_stale()
    try:
        return await ts.snapshot(ts.get_session(session_id))
    except ts.TelephonyNotFoundError:
        raise HTTPException(status_code=404, detail=f"Telephony call '{session_id}' not found")


@router.post("/calls/{session_id}/accept")
async def accept_call(
    session_id: str,
    _auth: str = Depends(_verify_provider_key),
    _rate: None = Depends(limit_telephony_signaling),
) -> Dict[str, Any]:
    try:
        session = await ts.accept_session(session_id)
    except ts.TelephonyNotFoundError:
        raise HTTPException(status_code=404, detail=f"Telephony call '{session_id}' not found")
    return await ts.snapshot(session)


@router.post("/calls/{session_id}/end")
async def end_call(
    session_id: str,
    _auth: str = Depends(_verify_provider_key),
    _rate: None = Depends(limit_telephony_signaling),
) -> Dict[str, Any]:
    try:
        session = await ts.end_session(session_id, reason="local_hangup")
    except ts.TelephonyNotFoundError:
        raise HTTPException(status_code=404, detail=f"Telephony call '{session_id}' not found")
    return await ts.snapshot(session)


# ── Provider webhooks (signature-verified signaling) ────────────────────────


def _twilio_expected_url(request: Request) -> str:
    if settings.telephony_public_base_url.strip():
        return settings.telephony_public_base_url.rstrip("/") + request.url.path
    return str(request.url)


def verify_twilio_signature(url: str, params: Dict[str, str], signature: str, auth_token: str) -> bool:
    """Exact Twilio request-validation: base64(HMAC-SHA1(token, url + k+v…))."""
    data = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature)


@router.post("/webhooks/{provider}")
async def provider_webhook(
    provider: str,
    request: Request,
    _rate: None = Depends(limit_telephony_webhook),
) -> Dict[str, Any]:
    configured = (settings.telephony_provider or "").strip().lower()
    if provider.lower() != "twilio" or configured != "twilio":
        raise HTTPException(status_code=404, detail=f"No webhook handler for provider '{provider}'")
    secret = settings.telephony_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Telephony provider not configured")

    length = int(request.headers.get("content-length", "0") or "0")
    if length > settings.telephony_max_body_bytes:
        raise HTTPException(status_code=413, detail="Webhook body exceeds size limit")
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip()
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail=f"Unsupported webhook content type '{content_type}'")
    raw = await request.body()
    if len(raw) > settings.telephony_max_body_bytes:
        raise HTTPException(status_code=413, detail="Webhook body exceeds size limit")

    from urllib.parse import parse_qsl

    try:
        params = dict(parse_qsl(raw.decode("utf-8"), keep_blank_values=True))
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed webhook body")
    signature = request.headers.get("x-twilio-signature", "")
    if not signature or not verify_twilio_signature(_twilio_expected_url(request), params, signature, secret):
        logger.warning("Rejected telephony webhook with invalid signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    call_sid = params.get("CallSid", "")
    if not call_sid:
        raise HTTPException(status_code=400, detail="Webhook missing CallSid")
    status = (params.get("CallStatus") or "").lower()

    if status in ("completed", "failed", "busy", "no-answer", "canceled"):
        existing = next(
            (s for s in ts.list_sessions() if s.telephony_call_id == call_sid), None
        )
        if existing is not None:
            await ts.end_session(existing.session_id, reason="remote_bye")
        return {"ok": True, "action": "ended"}

    if status in ("in-progress",):
        existing = next(
            (s for s in ts.list_sessions() if s.telephony_call_id == call_sid), None
        )
        if existing is None:
            session = await ts.create_session(
                provider_call_id=call_sid,
                transport=TRANSPORT_PROVIDER_STREAM,
                caller_raw=params.get("From"),
                called_raw=params.get("To"),
            )
            await ts.accept_session(session.session_id)
        else:
            await ts.accept_session(existing.session_id)
        return {"ok": True, "action": "accepted"}

    # initiated / ringing / queued: record the inbound leg, arm on answer.
    existing = next((s for s in ts.list_sessions() if s.telephony_call_id == call_sid), None)
    if existing is None:
        await ts.create_session(
            provider_call_id=call_sid,
            transport=TRANSPORT_PROVIDER_STREAM,
            caller_raw=params.get("From"),
            called_raw=params.get("To"),
        )
    return {"ok": True, "action": "received"}


# ── Provider media stream (Twilio Media Streams JSON protocol) ─────────────


@router.websocket("/calls/{session_id}/media")
async def provider_media_stream(websocket: WebSocket, session_id: str) -> None:
    """Receive genuine provider media frames for an existing accepted call."""
    from gateway import live_gateway as lg

    try:
        session = ts.get_session(session_id)
    except ts.TelephonyNotFoundError:
        await websocket.close(code=4404)
        return
    if session.transport != TRANSPORT_PROVIDER_STREAM:
        await websocket.close(code=4404)
        return
    if session.state in (TelephonyState.ENDED, TelephonyState.FAILED):
        await websocket.close(code=4404)
        return
    await websocket.accept()
    live = lg._sessions.get(session.live_session_id)
    if live is None:  # pragma: no cover - defensive
        await websocket.close(code=4404)
        return
    if live.state == lg.LiveState.CREATED:
        live.state = lg.LiveState.CONNECTED
        live.connected_at = time.time()
        await lg._emit(live, "telephony.media.connected", {"transport": TRANSPORT_PROVIDER_STREAM})
    ts.note_media_activity(session_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                session.packets_dropped += 1
                continue
            event = msg.get("event")
            if event == "connected":
                continue
            if event == "start":
                ts.note_media_activity(session_id)
                continue
            if event == "stop":
                await ts.end_session(session_id, reason="remote_bye")
                return
            if event != "media":
                session.packets_dropped += 1
                continue
            media = msg.get("media") or {}
            payload_b64 = media.get("payload", "")
            try:
                payload = base64.b64decode(payload_b64)
            except Exception:
                session.packets_dropped += 1
                continue
            track = (media.get("track") or "inbound").lower()
            if track != "inbound" or not payload:
                session.packets_dropped += 1
                continue
            try:
                pcm8 = mulaw_to_pcm16(payload)
                pcm = resample_to_16k(pcm8, 8000)
            except RtpError:
                session.packets_dropped += 1
                continue
            if session.codec is None:
                session.codec = "PCMU"
            session.packets_received += 1
            session.bytes_received += len(payload)
            session.audio_samples_16k += int(pcm.size)
            ts.note_media_activity(session_id)
            if session.state in (TelephonyState.CONNECTING_MEDIA, TelephonyState.ACCEPTED):
                session.state = TelephonyState.RECEIVING_AUDIO
                session.first_audio_at = time.time()
                await lg._emit(
                    live, "telephony.audio.receiving",
                    {"codec": "PCMU", "transport": TRANSPORT_PROVIDER_STREAM},
                )
            await lg.ingest_pcm16(live, pcm, source=TRANSPORT_PROVIDER_STREAM)
    except WebSocketDisconnect:
        if session.state not in (TelephonyState.ENDED, TelephonyState.FAILED):
            await ts.end_session(session_id, reason="remote_bye")
        return
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("Provider media socket closed for '%s': %s", session_id, e)
        return


# ── Lifecycle audit trail (operational, metadata only) ────────────────────


@router.get("/calls/{session_id}/events")
async def call_events(session_id: str) -> Dict[str, Any]:
    """Ordered lifecycle trail for one call, mapped to audit-facing names.

    Sources are the backing live session's actually-emitted events — nothing
    is synthesized. Audio, transcripts, scores, and secrets never appear here.
    """
    from gateway import live_gateway as lg

    try:
        session = ts.get_session(session_id)
    except ts.TelephonyNotFoundError:
        raise HTTPException(status_code=404, detail=f"Telephony call '{session_id}' not found")
    live = lg._sessions.get(session.live_session_id)
    trail = []
    for event in (live.event_log if live is not None else []):
        etype = event.get("type", "")
        trail.append(
            {
                "audit_event": EVENT_TO_AUDIT.get(etype, etype),
                "event": etype,
                "timestamp": event.get("timestamp"),
                "data": event.get("data") or {},
            }
        )
    return {"session_id": session_id, "total": len(trail), "events": trail}


# ── Asterisk ARI control (operator-driven, never auto-started) ────────────


@router.get("/ari/status")
async def ari_status() -> Dict[str, Any]:
    """Honest ARI controller state: configured? connected? last error?

    No secrets are ever returned (the password is never even read here).
    """
    return get_ari_controller().status()


@router.post("/ari/connect")
async def ari_connect(
    _auth: str = Depends(_verify_provider_key),
    _rate: None = Depends(limit_telephony_signaling),
) -> Dict[str, Any]:
    """Attach the ARI controller to the configured Asterisk host."""
    return await get_ari_controller().connect()


@router.post("/ari/disconnect")
async def ari_disconnect(
    _auth: str = Depends(_verify_provider_key),
    _rate: None = Depends(limit_telephony_signaling),
) -> Dict[str, Any]:
    """Detach the ARI controller (taps already attached keep running on the
    PBX; only new Stasis events stop being consumed)."""
    return await get_ari_controller().disconnect()
