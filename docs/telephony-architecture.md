# Telephony Architecture — VoiceShield PBX Integration

Status labels: **IMPLEMENTED** · **AUTOMATED TESTED** (`tests/test_asterisk_ari.py`,
`tests/test_telephony_ingress.py`) · **LOCALLY MANUALLY VERIFIED** · **EXTERNAL
PROVIDER REQUIRED** · **NOT YET VERIFIED**.

## 1. Target architecture

```
                    ┌──────────── Asterisk host (WSL2/Docker) ────────────┐
                    │  SIP 100 ←→ [internal(-direct)] ←→ SIP 101          │
Mobile ──PSTN──     │       │ Stasis(voiceshield) tap (TEST 2+)            │
(trunk, FUTURE) ──→ │  snoop(spy:both) + externalMedia ──RTP/ulaw─────────┼──→ VoiceShield
                    │  ARI :8088 ◄── controller (REST+WS) ────────────────┘    gateway
                                                                              (Windows)
                                                                               ↓
VoiceShield gateway ── telephony ingress ── LiveSession ── 8 s windows ── AI pipeline
(AASIST/ECAPA/Whisper, unmodified) ── fusion/risk ── ALLOW/FLAG/ESCALATE/BLOCK
(recorded) ── ops store + audit (anchor_pending when Fabric offline)
```

Strategy: **A — Asterisk + PJSIP + RTP**, isolated in **WSL2 Ubuntu** (Docker
alternative documented in `telephony-setup.md`). The Windows Python
environment is untouched by design; Asterisk never runs on Windows.

## 2. Why ARI snoop + externalMedia (and not alternatives)

| Option | Verdict |
|---|---|
| ARI snoop (`spy:both`) + externalMedia RTP to existing ingress | **Chosen — IMPLEMENTED**. Zero new audio code; both directions tapped; call preserved via `continue` → Dial. |
| AudioSocket TCP listener | Viable alternative, NOT implemented (would need a new TCP audio server + dialplan takeover semantics). |
| SIP trunk directly to gateway | Impossible — gateway has no SIP stack, by design. Trunks terminate on Asterisk. |
| Provider media-stream WS (Twilio) | Already implemented (`telephony-ingress.md` §2); orthogonal path, unchanged. |

## 3. Component map (all transport/input layer, no AI duplication)

| Piece | Location | Status |
|---|---|---|
| PJSIP endpoints 100/101, transports, templates | `asterisk/pjsip.conf` | IMPLEMENTED, AUTOMATED TESTED, NOT YET VERIFIED live |
| Dialplan `[internal-direct]` (TEST 1) + `[internal]` Stasis tap (TEST 2) | `asterisk/extensions.conf` | IMPLEMENTED, AUTOMATED TESTED, NOT YET VERIFIED live |
| ARI user, HTTP/WS, RTP range, modules | `asterisk/ari.conf`, `http.conf`, `rtp.conf`, `modules.conf` | IMPLEMENTED, AUTOMATED TESTED, NOT YET VERIFIED live |
| WSL2 install + secrets generation | `scripts/setup-asterisk-wsl2.sh` | IMPLEMENTED, NOT YET VERIFIED (operator-run) |
| ARI controller (tap recipe, lifecycle, reconnect) | `telephony/asterisk_ari.py` | IMPLEMENTED, AUTOMATED TESTED, NOT YET VERIFIED live |
| `asterisk-ari` transport + pending-leg RTP binding | `telephony/models.py`, `sessions.py` | IMPLEMENTED, AUTOMATED TESTED |
| ARI status/connect/disconnect, call events trail | `gateway/telephony_api.py` | IMPLEMENTED, AUTOMATED TESTED |
| Per-IP rate limits on signaling/webhooks | `gateway/rate_limit.py` | IMPLEMENTED, AUTOMATED TESTED |
| Detect-only action policy | `telephony/policy.py` | IMPLEMENTED, AUTOMATED TESTED |
| Lifecycle audit trail (`CALL_RECEIVED`…`CALL_ENDED`) | live-session `event_log` + `action.taken` | IMPLEMENTED, AUTOMATED TESTED |
| Live Calls UI: PBX badge, TELEPHONY UNAVAILABLE, latest action | `frontend/src/...` | IMPLEMENTED (build passes), NOT YET VERIFIED live |

## 4. Media path integrity rules (enforced)

- Gateway RTP ingress accepts **only** canonicalizable payloads (PCMU/PCMA/L16);
  anything else fails the leg explicitly (`unsupported_codec`).
- Missing packets are **counted** (`packets_lost`/`packets_dropped`), never
  concealed or synthesized.
- Raw audio lives in memory + short-lived window WAVs (deleted after use).
- Snapshots/events/logs carry masked numbers + HMAC refs only; the on-chain
  payload carries the decision hash (raw numbers excluded by construction).
- `direct_media=no` on Asterisk endpoints forces media through the PBX so the
  tap always observes both directions.

## 5. Call-security behavior (detect-only milestone)

`telephony_action_mode` is locked to `detect-only` (any other value fails
config validation). Decided actions (including BLOCK) are **recorded**
(ops store + audit chain) and **exposed** (snapshot `latest_action`, UI),
but the PBX call is never hung up, redirected, or disturbed by VoiceShield.
Preventive termination needs a future ARI-control phase with explicit
operator opt-in — it does not exist yet, and no endpoint claims otherwise.

## 6. What is deliberately NOT here

SIP trunk purchasing, DID provisioning, production routing, PBX replacement,
call recording, new RBAC, UI redesign, live Fabric deployment, any model
rewrite. External PSTN remains **EXTERNAL PROVIDER REQUIRED** (see
`real-phone-test.md` TEST 3 and `telephony-setup.md` §6).
