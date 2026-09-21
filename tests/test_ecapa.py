"""
Phase 3 Unit Tests: ECAPA-TDNN Speaker Verification Branch.

Tests:
1. Pinned Directional Test: same speaker (p274 vs p274) vs different bona-fide speaker (p274 vs spk01).
   Asserts sim(same) > sim(diff) and margin >= 0.20 using genuine human recordings.
2. Privacy & Encryption: verifies HMAC-SHA256 pseudonyms on disk and Fernet tensor encryption.
3. Not-Enrolled: unregistered caller produces BranchStatus.NOT_ENROLLED (triggers FLAG).
4. Fail-Closed: model failure produces BranchStatus.FAILED (triggers ESCALATE).
5. Insufficient Audio: VAD invalid audio propagates BranchStatus.INSUFFICIENT_AUDIO.
6. Deterministic Mock Fallback: mock sessions preserve SHA-256 reproducibility.
7. Pipeline E2E Integration: verifies full pipeline decisioning with real voice biometrics.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
import soundfile as sf
import torch
import torch.nn.functional as F

from branches.speaker.ecapa import (
    DEFAULT_THRESHOLD,
    MODEL_VERSION,
    compute_similarity,
    extract_embedding,
    get_ecapa_classifier,
    verify_speaker,
)
from branches.speaker.registry import SpeakerEnrollmentStore
from risk_engine.evaluator import RiskEvaluator
from schemas.models import (
    ActionType,
    BranchStatus,
    CallSession,
    ConsentRecord,
    Language,
    PreprocessedAudio,
    RiskLevel,
    normalize_ecapa_cosine,
)
from services.pipeline_service import PipelineService


@pytest.fixture
def bonafide_path() -> str:
    path = Path("test_vectors/audio/bonafide_sample.wav")
    assert path.is_file(), "Reference bonafide audio sample (p274) must exist"
    return str(path)


@pytest.fixture
def diff_speaker_path() -> str:
    path = Path("test_vectors/audio/different_speaker_bonafide.wav")
    assert path.is_file(), "Different bona-fide speaker sample (spk01) must exist"
    return str(path)


@pytest.fixture
def split_bonafide_samples(bonafide_path, tmp_path):
    """Split 5.12s bonafide sample into two non-overlapping audio files for same-speaker verification."""
    data, sr = sf.read(bonafide_path, dtype="float32")
    half = len(data) // 2
    enroll_audio = data[:half]
    test_audio = data[half:]

    enroll_path = tmp_path / "p274_enroll.wav"
    test_path = tmp_path / "p274_test.wav"
    sf.write(str(enroll_path), enroll_audio, sr)
    sf.write(str(test_path), test_audio, sr)

    return str(enroll_path), str(test_path)


@pytest.fixture
def isolated_enrollment_store(tmp_path):
    """Create isolated enrollment store in temp directory."""
    store = SpeakerEnrollmentStore(storage_dir=tmp_path / "enrollments")
    return store


def test_ecapa_directional_same_vs_different_speaker(
    bonafide_path, diff_speaker_path, split_bonafide_samples, isolated_enrollment_store
):
    """
    PINNED DIRECTIONAL TEST (Genuine Human Voice Verification):
    
    Compares:
    - Same Speaker Pair: speaker p274 enroll utterance vs p274 test utterance.
    - Different Speaker Pair: speaker p274 enroll utterance vs spk01 genuine recording.
    
    Explicitly asserts:
    1. sim(same) > sim(diff)
    2. sim(same) - sim(diff) >= 0.20 (directional separation margin)
    3. is_match is True for same speaker, False for different speaker
    4. normalized score >= 0.65 for same speaker, < 0.65 for different speaker
    """
    enroll_path, test_path = split_bonafide_samples
    classifier = get_ecapa_classifier()

    # 1. Extract embeddings directly
    emb_enroll = extract_embedding(enroll_path, classifier=classifier)
    emb_test_same = extract_embedding(test_path, classifier=classifier)
    emb_diff = extract_embedding(diff_speaker_path, classifier=classifier)

    assert emb_enroll.shape == torch.Size([192])
    assert emb_test_same.shape == torch.Size([192])
    assert emb_diff.shape == torch.Size([192])

    raw_cos_same, norm_same = compute_similarity(emb_test_same, emb_enroll)
    raw_cos_diff, norm_diff = compute_similarity(emb_diff, emb_enroll)

    # Directional assertion on raw cosine
    assert raw_cos_same > raw_cos_diff, (
        f"Directional failure: same-speaker cosine ({raw_cos_same:.4f}) must exceed "
        f"diff-speaker cosine ({raw_cos_diff:.4f})"
    )
    assert (raw_cos_same - raw_cos_diff) >= 0.20, (
        f"Margin failure: difference ({raw_cos_same - raw_cos_diff:.4f}) must be >= 0.20"
    )

    # 2. Branch-level verify_speaker with enrollment store
    consent = ConsentRecord(
        speaker_id="speaker_p274",
        consented_by="+919876543210",
        consent_scope="voice_biometrics_verification",
    )
    isolated_enrollment_store.enroll_speaker("speaker_p274", emb_enroll, consent)

    # Same speaker verification call
    res_same = verify_speaker(
        session_id="sess-same-spk-001",
        claimed_identity="speaker_p274",
        audio_path=test_path,
        enrollment_store=isolated_enrollment_store,
    )
    assert res_same.status == BranchStatus.OK
    assert res_same.is_match is True
    assert res_same.similarity_score >= DEFAULT_THRESHOLD
    assert res_same.model_version == MODEL_VERSION
    assert res_same.embedding_hash_sha256 is not None
    assert res_same.embedding_ref is not None

    # Different speaker verification call (imposter claiming to be speaker_p274)
    res_diff = verify_speaker(
        session_id="sess-diff-spk-002",
        claimed_identity="speaker_p274",
        audio_path=diff_speaker_path,
        enrollment_store=isolated_enrollment_store,
    )
    assert res_diff.status == BranchStatus.OK
    assert res_diff.is_match is False
    assert res_diff.similarity_score < DEFAULT_THRESHOLD
    assert res_diff.model_version == MODEL_VERSION

    # Directional branch score assertion
    assert res_same.similarity_score > res_diff.similarity_score
    assert (res_same.similarity_score - res_diff.similarity_score) >= 0.10


def test_ecapa_privacy_preservation_and_encryption(split_bonafide_samples, isolated_enrollment_store):
    """
    Verify privacy guarantees of the enrollment store:
    1. On-disk files are named by 64-char HMAC-SHA256 pseudonym, never raw speaker_id.
    2. Biometric voiceprint embedding on disk is Fernet-encrypted, not raw PyTorch bytes.
    """
    enroll_path, _ = split_bonafide_samples
    emb = extract_embedding(enroll_path)

    raw_speaker_id = "user_aarav_sharma_9876543210"
    consent = ConsentRecord(
        speaker_id=raw_speaker_id,
        consented_by="+919876543210",
    )
    enrollment = isolated_enrollment_store.enroll_speaker(raw_speaker_id, emb, consent)

    subject_ref = isolated_enrollment_store.get_subject_ref(raw_speaker_id)
    assert len(subject_ref) == 64
    assert all(c in "0123456789abcdef" for c in subject_ref)

    # Ensure raw speaker_id does NOT appear as any filename
    for file_path in isolated_enrollment_store.storage_dir.iterdir():
        assert raw_speaker_id not in file_path.name

    # Check encrypted file
    enc_file = isolated_enrollment_store.storage_dir / f"{subject_ref}.enc"
    assert enc_file.is_file()

    # Verify that raw torch.load directly on the encrypted bytes fails (proves encryption)
    with pytest.raises(Exception):
        torch.load(io.BytesIO(enc_file.read_bytes()))

    # Verify store can successfully decrypt and return the embedding
    decrypted_emb = isolated_enrollment_store.get_embedding(raw_speaker_id)
    assert decrypted_emb is not None
    assert torch.allclose(emb, decrypted_emb, atol=1e-5)


def test_ecapa_unregistered_speaker_not_enrolled(diff_speaker_path, isolated_enrollment_store):
    """Unregistered caller identity returns BranchStatus.NOT_ENROLLED (fail-closed)."""
    res = verify_speaker(
        session_id="sess-unregistered-01",
        claimed_identity="unregistered_user_123",
        audio_path=diff_speaker_path,
        enrollment_store=isolated_enrollment_store,
    )
    assert res.status == BranchStatus.NOT_ENROLLED
    assert res.similarity_score == 0.0
    assert res.is_match is False
    assert res.raw_cosine is None

    # Verify risk engine treats NOT_ENROLLED as FLAG (fail-closed)
    evaluator = RiskEvaluator()
    from schemas.models import FusedEvidence, IntentResult, SpoofResult
    evidence = FusedEvidence(
        session_id="sess-unregistered-01",
        spoof_result=SpoofResult(session_id="sess-unregistered-01", status=BranchStatus.OK, spoof_score=0.1, is_spoofed=False, model_version="v0", confidence=0.9, processing_time_ms=5.0),
        speaker_result=res,
        intent_result=IntentResult(session_id="sess-unregistered-01", status=BranchStatus.OK, transcript="hello", transcript_hash_sha256="abc", language_detected=Language.EN, scam_score=0.1, processing_time_ms=5.0),
    )
    decision = evaluator.evaluate(evidence)
    assert any(r.rule_id == "STATUS_NOT_ENROLLED" for r in decision.fired_rules)
    assert decision.action in [ActionType.FLAG, ActionType.ESCALATE]


def test_ecapa_model_failure_fail_closed(diff_speaker_path, tmp_path, isolated_enrollment_store):
    """Corrupt weights directory causes verify_speaker to return BranchStatus.FAILED."""
    # Enroll a speaker first
    fake_emb = torch.randn(192)
    consent = ConsentRecord(speaker_id="spk_fail", consented_by="+910000000000")
    isolated_enrollment_store.enroll_speaker("spk_fail", fake_emb, consent)

    corrupt_dir = tmp_path / "corrupt_weights"
    corrupt_dir.mkdir()
    (corrupt_dir / "hyperparams.yaml").write_text("invalid: yaml: syntax: [}")

    res = verify_speaker(
        session_id="sess-fail-01",
        claimed_identity="spk_fail",
        audio_path=diff_speaker_path,
        enrollment_store=isolated_enrollment_store,
        model_weights_dir=corrupt_dir,
    )
    assert res.status == BranchStatus.FAILED
    assert res.similarity_score == 0.0
    assert res.is_match is False
    assert res.error_message is not None


def test_ecapa_insufficient_audio_from_vad(diff_speaker_path, isolated_enrollment_store):
    """When Phase 1 VAD determines audio is invalid, Speaker verification sets INSUFFICIENT_AUDIO."""
    invalid_vad = PreprocessedAudio(
        session_id="sess-vad-invalid",
        sample_rate=16000,
        duration_s=0.2,
        speech_duration_s=0.0,
        vad_segments=[],
        is_valid=False,
    )

    res = verify_speaker(
        session_id="sess-vad-invalid",
        claimed_identity="user_test",
        preprocessed_audio=invalid_vad,
        audio_path=diff_speaker_path,
        enrollment_store=isolated_enrollment_store,
    )
    assert res.status == BranchStatus.INSUFFICIENT_AUDIO
    assert res.similarity_score == 0.0
    assert res.is_match is False


def test_ecapa_mock_fallback_continuity():
    """Mock/simulated sessions without audio continue using deterministic SHA-256 stub."""
    run1 = verify_speaker("sess-mock-deterministic", claimed_identity="user_rohit")
    run2 = verify_speaker("sess-mock-deterministic", claimed_identity="user_rohit")

    assert run1.similarity_score == run2.similarity_score
    assert run1.raw_cosine == run2.raw_cosine
    assert run1.is_match == run2.is_match
    assert run1.status == BranchStatus.OK
    assert run1.model_version == MODEL_VERSION


def test_pipeline_e2e_with_real_speaker_verification(
    split_bonafide_samples, diff_speaker_path, isolated_enrollment_store, monkeypatch
):
    """
    End-to-end PipelineService test with real audio and real speaker verification:
    - Bona-fide enrolled caller -> ALLOW.
    - Imposter caller (different speaker claiming identity) -> FLAG or ESCALATE.
    """
    enroll_path, test_path = split_bonafide_samples
    emb = extract_embedding(enroll_path)
    consent = ConsentRecord(speaker_id="enrolled_customer", consented_by="+919876543210")
    isolated_enrollment_store.enroll_speaker("enrolled_customer", emb, consent)

    # Monkeypatch global store in branches.speaker to use our test store
    monkeypatch.setattr("branches.speaker.ecapa.get_enrollment_store", lambda: isolated_enrollment_store)

    from configs.settings import settings
    monkeypatch.setattr(settings, "enforce_model_registry", False)

    pipeline = PipelineService()

    # 1. Bona-fide enrolled caller session
    session_bona = CallSession(
        session_id="sess-e2e-spk-bona",
        caller_id="+919876543210",
        claimed_identity="enrolled_customer",
        audio_path_encrypted=test_path,
        audio_hash_sha256="a" * 64,
        language_hint=Language.EN,
    )
    decision_bona = pipeline.process_call_session(
        session_bona,
        override_spoof_score=0.10,
        override_scam_score=0.10,
    )
    spk_res = decision_bona.fused_evidence.speaker_result
    assert spk_res.status == BranchStatus.OK
    assert spk_res.is_match is True
    assert spk_res.similarity_score >= DEFAULT_THRESHOLD
    assert decision_bona.action == ActionType.ALLOW

    # 2. Imposter caller session (different voice claiming enrolled_customer)
    session_imposter = CallSession(
        session_id="sess-e2e-spk-imposter",
        caller_id="+919876543210",
        claimed_identity="enrolled_customer",
        audio_path_encrypted=diff_speaker_path,
        audio_hash_sha256="b" * 64,
        language_hint=Language.EN,
    )
    decision_imposter = pipeline.process_call_session(
        session_imposter,
        override_spoof_score=0.10,
        override_scam_score=0.10,
    )
    imp_spk_res = decision_imposter.fused_evidence.speaker_result
    assert imp_spk_res.status == BranchStatus.OK
    assert imp_spk_res.is_match is False
    assert imp_spk_res.similarity_score < DEFAULT_THRESHOLD
    # Risk engine should flag or escalate because speaker is weak/fail
    assert decision_imposter.action in [ActionType.FLAG, ActionType.ESCALATE]
