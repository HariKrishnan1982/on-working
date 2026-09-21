#!/usr/bin/env bash
# ==============================================================================
# Hyperledger Fabric Chaincode Deployment Script
# Deploys TypeScript VoiceFraudChaincode with endorsement policy: AND(Org1, Org2)
# ==============================================================================

set -euo pipefail

CHANNEL_NAME="fraud-channel"
CC_NAME="voice_fraud_cc"
CC_VERSION="1.0"
CC_SEQUENCE="1"
if [ -d "${PWD}/../chaincode" ]; then
    CC_SRC_PATH="${PWD}/../chaincode"
elif [ -d "${HOME}/vfd-fabric/chaincode" ]; then
    CC_SRC_PATH="${HOME}/vfd-fabric/chaincode"
else
    CC_SRC_PATH="${PWD}/chaincode"
fi

CC_RUNTIME_LANGUAGE="typescript"
CC_POLICY="AND('Org1MSP.peer','Org2MSP.peer')"

echo "==> Deploying '${CC_NAME}' chaincode to channel '${CHANNEL_NAME}'..."
echo "==> Source Path: ${CC_SRC_PATH}"
echo "==> Endorsement Policy: ${CC_POLICY}"

if [ ! -d "test-network" ]; then
    if [ -d "${HOME}/vfd-fabric/fabric-samples/test-network" ]; then
        cd "${HOME}/vfd-fabric/fabric-samples"
    else
        echo "ERROR: Please run this script from the directory containing test-network."
        exit 1
    fi
fi

cd test-network

./network.sh deployCC \
    -c "${CHANNEL_NAME}" \
    -ccn "${CC_NAME}" \
    -ccp "${CC_SRC_PATH}" \
    -ccl "${CC_RUNTIME_LANGUAGE}" \
    -ccv "${CC_VERSION}" \
    -ccs "${CC_SEQUENCE}" \
    -ccep "${CC_POLICY}"

echo "==> Successfully deployed ${CC_NAME} with AND(Org1, Org2) endorsement policy!"
