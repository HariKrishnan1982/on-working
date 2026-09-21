"""Shared test fixtures for the voice-fraud detection test suite."""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import hashlib
import pytest

from schemas.models import (
    BranchStatus,
    CallSession,
    ConsentRecord,
    FusedEvidence,
    IntentCategory,
    IntentResult,
    Language,
    SpeakerEnrollment,
    SpeakerResult,
    SpoofResult,
)


@pytest.fixture
def sample_session_id() -> str:
    return "sess-reproducible-12345"


@pytest.fixture
def sample_call_session(sample_session_id: str) -> CallSession:
    audio_path = "/data/audio/sample_call.wav"
    audio_hash = hashlib.sha256(audio_path.encode("utf-8")).hexdigest()
    return CallSession(
        session_id=sample_session_id,
        caller_id="+919876543210",
        claimed_identity="user_aarav_sharma",
        audio_path_encrypted=audio_path,
        audio_hash_sha256=audio_hash,
        language_hint=Language.HI,
        metadata={"region": "IN-MH", "carrier": "Jio"},
    )


@pytest.fixture
def sample_enrollment() -> SpeakerEnrollment:
    speaker_id = "user_aarav_sharma"
    consent = ConsentRecord(
        speaker_id=speaker_id,
        consent_scope="voice_biometrics_verification",
        consented_by="+919876543210",
    )
    return SpeakerEnrollment(
        speaker_id=speaker_id,
        consent=consent,
        embedding_ref="/encrypted_storage/embeddings/aarav.enc",
        embedding_hash_sha256=hashlib.sha256(b"aarav_embedding").hexdigest(),
    )


def make_fused_evidence(
    spoof_score: float = 0.10,
    similarity_score: float = 0.85,
    scam_score: float = 0.10,
    spoof_status: BranchStatus = BranchStatus.OK,
    speaker_status: BranchStatus = BranchStatus.OK,
    intent_status: BranchStatus = BranchStatus.OK,
    session_id: str = "test-session-001",
) -> FusedEvidence:
    """Helper to construct FusedEvidence with precise metric scores and branch statuses."""
    spoof = SpoofResult(
        session_id=session_id,
        status=spoof_status,
        spoof_score=spoof_score,
        is_spoofed=spoof_score >= 0.60,
        model_version="aasist-asvspoof2019-v0",
        confidence=0.95,
        processing_time_ms=10.0,
    )
    speaker = SpeakerResult(
        session_id=session_id,
        status=speaker_status,
        similarity_score=similarity_score,
        raw_cosine=(similarity_score * 2.0 - 1.0),
        is_match=similarity_score >= 0.65,
        claimed_identity="user_aarav_sharma",
        threshold_used=0.65,
        embedding_hash_sha256=hashlib.sha256(f"emb:{session_id}".encode()).hexdigest(),
        embedding_ref=f"/encrypted_storage/embeddings/{session_id}.enc",
        model_version="ecapa-tdnn-voxceleb-v0",
        processing_time_ms=12.0,
    )
    intent = IntentResult(
        session_id=session_id,
        status=intent_status,
        transcript="Standard account verification call.",
        transcript_hash_sha256=hashlib.sha256(b"Standard account verification call.").hexdigest(),
        transcript_ref=f"/encrypted_storage/transcripts/{session_id}.txt",
        language_detected=Language.HI,
        scam_score=scam_score,
        scam_indicators=["urgent_request"] if scam_score >= 0.50 else [],
        intent_category=(
            IntentCategory.SCAM_CONFIRMED if scam_score >= 0.80 else
            IntentCategory.SCAM_LIKELY if scam_score >= 0.50 else
            IntentCategory.SUSPICIOUS if scam_score >= 0.30 else
            IntentCategory.BENIGN
        ),
        model_version="whisper-largev3-rules-v0",
        processing_time_ms=15.0,
    )
    return FusedEvidence(
        session_id=session_id,
        spoof_result=spoof,
        speaker_result=speaker,
        intent_result=intent,
    )
