#!/usr/bin/env bash
# ==============================================================================
# Hyperledger Fabric Test-Network Orchestrator for Voice Fraud Detection
# ==============================================================================
# NOTE: Run this script inside the WSL2 Ubuntu filesystem (e.g. ~/fabric-samples)
# Pin versions: Fabric v2.5.9, Fabric-CA v1.5.12
# ==============================================================================

set -euo pipefail

CHANNEL_NAME="fraud-channel"
FABRIC_VERSION="2.5.9"
CA_VERSION="1.5.12"

command="${1:-help}"

function print_help() {
    echo "Usage: ./network.sh [up|down|restart]"
    echo "  up       - Bring up Fabric 2-org test-network with CA and create fraud-channel"
    echo "  down     - Bring down test-network and clean containers/volumes"
    echo "  restart  - down followed by up"
}

case "${command}" in
    up)
        echo "==> Bringing up Hyperledger Fabric 2-Org Network (Channel: ${CHANNEL_NAME})..."
        if [ ! -d "test-network" ]; then
            echo "ERROR: Please run this inside the 'fabric-samples' directory in WSL2."
            exit 1
        fi
        cd test-network
        ./network.sh up createChannel -c "${CHANNEL_NAME}" -ca -s couchdb
        echo "==> Fabric test-network is UP on channel '${CHANNEL_NAME}'!"
        ;;

    down)
        echo "==> Tearing down Fabric network and cleaning containers..."
        if [ -d "test-network" ]; then
            cd test-network
            ./network.sh down
        fi
        echo "==> Network teardown complete."
        ;;

    restart)
        $0 down
        $0 up
        ;;

    *)
        print_help
        exit 1
        ;;
esac
