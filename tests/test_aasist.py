"""
Phase 2 Unit Tests: AASIST Anti-Spoofing & Deepfake Detection.

Official Reference: Clova AI AASIST (Jung et al., ICASSP 2022)
Protocol: ASVspoof 2019 Logical Access (LA)
Index 0 = spoof, Index 1 = bonafide.
"""

from pathlib import Path
import pytest
import soundfile as sf
import torch
import torch.nn.functional as F

from branches.antispoof.aasist import (
    MODEL_VERSION,
    analyze_spoof,
    get_aasist_model,
    run_aasist_inference,
)
from schemas.models import BranchStatus, PreprocessedAudio, VADSegment
from services.pipeline_service import PipelineService
from schemas.models import CallSession, Language, ActionType


@pytest.fixture
def bonafide_path():
    path = Path("test_vectors/audio/bonafide_sample.wav")
    assert path.is_file(), "Reference bonafide audio sample must exist"
    return str(path)


@pytest.fixture
def spoofed_path():
    path = Path("test_vectors/audio/spoofed_sample.wav")
    assert path.is_file(), "Reference spoofed audio sample must exist"
    return str(path)


def test_aasist_directional_bonafide_vs_spoof(bonafide_path, spoofed_path):
    """
    PINNED DIRECTIONAL TEST (Per official ASVspoof2019 / Clova AI protocol):
    Index 0 = spoof, Index 1 = bonafide.
    
    Explicitly asserts:
    - Real bona-fide sample scores: probs[:, 1] > probs[:, 0] (bonafide wins, spoof_score < 0.50).
    - Real spoofed sample scores:   probs[:, 0] > probs[:, 1] (spoof wins, spoof_score > 0.50).
    Guards against silently inverting class indices or fraud decisions.
    """
    model = get_aasist_model()

    # 1. Direct raw model tensor verification
    audio_b, _ = sf.read(bonafide_path, dtype="float32")
    t_b = torch.from_numpy(audio_b[:64600]).unsqueeze(0).float()
    with torch.no_grad():
        _, out_b = model(t_b)
        probs_b = F.softmax(out_b, dim=-1)

    audio_s, _ = sf.read(spoofed_path, dtype="float32")
    t_s = torch.from_numpy(audio_s[:64600]).unsqueeze(0).float()
    with torch.no_grad():
        _, out_s = model(t_s)
        probs_s = F.softmax(out_s, dim=-1)

    # Directional assertion:
    # Bona-fide: Index 1 (bonafide) MUST beat Index 0 (spoof)
    assert probs_b[0, 1].item() > probs_b[0, 0].item(), (
        f"Directional failure on bona-fide sample: p_bonafide ({probs_b[0, 1].item()}) "
        f"must be > p_spoof ({probs_b[0, 0].item()})"
    )

    # Spoofed: Index 0 (spoof) MUST beat Index 1 (bonafide)
    assert probs_s[0, 0].item() > probs_s[0, 1].item(), (
        f"Directional failure on spoofed sample: p_spoof ({probs_s[0, 0].item()}) "
        f"must be > p_bonafide ({probs_s[0, 1].item()})"
    )

    # 2. Branch-level analyze_spoof verification
    res_b = analyze_spoof("sess-test-bonafide", audio_path=bonafide_path)
    assert res_b.status == BranchStatus.OK
    assert res_b.is_spoofed is False
    assert res_b.spoof_score < 0.50
    assert res_b.confidence >= 0.50
    assert res_b.model_version == "aasist-asvspoof2019-v0"

    res_s = analyze_spoof("sess-test-spoofed", audio_path=spoofed_path)
    assert res_s.status == BranchStatus.OK
    assert res_s.is_spoofed is True
    assert res_s.spoof_score > 0.50
    assert res_s.confidence >= 0.50
    assert res_s.model_version == "aasist-asvspoof2019-v0"


def test_aasist_model_load_failure_fail_closed(bonafide_path, tmp_path):
    """Corrupt or missing model weights trigger BranchStatus.FAILED (fail-closed)."""
    corrupt_weights = tmp_path / "corrupt.pth"
    corrupt_weights.write_text("not a valid pytorch file")

    res = analyze_spoof(
        session_id="sess-test-corrupt-weights",
        audio_path=bonafide_path,
        model_weights_path=corrupt_weights,
    )

    assert res.status == BranchStatus.FAILED
    assert res.is_spoofed is False
    assert res.model_version == "aasist-asvspoof2019-v0"
    assert res.error_message is not None
    assert "AASIST inference failure" in res.error_message


def test_aasist_insufficient_audio_from_vad(bonafide_path):
    """When Phase 1 VAD flags audio as invalid, AASIST sets INSUFFICIENT_AUDIO."""
    invalid_vad = PreprocessedAudio(
        session_id="sess-test-invalid-vad",
        sample_rate=16000,
        duration_s=0.2,
        speech_duration_s=0.0,
        vad_segments=[],
        is_valid=False,
    )

    res = analyze_spoof(
        session_id="sess-test-invalid-vad",
        preprocessed_audio=invalid_vad,
        audio_path=bonafide_path,
    )

    assert res.status == BranchStatus.INSUFFICIENT_AUDIO
    assert res.is_spoofed is False
    assert res.model_version == "aasist-asvspoof2019-v0"


def test_aasist_mock_fallback_continuity():
    """Simulated mock sessions without physical audio continue to use deterministic stub."""
    res1 = analyze_spoof("sess-mock-deterministic-run")
    res2 = analyze_spoof("sess-mock-deterministic-run")

    assert res1.spoof_score == res2.spoof_score
    assert res1.is_spoofed == res2.is_spoofed
    assert res1.model_version == "aasist-asvspoof2019-v0"
    assert res1.status == BranchStatus.OK


def test_pipeline_integration_with_real_audio(bonafide_path, spoofed_path, monkeypatch):
    """PipelineService successfully analyzes real audio through both VAD and AASIST."""
    import hashlib
    from configs.settings import settings

    monkeypatch.setattr(settings, "enforce_model_registry", False)

    pipeline = PipelineService()
    bona_hash = hashlib.sha256(Path(bonafide_path).read_bytes()).hexdigest()
    spoof_hash = hashlib.sha256(Path(spoofed_path).read_bytes()).hexdigest()

    # 1. Bona-fide call
    session_bona = CallSession(
        session_id="sess-e2e-bona",
        caller_id="+919876543210",
        audio_path_encrypted=bonafide_path,
        audio_hash_sha256=bona_hash,
        language_hint=Language.EN,
    )
    decision_bona = pipeline.process_call_session(
        session_bona,
        override_similarity_score=0.90,  # simulate valid enrolled speaker
        override_scam_score=0.10,        # simulate clean intent
    )
    assert decision_bona.fused_evidence.spoof_result.status == BranchStatus.OK
    assert decision_bona.fused_evidence.spoof_result.spoof_score < 0.50
    assert decision_bona.action == ActionType.ALLOW

    # 2. Spoofed call
    session_spoof = CallSession(
        session_id="sess-e2e-spoof",
        caller_id="+919876543210",
        audio_path_encrypted=spoofed_path,
        audio_hash_sha256=spoof_hash,
        language_hint=Language.EN,
    )
    decision_spoof = pipeline.process_call_session(
        session_spoof,
        override_similarity_score=0.90,
        override_scam_score=0.10,
    )
    assert decision_spoof.fused_evidence.spoof_result.status == BranchStatus.OK
    assert decision_spoof.fused_evidence.spoof_result.spoof_score > 0.50
    assert decision_spoof.fused_evidence.spoof_result.is_spoofed is True
    assert decision_spoof.action in [ActionType.BLOCK, ActionType.ESCALATE]
