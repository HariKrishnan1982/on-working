/**
 * VoiceShield backend API client.
 *
 * Talks to the FastAPI gateway (default http://127.0.0.1:8000).
 * Override with a `.env` file containing VITE_API_BASE=<gateway-url>.
 *
 * Every screen uses these helpers with graceful fallback to local demo
 * data when the gateway is unreachable (e.g. Figma preview sandbox).
 */

const RAW_BASE = (import.meta as unknown as { env?: Record<string, string | undefined> }).env
  ?.VITE_API_BASE;

export const API_BASE = (RAW_BASE && RAW_BASE.trim()) || 'http://127.0.0.1:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status} ${path}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

// ─── Types (mirror gateway/ops_api.py serializers) ───────────────────────────

export interface SessionCall {
  id: string;
  caller: string;
  claimed_identity: string | null;
  duration: string;
  risk: number;
  identity: number;
  deepfake: number;
  context: number;
  behavior: number;
  action: string;
  status: string;
  risk_level: string;
  recorded_at: string;
}

export interface SessionsResponse {
  total: number;
  sessions: SessionCall[];
}

export interface FiredRule {
  rule_id: string;
  description: string;
  risk_level: string;
  action: string;
  condition_summary: string;
}

/** Full branch payloads returned inside SessionDetail.evidence (mirror schemas/models.py). */
export interface SpoofEvidence {
  session_id: string;
  status: string;
  spoof_score: number;
  is_spoofed: boolean;
  model_version: string;
  confidence: number;
  processing_time_ms: number;
  error_message: string | null;
}

export interface SpeakerEvidence {
  session_id: string;
  status: string;
  similarity_score: number;
  raw_cosine: number | null;
  is_match: boolean;
  claimed_identity: string | null;
  threshold_used: number;
  embedding_hash_sha256: string | null;
  embedding_ref: string | null;
  model_version: string;
  processing_time_ms: number;
  error_message: string | null;
}

export interface IntentEvidence {
  session_id: string;
  status: string;
  transcript: string;
  transcript_hash_sha256: string;
  transcript_ref: string | null;
  language_detected: string;
  scam_score: number;
  scam_indicators: string[];
  intent_category: string;
  model_version: string;
  processing_time_ms: number;
  error_message: string | null;
}

export interface SessionEvidence {
  spoof: SpoofEvidence;
  speaker: SpeakerEvidence;
  intent: IntentEvidence;
}

/** Phase-1 VAD readout captured at analysis time (mirrors demo.py stage 2). */
export interface VadSummary {
  is_valid: boolean;
  segment_count: number;
  speech_duration_s: number;
  total_duration_s: number;
  snr_db: number | null;
  sample_rate: number;
}

export interface SessionDetail {
  id: string;
  caller_id: string;
  claimed_identity: string | null;
  risk_score: number;
  risk_level: string;
  action: string;
  action_badge: string;
  status: string;
  duration_s: number | null;
  sample_rate: number | null;
  channels: number | null;
  vad: VadSummary | null;
  recorded_at: string;
  rules_version: string;
  model_versions: Record<string, string>;
  fired_rules: FiredRule[];
  reasons: string[];
  detection_summary: string;
  evidence: SessionEvidence;
  decision_hash: string;
}

export interface AlertItem {
  id: string;
  session: string;
  title: string;
  risk: number;
  action: string;
  severity: string;
  time: string;
  resolved: boolean;
}

export interface AlertsResponse {
  total: number;
  alerts: AlertItem[];
}

export interface AuditItem {
  id: string;
  time: string;
  session: string;
  event: string;
  risk: number;
  action: string;
  hash: string;
  verified: boolean;
  chain_position: number | null;
}

export interface AuditResponse {
  source: string;
  chain_verified: boolean;
  records: AuditItem[];
}

export interface UserProfile {
  id: string;
  name: string;
  role: string;
  dept: string;
  profile: string;
  status: string;
  quality: number;
  enrolled: string;
  emp_id: string;
}

export interface UsersResponse {
  total: number;
  enrolled: number;
  suspended: number;
  avg_quality: number;
  users: UserProfile[];
}

export interface PolicyItem {
  id: string;
  name: string;
  severity: string;
  enabled: boolean;
  conditions: { field: string; op: string; value: string }[];
  actions: string[];
  risk_level: string;
  action: string;
}

export interface PoliciesResponse {
  total: number;
  version: string;
  policies: PolicyItem[];
}

export interface ServiceStatus {
  name: string;
  status: string;
  latency: number;
  version: string;
  uptime: string;
}

export interface SystemStatusResponse {
  backend: {
    status: string;
    timestamp: string;
    version: string;
    database: string;
    fabric_bridge: string;
    outbox_pending: number | null;
    outbox_anchored: number | null;
    response_time_ms: number;
  };
  services: ServiceStatus[];
  apiMetrics: { endpoint: string; method: string; status: number }[];
  stack: { name: string; version: string }[];
}

export interface DashboardSummary {
  total_sessions: number;
  active_calls: number;
  threats_detected: number;
  calls_blocked: number;
  recent_events: {
    time: string;
    caller: string;
    risk: number;
    detection: string;
    action: string;
    session_id: string;
  }[];
}

export interface HealthResponse {
  status: string;
  service: string;
}

// ─── Endpoints ───────────────────────────────────────────────────────────────

export function checkHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export function listSessions(limit = 200): Promise<SessionsResponse> {
  return request<SessionsResponse>(`/api/v1/sessions?limit=${limit}`);
}

export function getSession(sessionId: string): Promise<SessionDetail> {
  return request<SessionDetail>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
}

export function listAlerts(): Promise<AlertsResponse> {
  return request<AlertsResponse>('/api/v1/alerts');
}

export function getAudit(): Promise<AuditResponse> {
  return request<AuditResponse>('/api/v1/audit');
}

/** Per-decision audit-chain proof (GET /api/v1/sessions/{id}/audit-proof). */
export interface DecisionAuditProof {
  session_id: string;
  found: boolean;
  source: string;
  record_id: string | null;
  record_hash: string | null;
  chain_position: number | null;
  anchor_status: string | null;
  outbox_status: string | null;
  chain_verified: boolean;
  decision_hash: string;
  note?: string;
}

export function getDecisionAuditProof(sessionId: string): Promise<DecisionAuditProof> {
  return request<DecisionAuditProof>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/audit-proof`);
}

export function listUsers(): Promise<UsersResponse> {
  return request<UsersResponse>('/api/v1/users');
}

export function listPolicies(): Promise<PoliciesResponse> {
  return request<PoliciesResponse>('/api/v1/policies');
}

export function getSystemStatus(): Promise<SystemStatusResponse> {
  return request<SystemStatusResponse>('/api/v1/system/status');
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>('/api/v1/dashboard/summary');
}

/** One-shot upload → deterministic pipeline → recorded session detail. */
export function analyzeUpload(params: {
  callerId: string;
  claimedIdentity?: string;
  languageHint?: string;
  file: File;
}): Promise<SessionDetail> {
  const form = new FormData();
  form.append('caller_id', params.callerId);
  if (params.claimedIdentity) form.append('claimed_identity', params.claimedIdentity);
  form.append('language_hint', params.languageHint || 'EN');
  form.append('audio_file', params.file, params.file.name);
  return request<SessionDetail>('/api/v1/sessions/analyze', {
    method: 'POST',
    body: form,
  });
}

export interface EnrollResult {
  id: string;
  name: string;
  profile: string;
  role: string;
  dept: string;
  quality: number;
  status: string;
  enrolled: string;
  emp_id: string;
  subject_ref_last8: string;
  voice_samples: number;
  embedding_ref: string | null;
}

/** Enroll a speaker: multipart name/emp_id/role/dept + 1..3 audio samples. */
export function enrollUser(params: {
  name: string;
  empId: string;
  email?: string;
  role?: string;
  dept?: string;
  samples: File[];
}): Promise<EnrollResult> {
  const form = new FormData();
  form.append('name', params.name);
  form.append('emp_id', params.empId);
  form.append('email', params.email || '');
  form.append('role', params.role || '');
  form.append('dept', params.dept || '');
  for (const f of params.samples) form.append('samples', f, f.name);
  return request<EnrollResult>('/api/v1/users', { method: 'POST', body: form });
}
