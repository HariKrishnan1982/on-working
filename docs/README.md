# Voice Fraud Detection System

A high-assurance, multi-branch voice fraud detection platform that analyzes telephone audio to detect voice cloning, verify speaker identity, evaluate social engineering intent, and trigger deterministic fail-closed risk decisions with a tamper-evident audit ledger.

| # | Core Question | Branch | Model / Algorithm |
|---|---|---|---|
| 1 | Is the audio spoofed/cloned? | Anti-Spoofing | AASIST (ASVspoof 5 benchmark) |
| 2 | Does the voice match the claimed person? | Speaker Verification | ECAPA-TDNN (SpeechBrain, normalized cosine) |
| 3 | Does the conversation sound like a scam? | ASR + Intent Analysis | Indic Whisper + IntentClassifier rule engine |
| 4 | What action do we take? | Risk Engine | Deterministic YAML rules engine (fail-closed, no ML) |

---

## Architectural Principles

1. **Deterministic Decision Loop**: The critical decision path is completely independent of LLM agents. All business logic executes through a shared `PipelineService`.
2. **Fail-Closed Architecture**: Every branch returns a `status` field (`ok`, `failed`, `insufficient_audio`, `not_enrolled`). Degraded or missing evidence **never** yields an `ALLOW` decision.
3. **Strict Separation of Concerns**: The Evidence Fusion layer (`fusion/engine.py`) only aggregates branch results. All inconsistency logic and thresholding live strictly in `risk_engine/rules.yaml`.
4. **Data Privacy in Audit Trail**: High-dimensional speaker embeddings and raw transcripts are never stored on the ledger. `AuditRecord` only stores cryptographic hashes (SHA-256) and storage pointers. Canonical JSON hashing guarantees mathematical tamper detection.
5. **Database-Level Immutability**: The PostgreSQL audit ledger uses advisory locks to serialize chain writes without forks, and attaches a database trigger blocking any `UPDATE` or `DELETE` operations.

---

## Quick Start

### Windows Task Runner (PowerShell)
When `make` is unavailable on Windows, use `run.ps1`:
```powershell
# Run all 35 tests
.\run.ps1 test

# Run audit tests against isolated PostgreSQL
.\run.ps1 test-audit

# Syntax compilation & linting
.\run.ps1 lint

# Start FastAPI Gateway locally
.\run.ps1 run-gateway
```

### Linux / macOS (Makefile)
```bash
make test
make test-audit
make lint
make run-gateway
```

### Docker Compose
PostgreSQL and the Gateway are bound strictly to `127.0.0.1`:
```bash
docker-compose up -d
```

---

## Repository Structure

```
voice-fraud-detection/
├── gateway/                 # FastAPI entry point with API key security and async job API
│   ├── app.py               # Routes: POST /analyze, POST /jobs, GET /jobs/{id}, GET /health
│   └── session.py           # CallSession constructor and hash validation
├── preprocess/              # Audio ingestion and VAD preprocessing
│   └── stub.py              # Preprocessing stub with hashlib.sha256 deterministic seeding
├── branches/
│   ├── antispoof/           # Branch 1: Anti-spoofing (AASIST / ASVspoof 5)
│   ├── speaker/             # Branch 2: Speaker verification (ECAPA-TDNN)
│   └── asr_intent/          # Branch 3: ASR & IntentClassifier interface
├── fusion/                  # Evidence aggregation layer (no hardcoded rules)
│   └── engine.py            # fuse_evidence aggregator
├── risk_engine/             # Deterministic rules engine
│   ├── evaluator.py         # Evaluator with strict AST validation schema (no eval)
│   └── rules.yaml           # Versioned rules with named bands, inconsistencies, fail-closed
├── services/                # Shared service layer decoupled from LLM agents
│   └── pipeline_service.py  # PipelineService: core orchestrator
├── actions/                 # Action dispatchers (ALLOW, FLAG, ESCALATE, BLOCK)
├── audit/                   # Tamper-evident audit ledger
│   ├── sink.py              # AuditSink interface
│   ├── local_hash_chain.py  # PostgresHashChainSink with advisory locking & immutability
│   └── fabric_stub.py       # Hyperledger Fabric sink stub
├── mcp_server/              # Unified MCP Server facade for autonomous agents
│   └── server.py            # Tool facade delegating to PipelineService
├── agents/                  # Structural definitions for 4 autonomous agents
├── schemas/                 # Authoritative Pydantic v2 data contracts
│   └── models.py            # CallSession, SpoofResult, SpeakerResult, RiskDecision, etc.
├── configs/                 # Pydantic BaseSettings (VFD_ prefix)
├── tests/                   # 35 test functions covering all contracts and branches
├── run.ps1                  # Windows PowerShell task runner
└── docker-compose.yml       # Docker Compose bound to 127.0.0.1
```

---

## Phase Roadmap & Specifications

- **Phase 0 (Current)**: Plan, contracts, stubs, deterministic risk engine v0, PostgreSQL audit chain, gateway with API-key auth & async jobs, task runner, and 35 passing tests.
- **Phase 1**: Chunk-friendly audio preprocessing with Silero VAD (16 kHz mono) and SNR filtering.
- **Phase 2**: AASIST model integration fine-tuned on the **ASVspoof 5** benchmark.
- **Phase 3**: ECAPA-TDNN speaker verification with SpeechBrain and Option (a) consented enrollment contracts.
- **Phase 4**: Indic Whisper (Hindi, Tamil, Telugu, Malayalam, Kannada, English) + `IntentClassifier` rule-based and ML models.
- **Phase 5**: Fusion calibration on dev set + offline adversarial red-team perturbation agent with fixed CI perturbation suites.
- **Phase 6**: Hyperledger Fabric ledger integration and monitoring dashboard.
