"""
Telephony ingress implementations (transport layer only).

- TelephonyIngress: provider-neutral interface. Every implementation turns
  real inbound call media into canonical 16 kHz mono int16 PCM and feeds it
  to the existing live-session ingest (gateway/live_gateway.py).
- LocalRtpIngress: a REAL asyncio UDP listener receiving genuine RFC 3550
  RTP packets (PCMU/PCMA/L16). Point any real SIP phone or PBX
  (linphone, baresip, Asterisk, FreeSWITCH) at the bound host/port and
  actual call audio flows into the analysis pipeline. No carrier account,
  no SIP signaling stack, and no simulated media — sessions are created
  only when real packets arrive.

Packet loss, jitter, silence, discontinuity, codec mismatch, and stream
termination are accounted explicitly. Missing audio is counted, never
replaced with generated samples.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import time
from typing import Dict, Optional, Tuple

from configs.settings import settings
from telephony import sessions as ts
from telephony.audio import (
    RtpError,
    RtpPacket,
    RtpStreamTracker,
    UnsupportedCodecError,
    normalize_telephony_payload,
    parse_rtp,
)
from telephony.models import TRANSPORT_LOCAL_RTP, TelephonyState

logger = logging.getLogger(__name__)


class TelephonyIngress(abc.ABC):
    """Provider-neutral ingress interface."""

    @abc.abstractmethod
    async def start(self) -> None:
        """Bind/connect the media path. Idempotent."""
        raise NotImplementedError

    @abc.abstractmethod
    async def stop(self) -> None:
        """Release the media path. Idempotent."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def running(self) -> bool:
        raise NotImplementedError


class _RtpProtocol(asyncio.DatagramProtocol):
    def __init__(self, owner: "LocalRtpIngress") -> None:
        self.owner = owner

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        asyncio.ensure_future(self.owner.handle_datagram(bytes(data), addr))

    def error_received(self, exc: Exception) -> None:  # pragma: no cover - socket errors
        logger.warning("Local RTP socket error: %s", exc)


class LocalRtpIngress(TelephonyIngress):
    """Real UDP/RTP receiver. Sessions keyed by source socket address."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        auto_accept: Optional[bool] = None,
    ) -> None:
        self.host = host or settings.telephony_local_rtp_host
        self.port = port if port is not None else settings.telephony_local_rtp_port
        self.auto_accept = (
            auto_accept if auto_accept is not None else settings.telephony_auto_accept_local
        )
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._trackers: Dict[str, RtpStreamTracker] = {}
        self.bound_port: Optional[int] = None

    @property
    def running(self) -> bool:
        return self._transport is not None

    async def start(self) -> None:
        if self._transport is not None:
            return
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _RtpProtocol(self),
            local_addr=(self.host, self.port),
        )
        self._transport = transport
        sock = transport.get_extra_info("socket")
        self.bound_port = sock.getsockname()[1] if sock else self.port
        logger.info("Local RTP ingress listening on %s:%s", self.host, self.bound_port)

    async def stop(self) -> None:
        transport, self._transport = self._transport, None
        if transport is not None:
            transport.close()
        self._trackers.clear()
        self.bound_port = None

    def _key(self, addr: Tuple[str, int]) -> str:
        return f"{addr[0]}:{addr[1]}"

    async def handle_datagram(self, data: bytes, addr: Tuple[str, int]) -> None:
        """Ingest one genuine UDP datagram as RTP."""
        from gateway import live_gateway as lg

        key = self._key(addr)
        session_id = _addr_session_for_key(key)

        if session_id is None:
            # A real packet from an unknown source: an actual inbound call.
            try:
                parse_rtp(data)
            except RtpError:
                logger.debug("Dropped non-RTP datagram from %s", key)
                return
            # Prefer claiming an operator-provisioned leg awaiting media.
            pending = ts.find_pending_local()
            if pending is not None:
                _bind_addr_key(key, pending.session_id)
                session_id = pending.session_id
                ts.note_media_activity(session_id)
            else:
                session = await ts.create_session(
                    provider_call_id=f"local-rtp-{key}",
                    transport=TRANSPORT_LOCAL_RTP,
                    caller_raw=None,
                    called_raw=None,
                )
                _bind_addr_key(key, session.session_id)
                session_id = session.session_id
                ts.note_media_activity(session_id)
                if self.auto_accept:
                    await ts.accept_session(session_id)
                else:
                    logger.info("Local RTP call awaiting accept id=%s from=%s", session_id, key)
                    return

        try:
            session = ts.get_session(session_id)
        except ts.TelephonyNotFoundError:
            return
        if session.state in (TelephonyState.ENDED, TelephonyState.FAILED):
            return

        try:
            pkt = parse_rtp(data)
        except RtpError as e:
            session.packets_dropped += 1
            logger.debug("Dropped malformed RTP from %s: %s", key, e)
            return

        tracker = self._trackers.get(key)
        if tracker is None:
            tracker = RtpStreamTracker()
            self._trackers[key] = tracker
        outcome = tracker.observe(pkt)
        session.packets_lost = tracker.packets_lost
        session.discontinuities = tracker.discontinuities
        session.jitter_max_ms = round(tracker.jitter_max_ms, 2)
        if outcome == "duplicate":
            session.packets_dropped += 1
            return

        try:
            pcm, codec = normalize_telephony_payload(pkt.payload_type, pkt.payload)
        except UnsupportedCodecError as e:
            await ts.fail_session(session.session_id, str(e), "unsupported_codec")
            try:
                await lg.end_live_session(session.live_session_id)
            except Exception:
                pass
            return
        except RtpError as e:
            session.packets_dropped += 1
            logger.debug("Dropped undecodable RTP from %s: %s", key, e)
            return

        if session.codec is None:
            session.codec = codec
        session.packets_received += 1
        session.bytes_received += len(data)
        session.audio_samples_16k += int(pcm.size)
        ts.note_media_activity(session.session_id)

        live = lg._sessions.get(session.live_session_id)
        if live is None:
            return
        if session.state in (TelephonyState.CONNECTING_MEDIA, TelephonyState.ACCEPTED):
            session.state = TelephonyState.RECEIVING_AUDIO
            session.first_audio_at = time.time()
            await lg._emit(
                live,
                "telephony.audio.receiving",
                {"codec": codec, "transport": TRANSPORT_LOCAL_RTP},
            )
        await lg.ingest_pcm16(live, pcm, source=TRANSPORT_LOCAL_RTP)


# Source-address → telephony session binding (module-level so the protocol
# callback, which is synchronous, can resolve without awaiting a lock; the
# dict is only mutated on the event loop thread).
_addr_bindings: Dict[str, str] = {}


def _addr_session_for_key(key: str) -> Optional[str]:
    sid = _addr_bindings.get(key)
    if sid is None:
        return None
    try:
        ts.get_session(sid)
    except ts.TelephonyNotFoundError:
        _addr_bindings.pop(key, None)
        return None
    return sid


def _bind_addr_key(key: str, session_id: str) -> None:
    _addr_bindings[key] = session_id


_ingress: Optional[LocalRtpIngress] = None


async def get_local_ingress() -> LocalRtpIngress:
    """Process-wide local RTP ingress (started lazily, exactly once)."""
    global _ingress
    if _ingress is None:
        _ingress = LocalRtpIngress()
    if not _ingress.running and settings.telephony_local_rtp_enabled:
        await _ingress.start()
    return _ingress
