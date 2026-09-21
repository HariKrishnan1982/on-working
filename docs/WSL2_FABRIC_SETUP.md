# Hyperledger Fabric WSL2 Setup Guide (Phase 0.5)

This guide documents how to stand up the 2-Organization Hyperledger Fabric test network (**Org1 = Operator**, **Org2 = Auditor**) under WSL2 and run the Voice Fraud Detection blockchain layer.

---

## 1. System Requirements & Pinned Versions

- **OS**: Windows 10/11 with WSL2 enabled.
- **Linux Distro**: Ubuntu 22.04 LTS.
- **Hyperledger Fabric**: `v2.5.9` (pinned LTS).
- **Fabric-CA**: `v1.5.12`.
- **Node.js**: `v20.x` LTS.
- **Endorsement Policy**: `AND('Org1MSP.peer', 'Org2MSP.peer')` on all contract writes.

---

## 2. Setting Up WSL2 & Docker

### Step 1: Install WSL2 (Windows PowerShell as Admin)
```powershell
wsl --install -d Ubuntu-22.04
```
Restart your computer if prompted.

### Step 2: Configure Docker Desktop
1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/).
2. In Docker Desktop Settings:
   - Check **Use the WSL 2 based engine**.
   - Under **Resources > WSL Integration**, turn on integration for **Ubuntu-22.04**.

---

## 3. Bootstrapping Fabric in Native WSL2 Filesystem

Open your Ubuntu WSL2 terminal (ensure you are working in the native Linux filesystem `~`, NOT `/mnt/c`):
```bash
# Create native Linux working directory for Fabric
mkdir -p ~/vfd-fabric
cd ~/vfd-fabric

# Download pinned Fabric v2.5.9 and Fabric-CA v1.5.12
curl -sSL https://raw.githubusercontent.com/hyperledger/fabric/main/scripts/install-fabric.sh | bash -s -- --fabric-version 2.5.9 --ca-version 1.5.12 docker binary samples

# Copy chaincode and scripts to native Linux filesystem to avoid DrvFs permission issues
cp -r /mnt/c/Users/PRAYAG\ S/Documents/SIH/Build/voice-fraud-detection/chaincode ~/vfd-fabric/
cp -r /mnt/c/Users/PRAYAG\ S/Documents/SIH/Build/voice-fraud-detection/scripts/fabric/* ~/vfd-fabric/

# Export Fabric binaries to PATH
export PATH=$HOME/vfd-fabric/fabric-samples/bin:$PATH
echo 'export PATH=$HOME/vfd-fabric/fabric-samples/bin:$PATH' >> ~/.bashrc
```

---

## 4. Launching the 2-Org Network & Channel

```bash
cd ~/vfd-fabric/fabric-samples/test-network

# 1. Bring up network with Certificate Authorities and create 'fraud-channel'
./network.sh up createChannel -c fraud-channel -ca -s couchdb

# 2. Deploy VoiceFraudChaincode with AND('Org1MSP.peer', 'Org2MSP.peer') policy from native path
./network.sh deployCC \
  -c fraud-channel \
  -ccn voice_fraud_cc \
  -ccp ~/vfd-fabric/chaincode \
  -ccl typescript \
  -ccv 1.0 \
  -ccs 1 \
  -ccep "AND('Org1MSP.peer','Org2MSP.peer')"
```

---

## 5. Running the Fabric Bridge Service

The REST bridge exposes the smart contracts on `127.0.0.1:8080`:

```bash
cd "c:\Users\PRAYAG S\Documents\SIH\Build\voice-fraud-detection\fabric-bridge"

# Set environment variable
export VFD_FABRIC_BRIDGE_API_KEY=your-secure-bridge-api-key-here

# Install dependencies and start bridge
npm install
npm run build
npm start
```

---

## 6. Running the Tamper & Audit Verification Demo

From Windows PowerShell:
```powershell
# Run audit verification across Postgres and Blockchain
python scripts/verify_audit.py

# Run tamper demonstration (Modification, Deletion, Insertion)
python scripts/tamper_demo.py
```
