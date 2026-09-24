"""Tests for Asterisk PBX readiness: configs, ARI controller, audit trail,
detect-only policy, rate limiting, and real-pipeline telephony decisions.

Conventions (same honesty rules as test_telephony_ingress.py):
- ARI network traffic is emulated with httpx.MockTransport + injected event
  dicts — these are TEST FIXTURES for the controller state machine, never
  presented as real calls. No live Asterisk exists in this environment.
- Inbound audio bytes use the same deterministic µ-law/RTP fixtures.
- The full-pipeline test runs the REAL unmodified AI pipeline on real
  (fixture-generated) audio and asserts only that a genuine decision,
  audit event, and ops record result — never specific scores.
"""

import asyncio
import json
import re
import struct
import sys
import time
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from configs.settings import settings  # noqa: E402
from gateway.app import app  # noqa: E402
from gateway.rate_limit import check as rate_check  # noqa: E402
from gateway import rate_limit as rate_limit_mod  # noqa: E402
from telephony import sessions as ts  # noqa: E402
from telephony.asterisk_ari import AriController, get_ari_controller, reset_ari_controller  # noqa: E402
from telephony.ingress import LocalRtpIngress, _addr_bindings  # noqa: E402
from telephony.models import TRANSPORT_ASTERISK_ARI, TelephonyState  # noqa: E402
from telephony.policy import EVENT_TO_AUDIT, resolve_call_action  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AST = ROOT / "asterisk"

client = TestClient(app)
API_KEY = settings.api_key
AUTH = {"X-API-Key": API_KEY}


@pytest.fixture(autouse=True)
def _reset_state():
    rate_limit_mod.reset()
    _addr_bindings.clear()
    ts._store.clear()
    ts._last_media_at.clear()
    reset_ari_controller()
    yield
    rate_limit_mod.reset()
    _addr_bindings.clear()
    ts._store.clear()
    ts._last_media_at.clear()
    reset_ari_controller()


# ── Test-only inbound byte fixtures (never production data) ─────────────


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


# ── 1. Asterisk configuration validation ────────────────────────────────


def _read(name: str) -> str:
    path = AST / name
    assert path.is_file(), f"missing asterisk/{name}"
    return path.read_text(encoding="utf-8")


def _ini_sections(text: str) -> dict:
    """Parse real [section] headers (ignoring ; comments that mention them)."""
    sections: dict = {}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1]
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


def test_pjsip_extensions_present_with_templates():
    conf = _read("pjsip.conf")
    assert "[transport-udp]" in conf
    for ext in ("100", "101"):
        assert re.search(rf"^\[{ext}\]\(endpoint-template\)", conf, re.M)
        assert re.search(rf"^\[{ext}\]\(aor-template\)", conf, re.M)
        assert f"auth = auth{ext}" in conf
        assert f"callerid = Extension {ext} <{ext}>" in conf
    assert "direct_media = no" in conf  # media must hairpin for the tap
    assert "allow = ulaw,alaw" in conf
    assert '#include "pjsip-secrets.conf"' in conf


def test_pjsip_config_has_no_baked_in_secrets():
    for name in ("pjsip.conf", "extensions.conf", "ari.conf", "http.conf", "rtp.conf", "modules.conf"):
        conf = _read(name)
        for line in conf.splitlines():
            stripped = line.strip()
            if stripped.startswith(";") or stripped.startswith("#") or not stripped:
                continue
            assert not re.match(r"(?i)password\s*=\s*\S+", stripped), f"secret baked into asterisk/{name}: {stripped[:40]}"
    assert not (AST / "pjsip-secrets.conf").exists()
    assert not (AST / "ari-secrets.conf").exists()


def test_extensions_routing_and_stasis_tap():
    sections = _ini_sections(_read("extensions.conf"))
    assert "internal-direct" in sections and "internal" in sections
    for ctx in ("internal-direct", "internal"):
        section = sections[ctx]
        assert "exten => 100" in section and "Dial(PJSIP/100,30)" in section
        assert "exten => 101" in section and "Dial(PJSIP/101,30)" in section
    direct = sections["internal-direct"]
    tapped = sections["internal"]
    assert "Stasis" not in direct  # TEST 1 needs no VoiceShield
    assert "Stasis(voiceshield)" in tapped  # TEST 2 tap, call preserved via Dial


def test_ari_http_rtp_modules_config():
    ari = _read("ari.conf")
    assert "enabled = yes" in ari
    assert '#include "ari-secrets.conf"' in ari
    http_conf = _read("http.conf")
    assert "enabled = yes" in http_conf and "8088" in http_conf
    rtp = _read("rtp.conf")
    assert "rtpstart" in rtp and "rtpend" in rtp
    modules = _read("modules.conf")
    assert "noload = chan_sip.so" in modules
    assert "app_stasis.so" in modules


def test_setup_script_present_and_not_executed_here():
    script = ROOT / "scripts" / "setup-asterisk-wsl2.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "openssl rand" in text  # random local secrets, never committed
    assert "NOT executed" in text


# ── 2. ARI controller: auth, tap recipe, lifecycle ──────────────────────


def _mock_ari_client(calls: list, info_status: int = 200):
    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path  # includes the /ari base prefix
        calls.append((request.method, path, request.content.decode()[:300]))
        if path.endswith("/asterisk/info"):
            return httpx.Response(info_status, json={"version": "20.0.0"} if info_status == 200 else {"message": "unauthorized"})
        if path.endswith("/snoop"):
            return httpx.Response(200, json={"id": "snoop.1"})
        if path.endswith("/channels/externalMedia"):
            body = json.loads(request.content.decode() or "{}")
            assert body["format"] == "ulaw" and body["encapsulation"] == "rtp"
            return httpx.Response(200, json={"id": "ext.1"})
        if path.endswith("/bridges"):
            return httpx.Response(200, json={"id": "br.1"})
        if "addChannel" in path or path.endswith("/continue"):
            return httpx.Response(200, json={})
        if request.method == "DELETE":
            return httpx.Response(204, json={})
        return httpx.Response(404, json={})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://x/ari")


def _stasis_start(channel_id="chan-1", caller="+15550001111", called="101", args=None):
    return {
        "type": "StasisStart",
        "args": args or [],
        "channel": {
            "id": channel_id,
            "caller": {"number": caller},
            "dialplan": {"exten": called},
        },
    }


async def test_ari_connect_rejected_without_password():
    ctl = AriController(password=None, base_url="http://127.0.0.1:9/ari")
    status = await ctl.connect()
    assert status["state"] == "error"
    assert "not configured" in (status["last_error"] or "").lower()
    assert status["connected_at"] is None
    await ctl.disconnect()


async def test_ari_connect_auth_failure_is_honest():
    calls: list = []
    ctl = AriController(password="wrongsecret", client=_mock_ari_client(calls, info_status=401))
    status = await ctl.connect()
    assert status["state"] == "error"
    assert "401" in (status["last_error"] or "")
    assert ctl._listen_task is None  # no event loop on failed auth
    await ctl.disconnect()


async def test_ari_tap_recipe_creates_session_and_returns_call():
    calls: list = []
    ctl = AriController(password="testsecret-1", client=_mock_ari_client(calls))
    sid = await ctl.tap_call("chan-1", "+15550001111", "101")
    assert sid is not None
    session = ts.get_session(sid)
    assert session.transport == TRANSPORT_ASTERISK_ARI
    assert session.telephony_call_id == "asterisk-chan-1"
    assert session.caller_display == "+15******1111"
    assert "5550001111" not in json.dumps(await ts.snapshot(session))
    assert session.state == TelephonyState.CONNECTING_MEDIA

    paths = [p for _, p, _ in calls]
    assert any(p.endswith("/snoop") for p in paths)
    assert any(p.endswith("/channels/externalMedia") for p in paths)
    assert any(p.endswith("/bridges") for p in paths)
    assert any("addChannel" in p for p in paths)
    assert any(p.endswith("/continue") for p in paths)
    ext_body = next(b for m, p, b in calls if p.endswith("/channels/externalMedia"))
    assert "ulaw" in ext_body  # RTP target carries the negotiated codec

    await ctl.untap_call("chan-1", reason="remote_bye")
    assert ts.get_session(sid).state == TelephonyState.ENDED
    assert ts.get_session(sid).termination_reason == "remote_bye"
    await ctl.disconnect()


async def test_handle_event_lifecycle_and_malformed_input():
    calls: list = []
    ctl = AriController(password="testsecret-2", client=_mock_ari_client(calls))
    await ctl.handle_event(_stasis_start("chan-9", "+15550002222", "100"))
    sessions = [s for s in ts.list_sessions() if s.telephony_call_id == "asterisk-chan-9"]
    assert len(sessions) == 1
    sid = sessions[0].session_id

    # Snoop-channel echo must not open a duplicate session.
    await ctl.handle_event(_stasis_start("snoop.1", "", ""))
    assert len([s for s in ts.list_sessions() if s.telephony_call_id == "asterisk-chan-9"]) == 1
    # Malformed / unknown input never raises and creates nothing.
    before = len(ts.list_sessions())
    await ctl.handle_event({})
    await ctl.handle_event({"type": "DeviceStateChanged"})
    await ctl._handle_raw("not-json{{{")
    await ctl._handle_raw(None)
    assert len(ts.list_sessions()) == before

    await ctl.handle_event({"type": "ChannelDestroyed", "channel": {"id": "chan-9"}})
    assert ts.get_session(sid).state == TelephonyState.ENDED
    await ctl.disconnect()


async def test_asterisk_leg_claims_inbound_rtp():
    session = await ts.create_session(
        provider_call_id="asterisk-chan-rtp",
        transport=TRANSPORT_ASTERISK_ARI,
        caller_raw="+15550003333",
        called_raw="101",
    )
    await ts.accept_session(session.session_id)
    ingress = LocalRtpIngress(auto_accept=True)
    tone = _ulaw_tone(440.0, 0.02)
    addr = ("127.0.0.40", 41001)
    for i in range(5):
        await ingress.handle_datagram(_rtp(i, i * 160, 0x7777, payload=tone), addr)
    bound = _addr_bindings.get(ingress._key(addr))
    assert bound == session.session_id  # pending ARI leg claimed, no duplicate
    assert ts.get_session(session.session_id).state == TelephonyState.RECEIVING_AUDIO
    await ts.end_session(session.session_id, reason="local_hangup")


async def test_ari_status_and_endpoints_hide_secrets(monkeypatch):
    monkeypatch.setattr(settings, "asterisk_ari_password", "supersecret-ari-pw")
    body = client.get("/api/v1/telephony/ari/status").json()
    assert body["configured"] is True
    assert "supersecret-ari-pw" not in json.dumps(body)
    # Unconfigured controller reports honestly instead of fake-connecting.
    res = client.post("/api/v1/telephony/ari/connect", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["state"] in ("connecting", "error", "connected")
    assert client.post("/api/v1/telephony/ari/disconnect", headers=AUTH).status_code == 200
    assert client.post("/api/v1/telephony/ari/connect").status_code == 401


# ── 3. Lifecycle audit trail ────────────────────────────────────────────


async def test_call_events_endpoint_returns_ordered_trail():
    session = await ts.create_session(
        provider_call_id="evt-test-1", transport="local-rtp", caller_raw="+15550004444"
    )
    await ts.accept_session(session.session_id)
    ingress = LocalRtpIngress(auto_accept=True)
    tone = _ulaw_tone(440.0, 0.02)
    addr = ("127.0.0.41", 41002)
    for i in range(5):
        await ingress.handle_datagram(_rtp(i, i * 160, 0x8888, payload=tone), addr)
    res = client.get(f"/api/v1/telephony/calls/{session.session_id}/events")
    assert res.status_code == 200
    body = res.json()
    names = [e["audit_event"] for e in body["events"]]
    for expected in ("CALL_RECEIVED", "CALL_ACCEPTED", "MEDIA_CONNECTED", "AUDIO_RECEIVING"):
        assert expected in names, names
    assert names.index("CALL_RECEIVED") < names.index("CALL_ACCEPTED") < names.index("AUDIO_RECEIVING")
    assert client.get("/api/v1/telephony/calls/nope/events").status_code == 404
    await ts.end_session(session.session_id, reason="local_hangup")


async def test_event_log_is_capped(monkeypatch):
    from gateway import live_gateway as lg

    monkeypatch.setattr(settings, "telephony_event_log_cap", 16)
    session = await ts.create_session(provider_call_id="evt-cap-1", transport="local-rtp")
    live = lg._sessions[session.live_session_id]
    for i in range(40):
        await lg._emit(live, "test.ping", {"n": i})
    assert len(live.event_log) == 16
    assert live.event_log[-1]["data"] == {"n": 39}
    await ts.end_session(session.session_id, reason="local_hangup")


# ── 4. Detect-only policy ───────────────────────────────────────────────


def test_policy_never_enforces_call_termination():
    for action in ("ALLOW", "FLAG", "ESCALATE", "BLOCK", "CALLBACK", "MFA"):
        res = resolve_call_action(action, "sess-x")
        assert res["mode"] == "detect-only"
        assert res["recorded_action"] == action
        assert res["enforced"] is False
        assert res["call_preserved"] is True


async def test_block_decision_does_not_end_telephony_leg():
    session = await ts.create_session(
        provider_call_id="policy-leg-1", transport=TRANSPORT_ASTERISK_ARI, caller_raw="+15550005555"
    )
    await ts.accept_session(session.session_id)
    resolution = resolve_call_action("BLOCK", session.session_id)
    assert resolution["enforced"] is False
    # The policy path touches no session state: the leg survives BLOCK.
    assert ts.get_session(session.session_id).state == TelephonyState.CONNECTING_MEDIA
    await ts.end_session(session.session_id, reason="local_hangup")


def test_event_to_audit_mapping_covers_lifecycle():
    for name in (
        "CALL_RECEIVED", "CALL_ACCEPTED", "MEDIA_CONNECTED", "AUDIO_RECEIVING",
        "ANALYSIS_STARTED", "ANALYSIS_COMPLETED", "ACTION_TAKEN",
        "CALL_ENDED", "CALL_FAILED",
    ):
        assert name in set(EVENT_TO_AUDIT.values()), name


# ── 5. Rate limiting ────────────────────────────────────────────────────


def test_limiter_counts_windows_and_isolates_keys():
    rate_limit_mod.reset()
    for _ in range(3):
        rate_check("scope-a", "ip-1", limit_per_min=3)
    with pytest.raises(Exception) as exc:
        rate_check("scope-a", "ip-1", limit_per_min=3)
    assert exc.value.status_code == 429
    rate_check("scope-a", "ip-2", limit_per_min=3)  # other source unaffected
    rate_check("scope-b", "ip-1", limit_per_min=3)  # other scope unaffected


def test_calls_endpoint_returns_429_when_over_limit(monkeypatch):
    monkeypatch.setattr(settings, "telephony_rate_limit_per_min", 2)
    assert client.post("/api/v1/telephony/calls", json={"transport": "local-rtp"}, headers=AUTH).status_code == 201
    assert client.post("/api/v1/telephony/calls", json={"transport": "local-rtp"}, headers=AUTH).status_code == 201
    res = client.post("/api/v1/telephony/calls", json={"transport": "local-rtp"}, headers=AUTH)
    assert res.status_code == 429
    assert "Retry-After" in res.headers


# ── 6. Snapshot honesty: latest action / result linkage ─────────────────


async def test_snapshot_latest_action_none_before_analysis():
    session = await ts.create_session(provider_call_id="snap-1", transport="local-rtp")
    snap = await ts.snapshot(session)
    assert snap["latest_action"] is None
    assert snap["result_session_id"] is None
    await ts.end_session(session.session_id, reason="local_hangup")


# ── 7. Real AI pipeline on telephony audio (unmodified models) ──────────


async def test_telephony_audio_produces_real_decision_and_audit():
    """3 s of fixture audio -> END -> the REAL pipeline decides; the audit
    trail, snapshot linkage, and ops record must all reflect that decision.
    No score is asserted — only that genuine pipeline output flows through."""
    from gateway import live_gateway as lg

    session = await ts.create_session(
        provider_call_id="pipeline-leg-1", transport="local-rtp", caller_raw="+15550006666"
    )
    await ts.accept_session(session.session_id)
    ingress = LocalRtpIngress(auto_accept=True)
    tone = _ulaw_tone(440.0, 0.02)
    addr = ("127.0.0.42", 41003)
    n_packets = int(3.0 / 0.02)
    for i in range(n_packets):
        await ingress.handle_datagram(_rtp(i, (i * 160) % 2**32, 0x9999, payload=tone), addr)
    assert ts.get_session(session.session_id).audio_seconds >= 2.5
    await ts.end_session(session.session_id, reason="remote_bye")

    live_id = session.live_session_id
    deadline = time.monotonic() + 600.0
    final = {}
    while True:
        final = client.get(f"/api/v1/live/sessions/{live_id}").json()
        if final["final_status"] in ("complete", "failed"):
            break
        assert time.monotonic() < deadline, "final pipeline run never finished"
        await asyncio.sleep(2.0)
    assert final["final_status"] == "complete", final.get("final_error")
    result_id = final["result_session_id"]
    assert result_id

    snap = await ts.snapshot(ts.get_session(session.session_id))
    assert snap["latest_action"] is None  # windows never filled; final ran instead
    assert snap["result_session_id"] == result_id

    ops = client.get(f"/api/v1/sessions/{result_id}")
    assert ops.status_code == 200
    assert ops.json()["id"] == result_id

    events = client.get(f"/api/v1/telephony/calls/{session.session_id}/events").json()["events"]
    taken = [e for e in events if e["audit_event"] == "ACTION_TAKEN"]
    assert len(taken) == 1
    assert taken[0]["data"]["enforced"] is False  # detect-only, call preserved
