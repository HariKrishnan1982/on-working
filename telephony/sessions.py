"""
Telephony session store: creates and owns TelephonySession records and their
backing backend-owned live sessions.

Wiring (transport → existing analysis, never a second pipeline):

    TelephonySession (this module: transport state + media stats)
          ↓ live_session_id
    LiveSession (gateway/live_gateway.py: buffer, windows, PipelineService,
                 risk, ops store, audit — all reused unmodified)

Identity separation: the backing live session's caller_id carries the masked
display form only; the HMAC pseudonym (caller_ref) is the audit-safe
reference. Raw phone numbers never leave this module's creation path and
never appear in snapshots, events, logs, or the audit chain.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional

from configs.settings import settings
from schemas.hash_utils import compute_pseudonymous_subject_ref
from telephony.models import (
    TelephonySession,
    TelephonyState,
    mask_caller_number,
)

logger = logging.getLogger(__name__)

# Stale INCOMING supervision: never-accepted calls fail honestly, never linger.
INCOMING_TIMEOUT_S = 120.0
# RTP/media supervision: silence on an armed media path ends the call.
MEDIA_TIMEOUT_S = 60.0


class TelephonyNotFoundError(KeyError):
    pass


_store: Dict[str, TelephonySession] = {}
_store_lock = asyncio.Lock()
_last_media_at: Dict[str, float] = {}


def _caller_ref(raw_caller: Optional[str], provider_call_id: str) -> str:
    seed = (raw_caller or "").strip() or provider_call_id
    return compute_pseudonymous_subject_ref(seed, settings.vfd_hmac_secret)


async def create_session(
    provider_call_id: str,
    transport: str,
    caller_raw: Optional[str] = None,
    called_raw: Optional[str] = None,
    claimed_identity: Optional[str] = None,
) -> TelephonySession:
    """Create a telephony session on a genuine inbound signal (real packet,
    verified webhook, or authenticated API request). Never called with
    synthetic/demo data in production paths."""
    from gateway import live_gateway as lg

    live_id = uuid.uuid4().hex
    live = lg.LiveSession(
        session_id=live_id,
        caller_id=mask_caller_number(caller_raw),
        claimed_identity=claimed_identity,
        language_hint="EN",
    )
    live.transport = transport
    live.telephony_call_id = provider_call_id
    async with lg._sessions_lock:
        lg._sessions[live_id] = live

    session = TelephonySession(
        telephony_call_id=provider_call_id,
        transport=transport,
        live_session_id=live_id,
        caller_ref=_caller_ref(caller_raw, provider_call_id),
        caller_display=mask_caller_number(caller_raw),
        called_number=mask_caller_number(called_raw) if called_raw else None,
        claimed_identity=claimed_identity,
    )
    async with _store_lock:
        _store[session.session_id] = session
    await lg._emit(live, "telephony.call.received", {"transport": transport})
    logger.info(
        "telephony call received id=%s transport=%s live=%s caller=%s",
        session.session_id,
        transport,
        live_id,
        session.caller_display,
    )
    return session


def get_session(session_id: str) -> TelephonySession:
    session = _store.get(session_id)
    if session is None:
        raise TelephonyNotFoundError(session_id)
    return session


def list_sessions() -> List[TelephonySession]:
    return sorted(_store.values(), key=lambda s: s.created_at, reverse=True)


def find_pending_local(max_age_s: float = 120.0) -> Optional[TelephonySession]:
    """Oldest provisioned RTP-backed leg still awaiting its first packet.

    Lets an operator-provisioned call (POST /calls, or an ARI-tapped Asterisk
    leg whose externalMedia RTP has not arrived yet) claim the next unknown
    media source instead of diverging into a duplicate session.
    """
    from telephony.models import TRANSPORT_ASTERISK_ARI, TRANSPORT_LOCAL_RTP

    now = time.time()
    candidates = [
        s
        for s in _store.values()
        if s.transport in (TRANSPORT_LOCAL_RTP, TRANSPORT_ASTERISK_ARI)
        and s.state in (TelephonyState.INCOMING, TelephonyState.ACCEPTED, TelephonyState.CONNECTING_MEDIA)
        and s.packets_received == 0
        and (now - s.created_at) < max_age_s
    ]
    return min(candidates, key=lambda s: s.created_at) if candidates else None


async def accept_session(session_id: str) -> TelephonySession:
    """Accept an INCOMING call: arms the media path (CONNECTING_MEDIA)."""
    from gateway import live_gateway as lg

    async with _store_lock:
        session = _store.get(session_id)
        if session is None:
            raise TelephonyNotFoundError(session_id)
        if session.state != TelephonyState.INCOMING:
            return session
        session.state = TelephonyState.CONNECTING_MEDIA
        session.accepted_at = time.time()
        live = lg._sessions.get(session.live_session_id)
    if live is not None and live.state == lg.LiveState.CREATED:
        live.state = lg.LiveState.CONNECTED
        live.connected_at = time.time()
        await lg._emit(live, "telephony.call.accepted", {"transport": session.transport})
        await lg._emit(live, "telephony.media.connected", {"transport": session.transport})
    logger.info("telephony call accepted id=%s transport=%s", session_id, session.transport)
    return session


async def fail_session(session_id: str, error: str, reason: str) -> Optional[TelephonySession]:
    """Mark a call FAILED (explicit failure, never silent)."""
    from gateway import live_gateway as lg

    async with _store_lock:
        session = _store.get(session_id)
        if session is None:
            return None
        if session.state in (TelephonyState.ENDED, TelephonyState.FAILED):
            return session
        session.state = TelephonyState.FAILED
        session.error = error
        session.ended_at = time.time()
        session.termination_reason = reason
        live = lg._sessions.get(session.live_session_id)
    if live is not None and live.state not in (lg.LiveState.ENDED, lg.LiveState.FAILED):
        live.state = lg.LiveState.FAILED
        live.error = error
        live.ended_at = time.time()
        await lg._emit(live, "telephony.call.failed", {"error": error, "reason": reason})
    logger.warning("telephony call failed id=%s reason=%s error=%s", session_id, reason, error)
    return session


async def end_session(session_id: str, reason: str = "local_hangup") -> TelephonySession:
    """End a call: stops ingest, runs the shared finalize path (windows +
    full-audio pipeline + ops record + audit), releases resources. Idempotent."""
    from gateway import live_gateway as lg

    async with _store_lock:
        session = _store.get(session_id)
        if session is None:
            raise TelephonyNotFoundError(session_id)
        already = session.state in (TelephonyState.ENDED, TelephonyState.FAILED)
        if not already:
            session.state = TelephonyState.ENDED
            session.ended_at = time.time()
            session.termination_reason = reason
    if not already:
        try:
            await lg.end_live_session(session.live_session_id)
        except Exception as e:
            logger.debug("Backing live end skipped for %s: %s", session_id, e)
        live = lg._sessions.get(session.live_session_id)
        if live is not None:
            await lg._emit(
                live,
                "telephony.call.ended",
                {"reason": reason, "audio_seconds": session.audio_seconds},
            )
        logger.info(
            "telephony call ended id=%s reason=%s audio_s=%s packets=%s lost=%s",
            session_id,
            reason,
            session.audio_seconds,
            session.packets_received,
            session.packets_lost,
        )
    return session


def note_media_activity(session_id: str) -> None:
    _last_media_at[session_id] = time.time()


async def sweep_stale() -> None:
    """Supervision: fail never-accepted calls, end media-timed-out calls."""
    from gateway import live_gateway as lg

    now = time.time()
    async with _store_lock:
        stale = [
            s
            for s in _store.values()
            if s.state == TelephonyState.INCOMING
            and (now - s.created_at) > INCOMING_TIMEOUT_S
        ]
        timed_out = [
            s
            for s in _store.values()
            if s.state in (TelephonyState.CONNECTING_MEDIA, TelephonyState.RECEIVING_AUDIO)
            and _last_media_at.get(s.session_id, s.accepted_at or s.created_at) + MEDIA_TIMEOUT_S < now
        ]
    for s in stale:
        await fail_session(s.session_id, "Call not accepted in time", "signaling_error")
    for s in timed_out:
        await end_session(s.session_id, reason="media_timeout")


async def snapshot(session: TelephonySession) -> dict:
    """Snapshot enriched with backing live-session truth (state, windows).

    `latest_action` is the most recent real window/final decision action, or
    None when no analysis has produced one yet — never a placeholder.
    """
    from gateway import live_gateway as lg

    live = lg._sessions.get(session.live_session_id)
    snap = session.snapshot(
        live_state=live.state.value if live else None,
        live_windows=len(live.windows) if live else 0,
    )
    snap["latest_action"] = live.windows[-1].action if live and live.windows else None
    snap["result_session_id"] = live.result_session_id if live else None
    return snap
