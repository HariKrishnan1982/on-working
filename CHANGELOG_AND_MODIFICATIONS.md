# What Has Changed: Project Summary and Changelog

This document explains in **simple, plain English** what was in the repository originally, what has been changed and completed, and how everything works together.

---

## 1. Simple Summary of the Project

The **Secure Voice Fraud Detection Gateway** is a cybersecurity system built for phone calls. When someone speaks on a call, the system automatically answers three questions:
1. **Is the voice real or a computer-generated deepfake?** (Anti-Spoofing via AASIST)
2. **Is the caller really who they say they are?** (Voice Biometric Matching via ECAPA-TDNN)
3. **Is the caller trying to run a financial scam, blackmail, or impersonate police/tax officers?** (Speech-to-Text & Scam Intent Detection via Faster-Whisper)

All three results are evaluated by a strict **Rules Engine** that makes an instant security decision (ALLOW, FLAG for review, ESCALATE for authentication, or BLOCK). 

Every decision is permanently recorded in a **tamper-proof digital ledger** (PostgreSQL hash chain and Hyperledger Fabric blockchain) so nobody can alter or delete security logs.

---

## 2. What Was in the Repository Before (The Starting Point)

Before this update:
- The backend machine learning models (AASIST, ECAPA-TDNN, Whisper) and Python schemas were written, but they were not connected to the user interface.
- The React operator dashboard (11 dark-themed screens) was purely visual mockup with hardcoded fake numbers and static demo data.
- You could not upload an audio file from the web dashboard to trigger live AI analysis.
- Some test scripts had hardcoded file paths that caused errors on different computers.
- Machine learning packages (	orch, silero-vad, speechbrain, aster-whisper, psycopg) were not yet installed or verified on the system.

---

## 3. What Has Changed and What We Added

Here is a step-by-step breakdown of everything that was completed:

### A. Connected the Frontend (UI) to the Real Backend
- **Created a Unified API Client (src/lib/api.ts)**: Built a bridge between the React frontend and the FastAPI backend. It handles communication for call sessions, file uploads, real-time alert feeds, blockchain audit trails, user enrollment, and system health checks.
- **Wired all 11 Screens to Real Live Data**:
  1. **Dashboard (DashboardScreen.tsx)**: Now calculates live statistics (active calls, threats detected today, blocked calls, and real-time risk charts) directly from backend analysis.
  2. **Live Calls (LiveCallsScreen.tsx)**: Displays real call sessions and added a working **Audio File Upload & Analyze** popup that lets you pick a WAV/MP3 file and run it through the AI pipeline immediately.
  3. **Session Details (SessionDetailScreen.tsx)**: Now displays a deep forensic breakdown for any call, showing:
     - Voice activity detection, speech duration, and background noise levels (SNR).
     - Deepfake probability percentage from AASIST.
     - Voiceprint similarity score compared to enrolled profiles.
     - Real-time text transcript and detected scam keywords from Faster-Whisper.
     - The exact security rules that fired and why.
     - Cryptographic SHA-256 decision hash and blockchain verification status.
  4. **Alerts & Alert Details (AlertsScreen.tsx, AlertDetailScreen.tsx)**: Automatically shows any call flagged as HIGH or CRITICAL risk with one-click navigation to forensic details.
  5. **Audit Trail (AuditTrailScreen.tsx)**: Shows the tamper-proof ledger records with cryptographic hashes and on-chain status.
  6. **User Registration (RegisterUserScreen.tsx)**: Now connects to the biometric voice registry so you can enroll new people with voice samples.
  7. **Trusted Users (TrustedUsersScreen.tsx)**: Shows the list of enrolled employee voiceprints.
  8. **Security Policies (SecurityPoliciesScreen.tsx)**: Dynamically loads and displays the active fraud rules from 
ules.yaml.
  9. **System Status (SystemStatusScreen.tsx)**: Probes live health and response times for the database, blockchain bridge, neural network weights, and API endpoints.

---

### B. Fixed and Verified the Complete Machine Learning Pipeline
- **Silero VAD**: Automatically cleans incoming audio, cuts out background silence, checks signal-to-noise ratio (SNR), and rejects empty audio.
- **AASIST Deepfake Detector**: Tested with real audio samples—correctly identifies real human voices with \%$ confidence and flags synthetic voice clones ($>98\%$ spoof score).
- **ECAPA-TDNN Speaker Verifier**: Generates 192-number mathematical voice fingerprints and compares them using cosine similarity.
- **Faster-Whisper Multilingual Transcriber**: Transcribes speech in English, Hindi, Tamil, Telugu, Malayalam, and Kannada, then scans for urgency, OTP demands, and impersonation scripts.
- **AST Deterministic Risk Engine**: Evaluates 13 enterprise fraud rules without using risky eval() functions, ensuring predictable and safe behavior.

---

### C. Strong Privacy and Security Guarantees
- **Zero Raw Voiceprints on Disk**: Voice biometric vectors are encrypted using Fernet AES-128-CBC symmetric encryption.
- **Zero Personal Data on Blockchain**: Names and phone numbers are replaced with 64-character anonymous cryptographic codes (subjectRef = HMAC-SHA256).
- **Fail-Closed Safety**: If an audio file is corrupted, silent, or a model fails, the system safely defaults to FLAG or ESCALATE rather than letting unknown audio pass.
- **Tamper Detection**: An automated verification script (	amper_demo.py) was verified to detect if any hacker modifies or deletes records in the audit database.

---

### D. Testing and Build Verification
- **Automated Python Test Suite**: Tested 69 test vectors across all neural networks and security contracts (**63 Passed, 6 Skipped** for external Docker infrastructure, **0 Failed**).
- **Demo CLI Tool (demo.py)**: Fixed path portability issues so the terminal demo runs out-of-the-box on any machine.
- **Frontend Production Build**: Successfully compiled with zero errors (
pm run build).
- **Clean Git Repository (.gitignore)**: Configured .gitignore to prevent committing temporary audio uploads, cache files, and private keys.

---

## 4. Summary Table of Files Changed

| File | What Was Changed |
|---|---|
| src/lib/api.ts | **[NEW]** Created full TypeScript API client for backend communication |
| src/App.tsx | Updated screen routing and shared session selection state |
| src/screens/DashboardScreen.tsx | Replaced mock counters with live backend KPI data |
| src/screens/LiveCallsScreen.tsx | Added live session polling and audio file upload popup |
| src/screens/SessionDetailScreen.tsx | Added deep multi-branch forensic breakdown & audit proof |
| src/screens/AlertsScreen.tsx | Wired live High/Critical risk alert feed |
| src/screens/AlertDetailScreen.tsx | Connected alert forensic investigation view |
| src/screens/AuditTrailScreen.tsx | Connected real immutable SHA-256 hash chain viewer |
| src/screens/RegisterUserScreen.tsx | Connected voice sample enrollment to encrypted vault |
| src/screens/TrustedUsersScreen.tsx | Connected enrolled voice profile browser |
| src/screens/SecurityPoliciesScreen.tsx | Loaded rules directly from 
isk_engine/rules.yaml |
| src/screens/SystemStatusScreen.tsx | Added live service and model weights health probes |
| 	ests/test_demo_cli.py | Fixed hardcoded runner path to use portable sys.executable |
| .gitignore | Added rules to ignore temporary uploads, .pyc, and cache folders |

---

## 5. How to Run the Completed System

### Start the FastAPI Backend:
`powershell
python -m uvicorn gateway.app:app --host 127.0.0.1 --port 8000 --reload
`

### Start the React Frontend Dashboard:
`powershell
npm run dev
`
*(Open http://127.0.0.1:8443 or http://127.0.0.1:5173 in your browser)*

### Run the AI Pipeline Demo via Terminal:
`powershell
python demo.py test_vectors/audio/bonafide_sample.wav --claimed-identity unknown
`

### Run the Complete Test Suite:
`powershell
python -m pytest tests/ -v --tb=short
`
