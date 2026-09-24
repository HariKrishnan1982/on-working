#!/usr/bin/env bash
# VoiceShield — Asterisk 20 LTS setup inside WSL2 Ubuntu (24.04).
#
# OPERATOR-RUN ONLY. This script was NOT executed in the VoiceShield build
# environment (no WSL2/Docker there). Run it inside WSL2 Ubuntu yourself:
#
#   wsl --install -d Ubuntu-24.04        # needs reboot, first time only
#   wsl -d Ubuntu-24.04
#   cd /mnt/c/<path-to>/voice-fraud-detection
#   bash scripts/setup-asterisk-wsl2.sh
#
# What it does:
#   1. Installs Asterisk 20 LTS (+ sngrep for SIP debugging) via apt.
#   2. Backs up /etc/asterisk and installs asterisk/*.conf from this repo.
#   3. Generates RANDOM SIP (100/101) + ARI passwords into
#      pjsip-secrets.conf / ari-secrets.conf (0600, asterisk:asterisk).
#      Secrets are printed ONCE for your own .env — never committed.
#   4. Starts Asterisk and runs verification checks.
#
# After this: follow docs/telephony-setup.md (register softphones, TEST 1).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AST_DIR="/etc/asterisk"
BACKUP_DIR="/etc/asterisk.orig.$(date +%Y%m%d-%H%M%S)"

echo "==> [1/6] Preflight: Ubuntu + network"
if ! grep -qi ubuntu /etc/os-release 2>/dev/null; then
    echo "ERROR: expected Ubuntu (WSL2). Aborting." >&2
    exit 1
fi

echo "==> [2/6] Installing Asterisk 20 LTS + sngrep"
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y asterisk openssl sngrep

echo "==> [3/6] Backing up stock config to ${BACKUP_DIR}"
if [ ! -d "${BACKUP_DIR}" ]; then
    sudo cp -a "${AST_DIR}" "${BACKUP_DIR}"
fi

echo "==> [4/6] Installing VoiceShield configs"
for f in pjsip.conf extensions.conf ari.conf http.conf rtp.conf modules.conf; do
    sudo cp "${REPO_DIR}/asterisk/${f}" "${AST_DIR}/${f}"
done
sudo chown root:asterisk "${AST_DIR}"/pjsip.conf "${AST_DIR}"/extensions.conf \
    "${AST_DIR}"/ari.conf "${AST_DIR}"/http.conf "${AST_DIR}"/rtp.conf \
    "${AST_DIR}"/modules.conf
sudo chmod 0640 "${AST_DIR}"/pjsip.conf "${AST_DIR}"/ari.conf

echo "==> [5/6] Generating random secrets (never committed)"
SIP_100_PASSWORD="$(openssl rand -hex 24)"
SIP_101_PASSWORD="$(openssl rand -hex 24)"
ARI_PASSWORD="$(openssl rand -hex 24)"
sudo tee "${AST_DIR}/pjsip-secrets.conf" > /dev/null <<EOF
; GENERATED LOCALLY by setup-asterisk-wsl2.sh — DO NOT COMMIT.
[auth100](auth-template)
username = 100
password = ${SIP_100_PASSWORD}

[auth101](auth-template)
username = 101
password = ${SIP_101_PASSWORD}
EOF
sudo tee "${AST_DIR}/ari-secrets.conf" > /dev/null <<EOF
; GENERATED LOCALLY by setup-asterisk-wsl2.sh — DO NOT COMMIT.
[voiceshield]
type = user
read_only = no
password = ${ARI_PASSWORD}
password_format = plain
EOF
sudo chown asterisk:asterisk "${AST_DIR}/pjsip-secrets.conf" "${AST_DIR}/ari-secrets.conf"
sudo chmod 0600 "${AST_DIR}/pjsip-secrets.conf" "${AST_DIR}/ari-secrets.conf"

echo "==> [6/6] Starting Asterisk + verification"
sudo systemctl enable --now asterisk 2>/dev/null || sudo service asterisk start
sleep 3
sudo asterisk -rx "core show version"
sudo asterisk -rx "pjsip show endpoints" | grep -E "Endpoint|100|101" || true
sudo asterisk -rx "module show like res_ari" | grep -E "res_ari|0 modules" || true

WSL_IP="$(hostname -I | awk '{print $1}')"
HOST_IP="$(ip route show default | awk '{print $3}')"

cat <<EOF

================ VoiceShield Asterisk setup complete ================
Asterisk host (WSL2):   ${WSL_IP}
Windows host (gateway): ${HOST_IP}

Register softphones (linphone/Zoiper, UDP) — server ${WSL_IP}:5060:
  user 100 / password <SIP_100_PASSWORD above>
  user 101 / password <SIP_101_PASSWORD above>

Gateway .env (Windows side, keep private — shown ONCE):
  VFD_ASTERISK_ARI_URL=http://${WSL_IP}:8088/ari
  VFD_ASTERISK_ARI_USER=voiceshield
  VFD_ASTERISK_ARI_PASSWORD=${ARI_PASSWORD}
  VFD_ASTERISK_ARI_APP=voiceshield
  VFD_TELEPHONY_LOCAL_RTP_HOST=<your Windows LAN IP, reachable from WSL2>

Real secrets (copy NOW into your private .env, never into git):
  SIP_100_PASSWORD=${SIP_100_PASSWORD}
  SIP_101_PASSWORD=${SIP_101_PASSWORD}

Next: docs/telephony-setup.md (TEST 1: 100 <-> 101, then TEST 2 tap).
=====================================================================
EOF
