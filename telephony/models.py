"""
Telephony session abstraction (provider-neutral).

A TelephonySession represents one real inbound call leg. It owns transport
state and media statistics only; analysis state lives on the backing
backend-owned live session (gateway/live_gateway.py), which is the single
source of truth for audio windows, risk, and audit.

Identity separation (never the raw phone number as primary identity):
- session_id .......... internal backend-owned UUID (primary identity)
- provider_call_id .... opaque provider/local reference (routing only)
- caller_ref .......... HMAC-SHA256 pseudonym of the caller (audit-safe)
- caller_display ...... masked display form, e.g. +91******3210 (UI only)
- live_session_id ..... backing real-time gateway session (analysis truth)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class TelephonyState(str, Enum):
    INCOMING = "INCOMING"
    ACCEPTED = "ACCEPTED"
    CONNECTING_MEDIA = "CONNECTING_MEDIA"
    RECEIVING_AUDIO = "RECEIVING_AUDIO"
    ANALYZING = "ANALYZING"
    ENDED = "ENDED"
    FAILED = "FAILED"


class TerminationReason(str, Enum):
    REMOTE_BYE = "remote_bye"
    LOCAL_HANGUP = "local_hangup"
    MEDIA_TIMEOUT = "media_timeout"
    SIGNALING_ERROR = "signaling_error"
    UNSUPPORTED_CODEC = "unsupported_codec"
    AUTH_FAILED = "auth_failed"


TRANSPORT_LOCAL_RTP = "local-rtp"
TRANSPORT_PROVIDER_STREAM = "provider-media-stream"
# Asterisk PBX legs tapped via the ARI controller (snoop + externalMedia RTP
# into the local RTP ingress). Media arrives as RTP; only the signaling path
# (StasisStart/End) and correlation differ from plain local-rtp.
TRANSPORT_ASTERISK_ARI = "asterisk-ari"


def mask_caller_number(raw: Optional[str]) -> str:
    """Best-effort masked display form: keep '+' + first 2 + last 4 digits.

    Returns 'unknown' for missing/too-short input. Deterministic and
    irreversible for display purposes; the raw number is never exposed
    through telephony snapshots.
    """
    if not raw:
        return "unknown"
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) < 7:
        return "unknown"
    prefix = "+" + digits[:2]
    return f"{prefix}******{digits[-4:]}"


def _ts(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


@dataclass
class TelephonySession:
    telephony_call_id: str
    transport: str
    live_session_id: str
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    caller_ref: Optional[str] = None
    caller_display: str = "unknown"
    called_number: Optional[str] = None  # masked at creation, never raw
    claimed_identity: Optional[str] = None
    state: TelephonyState = TelephonyState.INCOMING
    created_at: float = field(default_factory=time.time)
    accepted_at: Optional[float] = None
    media_connected_at: Optional[float] = None
    first_audio_at: Optional[float] = None
    ended_at: Optional[float] = None
    termination_reason: Optional[str] = None
    error: Optional[str] = None
    # Media statistics (measured counters only, never estimated).
    packets_received: int = 0
    packets_lost: int = 0
    packets_dropped: int = 0
    bytes_received: int = 0
    audio_samples_16k: int = 0
    discontinuities: int = 0
    jitter_max_ms: float = 0.0
    codec: Optional[str] = None

    @property
    def audio_seconds(self) -> float:
        return round(self.audio_samples_16k / 16000, 2)

    def snapshot(self, live_state: Optional[str] = None, live_windows: int = 0) -> Dict[str, Any]:
        """Backend-owned snapshot. Raw phone numbers never appear here."""
        reported = self.state.value
        # ANALYZING is derived truthfully: media flowing AND the backing
        # live session has started real window processing.
        if self.state == TelephonyState.RECEIVING_AUDIO and (
            live_state == "PROCESSING" or live_windows > 0
        ):
            reported = TelephonyState.ANALYZING.value
        return {
            "session_id": self.session_id,
            "telephony_call_id": self.telephony_call_id,
            "transport": self.transport,
            "live_session_id": self.live_session_id,
            "caller_ref": self.caller_ref,
            "caller_display": self.caller_display,
            "called_number": self.called_number,
            "claimed_identity": self.claimed_identity,
            "state": reported,
            "created_at": _ts(self.created_at),
            "accepted_at": _ts(self.accepted_at) if self.accepted_at else None,
            "media_connected_at": _ts(self.media_connected_at) if self.media_connected_at else None,
            "first_audio_at": _ts(self.first_audio_at) if self.first_audio_at else None,
            "ended_at": _ts(self.ended_at) if self.ended_at else None,
            "termination_reason": self.termination_reason,
            "error": self.error,
            "audio_seconds": self.audio_seconds,
            "stats": {
                "packets_received": self.packets_received,
                "packets_lost": self.packets_lost,
                "packets_dropped": self.packets_dropped,
                "bytes_received": self.bytes_received,
                "discontinuities": self.discontinuities,
                "jitter_max_ms": self.jitter_max_ms,
                "codec": self.codec,
            },
        }
