"""
Comprehensive test suite for the deterministic Risk Engine.

Covers:
- Boundary-value tests for every named band
- Cross-signal inconsistency rules (INCON_SPOOF_MATCH, INCON_CLEAN_SCAM, INCON_ALL_MODERATE)
- Fail-closed enforcement: degraded or failed status NEVER yields ALLOW
- Highest-wins logic for risk levels and actions
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from risk_engine.evaluator import RiskEvaluator
from schemas.models import ActionType, BranchStatus, RiskLevel
from tests.conftest import make_fused_evidence


@pytest.fixture
def evaluator() -> RiskEvaluator:
    return RiskEvaluator()


# ── Clean Baseline ────────────────────────────────────────────────────────────


def test_clean_call_yields_allow(evaluator):
    """When all signals are completely benign and all branches OK, decision is LOW / ALLOW."""
    evidence = make_fused_evidence(spoof_score=0.10, similarity_score=0.90, scam_score=0.10)
    decision = evaluator.evaluate(evidence)

    assert decision.risk_level == RiskLevel.LOW
    assert decision.action == ActionType.ALLOW
    assert len(decision.fired_rules) == 0
    assert "0.2.0:" in decision.rules_version


# ── Fail-Closed Status Tests ──────────────────────────────────────────────────


def test_fail_closed_on_branch_failed(evaluator):
    """Degraded evidence (branch failed) must NEVER yield ALLOW."""
    # Scores are benign, but spoof branch failed
    evidence = make_fused_evidence(
        spoof_score=0.05,
        similarity_score=0.95,
        scam_score=0.05,
        spoof_status=BranchStatus.FAILED,
    )
    decision = evaluator.evaluate(evidence)

    assert decision.action != ActionType.ALLOW
    assert decision.action == ActionType.ESCALATE
    assert decision.risk_level == RiskLevel.HIGH
    assert any(r.rule_id == "STATUS_BRANCH_FAILED" for r in decision.fired_rules)


def test_fail_closed_on_insufficient_audio(evaluator):
    """Degraded evidence (insufficient audio) must FLAG or ESCALATE, never ALLOW."""
    evidence = make_fused_evidence(
        spoof_score=0.05,
        similarity_score=0.95,
        scam_score=0.05,
        speaker_status=BranchStatus.INSUFFICIENT_AUDIO,
    )
    decision = evaluator.evaluate(evidence)

    assert decision.action != ActionType.ALLOW
    assert decision.action == ActionType.FLAG
    assert decision.risk_level == RiskLevel.MEDIUM
    assert any(r.rule_id == "STATUS_INSUFFICIENT_AUDIO" for r in decision.fired_rules)


def test_fail_closed_on_not_enrolled(evaluator):
    """Caller not enrolled in biometrics must be flagged, never allowed blindly."""
    evidence = make_fused_evidence(
        spoof_score=0.05,
        similarity_score=0.75,
        scam_score=0.05,
        speaker_status=BranchStatus.NOT_ENROLLED,
    )
    decision = evaluator.evaluate(evidence)

    assert decision.action != ActionType.ALLOW
    assert decision.action == ActionType.FLAG
    assert any(r.rule_id == "STATUS_NOT_ENROLLED" for r in decision.fired_rules)


# ── Boundary-Value Tests for Individual Named Bands ───────────────────────────


def test_spoof_high_boundary(evaluator):
    """Band: high [0.85, 1.0]. Exactly 0.85 should fire SPOOF_HIGH."""
    ev_at = make_fused_evidence(spoof_score=0.85, similarity_score=0.90, scam_score=0.10)
    dec_at = evaluator.evaluate(ev_at)
    assert any(r.rule_id == "SPOOF_HIGH" for r in dec_at.fired_rules)
    assert dec_at.risk_level == RiskLevel.CRITICAL
    assert dec_at.action == ActionType.BLOCK

    ev_below = make_fused_evidence(spoof_score=0.849, similarity_score=0.90, scam_score=0.10)
    dec_below = evaluator.evaluate(ev_below)
    assert not any(r.rule_id == "SPOOF_HIGH" for r in dec_below.fired_rules)
    assert any(r.rule_id == "SPOOF_MED" for r in dec_below.fired_rules)


def test_spoof_med_boundary(evaluator):
    """Band: med [0.60, 0.85). 0.60 fires med, 0.599 does not."""
    ev_at = make_fused_evidence(spoof_score=0.60, similarity_score=0.90, scam_score=0.10)
    dec_at = evaluator.evaluate(ev_at)
    assert any(r.rule_id == "SPOOF_MED" for r in dec_at.fired_rules)

    ev_below = make_fused_evidence(spoof_score=0.599, similarity_score=0.90, scam_score=0.10)
    dec_below = evaluator.evaluate(ev_below)
    assert not any(r.rule_id == "SPOOF_MED" for r in dec_below.fired_rules)
    assert any(r.rule_id == "SPOOF_LOW" for r in dec_below.fired_rules)


def test_speaker_fail_boundary(evaluator):
    """Band: fail [0.0, 0.40). 0.399 fires SPEAKER_FAIL, 0.40 fires SPEAKER_WEAK."""
    ev_fail = make_fused_evidence(spoof_score=0.10, similarity_score=0.399, scam_score=0.10)
    dec_fail = evaluator.evaluate(ev_fail)
    assert any(r.rule_id == "SPEAKER_FAIL" for r in dec_fail.fired_rules)
    assert dec_fail.action == ActionType.ESCALATE

    ev_weak = make_fused_evidence(spoof_score=0.10, similarity_score=0.40, scam_score=0.10)
    dec_weak = evaluator.evaluate(ev_weak)
    assert not any(r.rule_id == "SPEAKER_FAIL" for r in dec_weak.fired_rules)
    assert any(r.rule_id == "SPEAKER_WEAK" for r in dec_weak.fired_rules)


def test_scam_high_boundary(evaluator):
    """Band: high [0.80, 1.0]. 0.80 fires SCAM_HIGH, 0.79 fires SCAM_MED."""
    ev_high = make_fused_evidence(spoof_score=0.10, similarity_score=0.90, scam_score=0.80)
    dec_high = evaluator.evaluate(ev_high)
    assert any(r.rule_id == "SCAM_HIGH" for r in dec_high.fired_rules)

    ev_med = make_fused_evidence(spoof_score=0.10, similarity_score=0.90, scam_score=0.79)
    dec_med = evaluator.evaluate(ev_med)
    assert not any(r.rule_id == "SCAM_HIGH" for r in dec_med.fired_rules)
    assert any(r.rule_id == "SCAM_MED" for r in dec_med.fired_rules)


# ── Cross-Signal Inconsistency Rules ──────────────────────────────────────────


def test_incon_spoof_match(evaluator):
    """spoof >= 0.60 AND speaker >= 0.70 -> Suspected voice clone -> CRITICAL / BLOCK."""
    evidence = make_fused_evidence(spoof_score=0.75, similarity_score=0.85, scam_score=0.10)
    decision = evaluator.evaluate(evidence)

    assert any(r.rule_id == "INCON_SPOOF_MATCH" for r in decision.fired_rules)
    assert decision.risk_level == RiskLevel.CRITICAL
    assert decision.action == ActionType.BLOCK


def test_incon_clean_scam(evaluator):
    """spoof clean (<0.30) AND speaker high_match (>=0.70) AND scam high (>=0.80)."""
    evidence = make_fused_evidence(spoof_score=0.15, similarity_score=0.80, scam_score=0.85)
    decision = evaluator.evaluate(evidence)

    assert any(r.rule_id == "INCON_CLEAN_SCAM" for r in decision.fired_rules)
    assert decision.risk_level == RiskLevel.HIGH
    assert decision.action == ActionType.ESCALATE


def test_incon_all_moderate(evaluator):
    """All 3 signals borderline (low spoof, weak speaker, med scam) -> Uncertainty ESCALATE."""
    evidence = make_fused_evidence(spoof_score=0.50, similarity_score=0.50, scam_score=0.60)
    decision = evaluator.evaluate(evidence)

    assert any(r.rule_id == "INCON_ALL_MODERATE" for r in decision.fired_rules)
    assert decision.risk_level == RiskLevel.HIGH
    assert decision.action == ActionType.ESCALATE


# ── Highest-Wins Resolution ───────────────────────────────────────────────────


def test_highest_risk_and_action_wins(evaluator):
    """When multiple rules fire, highest risk and most restrictive action win."""
    # SPOOF_LOW (MEDIUM, FLAG) + SCAM_HIGH (HIGH, ESCALATE) -> HIGH, ESCALATE
    evidence = make_fused_evidence(spoof_score=0.50, similarity_score=0.90, scam_score=0.85)
    decision = evaluator.evaluate(evidence)

    fired_ids = [r.rule_id for r in decision.fired_rules]
    assert "SPOOF_LOW" in fired_ids
    assert "SCAM_HIGH" in fired_ids
    assert decision.risk_level == RiskLevel.HIGH
    assert decision.action == ActionType.ESCALATE
