# DONE — Voice Fraud Detection: Work Completed So Far

> Status snapshot of the `voice-fraud-detection/` project: what is implemented,
> tested, wired, and what is still pending. Last updated after the per-screen
> dashboard-vs-backend audit (frontend screens verified 100% mock; backend
> fully implemented and tested).

---

## 1. Project overview

Real-time multi-branch **voice fraud detection** backend (FastAPI + Python)
with an operator dashboard (React + Vite + TypeScript). Every call session is
analyzed by three parallel branches, fused into one evidence object, judged by
a **deterministic, AST-evaluated risk engine** (no `eval()`, no LLM in the
decision path), and anchored to an **immutable dual-write audit layer**
(PostgreSQL 16 hash chain + Hyperledger Fabric 2.5 outbox).

- Backend entrypoint: `gateway/app.py` → `uvicorn gateway.app:app`
- Dashboard entrypoint: `frontend/src/App.tsx` (11 screens, Figma-matched dark UI)
- CLI demo: `demo.py <audio-file>` (terminal walkthrough of all pipeline stages)
- Task runner: `run.ps1` (`test`, `test-audit`, `lint`, `up`, `down`, `build`, `run-gateway`, `clean`)
- Full design history: `PROJECT_MASTER_STATUS_REPORT.md`; architecture: `docs/`

---

## 2. Detection pipeline — IMPLEMENTED & TESTED (do not modify)

| Phase | What | Key files |
|---|---|---|
| 0 — Contracts | Strict Pydantic v2 schemas (`CallSession`, `SpoofResult`, `SpeakerResult`, `IntentResult`, `FusedEvidence`, `RiskDecision`, `AuditRecord`); score ranges pinned to `[0.0, 1.0]`; SHA-256 regex validation | `schemas/models.py`, `schemas/hash_utils.py` |
| 1 — VAD & preprocess | 16 kHz mono polyphase resampling, Silero VAD segmentation, energy SNR estimate, fail-closed silence guard (`INSUFFICIENT_AUDIO`) | `preprocess/vad.py` |
| 2 — Anti-spoofing | Clova AI **AASIST** (graph-attention network), pretrained weights `models/weights/AASIST.pth`, `is_spoofed = spoof_score >= 0.50` | `branches/antispoof/aasist.py`, `aasist_model.py` |
| 3 — Speaker verification | SpeechBrain **ECAPA-TDNN** 192-dim embeddings (`models/weights/ecapa-voxceleb/`), normalized cosine similarity, operating threshold `0.65`; privacy enrollment store (HMAC-SHA256 `subjectRef` keys, Fernet-encrypted tensors, consent records) | `branches/speaker/ecapa.py`, `branches/speaker/registry.py` |
| 4 — ASR + scam intent | **Faster-Whisper** transcription (`models/weights/whisper/`, EN/HI/TA/TE/ML/KN) + multilingual regex scam scanner (urgency, OTP/financial pressure, police/CBI impersonation) + zero-PII encrypted transcript store | `branches/asr_intent/asr.py`, `intent.py`, `scanner.py`, `transcript_store.py` |
| Fusion | Aggregation-only evidence fusion (no thresholds/rules — those live in `rules.yaml`) | `fusion/engine.py` |
| Risk engine | Deterministic AST rule evaluator over `risk_engine/rules.yaml` (13 rules: score bands, cross-signal inconsistency like high-spoof + high-match → BLOCK, fail-closed degraded-branch rules) | `risk_engine/evaluator.py`, `rules.yaml` |
| Orchestration | `PipelineService.process_call_session()` → preprocess → 3 branches → fuse → evaluate → dispatch action → audit append. Returns `RiskDecision` | `services/pipeline_service.py`, `actions/dispatcher.py` |
| MCP facade | `mcp_server/server.py` delegates to the **real** branch modules (not stubs) | `mcp_server/server.py` |
| CLI demo | `demo.py` renders every stage in terminal: VAD stats, AASIST probabilities, ECAPA match/raw-cosine, transcript under `[PRIVACY GUARD: Rendered locally in terminal only; never committed to ledger/blockchain]`, fired rules, action, decision hash + chain position + outbox status | `demo.py` |

---

## 3. Audit / blockchain layer — IMPLEMENTED (live Fabric network deferred)

- `audit/fabric_sink.py` — `FabricSink`: atomic dual write (PG `audit_ledger` hash chain + `audit_outbox` row with `anchor_pending`), advisory-lock serialized appends, idempotent retry worker (`process_outbox`), `get_chain` / `verify_chain`, PG `connect_timeout=3` so offline DB fails fast.
- `audit/local_hash_chain.py` — `PostgresHashChainSink` (exists, not the wired sink).
- `audit/sink.py` — `AuditSink` interface (`append`, `get_latest`, `get_chain`, `verify_chain`).
- Chaincode (Fabric 2.5, TypeScript): `chaincode/src/decision_ledger.ts`, `model_registry.ts`, `consent_registry.ts`.
- `fabric-bridge/src/server.ts` — Node/TS REST proxy to the Fabric Gateway SDK.
- `services/integrity_guard.py` — on-chain model/rules hash verification with TTL cache, fail-closed.
- Tamper tooling: `scripts/verify_audit.py`, `scripts/tamper_demo.py`, `scripts/secret_scan.py` (+ `tests/test_tamper_demo.py`, `tests/test_secret_scan.py`).
- **Deferred:** live Fabric network boot (see `docs/WSL2_FABRIC_SETUP.md`). Bridge genuinely reports OFFLINE; outbox rows stay `anchor_pending` until then.

---

## 4. Gateway API — IMPLEMENTED (note: `gateway/app.py`, there is no `gateway/main.py`)

Key-authed core (`X-API-Key`, `gateway/app.py`):

| Method & path | Purpose |
|---|---|
| `GET /health` | Unauthenticated health check |
| `POST /analyze` | Synchronous full-pipeline analysis → `RiskDecision` |
| `POST /jobs` | Async analysis (multipart audio upload persisted to `storage/uploads/`, or existing path) → `202 + job_id` |
| `GET /jobs/{job_id}` | Job status + decision |

Dashboard ops router, `gateway/ops_api.py` (no auth — LAN demo use):

| Method & path | Purpose |
|---|---|
| `GET /api/v1/sessions` | Recent pipeline runs as dashboard call cards |
| `POST /api/v1/sessions/analyze` → 201 | One-shot upload → pipeline → recorded session detail (dashboard's analyze call) |
| `GET /api/v1/dashboard/summary` | KPI aggregate + recent events |
| `GET /api/v1/sessions/{session_id}` | One decision's full breakdown incl. complete `evidence` dumps |
| `GET /api/v1/alerts` | HIGH/CRITICAL sessions as alerts |
| `GET /api/v1/audit` | Real PG chain rows (`record_hash`, `chain_position`, server-computed `chain_verified`) or labeled `in_memory_fallback` |
| `GET /api/v1/users` / `POST /api/v1/users` | Real enrollment list / enroll speaker from voice samples (409 if enrolled, 503 if ECAPA unavailable) |
| `GET /api/v1/policies` | Real read of `rules.yaml` (13 rules + version) |
| `GET /api/v1/system/status` | Real probes: PG `SELECT 1`, bridge `/health`, weights files, rules load, enrollment count |

Prior integration fixes already in place: upload bytes persisted (not discarded),
ops-session recording on every pipeline run, job completion mirrored to ops +
audit, `asyncio.run` deadlock fix (daemon-thread audit append), PG connect
timeouts, MCP server pointed at real branches.

---

## 5. Frontend dashboard — BUILT, VISUALLY COMPLETE, DATA NOT YET WIRED

`frontend/` (React 19 + Vite + Tailwind v4, extracted from `FigmaFrontEnd.zip`
— a real VoiceShield design export, not a template; 27 files byte-identical).
11 screens, all matching the Figma dark enterprise design:

`LoginScreen`, `DashboardScreen`, `LiveCallsScreen`, `SessionDetailScreen`,
`AlertsScreen`, `AlertDetailScreen`, `AuditTrailScreen`,
`TrustedUsersScreen`, `RegisterUserScreen`, `SecurityPoliciesScreen`,
`SystemStatusScreen` (+ `components/Layout.tsx`, `components/ui.tsx`).

**Current data state (verified): screens are 100% mock — hardcoded constants,
zero data fetching.** `frontend/src/lib/api.ts` (typed `fetch` client for all
endpoints above) exists but **no screen imports it**. Per-screen wiring audit:

- **(a) Wire as-is:** Dashboard (`/dashboard/summary`), LiveCalls (`/sessions` + `/sessions/analyze`), SessionDetail (`/sessions/{id}`, same `RiskDecision` shape as `/analyze`), Alerts (`/alerts`), AlertDetail (client-side join, no new endpoint), AuditTrail (`/audit`, server-side `chain_verified` — no frontend hashing), RegisterUser (`POST /api/v1/users` maps 1:1).
- **(b) Needs small additive backend change:** SystemStatus — `outbox_pending` is hardcoded `0` (`ops_api.py:695`, needs real outbox `COUNT(*)`) and all latencies are hardcoded placeholders; SessionDetail — VAD segment stats/SNR and per-record `anchor_status` not exposed; TrustedUsers — list is real, but presence/role-management has no backend; SecurityPolicies — read is real, toggles/Edit are mock (`enabled: True` hardcoded).
- **(c) No backend concept:** LoginScreen — auth is one shared `X-API-Key`, no accounts/roles/sessions. Biggest design-vs-backend gap; decision pending: (a) minimal single-operator auth vs (b) labeled demo/mockup sections.
- **Caveats recorded:** dashboard history is process-local (lost on gateway restart); `audit_ledger` alone cannot drive call cards (scores never go on-chain — privacy invariant); `quality %` is pseudoderived; Fabric truthfully shows OFFLINE.

---

## 6. Tests — 69 collected, last full run 68 passed / 1 skipped

`tests/`: `test_vad`, `test_aasist`, `test_ecapa`, `test_asr_intent`,
`test_fusion`, `test_risk_engine`, `test_schemas`, `test_stubs`,
`test_pipeline_e2e` (gateway: auth, `/analyze`, `/jobs` flow, upload guards),
`test_audit`, `test_fabric_sink`, `test_tamper_demo`, `test_test_vectors`,
`test_demo_cli`, `test_secret_scan` (+ `conftest.py`).

```powershell
.\run.ps1 test          # full suite
.\run.ps1 test-audit    # audit tests vs isolated PostgreSQL
.\run.ps1 lint          # compileall
```

---

## 7. Pending / decided-next (not started)

1. Wire (a)-category screens via `lib/api.ts` (approved scope, awaiting go-ahead).
2. SystemStatus honesty fixes: real `outbox_pending`/`anchored` counts, measured-or-removed latencies.
3. SessionDetail micro-gaps (proposed, unconfirmed): `GET /api/v1/sessions/{id}/audit-proof` (per-decision hash/position/`anchor_status`) and VAD summary (`vad_segments`, `speech_duration_s`, `snr_db`) in session detail.
4. Decide Login/users strategy: minimal single-operator auth vs explicitly labeled mockup sections.
5. Boot live Fabric network (`docs/WSL2_FABRIC_SETUP.md`) → bridge ONLINE, outbox drains `anchor_pending` → `anchored`.

## 8. How to run

```powershell
# Backend (unchanged)
.\run.ps1 run-gateway
# or: uv run uvicorn gateway.app:app --host 127.0.0.1 --port 8000

# Dashboard
cd frontend; npm install   # first time only
npm run dev                # http://127.0.0.1:5173 (or :8443)

# CLI demo (no servers needed)
uv run python demo.py test_vectors/audio/bonafide_sample.wav --claimed-identity unknown
```

Login accepts any credentials (demo gate). With the backend down, screens show
labeled demo data; with it up (and wiring done), they show live pipeline runs.
