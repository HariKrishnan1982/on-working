"""Tests for the real-time voice gateway (gateway/live_gateway.py).

Covers: session creation/state, invalid sessions, malformed signaling,
session cleanup + isolation, the WebRTC→PCM adapter, window slicing, WS
events, and one honest end-to-end window through the REAL (unmodified)
PipelineService. Synthetic audio below is a test-only transport/pipeline
fixture — production code paths never synthesize audio.
"""

import asyncio
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from av.audio.frame import AudioFrame  # noqa: E402

from gateway.app import app  # noqa: E402
from gateway.live_gateway import (  # noqa: E402
    TARGET_SAMPLE_RATE,
    LiveState,
    _sessions,
    webrtc_frame_to_pcm16,
)
from schemas.models import RiskLevel  # noqa: E402

client = TestClient(app)


def _create(caller_id: str = "+911234567890") -> dict:
    res = client.post(
        "/api/v1/live/sessions",
        json={"caller_id": caller_id, "claimed_identity": None, "language_hint": "EN"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _sine_pcm16(freq: float, seconds: float, sr: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    # Harmonic stack + slow amplitude modulation: voiced-ish, never silent.
    wave = (
        0.5 * np.sin(2 * np.pi * freq * t)
        + 0.25 * np.sin(2 * np.pi * 2 * freq * t)
        + 0.12 * np.sin(2 * np.pi * 3 * freq * t)
    ) * (0.6 + 0.4 * np.sin(2 * np.pi * 3.0 * t))
    return (np.clip(wave, -1, 1) * 32767).astype(np.int16)


from aiortc import AudioStreamTrack  # noqa: E402


class SineTrack(AudioStreamTrack):
    """48 kHz mono sine audio track (test-only audio source)."""

    kind = "audio"

    def __init__(self, freq: float = 440.0):
        super().__init__()
        self.freq = freq
        self.t = 0

    async def recv(self) -> AudioFrame:
        await asyncio.sleep(0.02)
        n = int(48000 * 0.02)
        tt = (np.arange(n) + self.t) / 48000.0
        self.t += n
        data = (0.3 * np.sin(2 * np.pi * self.freq * tt) * 32767).astype(np.int16)
        frame = AudioFrame.from_ndarray(data.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = 48000
        frame.pts = self.t
        frame.time_base = Fraction(1, 48000)
        return frame


# ── Session lifecycle ───────────────────────────────────────────────────────


def test_create_live_session():
    body = _create()
    assert body["state"] == LiveState.CREATED.value
    assert len(body["session_id"]) == 32
    assert body["audio_seconds_received"] == 0
    assert body["windows_processed"] == 0
    assert body["final_status"] == "none"


def test_get_live_session_invalid():
    res = client.get("/api/v1/live/sessions/does-not-exist")
    assert res.status_code == 404


def test_offer_invalid_session():
    res = client.post(
        "/api/v1/live/sessions/does-not-exist/offer",
        json={"sdp": "v=0", "type": "offer"},
    )
    assert res.status_code == 404


def test_offer_wrong_type_rejected():
    sid = _create()["session_id"]
    res = client.post(
        f"/api/v1/live/sessions/{sid}/offer",
        json={"sdp": "v=0\r\n", "type": "answer"},
    )
    assert res.status_code == 400


def test_offer_malformed_sdp_rejected():
    sid = _create()["session_id"]
    res = client.post(
        f"/api/v1/live/sessions/{sid}/offer",
        json={"sdp": "this is not SDP", "type": "offer"},
    )
    assert res.status_code == 400
    # Failed handshake is honestly reported, not left hanging.
    assert client.get(f"/api/v1/live/sessions/{sid}").json()["state"] == LiveState.FAILED.value


def test_end_invalid_session():
    res = client.post("/api/v1/live/sessions/does-not-exist/end")
    assert res.status_code == 404


def test_end_is_idempotent_and_cleans_up():
    sid = _create()["session_id"]
    first = client.post(f"/api/v1/live/sessions/{sid}/end")
    assert first.status_code == 200
    assert first.json()["state"] == LiveState.ENDED.value
    second = client.post(f"/api/v1/live/sessions/{sid}/end")
    assert second.status_code == 200
    assert second.json()["state"] == LiveState.ENDED.value
    # Backend released the peer connection.
    assert _sessions[sid].pc is None


def test_session_isolation():
    a = _create("+911111111111")["session_id"]
    b = _create("+912222222222")["session_id"]
    assert a != b
    client.post(f"/api/v1/live/sessions/{a}/end")
    assert client.get(f"/api/v1/live/sessions/{a}").json()["state"] == "ENDED"
    assert client.get(f"/api/v1/live/sessions/{b}").json()["state"] == "CREATED"


# ── Audio adapter ───────────────────────────────────────────────────────────


def test_adapter_stereo_48k_to_mono_16k():
    ch = _sine_pcm16(440.0, 1.0, 48000)
    interleaved = np.stack([ch, ch]).T.reshape(1, -1)  # packed s16 stereo row
    frame = AudioFrame.from_ndarray(interleaved, format="s16", layout="stereo")
    frame.sample_rate = 48000
    pcm = webrtc_frame_to_pcm16(frame)
    assert pcm.dtype == np.int16
    assert pcm.ndim == 1
    assert len(pcm) == TARGET_SAMPLE_RATE  # 48000 -> 16000, exactly 1 s
    spectrum = np.abs(np.fft.rfft(pcm.astype(np.float64)))
    peak = int(np.argmax(spectrum[1:]) + 1) * TARGET_SAMPLE_RATE / len(pcm)
    assert abs(peak - 440.0) < 15.0  # tone survived resampling


def test_adapter_mono_passthrough_and_empty_rejected():
    mono = _sine_pcm16(300.0, 0.5)
    frame = AudioFrame.from_ndarray(mono.reshape(1, -1), format="s16", layout="mono")
    frame.sample_rate = 16000
    pcm = webrtc_frame_to_pcm16(frame)
    assert len(pcm) == len(mono)
    assert np.max(np.abs(pcm.astype(np.int32) - mono.astype(np.int32))) < 2000

    empty = AudioFrame.from_ndarray(np.zeros((1, 0), dtype=np.int16), format="s16", layout="mono")
    empty.sample_rate = 16000
    with pytest.raises(ValueError):
        webrtc_frame_to_pcm16(empty)


# ── WebRTC loopback: real media transport ─────────────────────────────────


@pytest.mark.asyncio
async def test_webrtc_loopback_receives_real_audio(monkeypatch):
    """In-process aiortc loopback: offer → answer → connected → audio lands.

    Test-only fixture: this sandbox has no mutually-routable LAN pair and
    aioice excludes 127.0.0.1 from host candidates, so loopback is patched
    in here (production code untouched) to prove the media path end to end.
    """
    import aioice.ice as _aioice

    _real_enum = _aioice.get_host_addresses

    def _with_loopback(use_ipv4: bool = True, use_ipv6: bool = True):
        addrs = list(_real_enum(use_ipv4, use_ipv6))
        if use_ipv4 and "127.0.0.1" not in addrs:
            addrs.append("127.0.0.1")
        return addrs

    monkeypatch.setattr(_aioice, "get_host_addresses", _with_loopback)

    from aiortc import RTCPeerConnection, RTCSessionDescription

    sid = _create()["session_id"]
    pc = RTCPeerConnection()
    try:
        pc.addTrack(SineTrack())
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        desc = pc.localDescription
        res = await asyncio.to_thread(
            client.post,
            f"/api/v1/live/sessions/{sid}/offer",
            json={"sdp": desc.sdp, "type": desc.type},
        )
        assert res.status_code == 200, res.text
        answer = res.json()
        assert "audio" in answer["sdp"]
        await pc.setRemoteDescription(
            RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
        )

        # Wait for the server to report genuinely received audio.
        deadline = asyncio.get_event_loop().time() + 150.0
        snap: dict = {}
        while True:
            resp = await asyncio.to_thread(client.get, f"/api/v1/live/sessions/{sid}")
            snap = resp.json()
            if snap["audio_seconds_received"] >= 1.0:
                break
            if asyncio.get_event_loop().time() >= deadline:
                raise AssertionError(
                    f"no audio received (client {pc.connectionState}/"
                    f"{pc.iceConnectionState}): {snap}"
                )
            await asyncio.sleep(1.0)
        assert snap["state"] == LiveState.RECEIVING_AUDIO.value
    finally:
        await pc.close()

    # Duplicate signaling on a connected session is rejected, not duplicated.
    pc2 = RTCPeerConnection()
    try:
        pc2.addTrack(SineTrack())
        offer2 = await pc2.createOffer()
        await pc2.setLocalDescription(offer2)
        desc2 = pc2.localDescription
        res2 = await asyncio.to_thread(
            client.post,
            f"/api/v1/live/sessions/{sid}/offer",
            json={"sdp": desc2.sdp, "type": desc2.type},
        )
        assert res2.status_code == 409
    finally:
        await pc2.close()

    end = await asyncio.to_thread(client.post, f"/api/v1/live/sessions/{sid}/end")
    assert end.status_code == 200
    assert end.json()["state"] == LiveState.ENDED.value


# ── Windows through the real pipeline ───────────────────────────────────────


@pytest.mark.asyncio
async def test_window_processed_by_real_pipeline():
    """8 s of test audio → one window → REAL PipelineService decision (unmodified).

    The window task runs on the test loop (no consumer/WS touches this
    session concurrently); completion is observed via authoritative REST.
    """
    from gateway.live_gateway import _maybe_process_window as _m

    sid = _create()["session_id"]
    session = _sessions[sid]
    pcm = _sine_pcm16(220.0, 8.0)
    async with session.buffer_lock:
        session.buffer.extend(pcm.tobytes())
    await _m(session)
    assert session.window_task is not None

    deadline = asyncio.get_event_loop().time() + 600.0
    snap: dict = {}
    while True:
        resp = await asyncio.to_thread(client.get, f"/api/v1/live/sessions/{sid}")
        snap = resp.json()
        if snap["windows_processed"] >= 1:
            break
        assert asyncio.get_event_loop().time() < deadline, "window never processed"
        await asyncio.sleep(2.0)

    w = snap["windows"][0]
    assert w["audio_s"] == pytest.approx(8.0, abs=0.1)
    assert w["risk_level"] in {r.value for r in RiskLevel}
    assert w["latency_ms"] > 0  # measured, never hardcoded
    # Temp window file removed after processing (no raw audio persisted).
    assert not (Path("storage") / "live_windows" / sid / "window_000.wav").exists()


def test_finalize_rejects_insufficient_audio_honestly():
    import time as _t

    sid = _create()["session_id"]
    _sessions[sid].buffer.extend(_sine_pcm16(220.0, 1.0).tobytes())  # < 2 s final minimum
    client.post(f"/api/v1/live/sessions/{sid}/end")
    # Finalize runs server-side: poll authoritative state.
    deadline = _t.monotonic() + 300.0
    snap: dict = {}
    while True:
        snap = client.get(f"/api/v1/live/sessions/{sid}").json()
        if snap["final_status"] in ("complete", "failed"):
            break
        assert _t.monotonic() < deadline, "finalize never finished"
        _t.sleep(1.0)
    assert snap["final_status"] == "failed"
    assert "Insufficient live audio" in snap["final_error"]
    assert snap["result_session_id"] is None


# ── WebSocket events ────────────────────────────────────────────────────────


def test_ws_events_snapshot_then_ended():
    sid = _create()["session_id"]
    with client.websocket_connect(f"/api/v1/live/sessions/{sid}/events") as ws:
        first = ws.receive_json()
        assert first["type"] == "session.state"
        assert first["session_id"] == sid
        client.post(f"/api/v1/live/sessions/{sid}/end")
        kinds = {first["type"]}
        for _ in range(10):
            msg = ws.receive_json()
            kinds.add(msg["type"])
            if msg["type"] == "session.ended":
                break
        assert "session.ended" in kinds


def test_ws_unknown_session_rejected():
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/live/sessions/nope/events") as ws:
            ws.receive_json()
