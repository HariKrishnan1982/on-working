# Telephony Ingress — Real Phone Calls into the Voice-Fraud Pipeline

Status legend used in this document:

- **IMPLEMENTED** — code exists in the repo.
- **TESTED AUTOMATICALLY** — covered by `tests/test_telephony_ingress.py`.
- **MANUALLY VERIFIED** — exercised by a human against a running gateway.
- **REQUIRES EXTERNAL PROVIDER** — needs a carrier/provider account or PBX.

## 1. Architecture

```
REAL PHONE CALL
      ↓ PSTN / SIP phone / PBX
Telephony source (SIP phone, Asterisk/FreeSWITCH, or provider)
      ↓  (a) raw RTP/UDP  |  (b) provider media-stream WebSocket
telephony/  (transport layer ONLY: TelephonySession, RTP parse,
             G.711 → 16 kHz mono PCM normalization)
      ↓  gateway.live_gateway.ingest_pcm16  (shared with browser WebRTC)
Existing LiveSession → 8 s windows → PipelineService (AASIST + ECAPA +
Whisper, unmodified) → fusion → risk engine → actions → ops store →
audit chain (decision hashes only)
```

Scope decision: **Option C** — a provider-neutral `TelephonyIngress`
interface with two real ingresses and no fake carrier:

- (a) **Local RTP/UDP ingress** (`telephony/ingress.py::LocalRtpIngress`):
  a genuine asyncio UDP listener receiving real RFC 3550 RTP packets
  (PCMU/PCMA/L16). Any real SIP phone (linphone, baresip) or PBX pointed
  at the bound host/port delivers actual call audio. No carrier account,
  no SIP-signaling stack.
- (b) **Provider media-stream boundary** (`gateway/telephony_api.py`):
  Twilio-compatible signaling webhook (HMAC-SHA1 verified) + Media
  Streams WebSocket (base64 µ-law). Application side is implemented; the
  provider account, phone number, and public URL are the configuration
  boundary (see §3).

The telephony adapter never duplicates the AI pipeline: both transports
feed `LiveSession` buffers through the single `ingest_pcm16` interface.

## 2. Supported telephony transport — IMPLEMENTED, TESTED AUTOMATICALLY

| Transport | Status | Notes |
|---|---|---|
| RTP/UDP PCMU (PT 0, 8 kHz) | IMPLEMENTED, TESTED AUTOMATICALLY | G.711 µ-law → 16 kHz mono int16 |
| RTP/UDP PCMA (PT 8, 8 kHz) | IMPLEMENTED, TESTED AUTOMATICALLY | G.711 A-law → 16 kHz mono int16 |
| RTP dynamic L16 (PT 96) | IMPLEMENTED (local negotiation only) | 8/16 kHz linear |
| Twilio Media Streams WS (µ-law) | IMPLEMENTED, TESTED AUTOMATICALLY | `WS /api/v1/telephony/calls/{id}/media` |
| Twilio voice webhook | IMPLEMENTED, TESTED AUTOMATICALLY | signature-verified, §7 |
| SIP signaling (INVITE/BYE/trunk) | PBX-side configs + ARI controller IMPLEMENTED, AUTOMATED TESTED, NOT YET VERIFIED live | See `docs/telephony-architecture.md`: `asterisk/` (PJSIP 100/101, dialplan, ARI) + `telephony/asterisk_ari.py` (snoop + externalMedia tap). No live Asterisk in this environment, so no live verification yet. |

Unsupported payload types fail the call explicitly (`unsupported_codec`);
they are never silently substituted.

## 3. Required provider configuration — IMPLEMENTED

Environment variables (`VFD_` prefix, see `.env.example` — placeholders
only, never commit secrets):

- `VFD_TELEPHONY_PROVIDER` — e.g. `twilio`; empty = no provider.
- `VFD_TELEPHONY_API_KEY` / `VFD_TELEPHONY_API_SECRET` — provider creds.
- `VFD_TELEPHONY_WEBHOOK_SECRET` — Twilio auth token; doubles as the
  webhook signature key. Webhooks are rejected (503) when unset.
- `VFD_TELEPHONY_SIP_DOMAIN` — informational, future trunk wiring.
- `VFD_TELEPHONY_PUBLIC_BASE_URL` — public gateway URL used to rebuild
  the signed webhook URL (falls back to the incoming request URL).
- `VFD_TELEPHONY_LOCAL_RTP_ENABLED/HOST/PORT` — local ingress bind.
- `VFD_TELEPHONY_AUTO_ACCEPT_LOCAL` — accept local calls on arrival.
- `VFD_TELEPHONY_MAX_BODY_BYTES` — webhook size cap (413 above it).

## 4. Local development setup — IMPLEMENTED, MANUALLY VERIFIED (API only)

1. `.\run.ps1 run-gateway` (gateway on 127.0.0.1:8000).
2. `GET /api/v1/telephony/status` → `local_rtp.listening` is false until
   the first provisioned leg; `POST /api/v1/telephony/calls`
   (`X-API-Key`) starts the listener and returns `{host, port, codecs}`.
3. Point a SIP phone at that host/port with PCMU/PCMA, or send RFC 3550
   packets: a session appears under `GET /api/v1/telephony/calls` only
   when genuine packets arrive. No packet → no session, ever.
4. End with `POST /api/v1/telephony/calls/{id}/end`.

## 5. Webhook/signaling flow — IMPLEMENTED, TESTED AUTOMATICALLY

`POST /api/v1/telephony/webhooks/twilio` (form-encoded):
`ringing/initiated/queued` → session RECEIVED; `in-progress` → ACCEPTED;
`completed/failed/busy/no-answer/canceled` → ENDED (`remote_bye`).
Unknown providers → 404. Media then flows over the per-call WS.

## 6. Audio normalization — IMPLEMENTED, TESTED AUTOMATICALLY

`telephony/audio.py`: G.711 µ-law/A-law decode (ITU-T G.711) →
`resample_poly` to **16 kHz mono int16** (the pipeline's canonical form,
same primitive as the preprocessor). In-memory only; window WAVs are
short-lived temp files deleted after processing. RTP accounting per
RFC 3550: sequence-gap loss, duplicates, SSRC changes, timestamp
discontinuities, interarrival jitter. Missing audio is counted as
lost/dropped — never concealed with generated samples.

## 7. Security model — IMPLEMENTED, TESTED AUTOMATICALLY

- Provider webhooks: exact Twilio HMAC-SHA1 validation with
  `compare_digest`; 401 on mismatch, 415 on wrong content type, 413 on
  oversize, 400 on malformed bodies. No session is created before a
  valid signature.
- Call control (`POST /calls`, `/accept`, `/end`): same `X-API-Key` as
  the main gateway. Reads (`GET /status`, `/calls`) match the open
  dashboard posture.
- Session isolation: media WS binds to a pre-existing call id; unknown
  ids close with 4404; one call cannot touch another (tested).
- Never logged: raw audio, secrets, full transcripts, raw numbers.
  Structured logs carry session ids, transitions, and counters only.

## 8. Privacy model — IMPLEMENTED, TESTED AUTOMATICALLY

- Primary identity is always the internal `session_id`.
- `caller_ref` = HMAC-SHA256(caller, `VFD_VFD_HMAC_SECRET`) — reuse of
  `schemas/hash_utils.py`, the same mechanism as enrollment subject refs.
- UI/audit see only `caller_display` (masked, e.g. `+91******3210`).
- The backing live session's `caller_id` is the masked form, so the
  on-chain decision hash (`caller_id` field) never contains a raw number.
- Raw audio and transcripts never enter the audit chain (hashes only,
  via the shared finalize path). Tests assert raw digits appear nowhere.

## 9. Connection to the existing analysis pipeline — IMPLEMENTED

`TelephonySession.live_session_id` → existing `LiveSession`; media via
`ingest_pcm16` (also used by WebRTC — the browser flow is untouched);
8 s windows → `PipelineService` → existing fusion/risk/actions; END via
`end_live_session` → ops record + `FabricSink.append` (decision hash).
`anchor_pending` behavior when Fabric is offline is preserved. Telephony
events (`telephony.call.received/accepted`, `telephony.media.connected`,
`telephony.audio.receiving`, `telephony.call.ended/failed`) reuse the
live-session event queue, alongside the existing `analysis.*` events.

## 10. Real phone-call test — documented procedures (NOT PERFORMED)

Live verification lives in `docs/real-phone-test.md` (TEST 1: SIP 100↔101,
TEST 2: VoiceShield tap with real AI analysis, TEST 3: external provider).
None has been performed in this environment (no WSL2/Docker/Asterisk,
endpoints, or provider).

Phone A (cellular) → call the provider number → provider webhook hits
`https://<public-base>/api/v1/telephony/webhooks/twilio` → leg ACCEPTED
→ provider opens media WS → `telephony.audio.receiving` → audio seconds
increase → 8 s windows → AASIST/ECAPA/Whisper → risk result → Live Calls
UI telephony card → View Analysis → audit record → hang up → ENDED +
resources released. Alternatively via PBX: route a trunk/extension's RTP
to the local ingress port (§4). Verify each hop with `GET
/api/v1/telephony/calls/{id}` (state, `audio_seconds`, `stats`,
`live_session_id` → `result_session_id`).

## 11. Known limitations

- No SIP-signaling stack: INVITE/BYE/trunking need Asterisk/FreeSWITCH
  or a provider; the gateway speaks RTP + provider webhooks/streams.
- `test_webrtc_loopback_receives_real_audio` and TestClient UDP delivery
  fail in this sandbox (harness loop limits); the RTP path is covered by
  a live-uvicorn UDP test instead.
- No real-carrier call has been placed: PSTN support is NOT claimed.
- All latencies below are NOT MEASURED (no live call yet); window/final
  events carry measured `latency_ms` once media flows.
