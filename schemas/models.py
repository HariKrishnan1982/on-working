"""
Voice-Fraud Detection System — Pydantic Data Contracts

Every component in the pipeline communicates exclusively through these models.
All fields use strict validation; scores are clamped to [0.0, 1.0].
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ─── Enums ────────────────────────────────────────────────────────────────────


class RiskLevel(str, Enum):
    """Ordered risk severity. Used by the risk engine to classify a call."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionType(str, Enum):
    """Action the system takes in response to a risk decision."""
    ALLOW = "ALLOW"
    FLAG = "FLAG"
    ESCALATE = "ESCALATE"
    BLOCK = "BLOCK"


class IntentCategory(str, Enum):
    """Classification of conversational intent."""
    BENIGN = "BENIGN"
    SUSPICIOUS = "SUSPICIOUS"
    SCAM_LIKELY = "SCAM_LIKELY"
    SCAM_CONFIRMED = "SCAM_CONFIRMED"


class Language(str, Enum):
    """Supported languages for ASR and intent analysis."""
    EN = "EN"
    HI = "HI"  # Hindi
    TA = "TA"  # Tamil
    TE = "TE"  # Telugu
    ML = "ML"  # Malayalam
    KN = "KN"  # Kannada


class BranchStatus(str, Enum):
    """Execution status for each analysis branch. Enables fail-closed behavior."""
    OK = "ok"
    FAILED = "failed"
    INSUFFICIENT_AUDIO = "insufficient_audio"
    NOT_ENROLLED = "not_enrolled"


class JobStatus(str, Enum):
    """Status of an asynchronous analysis job."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


def canonical_json_bytes(data: Any) -> bytes:
    """Produce deterministic canonical JSON bytes with sorted keys and no unnecessary whitespace."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def normalize_ecapa_cosine(raw_cosine: float) -> float:
    """
    Normalize ECAPA-TDNN raw cosine similarity into the contract range [0.0, 1.0].
    Raw cosine is bounded in [-1.0, 1.0].
    Formula: (clamped_cosine + 1.0) / 2.0.
    1.0 = perfect speaker match; 0.0 = polar opposite voice vector.
    """
    clamped = max(-1.0, min(1.0, float(raw_cosine)))
    return (clamped + 1.0) / 2.0


# ─── Enrollment Contracts ─────────────────────────────────────────────────────


class ConsentRecord(BaseModel):
    """Record of explicit user consent for voice biometric enrollment."""
    consent_id: str = Field(default_factory=new_uuid, description="Unique consent tracking ID")
    speaker_id: str = Field(..., description="Identity of the consenting individual")
    consent_timestamp: datetime = Field(default_factory=utcnow, description="When consent was granted")
    consent_scope: str = Field(
        "voice_biometrics_verification",
        description="Scope of consent (e.g. authentication, fraud prevention)",
    )
    consented_by: str = Field(..., description="User ID or verified phone number of authorizer")


class SpeakerEnrollment(BaseModel):
    """Enrolled speaker profile with biometric reference pointer and consent audit."""
    speaker_id: str = Field(..., description="Unique speaker identifier")
    consent: ConsentRecord = Field(..., description="Verified consent record")
    embedding_ref: str = Field(..., description="Encrypted storage URI for speaker embedding")
    embedding_hash_sha256: str = Field(..., description="SHA-256 hash of enrolled embedding tensor")
    created_at: datetime = Field(default_factory=utcnow)


# ─── Core Models ──────────────────────────────────────────────────────────────


class CallSession(BaseModel):
    """
    Represents an incoming call session.

    Created by the gateway when a call arrives. Carries metadata needed
    by every downstream branch (caller ID, claimed identity, language hint,
    and a SHA-256 hash of the encrypted audio for audit purposes).
    """
    session_id: str = Field(default_factory=new_uuid, description="Unique session identifier")
    caller_id: str = Field(..., description="Phone number or SIP URI of the caller")
    claimed_identity: Optional[str] = Field(
        None,
        description="The identity the caller claims to be (for speaker verification)",
    )
    audio_path_encrypted: str = Field(..., description="Path to the encrypted audio file")
    audio_hash_sha256: str = Field(..., description="SHA-256 hash of the raw audio bytes")
    language_hint: Language = Field(
        Language.EN,
        description="Expected language; used to guide ASR",
    )
    timestamp: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata (carrier info, region, etc.)",
    )

    @field_validator("audio_hash_sha256")
    @classmethod
    def _validate_sha256(cls, v: str) -> str:
        if len(v) != 64 or not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError("audio_hash_sha256 must be a 64-character hex string")
        return v.lower()


class VADSegment(BaseModel):
    """A single voice-activity segment detected by VAD."""
    start_s: float = Field(..., ge=0.0, description="Segment start time in seconds")
    end_s: float = Field(..., ge=0.0, description="Segment end time in seconds")
    confidence: float = Field(..., ge=0.0, le=1.0, description="VAD confidence")

    @model_validator(mode="after")
    def _end_after_start(self) -> "VADSegment":
        if self.end_s <= self.start_s:
            raise ValueError(f"end_s ({self.end_s}) must be > start_s ({self.start_s})")
        return self


class PreprocessedAudio(BaseModel):
    """
    Output of the preprocessing pipeline.

    Consumed by all three analysis branches. Contains VAD segments,
    signal quality metrics, and a pointer to extracted features.
    """
    session_id: str = Field(..., description="Links back to the CallSession")
    sample_rate: int = Field(16000, description="Target sample rate in Hz")
    duration_s: float = Field(..., gt=0.0, description="Total audio duration in seconds")
    speech_duration_s: float = Field(..., ge=0.0, description="Duration of voiced speech segments")
    vad_segments: list[VADSegment] = Field(
        default_factory=list,
        description="Detected voice-activity segments",
    )
    snr_db: Optional[float] = Field(None, description="Estimated signal-to-noise ratio in dB")
    features_path: Optional[str] = Field(
        None,
        description="Path to extracted feature file (e.g. raw wav tensor, spectrogram)",
    )
    is_valid: bool = Field(True, description="False if audio is too short, silent, or corrupt")


class SpoofResult(BaseModel):
    """
    Output of the anti-spoofing branch (AASIST / ASVspoof 5).

    spoof_score ∈ [0.0, 1.0]:
        - Direction: Higher = MORE likely spoofed / synthetic.
        - 0.0 = completely bonafide human speech.
        - 1.0 = confirmed synthetic, replay, or voice clone attack.
    """
    session_id: str
    status: BranchStatus = Field(BranchStatus.OK, description="Branch execution status")
    spoof_score: float = Field(..., ge=0.0, le=1.0, description="0=bonafide, 1=spoofed")
    is_spoofed: bool = Field(..., description="True if spoof_score >= threshold")
    model_version: str = Field("aasist-asvspoof2019-v0", description="Model identifier for audit")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence in score")
    processing_time_ms: float = Field(..., ge=0.0, description="Inference time in milliseconds")
    error_message: Optional[str] = Field(None, description="Details if status is not OK")


class SpeakerResult(BaseModel):
    """
    Output of the speaker verification branch (ECAPA-TDNN via SpeechBrain).

    similarity_score ∈ [0.0, 1.0]:
        - Direction: Higher = BETTER match to claimed identity.
        - Normalized from ECAPA raw cosine similarity [-1.0, 1.0] via:
          normalized = max(0.0, min(1.0, (raw_cosine + 1.0) / 2.0))
        - 1.0 = exact biometric match.
        - 0.0 = completely dissimilar voice vector.
    """
    session_id: str
    status: BranchStatus = Field(BranchStatus.OK, description="Branch execution status")
    similarity_score: float = Field(..., ge=0.0, le=1.0, description="Normalized similarity [0, 1]")
    raw_cosine: Optional[float] = Field(None, ge=-1.0, le=1.0, description="Original ECAPA cosine")
    is_match: bool = Field(..., description="True if similarity_score >= threshold")
    claimed_identity: Optional[str] = Field(None, description="Who the caller claims to be")
    threshold_used: float = Field(..., ge=0.0, le=1.0, description="Decision threshold applied")
    embedding_hash_sha256: Optional[str] = Field(None, description="Hash of extracted test embedding")
    embedding_ref: Optional[str] = Field(None, description="Storage pointer to encrypted embedding")
    model_version: str = Field("ecapa-tdnn-voxceleb-v0", description="Model identifier for audit")
    processing_time_ms: float = Field(..., ge=0.0, description="Inference time in milliseconds")
    error_message: Optional[str] = Field(None, description="Details if status is not OK")


class IntentResult(BaseModel):
    """
    Output of the ASR + scam-intent analysis branch.

    scam_score ∈ [0.0, 1.0]:
        - Direction: Higher = GREATER likelihood of scam or fraudulent intent.
        - 0.0 = completely benign conversation.
        - 1.0 = confirmed fraudulent coercion, impersonation, or credential theft.
    """
    session_id: str
    status: BranchStatus = Field(BranchStatus.OK, description="Branch execution status")
    transcript: str = Field(..., description="Full transcription of the audio")
    transcript_hash_sha256: str = Field(..., description="SHA-256 hash of full transcript")
    transcript_ref: Optional[str] = Field(None, description="Storage pointer to off-chain encrypted transcript")
    language_detected: Language = Field(..., description="Detected or confirmed language")
    scam_score: float = Field(..., ge=0.0, le=1.0, description="0=benign, 1=scam")
    scam_indicators: list[str] = Field(
        default_factory=list,
        description="Phrases or patterns flagged as scam-related",
    )
    intent_category: IntentCategory = Field(
        IntentCategory.BENIGN,
        description="Classified intent category",
    )
    model_version: str = Field("whisper-largev3-rules-v0", description="ASR + intent model identifier")
    processing_time_ms: float = Field(..., ge=0.0, description="Total processing time in ms")
    error_message: Optional[str] = Field(None, description="Details if status is not OK")


class FusedEvidence(BaseModel):
    """
    Merged evidence assembled from all three analysis branches.

    The fusion layer acts strictly as an evidence aggregator. It does NOT
    contain hardcoded rule or inconsistency logic. All evaluation is performed
    deterministically by the Risk Engine based on rules.yaml.
    """
    session_id: str
    spoof_result: SpoofResult
    speaker_result: SpeakerResult
    intent_result: IntentResult
    timestamp: datetime = Field(default_factory=utcnow)


class FiredRule(BaseModel):
    """Record of a single rule that fired in the risk engine."""
    rule_id: str = Field(..., description="Unique rule identifier from rules.yaml")
    description: str = Field(..., description="What this rule checks")
    risk_level: RiskLevel
    action: ActionType
    condition_summary: str = Field(
        ...,
        description="Human-readable summary of the condition that triggered this rule",
    )


class RiskDecision(BaseModel):
    """
    Final explainable decision from the deterministic risk engine.

    Lists every rule that fired, the resulting risk level (highest wins),
    the action taken (most restrictive wins), rules version hash, and model versions.
    """
    session_id: str
    risk_level: RiskLevel
    action: ActionType
    fired_rules: list[FiredRule] = Field(
        default_factory=list,
        description="All rules that matched; empty only when strictly low-risk and all branches OK",
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Human-readable explanation of the decision",
    )
    rules_version: str = Field(..., description="SHA-256 hash or version tag of rules.yaml used")
    model_versions: dict[str, str] = Field(
        ...,
        description="Map of branch name to model version used during analysis",
    )
    fused_evidence: FusedEvidence
    timestamp: datetime = Field(default_factory=utcnow)


class AuditRecord(BaseModel):
    """
    Immutable audit trail entry.

    Forms an append-only hash chain: each record's hash includes the
    previous record's hash, making tampering detectable.

    Strict privacy requirement: Raw transcripts and high-dimensional voice embeddings
    are kept out of the audit record. Only cryptographic hashes and storage references
    are included.
    """
    record_id: str = Field(default_factory=new_uuid)
    session_id: str
    risk_level: RiskLevel
    action: ActionType
    fired_rule_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    rules_version: str
    model_versions: dict[str, str]
    
    # Cryptographic pointers (no raw audio/transcript/embedding data on chain)
    audio_hash_sha256: str
    transcript_hash_sha256: Optional[str] = None
    transcript_ref: Optional[str] = None
    embedding_hash_sha256: Optional[str] = None
    embedding_ref: Optional[str] = None

    # Chain metadata
    previous_hash: str = Field(
        ...,
        description="SHA-256 hash of preceding AuditRecord (genesis = '0' * 64)",
    )
    record_hash: str = Field("", description="SHA-256 hash of this record's canonical JSON")
    chain_position: int = Field(..., ge=0, description="Monotonically increasing position")
    timestamp: datetime = Field(default_factory=utcnow)
    operator_notes: Optional[str] = Field(None, description="Optional human annotations")

    def canonical_payload_dict(self) -> dict[str, Any]:
        """Produce dictionary of audit payload excluding record_hash for hashing."""
        return {
            "record_id": self.record_id,
            "session_id": self.session_id,
            "chain_position": self.chain_position,
            "previous_hash": self.previous_hash,
            "risk_level": self.risk_level.value,
            "action": self.action.value,
            "fired_rule_ids": sorted(self.fired_rule_ids),
            "reasons": self.reasons,
            "rules_version": self.rules_version,
            "model_versions": dict(sorted(self.model_versions.items())),
            "audio_hash_sha256": self.audio_hash_sha256,
            "transcript_hash_sha256": self.transcript_hash_sha256,
            "transcript_ref": self.transcript_ref,
            "embedding_hash_sha256": self.embedding_hash_sha256,
            "embedding_ref": self.embedding_ref,
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "operator_notes": self.operator_notes,
        }

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of the canonical JSON representation."""
        payload_bytes = canonical_json_bytes(self.canonical_payload_dict())
        return hashlib.sha256(payload_bytes).hexdigest()

    @model_validator(mode="after")
    def _set_hash(self) -> "AuditRecord":
        if not self.record_hash:
            self.record_hash = self.compute_hash()
        return self
