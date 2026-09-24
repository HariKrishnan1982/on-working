# Telephony Setup — Asterisk in WSL2 (or Docker) + VoiceShield

All live steps below are **NOT YET VERIFIED** in the build environment (no
WSL2/Docker there). Perform them on an operator machine and record results
in `docs/real-phone-test.md`.

## 1. Prerequisites (verify first, assume nothing)

- Windows 10/11 64-bit with virtualization enabled in firmware.
- WSL2: `wsl --install -d Ubuntu-24.04` (needs reboot, first time only), **or**
  Docker Desktop with WSL2 backend as an alternative host for Asterisk:
  `docker run -d --name asterisk --net host` from an Asterisk 20 image, then
  copy `asterisk/*.conf` (+ generated secrets) into `/etc/asterisk`.
- Actual ports in use: SIP `UDP/5060`, ARI/HTTP `TCP/8088`, RTP `UDP/10000–20000`
  (Asterisk side). Confirm with `sudo ss -ulpn` / `-tcpn` on the host.
- Networking: from WSL2, find the Windows host IP via
  `ip route show default` (the gateway side of `VFD_ASTERISK_ARI_URL`).
  Windows Firewall must allow the ARI port from WSL2 and UDP/RTP both ways.

## 2. Install + configure Asterisk (WSL2 path)

```bash
wsl -d Ubuntu-24.04
cd /mnt/c/<path-to>/voice-fraud-detection
bash scripts/setup-asterisk-wsl2.sh
```

The script installs Asterisk 20 LTS, installs `asterisk/*.conf`, generates
**random** SIP 100/101 + ARI passwords into `asterisk/*-secrets.conf`
(`0600`, never committed), and prints the gateway `.env` exports **once**.
Verify on the Asterisk host:

```bash
asterisk -rx "core show version"        # expect Asterisk 20.x
asterisk -rx "pjsip show endpoints"     # expect 100, 101 (Unavailable until registered)
asterisk -rx "module show like res_ari" # ari modules loaded
asterisk -rx "http show status"         # HTTP bound, typically :8088
sudo asterisk -rvvv                     # watch live dialplan/SIP during tests
sngrep                                  # SIP packet capture (optional, needs sudo)
```

## 3. Extensions 100/101 (unique credentials, contexts)

- Endpoints/auth/AORs: `asterisk/pjsip.conf` (+ generated `pjsip-secrets.conf`).
- Each extension: unique username (`100`/`101`), unique random password,
  `context=internal`, ulaw/alaw only, `direct_media=no`.
- Secrets live ONLY in `pjsip-secrets.conf` / your private `.env`
  (`SIP_100_PASSWORD`, `SIP_101_PASSWORD`); the repo carries none
  (enforced by `tests/test_asterisk_ari.py` + `test_secret_scan.py`).

## 4. Register softphones (linphone / Zoiper, UDP)

Server `<wsl2-ip>:5060`, user `100` (resp. `101`), password from setup output,
transport UDP, codecs PCMU/PCMA. Confirm `pjsip show endpoints` → `Available`.

## 5. TEST 1 wiring — direct context (no VoiceShield dependency)

Keep endpoint `context=internal-direct` initially (pure `Dial`, no Stasis).
`100 → 101` and `101 → 100` must ring, answer, and carry two-way audio.
Registration alone proves nothing — speak both ways before signing off.

## 6. TEST 2 wiring — VoiceShield tap

1. On Windows: `.\run.ps1 run-gateway`; set `VFD_TELEPHONY_LOCAL_RTP_HOST` to
   the Windows LAN IP reachable from WSL2 (NOT 127.0.0.1 — that is
   loopback-local to Windows and unreachable from WSL2).
2. `POST /api/v1/telephony/ari/connect` (`X-API-Key`) → `ari.status`
   `connected`. If it reports `error`, fix ARI URL/credentials/firewall —
   do not proceed.
3. Switch both endpoints to `context=internal` (`pjsip reload`), place
   `100 → 101`: the ARI controller taps via snoop + externalMedia RTP to
   the gateway ingress, then `continue`s the caller to Dial.
4. Watch `GET /api/v1/telephony/calls` (state → `RECEIVING_AUDIO`,
   `audio_seconds` increasing), Live Calls UI telephony card, then the real
   risk decision + audit record after hangup.

## 7. External SIP provider requirements (TEST 3, EXTERNAL PROVIDER REQUIRED)

Only after TEST 2 passes: a SIP trunk/DID from a real provider, inbound
route into `[from-trunk]` (Stasis tap BEFORE Dial), outbound route as
needed, provider SIP credentials, RTP reachability (public IP / NAT port
forwards for SIP + RTP range, or SBC), TLS/SRTP if the provider mandates
it, a public HTTPS base URL for provider webhooks/media streams
(`VFD_TELEPHONY_PUBLIC_BASE_URL`), and webhook-signature verification
(already implemented for Twilio-compatible providers). Purchase/provision
nothing automatically; commit no credentials. The external RTP MUST
terminate on the path feeding VoiceShield — a "linked number" that never
delivers media produces no analysis, by design.

## 8. Security / privacy checklist

- `0600` on `*-secrets.conf`; `.env` never committed; secret-scan tests green.
- ARI bound to a host-local/LAN interface or behind TLS reverse proxy in prod.
- Rate limits on signaling/webhooks (`VFD_TELEPHONY_RATE_LIMIT_PER_MIN`).
- No raw audio, passwords, keys, or raw numbers in logs/snapshots/chain.
