#!/usr/bin/env bash
# ==============================================================================
# WSL2 Bootstrap Script for Hyperledger Fabric v2.5.9
# Run inside WSL2 Ubuntu terminal: ~/bootstrap_wsl.sh
# ==============================================================================

set -euo pipefail

FABRIC_VERSION="2.5.9"
CA_VERSION="1.5.12"
NODE_VERSION="20"

echo "==> [1/4] Installing system prerequisites..."
sudo apt-get update -y
sudo apt-get install -y curl git jq docker.io docker-compose

# Ensure current user is in docker group
sudo usermod -aG docker "$USER" || true

echo "==> [2/4] Verifying / Installing Node.js LTS (v${NODE_VERSION})..."
if ! command -v node &> /dev/null || [[ $(node -v) != v${NODE_VERSION}* ]]; then
    curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi
echo "Node version: $(node -v), NPM version: $(npm -v)"

echo "==> [3/4] Downloading pinned Hyperledger Fabric v${FABRIC_VERSION} and CA v${CA_VERSION}..."
TARGET_DIR="$HOME/vfd-fabric"
mkdir -p "${TARGET_DIR}"
cd "${TARGET_DIR}"

if [ ! -d "fabric-samples" ]; then
    curl -sSLO https://raw.githubusercontent.com/hyperledger/fabric/main/scripts/install-fabric.sh
    chmod +x install-fabric.sh
    ./install-fabric.sh --fabric-version "${FABRIC_VERSION}" --ca-version "${CA_VERSION}" docker binary samples
fi

echo "==> [4/4] Adding Fabric binaries to PATH..."
export PATH="${TARGET_DIR}/fabric-samples/bin:$PATH"
if ! grep -q "vfd-fabric/fabric-samples/bin" "$HOME/.bashrc" 2>/dev/null; then
    echo "export PATH=\"${TARGET_DIR}/fabric-samples/bin:\$PATH\"" >> "$HOME/.bashrc"
fi

echo "==> WSL2 Fabric Bootstrap Complete in native filesystem: ${TARGET_DIR}"
echo "Next step: copy chaincode to ${TARGET_DIR}/chaincode and run ./network.sh up"
