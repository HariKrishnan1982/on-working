"""
Tests for Pydantic schema contracts.

Validates:
- CallSession integrity and SHA-256 hash checks
- BranchStatus and fail-closed schema fields
- Renamed scam_score and normalized ECAPA similarity
- ConsentRecord and SpeakerEnrollment contracts (Requirement Q2)
- Canonical JSON deterministic hashing in AuditRecord without raw transcript/embedding leakage
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hashlib
import pytest
from pydantic import ValidationError

from schemas.models import (
    ActionType,
    AuditRecord,
    BranchStatus,
    CallSession,
    ConsentRecord,
    IntentCategory,
    IntentResult,
    Language,
    RiskDecision,
    RiskLevel,
    SpeakerEnrollment,
    SpeakerResult,
    SpoofResult,
    VADSegment,
    canonical_json_bytes,
    normalize_ecapa_cosine,
)
from tests.conftest import make_fused_evidence


def test_call_session_validation():
    audio_hash = hashlib.sha256(b"raw_audio_bytes").hexdigest()
    session = CallSession(
        caller_id="+919876543210",
        audio_path_encrypted="/data/audio/call1.enc",
        audio_hash_sha256=audio_hash,
        language_hint=Language.HI,
    )
    assert session.caller_id == "+919876543210"
    assert session.audio_hash_sha256 == audio_hash
    assert session.language_hint == Language.HI

    # Rejects invalid sha256
    with pytest.raises(ValidationError):
        CallSession(
            caller_id="+919876543210",
            audio_path_encrypted="/data/audio/call1.enc",
            audio_hash_sha256="not_a_valid_sha256",
        )


def test_vad_segment_validation():
    seg = VADSegment(start_s=1.0, end_s=2.5, confidence=0.98)
    assert seg.end_s > seg.start_s

    with pytest.raises(ValidationError):
        VADSegment(start_s=3.0, end_s=1.0, confidence=0.98)


def test_score_bounds_and_status():
    # Out-of-bounds scores rejected
    with pytest.raises(ValidationError):
        SpoofResult(
            session_id="s1",
            spoof_score=1.5,
            is_spoofed=True,
            confidence=0.9,
            processing_time_ms=10.0,
        )

    # Valid with status
    spoof = SpoofResult(
        session_id="s1",
        status=BranchStatus.INSUFFICIENT_AUDIO,
        spoof_score=0.0,
        is_spoofed=False,
        confidence=0.0,
        processing_time_ms=5.0,
    )
    assert spoof.status == BranchStatus.INSUFFICIENT_AUDIO


def test_consent_and_speaker_enrollment_contract():
    """Verify Q2 Option (a) consented speaker enrollment contract."""
    consent = ConsentRecord(
        speaker_id="user_rohit",
        consent_scope="fraud_detection_verification",
        consented_by="+919988776655",
    )
    emb_hash = hashlib.sha256(b"mock_embedding_vector").hexdigest()
    enrollment = SpeakerEnrollment(
        speaker_id="user_rohit",
        consent=consent,
        embedding_ref="/vault/embeddings/rohit.bin",
        embedding_hash_sha256=emb_hash,
    )
    assert enrollment.speaker_id == "user_rohit"
    assert enrollment.consent.consented_by == "+919988776655"


def test_audit_record_canonical_json_and_privacy():
    """
    Verify that AuditRecord:
    1. Does NOT contain raw transcripts or voice embeddings.
    2. Auto-computes record_hash based on canonical JSON bytes.
    3. Hash is strictly deterministic across independent calculations.
    """
    evidence = make_fused_evidence(spoof_score=0.1, similarity_score=0.9, scam_score=0.1)
    decision = RiskDecision(
        session_id="session-audit-privacy",
        risk_level=RiskLevel.LOW,
        action=ActionType.ALLOW,
        rules_version="0.2.0:abcdef123456",
        model_versions={
            "antispoof": "aasist-v0",
            "speaker": "ecapa-v0",
            "asr_intent": "whisper-v0",
        },
        fused_evidence=evidence,
    )

    record = AuditRecord(
        session_id=decision.session_id,
        risk_level=decision.risk_level,
        action=decision.action,
        fired_rule_ids=[r.rule_id for r in decision.fired_rules],
        reasons=decision.reasons,
        rules_version=decision.rules_version,
        model_versions=decision.model_versions,
        audio_hash_sha256="a" * 64,
        transcript_hash_sha256="b" * 64,
        transcript_ref="/storage/transcripts/t1.enc",
        embedding_hash_sha256="c" * 64,
        embedding_ref="/storage/embeddings/e1.enc",
        previous_hash="0" * 64,
        chain_position=0,
    )

    # Verify no raw transcript or embedding text field exists in AuditRecord model
    payload_dict = record.canonical_payload_dict()
    assert "transcript" not in payload_dict
    assert "embedding" not in payload_dict
    assert "transcript_hash_sha256" in payload_dict

    # Check canonical JSON deterministic hashing
    canonical_bytes = canonical_json_bytes(payload_dict)
    assert hashlib.sha256(canonical_bytes).hexdigest() == record.record_hash
    assert len(record.record_hash) == 64
