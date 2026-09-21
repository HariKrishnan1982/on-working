"""
Unit tests for branch stubs and hashlib.sha256 deterministic seeding.
Verifies that multiple runs with identical input yield bit-identical outputs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from branches.antispoof.stub import analyze_spoof
from branches.asr_intent.stub import analyze_intent
from branches.speaker.stub import verify_speaker
from preprocess.stub import preprocess_audio
from schemas.models import BranchStatus, normalize_ecapa_cosine


def test_preprocess_stub_deterministic_seeding():
    """Verify that preprocess_audio produces identical outputs on repeated calls."""
    session_id = "test-session-deterministic-1"
    run1 = preprocess_audio(session_id)
    run2 = preprocess_audio(session_id)

    assert run1.duration_s == run2.duration_s
    assert run1.speech_duration_s == run2.speech_duration_s
    assert run1.snr_db == run2.snr_db
    assert len(run1.vad_segments) == len(run2.vad_segments)
    assert run1.vad_segments[0].start_s == run2.vad_segments[0].start_s
    assert run1.vad_segments[0].end_s == run2.vad_segments[0].end_s


def test_antispoof_stub_deterministic_seeding():
    """Verify analyze_spoof generates identical scores and decisions across runs."""
    session_id = "test-session-deterministic-2"
    run1 = analyze_spoof(session_id)
    run2 = analyze_spoof(session_id)

    assert run1.spoof_score == run2.spoof_score
    assert run1.is_spoofed == run2.is_spoofed
    assert run1.model_version == "aasist-asvspoof2019-v0"
    assert run1.status == BranchStatus.OK


def test_speaker_stub_deterministic_seeding():
    """Verify verify_speaker generates identical normalized scores and embeddings across runs."""
    session_id = "test-session-deterministic-3"
    run1 = verify_speaker(session_id, claimed_identity="user_test")
    run2 = verify_speaker(session_id, claimed_identity="user_test")

    assert run1.similarity_score == run2.similarity_score
    assert run1.raw_cosine == run2.raw_cosine
    assert run1.is_match == run2.is_match
    assert run1.embedding_hash_sha256 == run2.embedding_hash_sha256


def test_asr_intent_stub_deterministic_seeding():
    """Verify analyze_intent generates identical transcript hash and scam score across runs."""
    session_id = "test-session-deterministic-4"
    run1 = analyze_intent(session_id)
    run2 = analyze_intent(session_id)

    assert run1.scam_score == run2.scam_score
    assert run1.transcript == run2.transcript
    assert run1.transcript_hash_sha256 == run2.transcript_hash_sha256
    assert run1.intent_category == run2.intent_category


def test_ecapa_cosine_normalization_bounds():
    """Verify ECAPA cosine normalization bounds and values."""
    # -1.0 raw cosine maps to 0.0
    assert normalize_ecapa_cosine(-1.0) == 0.0
    # +1.0 raw cosine maps to 1.0
    assert normalize_ecapa_cosine(1.0) == 1.0
    # 0.0 raw cosine maps to 0.5
    assert normalize_ecapa_cosine(0.0) == 0.5
    # Beyond bounds clamped properly
    assert normalize_ecapa_cosine(-2.5) == 0.0
    assert normalize_ecapa_cosine(3.2) == 1.0
