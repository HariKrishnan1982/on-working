"""
Real ASR + Scam-Intent Branch Orchestrator.

Combines faster-whisper transcription with multilingual RuleBasedIntentClassifier
and zero-PII TranscriptStore encryption.

Dual-Mode Architecture:
1. Real audio on disk -> faster-whisper STT + multilingual fraud scanner + Fernet encryption.
2. Simulated/mock sessions (no audio on disk) -> deterministic SHA-256 stub fallback.
3. Fail-closed: model load failure -> BranchStatus.FAILED; invalid VAD -> BranchStatus.INSUFFICIENT_AUDIO.
4. Privacy: zero raw transcripts reach audit trail or blockchain ledger.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

from branches.asr_intent.asr import DEFAULT_WHISPER_DIR, get_asr_model, transcribe_audio
from branches.asr_intent.scanner import get_default_scanner
from branches.asr_intent.transcript_store import get_transcript_store
from schemas.models import BranchStatus, IntentCategory, IntentResult, Language, PreprocessedAudio

logger = logging.getLogger(__name__)

MODEL_VERSION = "faster-whisper-base-rules-v0"


def analyze_intent(
    session_id: str,
    preprocessed_audio: Optional[PreprocessedAudio] = None,
    audio_path: str = "",
    language_hint: Language = Language.EN,
    transcript_override: Optional[str] = None,
    override_scam_score: Optional[float] = None,
    status: BranchStatus = BranchStatus.OK,
    error_message: Optional[str] = None,
    delay_ms: float = 0.0,
    model_size: str = "base",
    model_weights_dir: Optional[Path] = None,
) -> IntentResult:
    """
    Analyze call audio or transcript for scam intent.

    Dual-mode:
    - Real audio on disk -> faster-whisper + multilingual fraud scanner.
    - Mock/simulated session -> deterministic SHA-256 stub fallback.
    """
    start_time = time.time()
    scanner = get_default_scanner()
    store = get_transcript_store()

    # 1. Handle degraded upstream or forced status
    if status != BranchStatus.OK:
        return IntentResult(
            session_id=session_id,
            status=status,
            transcript="",
            transcript_hash_sha256=hashlib.sha256(b"").hexdigest(),
            transcript_ref=None,
            language_detected=language_hint,
            scam_score=0.0,
            scam_indicators=[],
            intent_category=IntentCategory.BENIGN,
            model_version=MODEL_VERSION,
            processing_time_ms=delay_ms or 5.0,
            error_message=error_message or f"ASR intent branch state: {status.value}",
        )

    # 2. Calibration score override
    if override_scam_score is not None:
        score = max(0.0, min(1.0, override_scam_score))
        if score >= 0.80:
            category = IntentCategory.SCAM_CONFIRMED
        elif score >= 0.50:
            category = IntentCategory.SCAM_LIKELY
        elif score >= 0.30:
            category = IntentCategory.SUSPICIOUS
        else:
            category = IntentCategory.BENIGN
        indicators = ["override_indicator"] if score >= 0.5 else []

        transcript = transcript_override or "Simulated call session."
        t_hash, t_ref = store.store_transcript(transcript)

        return IntentResult(
            session_id=session_id,
            status=BranchStatus.OK,
            transcript=transcript,
            transcript_hash_sha256=t_hash,
            transcript_ref=t_ref,
            language_detected=language_hint,
            scam_score=round(score, 3),
            scam_indicators=indicators,
            intent_category=category,
            model_version=MODEL_VERSION,
            processing_time_ms=delay_ms or 10.0,
        )

    # 3. Check VAD audio validity from Phase 1
    if preprocessed_audio is not None and not preprocessed_audio.is_valid:
        return IntentResult(
            session_id=session_id,
            status=BranchStatus.INSUFFICIENT_AUDIO,
            transcript="",
            transcript_hash_sha256=hashlib.sha256(b"").hexdigest(),
            transcript_ref=None,
            language_detected=language_hint,
            scam_score=0.0,
            scam_indicators=[],
            intent_category=IntentCategory.BENIGN,
            model_version=MODEL_VERSION,
            processing_time_ms=delay_ms or 5.0,
            error_message="VAD determined audio is silent, corrupt, or insufficient for intent analysis",
        )

    # 4. Direct transcript text override (e.g. text-only scanning tests)
    if transcript_override is not None:
        score, category, indicators = scanner.classify(transcript_override, language_hint)
        t_hash, t_ref = store.store_transcript(transcript_override)
        elapsed_ms = (time.time() - start_time) * 1000.0

        return IntentResult(
            session_id=session_id,
            status=BranchStatus.OK,
            transcript=transcript_override,
            transcript_hash_sha256=t_hash,
            transcript_ref=t_ref,
            language_detected=language_hint,
            scam_score=round(score, 3),
            scam_indicators=indicators,
            intent_category=category,
            model_version=MODEL_VERSION,
            processing_time_ms=round(elapsed_ms, 2),
        )

    # 5. Resolve physical audio path
    target_path = ""
    if preprocessed_audio is not None and preprocessed_audio.features_path:
        if Path(preprocessed_audio.features_path).is_file():
            target_path = preprocessed_audio.features_path

    if not target_path and audio_path and Path(audio_path).is_file():
        target_path = audio_path

    # 6. Real ASR + Scam-Intent execution if physical audio exists
    if target_path:
        try:
            download_root = model_weights_dir or DEFAULT_WHISPER_DIR
            model = get_asr_model(model_size=model_size, download_root=download_root)
            transcript, detected_lang, asr_ms = transcribe_audio(
                target_path,
                model=model,
                language_hint=language_hint,
            )

            score, category, indicators = scanner.classify(transcript, detected_lang)
            t_hash, t_ref = store.store_transcript(transcript)
            total_elapsed_ms = (time.time() - start_time) * 1000.0

            return IntentResult(
                session_id=session_id,
                status=BranchStatus.OK,
                transcript=transcript,
                transcript_hash_sha256=t_hash,
                transcript_ref=t_ref,
                language_detected=detected_lang,
                scam_score=round(score, 3),
                scam_indicators=indicators,
                intent_category=category,
                model_version=MODEL_VERSION,
                processing_time_ms=round(total_elapsed_ms, 2),
            )
        except Exception as e:
            logger.error("ASR intent analysis failed for session %s: %s", session_id, e)
            return IntentResult(
                session_id=session_id,
                status=BranchStatus.FAILED,
                transcript="",
                transcript_hash_sha256=hashlib.sha256(b"").hexdigest(),
                transcript_ref=None,
                language_detected=language_hint,
                scam_score=0.0,
                scam_indicators=[],
                intent_category=IntentCategory.BENIGN,
                model_version=MODEL_VERSION,
                processing_time_ms=0.0,
                error_message=f"ASR intent analysis failure: {e}",
            )

    # 7. Fallback to deterministic SHA-256 stub for simulated mock sessions
    from branches.asr_intent.stub import analyze_intent as stub_analyze

    result = stub_analyze(
        session_id=session_id,
        language_hint=language_hint,
        transcript_override=transcript_override,
        override_scam_score=override_scam_score,
        status=status,
        error_message=error_message,
        delay_ms=delay_ms,
    )
    result.model_version = MODEL_VERSION
    return result
