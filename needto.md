# NEED TO IMPLEMENT — voice-fraud-detection

> What is left to build in this repo. Source of truth for pending work: `done.md §7`, `PROJECT_MASTER_STATUS_REPORT.md §8`.
> Backend pipeline is DONE (do not modify). Frontend is 100% mock (no screen imports `lib/api.ts` yet).

---

## 0. How to run (copy-paste cmds)

### First-time setup (Windows PowerShell, repo root `voice-fraud-detection/`)

```powershell
# 1. Backend env
Copy-Item .env.example .env
# edit .env -> set VFD_API_KEY, POSTGRES_PASSWORD, VFD_FABRIC_BRIDGE_API_KEY

# 2. Python deps (pick one)
uv sync
# or: python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
# + for full ML: pip install torch speechbrain librosa faster-whisper silero-vad
# + for DB/MCP: pip install psycopg2-binary sqlalchemy mcp

# 3. DB (optional but needed for real audit chain, else in-memory fallback)
docker-compose up -d postgres
# or: .\run.ps1 up

# 4. Frontend env
Copy-Item frontend\.env.example frontend\.env
# ensure it contains: VITE_API_BASE=http://127.0.0.1:8000
```

### Run Backend (FastAPI gateway → http://127.0.0.1:8000)

```powershell
# Terminal 1 — from repo root:
.\run.ps1 run-gateway
# equivalent:
uv run uvicorn gateway.app:app --host 127.0.0.1 --port 8000 --reload
# docs: http://127.0.0.1:8000/docs | health: http://127.0.0.1:8000/health
```

Other backend cmds:

```powershell
.\run.ps1 test          # full pytest suite (69 tests)
.\run.ps1 test-audit    # audit tests vs PostgreSQL
.\run.ps1 lint          # compileall
.\run.ps1 up            # docker-compose up -d (postgres + app)
.\run.ps1 down          # docker-compose down
.\run.ps1 build         # docker-compose build
.\run.ps1 clean         # clear __pycache__ / .pytest_cache

# CLI demo (no servers needed):
uv run python demo.py test_vectors/audio/bonafide_sample.wav --claimed-identity unknown
```

Auth: core `POST /analyze`, `POST /jobs` need header `X-API-Key: <VFD_API_KEY>`. Ops `GET /api/v1/*` is open (LAN demo).

### Run Frontend (React + Vite → http://127.0.0.1:5173 or :8443)

```powershell
# Terminal 2 — from repo root:
cd frontend; npm install   # first time only
npm run dev                # Vite dev, port = $env:PORT or 8443 fallback
# open http://127.0.0.1:8443  (or http://127.0.0.1:5173 if PORT=5173)
```

```powershell
# explicit port:
$env:PORT=5173; npm run dev
# or from root without cd:
npm --prefix frontend run dev
npm --prefix frontend run build   # prod build -> frontend/dist/
npm --prefix frontend run preview # preview prod build
```

> Frontend talks to `VITE_API_BASE` (default `http://127.0.0.1:8000`). If backend is down, screens show labeled demo data.

### Run both together (2 terminals)

```powershell
# T1 backend:
.\run.ps1 run-gateway
# T2 frontend:
cd frontend; npm run dev
```

### Run full stack via Docker

```powershell
docker-compose up -d --build
# app -> http://127.0.0.1:8000, postgres -> 127.0.0.1:5432
docker-compose logs -f app
docker-compose down
```

---

## 1. Frontend → Backend wiring (biggest gap, approved next)

`frontend/src/lib/api.ts` exists but **no screen imports it**. Wire per screen:

- [ ] `DashboardScreen` → `GET /api/v1/dashboard/summary`
- [ ] `LiveCallsScreen` → `GET /api/v1/sessions` + `POST /api/v1/sessions/analyze` (multipart upload)
- [ ] `SessionDetailScreen` → `GET /api/v1/sessions/{id}` (same `RiskDecision` shape as `/analyze`)
- [ ] `AlertsScreen` → `GET /api/v1/alerts`
- [ ] `AlertDetailScreen` → client-side join, no new endpoint needed
- [ ] `AuditTrailScreen` → `GET /api/v1/audit` (use server `chain_verified`, do NOT re-hash in frontend)
- [ ] `RegisterUserScreen` → `POST /api/v1/users` (handle 409 enrolled, 503 ECAPA-unavailable)
- [ ] Keep graceful fallback to local demo data when `fetch` fails (Figma preview sandbox has no gateway)

Files: `frontend/src/screens/*.tsx`, `frontend/src/lib/api.ts`, `gateway/ops_api.py`, `gateway/app.py:57-72` (CORS + router).

## 2. SystemStatus honesty fixes (small backend change)

- [ ] `gateway/ops_api.py:695` — `outbox_pending` hardcoded `0` → real `SELECT COUNT(*) FROM audit_outbox WHERE status='anchor_pending'` + anchored count
- [ ] Replace hardcoded latency placeholders with measured timings or remove them
- [ ] Surface real probes already present: PG `SELECT 1`, bridge `/health`, weights files, rules load, enrollment count → `GET /api/v1/system/status`
- [ ] Wire `SystemStatusScreen.tsx` to that endpoint

## 3. SessionDetail micro-gaps (proposed, unconfirmed)

- [ ] Add `GET /api/v1/sessions/{id}/audit-proof` → `{ record_hash, chain_position, anchor_status }`
- [ ] Add VAD summary to session detail: `vad_segments`, `speech_duration_s`, `snr_db` (from `preprocess/vad.py`)
- [ ] Expose per-record `anchor_status` (`anchor_pending` vs `anchored`) in session payload
- [ ] Wire `SessionDetailScreen.tsx` + `AlertDetailScreen.tsx`

## 4. Login / users strategy decision (biggest design-vs-backend gap)

Backend auth = one shared `X-API-Key`. `LoginScreen.tsx` accepts any credentials (demo gate). No accounts/roles/sessions exist.

- [ ] Decide: (a) minimal single-operator login (env `VFD_API_KEY` + session cookie) vs (b) keep login as explicitly labeled demo/mockup
- [ ] `TrustedUsersScreen` — list is real (`GET /api/v1/users`) but presence/role-management has no backend → either implement or label mock
- [ ] `SecurityPoliciesScreen` — read is real (`GET /api/v1/policies`, 13 rules + version) but toggles/Edit are mock (`enabled: True` hardcoded) → implement `PATCH /api/v1/policies` or label mock

## 5. Live Fabric network (deferred, see `docs/WSL2_FABRIC_SETUP.md`)

- [ ] Boot 2-org Fabric 2.5 network on native WSL2 filesystem (Docker env currently blocked)
- [ ] Deploy chaincode: `chaincode/src/decision_ledger.ts`, `model_registry.ts`, `consent_registry.ts`
- [ ] Start `fabric-bridge/src/server.ts` → bridge ONLINE (currently truthfully OFFLINE)
- [ ] Verify outbox drains `anchor_pending` → `anchored` via `audit/fabric_sink.py:process_outbox`
- [ ] Un-skip `test_live_fabric_bridge_integration`

## 6. Phase 4 — Real ASR + scam intent (currently 15% stub)

- [ ] Replace `branches/asr_intent/stub.py` with Faster-Whisper / Indic-Whisper (`models/weights/whisper/`, EN/HI/TA/TE/ML/KN)
- [ ] Keep multilingual regex scanner (`branches/asr_intent/scanner.py`) + add semantic intent scoring
- [ ] Keep zero-PII encrypted transcript store (`transcript_store.py`)
- [ ] Update `tests/test_asr_intent.py` vectors

## 7. Phase 5 — Calibration, latency, agents (currently ~10%)

- [ ] Calibrate fusion/rule thresholds (`risk_engine/rules.yaml`, 13 rules) on combined benchmark datasets
- [ ] Profile inference latency per branch (AASIST / ECAPA / Whisper) → sub-second target
- [ ] Finish MCP facade coverage (`mcp_server/server.py` already delegates to real branches)
- [ ] Persist dashboard history (currently process-local, lost on gateway restart — add PG table or JSONL in `storage/`)

## 8. Explicit non-goals / do-not-touch

- Detection pipeline (`preprocess/vad.py`, `branches/antispoof/aasist*.py`, `branches/speaker/ecapa.py` + `registry.py`, `fusion/engine.py`, `risk_engine/evaluator.py` + `rules.yaml`, `services/pipeline_service.py`, `actions/dispatcher.py`) — implemented & tested, do not modify without updating `tests/` + `test_vectors/decision_hash_vectors.json`.
- Privacy invariants: scores never go on-chain; PII → HMAC `subjectRef` only; embeddings Fernet-encrypted; `scripts/secret_scan.py` must stay green.

---

## Quick verify after wiring

```powershell
.\run.ps1 test
.\run.ps1 run-gateway          # T1
cd frontend; npm run dev       # T2
# Dashboard → Live Calls → Analyze upload → Session Detail → Alerts → Audit Trail → System Status
# System Status should show PG OK, bridge OFFLINE (until §5), weights present, rules vX, outbox_pending real count
```
