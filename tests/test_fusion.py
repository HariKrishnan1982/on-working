"""
Unit tests for evidence fusion.

Per Requirement 7, fusion acts solely as an evidence aggregator.
Inconsistency detection lives exclusively in rules.yaml / RiskEngine.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from branches.antispoof.stub import analyze_spoof
from branches.asr_intent.stub import analyze_intent
from branches.speaker.stub import verify_speaker
from fusion.engine import fuse_evidence
from schemas.models import BranchStatus, Language


def test_fusion_assembles_all_branch_results():
    """Verify that fuse_evidence aggregates all branch data faithfully."""
    session_id = "test-session-fusion-1"
    spoof = analyze_spoof(session_id, override_score=0.45)
    speaker = verify_speaker(session_id, claimed_identity="alice", override_score=0.72)
    intent = analyze_intent(session_id, language_hint=Language.HI, override_scam_score=0.33)

    evidence = fuse_evidence(spoof, speaker, intent)

    assert evidence.session_id == session_id
    assert evidence.spoof_result.spoof_score == 0.45
    assert evidence.speaker_result.similarity_score == 0.72
    assert evidence.intent_result.scam_score == 0.33
    assert evidence.speaker_result.claimed_identity == "alice"
    assert evidence.intent_result.language_detected == Language.HI


def test_fusion_rejects_session_id_mismatch():
    """Verify that fuse_evidence enforces session integrity."""
    spoof = analyze_spoof("session-1")
    speaker = verify_speaker("session-2")
    intent = analyze_intent("session-1")

    with pytest.raises(AssertionError, match="Session ID mismatch"):
        fuse_evidence(spoof, speaker, intent)


def test_fusion_preserves_degraded_branch_statuses():
    """Verify that fuse_evidence preserves non-OK branch statuses for fail-closed handling."""
    session_id = "test-session-fusion-3"
    spoof = analyze_spoof(session_id, status=BranchStatus.FAILED)
    speaker = verify_speaker(session_id, status=BranchStatus.NOT_ENROLLED)
    intent = analyze_intent(session_id, status=BranchStatus.INSUFFICIENT_AUDIO)

    evidence = fuse_evidence(spoof, speaker, intent)

    assert evidence.spoof_result.status == BranchStatus.FAILED
    assert evidence.speaker_result.status == BranchStatus.NOT_ENROLLED
    assert evidence.intent_result.status == BranchStatus.INSUFFICIENT_AUDIO
