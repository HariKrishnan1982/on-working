"""
Phase 3: ECAPA-TDNN Speaker Verification Branch.

Reference: SpeechBrain pretrained ECAPA-TDNN (speechbrain/spkrec-ecapa-voxceleb).
Architecture: Emphasized Channel Attention, Propagation and Aggregation TDNN.
Embedding Dimension: 192.
Model Version: ecapa-tdnn-voxceleb-v0.

Contract:
- Consumes VAD-validated audio from Phase 1 (PreprocessedAudio).
- Evaluates acoustic match against enrolled profile in SpeakerEnrollmentStore.
- Produces normalized similarity_score in [0.0, 1.0] via normalize_ecapa_cosine.
- Produces model-level boolean is_match based on acoustic operating threshold (default 0.65).
  Note: rules.yaml operates on continuous similarity_score bands independently.
- Fail-closed: missing enrollment -> NOT_ENROLLED; load error -> FAILED; invalid VAD -> INSUFFICIENT_AUDIO.
- Dual-mode: real audio on disk executes deep learning inference; simulated mock sessions fall back to deterministic stub.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import soundfile as sf
import torch
import torch.nn.functional as F

from branches.speaker.registry import SpeakerEnrollmentStore, get_enrollment_store
from schemas.models import BranchStatus, PreprocessedAudio, SpeakerResult, normalize_ecapa_cosine

logger = logging.getLogger(__name__)

# Ensure HuggingFace warnings about symlinks are suppressed and COPY strategy is default
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

MODEL_VERSION = "ecapa-tdnn-voxceleb-v0"
DEFAULT_WEIGHTS_DIR = Path("models/weights/ecapa-voxceleb")
DEFAULT_THRESHOLD = 0.65

_CACHED_CLASSIFIER = None


def get_ecapa_classifier(weights_dir: Path = DEFAULT_WEIGHTS_DIR):
    """Lazy-load and cache the SpeechBrain ECAPA-TDNN classifier."""
    global _CACHED_CLASSIFIER

    from speechbrain.inference.speaker import EncoderClassifier
    from speechbrain.utils.fetching import LocalStrategy

    # Bypass cache if a custom or corrupt weights dir is explicitly passed
    if Path(weights_dir) != DEFAULT_WEIGHTS_DIR:
        return EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=str(weights_dir),
            run_opts={"device": "cpu"},
            local_strategy=LocalStrategy.COPY,
        )

    if _CACHED_CLASSIFIER is not None:
        return _CACHED_CLASSIFIER

    try:
        classifier = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=str(weights_dir),
            run_opts={"device": "cpu"},
            local_strategy=LocalStrategy.COPY,
        )
        _CACHED_CLASSIFIER = classifier
        logger.info("ECAPA-TDNN classifier loaded successfully from %s", weights_dir)
        return _CACHED_CLASSIFIER
    except Exception as e:
        logger.error("Failed to load ECAPA-TDNN model: %s", e)
        raise RuntimeError(f"ECAPA-TDNN model loading failed: {e}") from e


def extract_embedding(
    audio: np.ndarray | str | Path | torch.Tensor,
    classifier=None,
    target_sr: int = 16000,
) -> torch.Tensor:
    """
    Extract 192-dimensional speaker embedding from 16kHz mono audio.
    Returns 1D torch.Tensor of shape [192].
    """
    if classifier is None:
        classifier = get_ecapa_classifier()

    if isinstance(audio, (str, Path)):
        data, sr = sf.read(str(audio), dtype="float32")
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        audio = data

    if isinstance(audio, np.ndarray):
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        tensor = torch.from_numpy(audio).float()
    elif isinstance(audio, torch.Tensor):
        tensor = audio.float()
        if tensor.ndim > 1:
            tensor = tensor.mean(dim=-1)
    else:
        raise ValueError(f"Unsupported audio type: {type(audio)}")

    # Ensure 2D shape [batch, time]
    if tensor.ndim == 1:
        tensor = tensor.unsqueeze(0)

    with torch.no_grad():
        emb = classifier.encode_batch(tensor)
    # Shape is [batch, 1, 192] -> squeeze to [192]
    return emb.squeeze()


def compute_similarity(
    test_embedding: torch.Tensor,
    enrolled_embedding: torch.Tensor,
) -> Tuple[float, float]:
    """
    Compute raw cosine similarity in [-1.0, 1.0] and normalized score in [0.0, 1.0].
    """
    raw_cos = F.cosine_similarity(
        test_embedding.unsqueeze(0),
        enrolled_embedding.unsqueeze(0),
        dim=-1,
    ).item()
    norm_score = normalize_ecapa_cosine(raw_cos)
    return raw_cos, norm_score


def verify_speaker(
    session_id: str,
    claimed_identity: Optional[str] = "unknown",
    preprocessed_audio: Optional[PreprocessedAudio] = None,
    audio_path: str = "",
    override_score: Optional[float] = None,
    override_raw_cosine: Optional[float] = None,
    status: BranchStatus = BranchStatus.OK,
    error_message: Optional[str] = None,
    delay_ms: float = 0.0,
    threshold: float = DEFAULT_THRESHOLD,
    enrollment_store: Optional[SpeakerEnrollmentStore] = None,
    model_weights_dir: Optional[Path] = None,
) -> SpeakerResult:
    """
    Verify claimed speaker identity against enrolled biometric voice profile.

    Dual-mode behavior:
    1. Real audio on disk + enrolled caller -> runs ECAPA-TDNN deep learning inference.
    2. Real audio on disk + unenrolled caller -> returns BranchStatus.NOT_ENROLLED (fail-closed).
    3. Simulated/mock session (no physical audio) -> falls back to deterministic SHA-256 stub.
    4. Corrupt/missing model -> returns BranchStatus.FAILED (fail-closed).
    """
    start_time = time.time()
    store = enrollment_store or get_enrollment_store()

    # 1. Status override or degraded upstream state
    if status != BranchStatus.OK:
        return SpeakerResult(
            session_id=session_id,
            status=status,
            similarity_score=0.0,
            raw_cosine=None,
            is_match=False,
            claimed_identity=claimed_identity,
            threshold_used=threshold,
            model_version=MODEL_VERSION,
            processing_time_ms=delay_ms or 5.0,
            error_message=error_message or f"Speaker branch state: {status.value}",
        )

    # 2. Calibration score override (e.g. testing boundaries)
    if override_score is not None:
        norm_score = max(0.0, min(1.0, override_score))
        raw_cos = override_raw_cosine if override_raw_cosine is not None else (norm_score * 2.0 - 1.0)
        return SpeakerResult(
            session_id=session_id,
            status=BranchStatus.OK,
            similarity_score=round(norm_score, 4),
            raw_cosine=round(raw_cos, 4),
            is_match=norm_score >= threshold,
            claimed_identity=claimed_identity,
            threshold_used=threshold,
            model_version=MODEL_VERSION,
            processing_time_ms=delay_ms or 10.0,
        )

    # 3. Check VAD audio validity from Phase 1
    if preprocessed_audio is not None and not preprocessed_audio.is_valid:
        return SpeakerResult(
            session_id=session_id,
            status=BranchStatus.INSUFFICIENT_AUDIO,
            similarity_score=0.0,
            raw_cosine=None,
            is_match=False,
            claimed_identity=claimed_identity,
            threshold_used=threshold,
            model_version=MODEL_VERSION,
            processing_time_ms=delay_ms or 5.0,
            error_message="VAD determined audio is silent, corrupt, or insufficient for speaker verification",
        )

    # 4. Caller identity check
    effective_identity = claimed_identity.strip() if claimed_identity else ""
    if not effective_identity or effective_identity == "unknown":
        return SpeakerResult(
            session_id=session_id,
            status=BranchStatus.NOT_ENROLLED,
            similarity_score=0.0,
            raw_cosine=None,
            is_match=False,
            claimed_identity=claimed_identity,
            threshold_used=threshold,
            model_version=MODEL_VERSION,
            processing_time_ms=delay_ms or 5.0,
            error_message="Caller has no claimed identity; speaker verification cannot be performed",
        )

    # 5. Resolve physical audio path
    target_path = ""
    if preprocessed_audio is not None and preprocessed_audio.features_path:
        if Path(preprocessed_audio.features_path).is_file():
            target_path = preprocessed_audio.features_path

    if not target_path and audio_path and Path(audio_path).is_file():
        target_path = audio_path

    # 6. Real ECAPA-TDNN inference if physical audio exists
    if target_path:
        # Check enrollment in store
        if not store.is_enrolled(effective_identity):
            return SpeakerResult(
                session_id=session_id,
                status=BranchStatus.NOT_ENROLLED,
                similarity_score=0.0,
                raw_cosine=None,
                is_match=False,
                claimed_identity=claimed_identity,
                threshold_used=threshold,
                model_version=MODEL_VERSION,
                processing_time_ms=round((time.time() - start_time) * 1000.0, 2),
                error_message=f"Caller identity '{effective_identity}' has no enrolled biometric voiceprint",
            )

        enrolled_emb = store.get_embedding(effective_identity)
        if enrolled_emb is None:
            return SpeakerResult(
                session_id=session_id,
                status=BranchStatus.NOT_ENROLLED,
                similarity_score=0.0,
                raw_cosine=None,
                is_match=False,
                claimed_identity=claimed_identity,
                threshold_used=threshold,
                model_version=MODEL_VERSION,
                processing_time_ms=round((time.time() - start_time) * 1000.0, 2),
                error_message=f"Failed to decrypt enrolled biometric vector for '{effective_identity}'",
            )

        try:
            weights_dir = model_weights_dir or DEFAULT_WEIGHTS_DIR
            classifier = get_ecapa_classifier(weights_dir=weights_dir)
            test_emb = extract_embedding(target_path, classifier=classifier)

            raw_cos, norm_score = compute_similarity(test_emb, enrolled_emb)
            elapsed_ms = (time.time() - start_time) * 1000.0

            # Hash test embedding for audit trail
            test_emb_hash = hashlib.sha256(test_emb.numpy().tobytes()).hexdigest()
            enrollment_record = store.get_enrollment(effective_identity)
            emb_ref = enrollment_record.embedding_ref if enrollment_record else None

            return SpeakerResult(
                session_id=session_id,
                status=BranchStatus.OK,
                similarity_score=round(norm_score, 4),
                raw_cosine=round(raw_cos, 4),
                is_match=norm_score >= threshold,
                claimed_identity=claimed_identity,
                threshold_used=threshold,
                embedding_hash_sha256=test_emb_hash,
                embedding_ref=emb_ref,
                model_version=MODEL_VERSION,
                processing_time_ms=round(elapsed_ms, 2),
            )
        except Exception as e:
            logger.error("ECAPA-TDNN speaker verification failed for session %s: %s", session_id, e)
            return SpeakerResult(
                session_id=session_id,
                status=BranchStatus.FAILED,
                similarity_score=0.0,
                raw_cosine=None,
                is_match=False,
                claimed_identity=claimed_identity,
                threshold_used=threshold,
                model_version=MODEL_VERSION,
                processing_time_ms=0.0,
                error_message=f"ECAPA-TDNN inference failure: {e}",
            )

    # 7. Fallback to deterministic SHA-256 stub for simulated mock sessions
    from branches.speaker.stub import verify_speaker as stub_verify

    result = stub_verify(
        session_id=session_id,
        claimed_identity=claimed_identity,
        override_score=override_score,
        override_raw_cosine=override_raw_cosine,
        status=status,
        error_message=error_message,
        delay_ms=delay_ms,
    )
    result.model_version = MODEL_VERSION
    return result
