"""Phase-1 supplemental tests for the real-time voice gateway.

Fast, deterministic, no model inference and no network media:
- request validation
- no-audio SDP rejection (honest signaling failure, no fake session)
- stale-handshake timeout sweep
- audio-adapter edge cases (float path, missing sample rate)
- endpoint surface documents the existing open dashboard auth posture
  (live endpoints match ops_api: reachable without X-API-Key)
- snapshot/event schema shape (backend-authoritative fields)

Test-only synthetic PCM below is a transport/adapter fixture; production
code paths never synthesize audio.
"""

import sys
import time
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

client = TestClient(app)


def _create(caller_id: str = "+911234567890") -> dict:
    res = client.post(
        "/api/v1/live/sessions",
        json={"caller_id": caller_id, "claimed_identity": None, "language_hint": "EN"},
    )
    assert res.status_code == 201, res.text
    return res.json()


# ── Request validation ──────────────────────────────────────────────────


def test_create_requires_caller_id():
    res = client.post("/api/v1/live/sessions", json={})
    assert res.status_code == 422


def test_create_rejects_blank_caller_id():
    res = client.post(
        "/api/v1/live/sessions",
        json={"caller_id": "", "language_hint": "EN"},
    )
    assert res.status_code == 422


def test_snapshot_carries_authoritative_fields():
    body = _create()
    for key in (
        "session_id",
        "state",
        "caller_id",
        "created_at",
        "audio_samples_received",
        "audio_seconds_received",
        "windows_processed",
        "windows",
        "final_status",
        "result_session_id",
        "error",
    ):
        assert key in body, f"missing snapshot field: {key}"
    assert body["state"] == LiveState.CREATED.value


# ── Signaling honesty ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offer_without_audio_section_rejected():
    """DataChannel-only offer parses but can never deliver voice → 400."""
    from aiortc import RTCPeerConnection

    sid = _create()["session_id"]
    pc = RTCPeerConnection()
    try:
        pc.createDataChannel("probe")
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        desc = pc.localDescription
        assert "m=audio" not in desc.sdp.lower()
        res = client.post(
            f"/api/v1/live/sessions/{sid}/offer",
            json={"sdp": desc.sdp, "type": desc.type},
        )
        assert res.status_code == 400
        assert "audio" in res.json()["detail"].lower()
        snap = client.get(f"/api/v1/live/sessions/{sid}").json()
        assert snap["state"] == LiveState.FAILED.value
    finally:
        await pc.close()


# ── Stale-handshake sweep ───────────────────────────────────────────────


def test_handshake_timeout_marks_failed():
    sid = _create()["session_id"]
    session = _sessions[sid]
    session.state = LiveState.CONNECTING
    session.created_at = time.time() - 200.0  # older than CONNECT_TIMEOUT_S
    snap = client.get(f"/api/v1/live/sessions/{sid}").json()
    assert snap["state"] == LiveState.FAILED.value
    assert "timed out" in (snap["error"] or "").lower()


# ── Adapter edges ───────────────────────────────────────────────────────


def test_adapter_float32_48k_to_mono_16k():
    sr = 48000
    t = np.arange(sr, dtype=np.float64) / sr
    mono = (0.4 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    frame = AudioFrame.from_ndarray(mono.reshape(1, -1), format="flt", layout="mono")
    frame.sample_rate = sr
    pcm = webrtc_frame_to_pcm16(frame)
    assert pcm.dtype == np.int16
    assert pcm.ndim == 1
    assert len(pcm) == TARGET_SAMPLE_RATE


def test_adapter_missing_sample_rate_rejected():
    mono = (np.zeros(1600, dtype=np.int16)).reshape(1, -1)
    frame = AudioFrame.from_ndarray(mono, format="s16", layout="mono")
    frame.sample_rate = 0
    with pytest.raises(ValueError):
        webrtc_frame_to_pcm16(frame)


# ── Auth posture (documents existing behavior) ──────────────────────────


def test_live_surface_matches_ops_open_dashboard_posture():
    """Live + ops dashboard endpoints share the same (keyless) posture.

    The gateway's X-API-Key gate applies to /analyze and /jobs only;
    dashboard/ops reads and the live voice gateway are intentionally
    reachable without it (same-origin operator UI). This test pins that
    so a future auth change is deliberate, not accidental.
    """
    res = client.post(
        "/api/v1/live/sessions",
        json={"caller_id": "+910000000001"},
        headers={},
    )
    assert res.status_code == 201
    ops = client.get("/api/v1/sessions", headers={})
    assert ops.status_code == 200
