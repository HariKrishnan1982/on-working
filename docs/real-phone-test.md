# Real Phone Test Plan — VoiceShield Telephony Milestones

Rule: a test succeeds only if actually performed end-to-end with real media.
Fixture traffic, registrations without audio, and log-only checks are NOT
passes. As of this writing **all three tests are NOT PERFORMED** (the build
environment has no WSL2/Docker/Asterisk, no SIP endpoints, no provider).

## TEST 1 — SIP 100 → Asterisk → SIP 101 (no VoiceShield)

Setup: `docs/telephony-setup.md` §§1–5, endpoints on `[internal-direct]`.

| # | Check | Result |
|---|---|---|
| 1.1 | `asterisk -rx "core show version"` → 20.x | NOT PERFORMED |
| 1.2 | 100 and 101 registered (`pjsip show endpoints` → Available) | NOT PERFORMED |
| 1.3 | 100 → 101: ring + answer + **two-way speech** (speak both ways) | NOT PERFORMED |
| 1.4 | 101 → 100: same | NOT PERFORMED |
| 1.5 | `rtp show stats` / sngrep confirms RTP both directions | NOT PERFORMED |

## TEST 2 — SIP 100 → VoiceShield tap → SIP 101 (detect-only)

Setup: `docs/telephony-setup.md` §6 (ARI connected, `[internal]` context).

| # | Check | Result |
|---|---|---|
| 2.1 | ARI `connected` via `GET /api/v1/telephony/ari/status` | NOT PERFORMED |
| 2.2 | Real call placed 100 → 101; call completes normally (preserved) | NOT PERFORMED |
| 2.3 | Telephony session created (`transport: asterisk-ari`, real IDs) | NOT PERFORMED |
| 2.4 | `audio_seconds` increases; codec PCMU/PCMA; loss counters sane | NOT PERFORMED |
| 2.5 | Events trail shows CALL_RECEIVED → … → CALL_ENDED in order | NOT PERFORMED |
| 2.6 | ≥2 s speech → real VAD segments (not `insufficient_audio`) | NOT PERFORMED |
| 2.7 | Real AASIST / ECAPA / Whisper outputs on call audio | NOT PERFORMED |
| 2.8 | Real risk decision + action in Session Detail (any action incl. BLOCK) | NOT PERFORMED |
| 2.9 | Call NOT disturbed by the decision (detect-only) | NOT PERFORMED |
| 2.10 | Frontend telephony card shows the real call + analysis link | NOT PERFORMED |
| 2.11 | Audit record present; `anchor_pending` iff Fabric offline (truthful) | NOT PERFORMED |
| 2.12 | Hangup → ENDED, RTP stops, resources released | NOT PERFORMED |

Latencies to record (measured, else NOT MEASURED): SIP registration, call
setup, RTP connect, first audio, first window, VAD, AASIST, ECAPA, ASR, risk
calc, end-to-end window. Never invent numbers.

## TEST 3 — External number → provider → VoiceShield (EXTERNAL PROVIDER REQUIRED)

Only with a real trunk/DID per `telephony-setup.md` §7.

| # | Check | Result |
|---|---|---|
| 3.1 | Real external (mobile) call to the DID reaches Asterisk media | NOT PERFORMED |
| 3.2 | VoiceShield receives the external audio (rising `audio_seconds`) | NOT PERFORMED |
| 3.3 | AI processing + security decision on the external audio | NOT PERFORMED |
| 3.4 | Documented call continuation/action per detect-only policy | NOT PERFORMED |
| 3.5 | Audit record for the external call | NOT PERFORMED |

## Automated coverage that already exists (not a substitute for the above)

- `tests/test_asterisk_ari.py`: config validation, ARI tap recipe against a
  mocked ARI REST surface, event mapping, echo suppression, RTP binding,
  audit trail ordering + cap, detect-only policy, rate limits, and a REAL
  unmodified-pipeline decision over ingress-fed audio (fail-closed
  CRITICAL/ESCALATE on non-speech, proving the path end-to-end in code).
- `tests/test_telephony_ingress.py`: RTP/G.711, webhooks, WS media, privacy.
