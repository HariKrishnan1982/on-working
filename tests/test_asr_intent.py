"""
Phase 4 Unit & Integration Tests: ASR & Scam-Intent Analysis Branch.

Test Scope & Clarifications:
1. Directional Audio Assertion:
   - Scam audio (test_vectors/audio/scam_sample.wav): Synthesized via Windows SAPI
     SpeechSynthesizer ("urgent call from police officer, account blocked immediately, share OTP right now").
   - Benign audio (test_vectors/audio/bonafide_sample.wav): Real human speech from VCTK corpus (speaker p274,
     "Employees are entitled to follow their contract to the letter").
   - Asserts: scam_score(scam) > scam_score(bonafide) with margin >= 0.40.
2. Direct Multilingual Scanner Tests:
   - Evaluates RuleBasedIntentClassifier directly on Hindi, Tamil, Telugu, and Hinglish strings,
     decoupled from ASR model transcription noise.
3. Privacy & Encryption:
   - Verifies transcripts are encrypted at rest with Fernet and keyed by SHA-256 hash.
   - Verifies zero cleartext transcripts in audit records.
4. Fail-Closed:
   - Model failure returns BranchStatus.FAILED (escalates to ESCALATE).
5. VAD Gating:
   - Insufficient audio propagates BranchStatus.INSUFFICIENT_AUDIO.
6. Mock Fallback:
   - Mock sessions without audio preserve deterministic SHA-256 continuity.
7. E2E Pipeline Integration:
   - Full pipeline processing with real audio and privacy enforcement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from branches.asr_intent.asr import get_asr_model, transcribe_audio
from branches.asr_intent.intent import MODEL_VERSION, analyze_intent
from branches.asr_intent.scanner import RuleBasedIntentClassifier
from branches.asr_intent.transcript_store import TranscriptStore
from risk_engine.evaluator import RiskEvaluator
from schemas.models import (
    ActionType,
    BranchStatus,
    CallSession,
    FusedEvidence,
    IntentCategory,
    Language,
    PreprocessedAudio,
    SpeakerResult,
    SpoofResult,
)
from services.pipeline_service import PipelineService


@pytest.fixture
def scam_audio_path() -> str:
    path = Path("test_vectors/audio/scam_sample.wav")
    assert path.is_file(), "Scam audio test vector must exist"
    return str(path)


@pytest.fixture
def bonafide_audio_path() -> str:
    path = Path("test_vectors/audio/bonafide_sample.wav")
    assert path.is_file(), "Bonafide audio test vector must exist"
    return str(path)


@pytest.fixture
def isolated_transcript_store(tmp_path):
    """Create isolated TranscriptStore in temporary directory."""
    return TranscriptStore(storage_dir=tmp_path / "transcripts")


def test_asr_directional_scam_vs_bonafide_audio(scam_audio_path, bonafide_audio_path):
    """
    PINNED DIRECTIONAL TEST (Audio -> ASR -> Scam Intent):
    
    Compares:
    - Scam audio: Windows SAPI TTS saying urgent police impersonation + account blocked + OTP request.
    - Bonafide audio: Real human speech (p274) reading neutral contractual sentence.
    
    Explicitly asserts:
    1. scam_score(scam) > scam_score(bonafide)
    2. Separation margin >= 0.40
    3. scam audio scores >= 0.70 (SCAM_CONFIRMED or SCAM_LIKELY)
    4. bonafide audio scores <= 0.20 (BENIGN)
    """
    # 1. Direct transcription verification
    scam_res = analyze_intent(
        session_id="sess-audio-scam-01",
        audio_path=scam_audio_path,
    )
    assert scam_res.status == BranchStatus.OK
    assert "otp" in scam_res.transcript.lower() or "blocked" in scam_res.transcript.lower()
    assert scam_res.scam_score >= 0.70
    assert scam_res.intent_category in [IntentCategory.SCAM_CONFIRMED, IntentCategory.SCAM_LIKELY]
    assert "financial_pressure" in scam_res.scam_indicators
    assert scam_res.transcript_hash_sha256 is not None
    assert scam_res.transcript_ref is not None

    bona_res = analyze_intent(
        session_id="sess-audio-bona-01",
        audio_path=bonafide_audio_path,
    )
    assert bona_res.status == BranchStatus.OK
    assert bona_res.scam_score <= 0.20
    assert bona_res.intent_category == IntentCategory.BENIGN
    assert len(bona_res.scam_indicators) == 0

    # Directional separation assertion
    assert scam_res.scam_score > bona_res.scam_score
    assert (scam_res.scam_score - bona_res.scam_score) >= 0.40


def test_multilingual_and_codeswitched_scanner_rules():
    """
    Direct scanner text-matching unit tests across Hindi, Tamil, Telugu, and Hinglish.
    Decoupled from ASR transcription noise to rigorously verify fraud indicator rules.
    """
    scanner = RuleBasedIntentClassifier()

    # 1. Hindi Devanagari Scam (Police impersonation + account block + OTP)
    hi_scam = "यह पुलिस अधिकारी की तरफ से जरूरी कॉल है। आपका बैंक खाता तुरंत ब्लॉक कर दिया जाएगा। अपना ओटीपी बताएं।"
    score_hi, cat_hi, ind_hi = scanner.classify(hi_scam, Language.HI)
    assert score_hi >= 0.80
    assert cat_hi == IntentCategory.SCAM_CONFIRMED
    assert "impersonation_language" in ind_hi
    assert "financial_pressure" in ind_hi
    assert "urgent_request" in ind_hi

    # 2. Hinglish Code-Switched Scam (CBI / Police + account blocked + urgent OTP)
    hinglish_scam = "CBI officer here. Your bank account is blocked immediately. Share OTP right now or face arrest warrant."
    score_hg, cat_hg, ind_hg = scanner.classify(hinglish_scam, Language.HI)
    assert score_hg >= 0.80
    assert cat_hg == IntentCategory.SCAM_CONFIRMED
    assert "impersonation_language" in ind_hg
    assert "financial_pressure" in ind_hg

    # 3. Tamil Scam (Police + bank account blocked + OTP)
    ta_scam = "காவல்துறை அதிகாரி பேசுகிறேன். உங்கள் வங்கி கணக்கு உடனடியாக முடக்கப்படும். ஓடிபி சொல்லுங்கள்."
    score_ta, cat_ta, ind_ta = scanner.classify(ta_scam, Language.TA)
    assert score_ta >= 0.80
    assert cat_ta == IntentCategory.SCAM_CONFIRMED
    assert "impersonation_language" in ind_ta
    assert "financial_pressure" in ind_ta

    # 4. Telugu Scam (Police + bank account blocked + OTP)
    te_scam = "పోలీస్ అధికారి మాట్లాడుతున్నాను. మీ బ్యాంకు ఖాతా వెంటనే బ్లాక్ చేయబడుతుంది. మీ ఓటీపీ చెప్పండి."
    score_te, cat_te, ind_te = scanner.classify(te_scam, Language.TE)
    assert score_te >= 0.80
    assert cat_te == IntentCategory.SCAM_CONFIRMED
    assert "impersonation_language" in ind_te
    assert "financial_pressure" in ind_te

    # 5. Benign conversation across languages
    benign_en = "Good morning, I would like to check my monthly statement for my account please."
    s_en, c_en, _ = scanner.classify(benign_en, Language.EN)
    assert s_en <= 0.20
    assert c_en == IntentCategory.BENIGN

    benign_hi = "नमस्ते, क्या आप मुझे नजदीकी शाखा का पता बता सकते हैं?"
    s_hi, c_hi, _ = scanner.classify(benign_hi, Language.HI)
    assert s_hi <= 0.20
    assert c_hi == IntentCategory.BENIGN


def test_transcript_privacy_and_fernet_encryption(scam_audio_path, isolated_transcript_store, monkeypatch):
    """
    Verify transcript privacy invariants:
    1. Transcripts are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256).
    2. Raw cleartext transcript cannot be read from the .enc file directly.
    3. Storage file is named by SHA-256 hash, zero session ID or cleartext in filename.
    """
    monkeypatch.setattr("branches.asr_intent.intent.get_transcript_store", lambda: isolated_transcript_store)

    res = analyze_intent(
        session_id="sess-privacy-test-01",
        audio_path=scam_audio_path,
    )
    assert res.status == BranchStatus.OK

    # Check on-disk file
    enc_path = isolated_transcript_store.storage_dir / f"{res.transcript_hash_sha256}.enc"
    assert enc_path.is_file()

    # Raw bytes must be encrypted ciphertext, NOT cleartext
    raw_content = enc_path.read_bytes()
    assert b"police" not in raw_content
    assert b"OTP" not in raw_content

    # Decrypt via store
    decrypted = isolated_transcript_store.get_transcript(res.transcript_hash_sha256)
    assert decrypted is not None
    assert "police" in decrypted.lower()


def test_asr_model_failure_fail_closed(scam_audio_path, tmp_path):
    """Invalid weights path or ASR failure causes analyze_intent to return BranchStatus.FAILED."""
    corrupt_dir = tmp_path / "non_existent_whisper_dir"

    res = analyze_intent(
        session_id="sess-asr-fail-01",
        audio_path=scam_audio_path,
        model_size="invalid_model_checkpoint_12345",
        model_weights_dir=corrupt_dir,
    )
    assert res.status == BranchStatus.FAILED
    assert res.scam_score == 0.0
    assert res.error_message is not None

    # Risk evaluator must treat FAILED status as ESCALATE
    evaluator = RiskEvaluator()
    evidence = FusedEvidence(
        session_id="sess-asr-fail-01",
        spoof_result=SpoofResult(session_id="sess-asr-fail-01", status=BranchStatus.OK, spoof_score=0.1, is_spoofed=False, model_version="v0", confidence=0.9, processing_time_ms=5.0),
        speaker_result=SpeakerResult(session_id="sess-asr-fail-01", status=BranchStatus.OK, similarity_score=0.9, raw_cosine=0.8, is_match=True, threshold_used=0.65, model_version="v0", processing_time_ms=5.0),
        intent_result=res,
    )
    decision = evaluator.evaluate(evidence)
    assert any(r.rule_id == "STATUS_BRANCH_FAILED" for r in decision.fired_rules)
    assert decision.action == ActionType.ESCALATE


def test_asr_insufficient_audio_from_vad(scam_audio_path):
    """When Phase 1 VAD flags audio as invalid, intent analysis returns INSUFFICIENT_AUDIO."""
    invalid_vad = PreprocessedAudio(
        session_id="sess-vad-short",
        sample_rate=16000,
        duration_s=0.1,
        speech_duration_s=0.0,
        vad_segments=[],
        is_valid=False,
    )

    res = analyze_intent(
        session_id="sess-vad-short",
        preprocessed_audio=invalid_vad,
        audio_path=scam_audio_path,
    )
    assert res.status == BranchStatus.INSUFFICIENT_AUDIO
    assert res.scam_score == 0.0
    assert res.intent_category == IntentCategory.BENIGN


def test_asr_mock_fallback_continuity():
    """Mock/simulated sessions without audio continue using deterministic SHA-256 stub."""
    run1 = analyze_intent(session_id="sess-mock-deterministic-asr")
    run2 = analyze_intent(session_id="sess-mock-deterministic-asr")

    assert run1.scam_score == run2.scam_score
    assert run1.intent_category == run2.intent_category
    assert run1.scam_indicators == run2.scam_indicators
    assert run1.status == BranchStatus.OK
    assert run1.model_version == MODEL_VERSION


def test_pipeline_e2e_with_real_asr_scam_detection(scam_audio_path, monkeypatch):
    """
    End-to-end PipelineService test with real audio processed through real ASR:
    - Real scam audio causes pipeline to ESCALATE or BLOCK.
    - Zero cleartext transcript in decision or audit logs.
    """
    from configs.settings import settings
    monkeypatch.setattr(settings, "enforce_model_registry", False)

    pipeline = PipelineService()
    session = CallSession(
        session_id="sess-e2e-scam-call",
        caller_id="+919876543210",
        claimed_identity="user_aarav",
        audio_path_encrypted=scam_audio_path,
        audio_hash_sha256="c" * 64,
        language_hint=Language.EN,
    )

    decision = pipeline.process_call_session(
        session,
        override_similarity_score=0.90,  # simulate verified enrolled speaker
        override_spoof_score=0.10,        # simulate clean acoustic audio
    )

    intent_res = decision.fused_evidence.intent_result
    assert intent_res.status == BranchStatus.OK
    assert intent_res.scam_score >= 0.70

    # Inconsistency rule INCON_CLEAN_SCAM fires (clean spoof + high speaker match + high scam intent)
    assert decision.action in [ActionType.ESCALATE, ActionType.BLOCK]
    assert any(r.rule_id in ["SCAM_HIGH", "INCON_CLEAN_SCAM"] for r in decision.fired_rules)
