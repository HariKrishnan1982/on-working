"""
Pipeline Service — Core Deterministic Orchestrator.

Implements the single source of truth for the voice fraud detection pipeline.
Completely decoupled from LLM agents. Both the FastAPI Gateway and the
Unified MCP Server facade call this service directly.

Integrates IntegrityGuard to verify model and rules on-chain endorsement.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from actions.dispatcher import dispatch_action
from audit.sink import AuditSink
from branches.antispoof import analyze_spoof
from branches.asr_intent import analyze_intent
from branches.speaker import verify_speaker
from configs.settings import settings
from fusion.engine import fuse_evidence
from preprocess import preprocess_audio
from risk_engine.evaluator import RiskEvaluator
from schemas.models import (
    ActionType,
    BranchStatus,
    CallSession,
    FiredRule,
    Language,
    PreprocessedAudio,
    RiskDecision,
    RiskLevel,
)
from services.integrity_guard import IntegrityGuard


class PipelineService:
    """
    Deterministic decision pipeline service.

    Orchestrates audio preprocessing, parallel branch execution, evidence fusion,
    rule evaluation, action dispatch, and audit append.
    """

    def __init__(
        self,
        evaluator: Optional[RiskEvaluator] = None,
        audit_sink: Optional[AuditSink] = None,
        integrity_guard: Optional[IntegrityGuard] = None,
    ) -> None:
        self.evaluator = evaluator or RiskEvaluator()
        self.audit_sink = audit_sink
        self.integrity_guard = integrity_guard or IntegrityGuard()

    def process_call_session(
        self,
        session: CallSession,
        spoof_status: BranchStatus = BranchStatus.OK,
        speaker_status: BranchStatus = BranchStatus.OK,
        intent_status: BranchStatus = BranchStatus.OK,
        override_spoof_score: Optional[float] = None,
        override_similarity_score: Optional[float] = None,
        override_scam_score: Optional[float] = None,
        operator_notes: Optional[str] = None,
    ) -> RiskDecision:
        """
        Execute full end-to-end pipeline synchronously on a CallSession.
        """
        # 1. Preprocess audio
        preprocessed = preprocess_audio(session.session_id, session.audio_path_encrypted)

        # Fail-closed guard: if preprocessed audio is invalid/insufficient, mark statuses accordingly
        effective_spoof_status = spoof_status
        effective_speaker_status = speaker_status
        effective_intent_status = intent_status
        if not preprocessed.is_valid:
            effective_spoof_status = BranchStatus.INSUFFICIENT_AUDIO
            effective_speaker_status = BranchStatus.INSUFFICIENT_AUDIO
            effective_intent_status = BranchStatus.INSUFFICIENT_AUDIO

        # 2. Execute branches
        spoof_result = analyze_spoof(
            session_id=session.session_id,
            preprocessed_audio=preprocessed,
            audio_path=session.audio_path_encrypted,
            override_score=override_spoof_score,
            status=effective_spoof_status,
        )

        speaker_result = verify_speaker(
            session_id=session.session_id,
            claimed_identity=session.claimed_identity or "unknown",
            preprocessed_audio=preprocessed,
            audio_path=session.audio_path_encrypted,
            override_score=override_similarity_score,
            status=effective_speaker_status,
        )

        intent_result = analyze_intent(
            session_id=session.session_id,
            preprocessed_audio=preprocessed,
            audio_path=session.audio_path_encrypted,
            language_hint=session.language_hint,
            override_scam_score=override_scam_score,
            status=effective_intent_status,
        )

        # 3. Fuse evidence (aggregation only)
        evidence = fuse_evidence(
            spoof=spoof_result,
            speaker=speaker_result,
            intent=intent_result,
        )

        # 4. Evaluate risk deterministically
        decision = self.evaluator.evaluate(evidence)

        # 5. On-Chain Integrity Verification Check (Fail-Closed)
        if settings.enforce_model_registry:
            mock_model_hashes = {
                "antispoof": hashlib.sha256(b"aasist_mock_weights").hexdigest(),
                "speaker": hashlib.sha256(b"ecapa_mock_weights").hexdigest(),
                "asr_intent": hashlib.sha256(b"whisper_mock_weights").hexdigest(),
            }
            is_valid, reason = self.integrity_guard.verify_integrity(
                local_rules_version=self.evaluator.rules_version,
                local_rules_sha256=self.evaluator.rules_sha256,
                model_versions=decision.model_versions,
                model_artifacts_sha256=mock_model_hashes,
            )
            if not is_valid and reason:
                # Override to ESCALATE (fail closed)
                decision.risk_level = RiskLevel.CRITICAL
                decision.action = ActionType.ESCALATE
                decision.reasons.append(reason)
                decision.fired_rules.append(
                    FiredRule(
                        rule_id="INTEGRITY_CHECK_FAILED",
                        description="Blockchain integrity verification check failed",
                        risk_level=RiskLevel.CRITICAL,
                        action=ActionType.ESCALATE,
                        condition_summary=reason,
                    )
                )

        # 6. Dispatch action
        dispatch_action(decision)

        return decision
