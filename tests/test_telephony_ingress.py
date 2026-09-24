"""Tests for the provider-neutral telephony ingress (telephony/ + gateway/telephony_api.py).

Covers: session creation + API-key auth, webhook signature validation and
rejection paths, isolation, state transitions, G.711/RTP normalization,
loss/jitter accounting, termination, wiring into the existing live-session
ingest, cleanup, audit honesty, privacy/PII invariants, and status surface.

Real deterministic fixtures throughout: genuine UDP/RTP datagrams on
loopback, real HMAC-SHA1 webhook signatures, real G.711 vectors. Test-only
µ-law ENCODING below is a fixture for producing inbound bytes; production
code never synthesizes audio. No fake AI scores anywhere — pipeline
integration reuses the project's existing test vectors/infrastructure.
"""

import base64
import hashlib
import hmac
import json
import socket
import struct
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from configs.settings import settings  # noqa: E402
from gateway.app import app  # noqa: E402
from schemas.hash_utils import compute_pseudonymous_subject_ref  # noqa: E402
from telephony import sessions as ts  # noqa: E402
from telephony.audio import (  # noqa: E402
    RtpError,
    RtpStreamTracker,
    UnsupportedCodecError,
    alaw_to_pcm16,
    mulaw_to_pcm16,
    normalize_telephony_payload,
    parse_rtp,
    resample_to_16k,
)
from telephony.ingress import LocalRtpIngress, _addr_bindings  # noqa: E402
from telephony.models import TelephonyState, mask_caller_number  # noqa: E402

client = TestClient(app)
API_KEY = settings.api_key
AUTH = {"X-API-Key": API_KEY}


# ── Test-only fixtures (inbound byte producers, never production data) ──


def _ulaw_encode_sample(s: int) -> int:
    s = max(-32635, min(32635, int(s)))
    sign = 0x80 if s < 0 else 0
    if sign:
        s = -s
    s += 0x84
    exp = 7
    mask = 0x4000
    while exp > 0 and not (s & mask):
        exp -= 1
        mask >>= 1
    mantissa = (s >> (exp + 3)) & 0x0F
    return (~(sign | (exp << 4) | mantissa)) & 0xFF


def _ulaw_tone(freq: float, seconds: float, sr: int = 8000, amp: float = 8000.0) -> bytes:
    t = np.arange(int(seconds * sr)) / sr
    pcm = (amp * np.sin(2 * np.pi * freq * t)).astype(np.int32)
    return bytes(_ulaw_encode_sample(int(v)) for v in pcm)


def _rtp(seq: int, timestamp: int, ssrc: int, pt: int = 0, payload: bytes = b"\x7f") -> bytes:
    return struct.pack(">BBHII", 0x80, pt & 0x7F, seq & 0xFFFF, timestamp & 0xFFFFFFFF, ssrc) + payload


@pytest.fixture(autouse=True)
def _reset_telephony_state():
    yield
    _addr_bindings.clear()
    ts._store.clear()
    ts._last_media_at.clear()


def _twilio_sig(url: str, params: dict, secret: str) -> str:
    data = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(secret.encode(), data.encode(), hashlib.sha1).digest()).decode()


def _provider_env(monkeypatch, secret: str = "test-webhook-secret"):
    monkeypatch.setattr(settings, "telephony_provider", "twilio")
    monkeypatch.setattr(settings, "telephony_webhook_secret", secret)
    return secret


# ── 1. Creation + API-key auth ────────────────────────────────────────────


def test_create_call_requires_api_key():
    assert client.post("/api/v1/telephony/calls", json={"transport": "local-rtp"}).status_code == 401
    assert client.post(
        "/api/v1/telephony/calls",
        json={"transport": "local-rtp"},
        headers={"X-API-Key": "wrong"},
    ).status_code == 401
    res = client.post("/api/v1/telephony/calls", json={"transport": "local-rtp"}, headers=AUTH)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["transport"] == "local-rtp"
    assert body["state"] in ("INCOMING", "CONNECTING_MEDIA")
    assert body["rtp"]["port"] >= 10000 or body["rtp"]["port"] > 0
    assert "PCMU/8000" in body["rtp"]["codecs"]


def test_create_rejects_unknown_transport():
    res = client.post(
        "/api/v1/telephony/calls", json={"transport": "pigeon"}, headers=AUTH
    )
    assert res.status_code == 400


def test_get_unknown_call_404():
    assert client.get("/api/v1/telephony/calls/does-not-exist").status_code == 404


# ── 2/3. Webhook signature validation + rejection ─────────────────────────


def test_webhook_unknown_provider_404(monkeypatch):
    _provider_env(monkeypatch)
    res = client.post("/api/v1/telephony/webhooks/acme", data={"CallSid": "x"})
    assert res.status_code == 404


def test_webhook_rejects_missing_and_bad_signature(monkeypatch):
    secret = _provider_env(monkeypatch)
    url = "http://testserver/api/v1/telephony/webhooks/twilio"
    params = {"CallSid": "CA123", "CallStatus": "ringing", "From": "+15550001111"}
    assert client.post(url, data=params).status_code == 401
    assert client.post(
        url, data=params, headers={"X-Twilio-Signature": "bogus"}
    ).status_code == 401
    assert client.post(
        url, data={**params, "CallStatus": "answered"},  # signed different params
        headers={"X-Twilio-Signature": _twilio_sig(url, params, secret)},
    ).status_code == 401


def test_webhook_rejects_wrong_content_type_and_missing_sid(monkeypatch):
    secret = _provider_env(monkeypatch)
    url = "http://testserver/api/v1/telephony/webhooks/twilio"
    res = client.post(
        url, json={"CallSid": "CA1"}, headers={"X-Twilio-Signature": "x"}
    )
    assert res.status_code == 415
    params = {"CallStatus": "ringing"}
    res = client.post(
        url, data=params, headers={"X-Twilio-Signature": _twilio_sig(url, params, secret)}
    )
    assert res.status_code == 400


def test_webhook_full_lifecycle(monkeypatch):
    secret = _provider_env(monkeypatch)
    url = "http://testserver/api/v1/telephony/webhooks/twilio"

    def post(params):
        return client.post(
            url, data=params, headers={"X-Twilio-Signature": _twilio_sig(url, params, secret)}
        )

    assert post({"CallSid": "CA999", "CallStatus": "ringing", "From": "+919876543210"}).json()["action"] == "received"
    assert post({"CallSid": "CA999", "CallStatus": "in-progress"}).json()["action"] == "accepted"
    calls = client.get("/api/v1/telephony/calls").json()["calls"]
    call = next(c for c in calls if c["telephony_call_id"] == "CA999")
    assert call["state"] == "CONNECTING_MEDIA"
    assert "9876543210" not in json.dumps(call)  # raw number never exposed
    assert call["caller_display"] == "+91******3210"
    assert post({"CallSid": "CA999", "CallStatus": "completed"}).json()["action"] == "ended"
    assert client.get(f"/api/v1/telephony/calls/{call['session_id']}").json()["state"] == "ENDED"


# ── 4. Isolation + idempotent end ─────────────────────────────────────────


def test_session_isolation_and_idempotent_end():
    a = client.post("/api/v1/telephony/calls", json={"transport": "local-rtp"}, headers=AUTH).json()
    b = client.post("/api/v1/telephony/calls", json={"transport": "local-rtp"}, headers=AUTH).json()
    assert a["session_id"] != b["session_id"]
    assert a["live_session_id"] != b["live_session_id"]
    assert client.post(f"/api/v1/telephony/calls/{a['session_id']}/end", headers=AUTH).json()["state"] == "ENDED"
    assert client.post(f"/api/v1/telephony/calls/{a['session_id']}/end", headers=AUTH).status_code == 200
    still = client.get(f"/api/v1/telephony/calls/{b['session_id']}").json()
    assert still["state"] != "ENDED"
    assert client.post("/api/v1/telephony/calls/nope/end", headers=AUTH).status_code == 404


# ── 5/6/7. Audio normalization vectors ────────────────────────────────────


def test_g711_symmetry_and_silence():
    for byte in (0x00, 0x2A, 0x7F, 0x80, 0xD5, 0xFF):
        assert int(mulaw_to_pcm16(bytes([byte]))[0]) == -int(mulaw_to_pcm16(bytes([byte ^ 0x80]))[0])
        assert int(alaw_to_pcm16(bytes([byte]))[0]) == -int(alaw_to_pcm16(bytes([byte ^ 0x80]))[0])
    assert int(mulaw_to_pcm16(b"\xff")[0]) == 0  # µ-law silence decodes to zero


def test_g711_roundtrip_within_quantization_step():
    sweep = np.array([-30000, -8000, -1000, -100, -10, 10, 100, 1000, 8000, 30000], dtype=np.int32)
    enc = bytes(_ulaw_encode_sample(int(v)) for v in sweep)
    dec = mulaw_to_pcm16(enc).astype(np.int32)
    assert np.max(np.abs(dec - sweep)) < 700  # G.711 step bound, never exact


def test_telephony_payload_to_canonical_16k():
    tone8k = _ulaw_tone(440.0, 0.5)
    pcm, codec = normalize_telephony_payload(0, tone8k)
    assert codec == "PCMU"
    assert pcm.dtype == np.int16 and pcm.ndim == 1
    assert len(pcm) == 8000  # 0.5 s @8k -> 0.5 s @16k
    spectrum = np.abs(np.fft.rfft(pcm.astype(np.float64)))
    peak = int(np.argmax(spectrum[1:]) + 1) * 16000 / len(pcm)
    assert abs(peak - 440.0) < 20.0  # tone survived companding + resampling
    pcm_a, codec_a = normalize_telephony_payload(8, bytes(b"\xd5" * 160))
    assert codec_a == "PCMA" and len(pcm_a) == 320
    with pytest.raises(UnsupportedCodecError):
        normalize_telephony_payload(13, b"\x00" * 160)
    with pytest.raises(RtpError):
        normalize_telephony_payload(0, b"")


def test_resample_passthrough_and_invalid():
    x = np.arange(160, dtype=np.int16)
    assert resample_to_16k(x, 16000).tolist() == x.tolist()
    with pytest.raises(RtpError):
        resample_to_16k(np.zeros(0, dtype=np.int16), 8000)


# ── 8. RTP parsing, loss, jitter, discontinuity ───────────────────────────


def test_rtp_parse_and_extension():
    pkt = parse_rtp(_rtp(100, 8000, 0xABCDEF01, pt=0, payload=b"\xff" * 160))
    assert (pkt.sequence, pkt.timestamp, pkt.ssrc, pkt.payload_type) == (100, 8000, 0xABCDEF01, 0)
    ext = struct.pack(">BBHII", 0x90, 0x00, 7, 1, 2) + struct.pack(">HH", 1, 1) + b"\x00" * 4 + b"\x01" * 10
    assert parse_rtp(ext).payload == b"\x01" * 10
    with pytest.raises(RtpError):
        parse_rtp(b"\x80\x00\x00")
    with pytest.raises(RtpError):
        parse_rtp(struct.pack(">BBHII", 0x40, 0, 1, 1, 1) + b"\x00" * 10)
    with pytest.raises(RtpError):
        parse_rtp(struct.pack(">BBHII", 0x80, 0, 1, 1, 1))  # header only, no media


def test_tracker_loss_duplicate_discontinuity():
    tr = RtpStreamTracker()
    assert tr.observe(parse_rtp(_rtp(10, 0, 1, payload=b"\x01"))) == "ok"
    assert tr.observe(parse_rtp(_rtp(13, 480, 1, payload=b"\x01"))) == "ok"
    assert tr.packets_lost == 2
    assert tr.observe(parse_rtp(_rtp(13, 480, 1, payload=b"\x01"))) == "duplicate"
    before = tr.packets_received
    tr.observe(parse_rtp(_rtp(5000, 999999, 1, payload=b"\x01")))
    assert tr.discontinuities == 1 and tr.packets_received == before + 1
    tr.observe(parse_rtp(_rtp(14, 800, 0xDEAD, payload=b"\x01")))
    assert tr.ssrc_changes == 1


def test_mask_caller_number():
    assert mask_caller_number("+919876543210") == "+91******3210"
    assert mask_caller_number(None) == "unknown"
    assert mask_caller_number("123") == "unknown"


# ── 9/10/11. Ingress → live session wiring, termination, cleanup ──────────


async def test_ingress_feeds_backing_live_session():
    from gateway import live_gateway as lg

    ingress = LocalRtpIngress(auto_accept=True)
    addr = ("127.0.0.9", 40001)
    tone = _ulaw_tone(440.0, 0.02)
    for i in range(10):
        await ingress.handle_datagram(_rtp(i, i * 160, 0x1111, payload=tone), addr)
    sid = _addr_bindings[ingress._key(addr)]
    session = ts.get_session(sid)
    assert session.state == TelephonyState.RECEIVING_AUDIO
    assert session.packets_received == 10
    assert session.audio_seconds == pytest.approx(0.2, abs=0.05)
    live = lg._sessions[session.live_session_id]
    assert live.audio_seconds == pytest.approx(0.2, abs=0.05)
    assert live.state == lg.LiveState.RECEIVING_AUDIO
    assert len(live.windows) == 0  # buffered, no window yet — pipeline untouched
    await ts.end_session(sid, reason="local_hangup")
    assert ts.get_session(sid).state == TelephonyState.ENDED
    assert lg._sessions[session.live_session_id].state == lg.LiveState.ENDED


async def test_malformed_datagrams_dropped_without_session():
    ingress = LocalRtpIngress(auto_accept=True)
    before = len(ts.list_sessions())
    await ingress.handle_datagram(b"not-rtp-at-all", ("127.0.0.8", 40002))
    assert len(ts.list_sessions()) == before
    addr = ("127.0.0.8", 40003)
    await ingress.handle_datagram(_rtp(0, 0, 0x2222, payload=_ulaw_tone(440.0, 0.02)), addr)
    sid = _addr_bindings[ingress._key(addr)]
    await ingress.handle_datagram(b"\x80", addr)  # truncated garbage on live call
    assert ts.get_session(sid).packets_dropped >= 1
    assert ts.get_session(sid).state == TelephonyState.RECEIVING_AUDIO


async def test_unsupported_codec_fails_call_explicitly():
    from gateway import live_gateway as lg

    ingress = LocalRtpIngress(auto_accept=True)
    addr = ("127.0.0.7", 40004)
    await ingress.handle_datagram(_rtp(0, 0, 0x3333, pt=13, payload=b"\x00" * 100), addr)
    sid = _addr_bindings[ingress._key(addr)]
    session = ts.get_session(sid)
    assert session.state == TelephonyState.FAILED
    assert session.termination_reason == "unsupported_codec"
    assert lg._sessions[session.live_session_id].state in ("ENDED", "FAILED")


async def test_stale_incoming_sweep_fails_honestly(monkeypatch):
    monkeypatch.setattr(settings, "telephony_auto_accept_local", False)
    session = await ts.create_session(
        provider_call_id="sweep-test", transport="local-rtp", caller_raw="+15550009999"
    )
    session.created_at = time.time() - 200.0
    await ts.sweep_stale()
    assert ts.get_session(session.session_id).state == TelephonyState.FAILED


async def test_end_finalize_insufficient_audio_honest():
    from gateway import live_gateway as lg

    ingress = LocalRtpIngress(auto_accept=True)
    addr = ("127.0.0.6", 40005)
    tone = _ulaw_tone(440.0, 0.02)
    for i in range(10):  # 0.2 s total — below the 2 s final minimum
        await ingress.handle_datagram(_rtp(i, i * 160, 0x4444, payload=tone), addr)
    sid = _addr_bindings[ingress._key(addr)]
    await ts.end_session(sid, reason="remote_bye")
    live_id = ts.get_session(sid).live_session_id
    deadline = time.monotonic() + 60.0
    while True:
        snap = client.get(f"/api/v1/live/sessions/{live_id}").json()
        if snap["final_status"] in ("complete", "failed"):
            break
        assert time.monotonic() < deadline, "finalize never finished"
        await __import__("asyncio").sleep(0.5)
    assert snap["final_status"] == "failed"
    assert "Insufficient live audio" in snap["final_error"]
    assert snap["result_session_id"] is None


# ── 12/13. Privacy invariants + status surface ────────────────────────────


def test_privacy_no_raw_pii_in_snapshots():
    raw = "+919876543210"
    res = client.post(
        "/api/v1/telephony/calls",
        json={"transport": "local-rtp", "caller_number": raw, "called_number": "+911800123456"},
        headers=AUTH,
    )
    body = res.json()
    assert "9876543210" not in json.dumps(body)
    assert "1800123456" not in json.dumps(body)
    assert body["caller_display"] == "+91******3210"
    assert body["caller_ref"] == compute_pseudonymous_subject_ref(raw, settings.vfd_hmac_secret)


def test_status_exposes_no_secrets(monkeypatch):
    _provider_env(monkeypatch, secret="super-secret-value")
    body = client.get("/api/v1/telephony/status").json()
    assert "super-secret-value" not in json.dumps(body)
    assert body["provider"] == "twilio"
    assert body["provider_configured"] is True


# ── Real UDP end-to-end against a live uvicorn server ───────────────────────
# NOTE: the FastAPI TestClient portal loop does not pump UDP readers in this
# environment (verified with a bare datagram endpoint — a harness limit, the
# same reason the pre-existing WebRTC loopback test cannot pass here). The
# ingress itself receives fine on a real loop, so this test boots a genuine
# uvicorn gateway and exchanges real RTP datagrams with it over loopback.


def test_local_rtp_real_udp_end_to_end():
    import os
    import subprocess

    import httpx

    root = Path(__file__).resolve().parent.parent
    port_http, port_rtp = 18001, 0  # ephemeral RTP port: never collides, read back from API
    env = dict(os.environ)
    env["VFD_TELEPHONY_LOCAL_RTP_PORT"] = str(port_rtp)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "gateway.app:app",
         "--host", "127.0.0.1", "--port", str(port_http)],
        cwd=str(root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port_http}"
        deadline = time.monotonic() + 90.0
        with httpx.Client(timeout=5.0) as http:
            while True:
                try:
                    if http.get(f"{base}/health").status_code == 200:
                        break
                except Exception:
                    pass
                assert time.monotonic() < deadline, "gateway did not boot"
                time.sleep(1.0)
            headers = {"X-API-Key": API_KEY}
            created = http.post(f"{base}/api/v1/telephony/calls", json={"transport": "local-rtp"}, headers=headers).json()
            sid = created["session_id"]
            rtp_port = created["rtp"]["port"]
            assert rtp_port > 0
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                tone = _ulaw_tone(440.0, 0.02)
                for i in range(30):
                    sock.sendto(_rtp(i, i * 160, 0x5555, payload=tone), ("127.0.0.1", rtp_port))
                    time.sleep(0.005)
                snap: dict = {}
                deadline = time.monotonic() + 20.0
                while True:
                    snap = http.get(f"{base}/api/v1/telephony/calls/{sid}").json()
                    if snap["state"] == "RECEIVING_AUDIO" and snap["audio_seconds"] >= 0.4:
                        break
                    assert time.monotonic() < deadline, f"RTP audio never landed: {snap}"
                    time.sleep(0.5)
                assert snap["stats"]["packets_received"] >= 25
                assert snap["stats"]["codec"] == "PCMU"
                assert snap["live_session_id"] == created["live_session_id"]
            finally:
                sock.close()
            ended = http.post(f"{base}/api/v1/telephony/calls/{sid}/end", headers=headers).json()
            assert ended["state"] == "ENDED"
            assert ended["termination_reason"] == "local_hangup"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except Exception:
            proc.kill()


# ── Provider media-stream WebSocket (Twilio protocol, real frames) ─────────


def test_provider_media_websocket_flow(monkeypatch):
    _provider_env(monkeypatch)
    created = client.post(
        "/api/v1/telephony/calls",
        json={"transport": "provider-media-stream", "provider_call_id": "CAWS1", "caller_number": "+15550002222"},
        headers=AUTH,
    ).json()
    sid = created["session_id"]
    client.post(f"/api/v1/telephony/calls/{sid}/accept", headers=AUTH)
    tone_b64 = base64.b64encode(_ulaw_tone(440.0, 0.02)).decode()
    with client.websocket_connect(f"/api/v1/telephony/calls/{sid}/media") as ws:
        ws.send_json({"event": "connected", "protocol": "Call", "version": "1.0.0"})
        ws.send_json({"event": "start", "streamSid": "MZ1", "start": {"callSid": "CAWS1"}})
        for _ in range(15):
            ws.send_json({"event": "media", "media": {"track": "inbound", "payload": tone_b64}})
        ws.send_json({"event": "stop"})
        time.sleep(1.0)
    snap = client.get(f"/api/v1/telephony/calls/{sid}").json()
    assert snap["state"] == "ENDED"
    assert snap["audio_seconds"] >= 0.2
    assert snap["stats"]["codec"] == "PCMU"
    assert "5550002222" not in json.dumps(snap)


def test_provider_media_websocket_unknown_call():
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/telephony/calls/nope/media"):
            pass
