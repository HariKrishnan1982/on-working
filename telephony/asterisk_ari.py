"""
Asterisk ARI controller — passive tap for PBX calls (transport layer only).

Recipe (documented in docs/telephony-architecture.md, dialplan [internal]):

    StasisStart(caller channel in Stasis(voiceshield))
        → create VoiceShield telephony session (transport "asterisk-ari")
        → snoop the caller (spy: both, whisper: none)
        → externalMedia channel with RTP pointed at the EXISTING local RTP
          ingress (zero new audio code — PCMU/PCMA flow through the same
          adapter → ingest_pcm16 → windows → pipeline path)
        → bridge snoop + externalMedia (mixed call audio reaches VoiceShield)
        → continue the caller back to Dial (the real call is preserved)
    ChannelDestroyed / StasisEnd(caller)
        → end the VoiceShield session (remote_bye)

Detect-only posture: this controller NEVER hangs up, redirects, or moves
any channel except returning the caller to its own dialplan via `continue`.
Call termination by VoiceShield requires a future ARI-control phase and is
explicitly out of scope.

Security: ARI basic-auth credentials come from env only, are never logged,
and never leave this module except inside the Authorization header. The
controller only talks to the operator-configured ARI URL.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from configs.settings import settings
from telephony import sessions as ts
from telephony.models import TRANSPORT_ASTERISK_ARI, TelephonyState

logger = logging.getLogger(__name__)

ARI_APP_FALLBACK = "voiceshield"


def _redacted(value: Optional[str]) -> str:
    return "***" if value else "(unset)"


@dataclass
class AriTap:
    """Bookkeeping for one tapped caller channel (channel IDs only, no audio)."""

    caller_channel_id: str
    session_id: str
    snoop_channel_id: Optional[str] = None
    external_channel_id: Optional[str] = None
    bridge_id: Optional[str] = None


class AriController:
    """Operator-driven ARI client. Never starts on import; see connect()."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        app: Optional[str] = None,
        timeout_s: Optional[float] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = (base_url or settings.asterisk_ari_url).rstrip("/")
        self.user = user if user is not None else settings.asterisk_ari_user
        self.password = password if password is not None else settings.asterisk_ari_password
        self.app = app or settings.asterisk_ari_app or ARI_APP_FALLBACK
        self.timeout_s = timeout_s if timeout_s is not None else settings.asterisk_ari_timeout_s
        self._client = client
        self._own_client = client is None
        self.state: str = "disconnected"
        self.last_error: Optional[str] = None
        self.last_error_at: Optional[float] = None
        self.connected_at: Optional[float] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._taps: Dict[str, AriTap] = {}
        # Every snoop/external channel ID ever created by this controller.
        # Echo StasisStart events for these must NEVER open sessions — the set
        # is append-only (cleanup removes PBX objects, not the memory of them).
        self._aux_channel_ids: set[str] = set()

    # ── lifecycle ─────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        return {
            "configured": bool(self.password),
            "state": self.state,
            "app": self.app,
            "url": self.base_url,
            "connected_at": self.connected_at,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "active_taps": len(self._taps),
        }

    def _client_or_raise(self) -> httpx.AsyncClient:
        if not self.password:
            raise RuntimeError("ARI not configured: set VFD_ASTERISK_ARI_PASSWORD")
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                auth=(self.user, self.password),
                timeout=self.timeout_s,
            )
        return self._client

    def _ws_url(self) -> str:
        base = self.base_url
        if base.startswith("https://"):
            base = "wss://" + base[len("https://"):]
        elif base.startswith("http://"):
            base = "ws://" + base[len("http://"):]
        else:  # pragma: no cover - defensive
            base = "ws://" + base
        return f"{base}/events?app={self.app}&subscribeAll=true"

    async def connect(self) -> Dict[str, Any]:
        """Verify ARI REST, then attach the event stream. Idempotent."""
        if self._listen_task is not None and not self._listen_task.done():
            return self.status()
        self._stop.clear()
        self.state = "connecting"
        try:
            client = self._client_or_raise()
            res = await client.get("/asterisk/info")
            if res.status_code != 200:
                raise RuntimeError(f"ARI info rejected (HTTP {res.status_code})")
            self._listen_task = asyncio.ensure_future(self._listen_loop())
            self.state = "connected"
            self.connected_at = time.time()
            self.last_error = None
            logger.info("ARI connected app=%s url=%s", self.app, self.base_url)
        except Exception as e:
            self.state = "error"
            self.last_error = str(e)
            self.last_error_at = time.time()
            logger.warning("ARI connect failed url=%s: %s", self.base_url, e)
        return self.status()

    async def disconnect(self) -> Dict[str, Any]:
        self._stop.set()
        task, self._listen_task = self._listen_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if self._own_client and self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
        if self.state == "connected":
            self.state = "disconnected"
        self._taps.clear()
        self._aux_channel_ids.clear()
        logger.info("ARI disconnected app=%s", self.app)
        return self.status()

    async def _listen_loop(self) -> None:
        try:
            try:
                from websockets.asyncio.client import connect as _ws_connect
            except ImportError:  # pragma: no cover - older websockets
                from websockets.client import connect as _ws_connect  # type: ignore[no-redef]
            assert self.password is not None
            basic = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
            backoff = 1.0
            while not self._stop.is_set():
                try:
                    async with _ws_connect(
                        self._ws_url(), additional_headers={"Authorization": f"Basic {basic}"}
                    ) as ws:
                        logger.info("ARI event stream attached app=%s", self.app)
                        backoff = 1.0
                        async for raw in ws:
                            if self._stop.is_set():
                                return
                            await self._handle_raw(raw)
                except asyncio.CancelledError:
                    return
                except Exception as e:
                    self.last_error = f"event stream dropped: {e}"
                    self.last_error_at = time.time()
                    logger.warning("ARI %s", self.last_error)
                    await asyncio.sleep(min(backoff, 30.0))
                    backoff *= 2.0
        except asyncio.CancelledError:
            pass
        finally:
            if self.state == "connected":
                self.state = "error" if self.last_error else "disconnected"

    # ── REST helpers ──────────────────────────────────────────────────────

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        client = self._client_or_raise()
        res = await client.post(path, json=payload)
        if res.status_code >= 300:
            raise RuntimeError(f"ARI POST {path} -> HTTP {res.status_code}: {res.text[:200]}")
        try:
            return res.json()
        except Exception:
            return {}

    async def _delete(self, path: str) -> None:
        client = self._client_or_raise()
        res = await client.delete(path)
        if res.status_code >= 300:
            raise RuntimeError(f"ARI DELETE {path} -> HTTP {res.status_code}")

    # ── tap recipe ────────────────────────────────────────────────────────

    async def _rtp_target(self) -> str:
        from telephony.ingress import get_local_ingress

        ingress = await get_local_ingress()
        port = ingress.bound_port or ingress.port
        return f"{ingress.host}:{port}"

    async def tap_call(self, channel_id: str, caller: str, called: str) -> Optional[str]:
        """Attach a passive tap; return the VoiceShield session id (or None)."""
        session = await ts.create_session(
            provider_call_id=f"asterisk-{channel_id}",
            transport=TRANSPORT_ASTERISK_ARI,
            caller_raw=caller or None,
            called_raw=called or None,
        )
        await ts.accept_session(session.session_id)
        tap = AriTap(caller_channel_id=channel_id, session_id=session.session_id)
        self._taps[channel_id] = tap
        try:
            snoop = await self._post(
                f"/channels/{channel_id}/snoop",
                {"spy": "both", "whisper": "none", "app": self.app},
            )
            tap.snoop_channel_id = snoop.get("id")
            if tap.snoop_channel_id:
                self._aux_channel_ids.add(tap.snoop_channel_id)
            target = await self._rtp_target()
            external = await self._post(
                "/channels/externalMedia",
                {
                    "app": self.app,
                    "external_host": target,
                    "encapsulation": "rtp",
                    "transport": "udp",
                    "connectionType": "client",
                    "format": "ulaw",
                },
            )
            tap.external_channel_id = external.get("id")
            if tap.external_channel_id:
                self._aux_channel_ids.add(tap.external_channel_id)
            bridge = await self._post("/bridges", {"type": "mixing"})
            tap.bridge_id = bridge.get("id")
            if tap.snoop_channel_id:
                await self._post(f"/bridges/{tap.bridge_id}/addChannel", {"channel": tap.snoop_channel_id})
            if tap.external_channel_id:
                await self._post(
                    f"/bridges/{tap.bridge_id}/addChannel", {"channel": tap.external_channel_id}
                )
            # Return the caller to its dialplan: the real call proceeds.
            await self._post(f"/channels/{channel_id}/continue", {})
            logger.info(
                "ARI tap attached session=%s channel=%s rtp=%s",
                session.session_id,
                channel_id,
                target,
            )
            return session.session_id
        except Exception as e:
            logger.warning("ARI tap failed channel=%s: %s", channel_id, e)
            await self._cleanup_tap(tap)
            await ts.fail_session(session.session_id, f"ARI tap failed: {e}", "signaling_error")
            return None

    async def untap_call(self, channel_id: str, reason: str = "remote_bye") -> None:
        tap = self._taps.pop(channel_id, None)
        if tap is not None:
            await self._cleanup_tap(tap)
            try:
                await ts.end_session(tap.session_id, reason=reason)
            except ts.TelephonyNotFoundError:
                pass

    async def _cleanup_tap(self, tap: AriTap) -> None:
        # NOTE: tap channel IDs stay in _aux_channel_ids on purpose, so late
        # echo StasisStart events can never open duplicate sessions.
        for cid in (tap.external_channel_id, tap.snoop_channel_id):
            if cid:
                try:
                    await self._delete(f"/channels/{cid}")
                except Exception as e:
                    logger.debug("ARI channel cleanup skipped %s: %s", cid, e)
        if tap.bridge_id:
            try:
                await self._delete(f"/bridges/{tap.bridge_id}")
            except Exception as e:
                logger.debug("ARI bridge cleanup skipped %s: %s", tap.bridge_id, e)

    # ── event handling (never raises on malformed input) ──────────────────

    async def _handle_raw(self, raw: Any) -> None:
        import json as _json

        try:
            msg = _json.loads(raw) if isinstance(raw, (str, bytes)) else dict(raw)
        except Exception:
            logger.debug("ARI ignoring malformed message")
            return
        try:
            await self.handle_event(msg if isinstance(msg, dict) else {})
        except Exception as e:
            logger.warning("ARI event handling failed: %s", e)

    async def handle_event(self, msg: Dict[str, Any]) -> None:
        """Map one ARI event to tap lifecycle. Unknown types are ignored."""
        if not isinstance(msg, dict):
            return
        event_type = msg.get("type", "")
        channel = msg.get("channel") or {}
        channel_id = channel.get("id", "")
        if event_type == "StasisStart":
            if not channel_id or channel_id in self._aux_channel_ids or channel_id in self._taps:
                return  # snoop/external channels and re-entries never open sessions
            args = [str(a).lower() for a in (msg.get("args") or [])]
            if args and "tap" not in args:
                return  # explicit opt-out, e.g. Stasis(voiceshield,notap)
            caller = ((channel.get("caller") or {}).get("number")) or ""
            called = ((channel.get("dialplan") or {}).get("exten")) or ""
            await self.tap_call(channel_id, caller, called)
        elif event_type in ("StasisEnd", "ChannelDestroyed", "ChannelHangupRequest"):
            if channel_id in self._taps:
                await self.untap_call(channel_id, reason="remote_bye")
        # All other ARI traffic (playback, bridge, device state…) is ignored.


_controller: Optional[AriController] = None


def get_ari_controller() -> AriController:
    """Process-wide ARI controller (idle until connect() is called)."""
    global _controller
    if _controller is None:
        _controller = AriController()
    return _controller


def reset_ari_controller() -> None:
    """Test hook: drop the singleton (disconnect first in production paths)."""
    global _controller
    _controller = None
