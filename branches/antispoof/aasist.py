"""
Phase 2: AASIST (Audio Anti-Spoofing using Integrated Spectro-Temporal Graph Attention Networks)
Official Reference: https://github.com/clovaai/aasist (Jung et al., ICASSP 2022)

Pretrained model: AASIST (Full variant), trained on ASVspoof 2019 Logical Access (LA).
Model version identifier: aasist-asvspoof2019-v0.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import soundfile as sf
import torch
import torch.nn.functional as F

from branches.antispoof.aasist_model import Model
from schemas.models import BranchStatus, PreprocessedAudio, SpoofResult

logger = logging.getLogger(__name__)

# Default model configuration from official AASIST.conf
AASIST_CONFIG = {
    "architecture": "AASIST",
    "nb_samp": 64600,
    "first_conv": 128,
    "filts": [70, [1, 32], [32, 32], [32, 64], [64, 64]],
    "gat_dims": [64, 32],
    "pool_ratios": [0.5, 0.7, 0.5, 0.5],
    "temperatures": [2.0, 2.0, 100.0, 100.0],
}

MODEL_VERSION = "aasist-asvspoof2019-v0"
DEFAULT_WEIGHTS_PATH = Path("models/weights/AASIST.pth")

_CACHED_AASIST_MODEL: Optional[Model] = None


def get_aasist_model(weights_path: Path = DEFAULT_WEIGHTS_PATH) -> Model:
    """Lazy-load and cache the AASIST PyTorch model."""
    global _CACHED_AASIST_MODEL
    # If custom weights path is specified, load freshly without using default cache
    if weights_path != DEFAULT_WEIGHTS_PATH:
        if not weights_path.is_file():
            raise FileNotFoundError(f"AASIST pretrained weights not found at '{weights_path}'")
        model = Model(AASIST_CONFIG)
        state_dict = torch.load(str(weights_path), map_location="cpu")
        model.load_state_dict(state_dict)
        model.eval()
        return model

    if _CACHED_AASIST_MODEL is None:
        if not weights_path.is_file():
            raise FileNotFoundError(f"AASIST pretrained weights not found at '{weights_path}'")

        model = Model(AASIST_CONFIG)
        state_dict = torch.load(str(weights_path), map_location="cpu")
        model.load_state_dict(state_dict)
        model.eval()
        _CACHED_AASIST_MODEL = model
        logger.info("AASIST model successfully loaded from %s", weights_path)

    return _CACHED_AASIST_MODEL


def pad_or_truncate(audio: np.ndarray, target_len: int = 64600) -> np.ndarray:
    """Pad (repeat) or truncate 1D audio to exactly target_len samples."""
    x_len = len(audio)
    if x_len == 0:
        return np.zeros(target_len, dtype=np.float32)
    if x_len >= target_len:
        return audio[:target_len]
    repeats = int(target_len / x_len) + 1
    return np.tile(audio, repeats)[:target_len]


def run_aasist_inference(
    audio_path: str | Path,
    model: Optional[Model] = None,
) -> Tuple[float, float, bool]:
    """
    Run AASIST inference on an audio file.
    Returns:
        (spoof_score, confidence, is_spoofed)
    Per official ASVspoof2019 / AASIST protocol:
        - Output index 0 = spoof
        - Output index 1 = bonafide
        - spoof_score = P(spoof) = probs[0, 0] in [0.0, 1.0]
    """
    if model is None:
        model = get_aasist_model()

    audio, sr = sf.read(str(audio_path), dtype="float32")
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    # Pad or slice to standard 64600 samples
    processed_audio = pad_or_truncate(audio, target_len=64600)
    tensor = torch.from_numpy(processed_audio).unsqueeze(0).float()

    with torch.no_grad():
        _, output = model(tensor)
        probs = F.softmax(output, dim=-1)
        p_spoof = float(probs[0, 0].item())
        p_bonafide = float(probs[0, 1].item())

    spoof_score = round(p_spoof, 4)
    confidence = round(max(p_spoof, p_bonafide), 4)
    is_spoofed = spoof_score >= 0.50

    return spoof_score, confidence, is_spoofed


def analyze_spoof(
    session_id: str,
    preprocessed_audio: Optional[PreprocessedAudio] = None,
    audio_path: str = "",
    override_score: Optional[float] = None,
    status: BranchStatus = BranchStatus.OK,
    error_message: Optional[str] = None,
    delay_ms: float = 0.0,
    model_weights_path: Optional[Path] = None,
) -> SpoofResult:
    """
    Analyze call audio for voice cloning, deepfake, or replay attacks using AASIST.
    Dual-mode:
    - Real audio present -> runs AASIST neural network.
    - No real audio -> falls back to deterministic SHA-256 stub.
    - Errors / Insufficient audio -> fail-closed branch statuses.
    """
    start_time = time.time()

    # 1. Manual status override or degraded branch state
    if status != BranchStatus.OK:
        return SpoofResult(
            session_id=session_id,
            status=status,
            spoof_score=0.0,
            is_spoofed=False,
            model_version=MODEL_VERSION,
            confidence=0.0,
            processing_time_ms=delay_ms or 5.0,
            error_message=error_message or f"Branch execution state: {status.value}",
        )

    # 2. Score override (e.g. testing calibration thresholds)
    if override_score is not None:
        score = max(0.0, min(1.0, override_score))
        return SpoofResult(
            session_id=session_id,
            status=BranchStatus.OK,
            spoof_score=score,
            is_spoofed=score >= 0.60,
            model_version=MODEL_VERSION,
            confidence=0.95,
            processing_time_ms=delay_ms or 10.0,
        )

    # 3. Check VAD input validity from Phase 1
    if preprocessed_audio is not None and not preprocessed_audio.is_valid:
        return SpoofResult(
            session_id=session_id,
            status=BranchStatus.INSUFFICIENT_AUDIO,
            spoof_score=0.0,
            is_spoofed=False,
            model_version=MODEL_VERSION,
            confidence=0.0,
            processing_time_ms=delay_ms or 5.0,
            error_message="VAD determined audio is silent, corrupt, or insufficient",
        )

    # 4. Resolve audio file path
    target_path = ""
    if preprocessed_audio is not None and preprocessed_audio.features_path:
        if Path(preprocessed_audio.features_path).is_file():
            target_path = preprocessed_audio.features_path

    if not target_path and audio_path and Path(audio_path).is_file():
        target_path = audio_path

    # 5. Real AASIST inference if physical audio exists
    if target_path:
        try:
            model = get_aasist_model(weights_path=model_weights_path or DEFAULT_WEIGHTS_PATH)
            spoof_score, confidence, is_spoofed = run_aasist_inference(target_path, model=model)
            elapsed_ms = (time.time() - start_time) * 1000.0

            return SpoofResult(
                session_id=session_id,
                status=BranchStatus.OK,
                spoof_score=spoof_score,
                is_spoofed=is_spoofed,
                model_version=MODEL_VERSION,
                confidence=confidence,
                processing_time_ms=round(elapsed_ms, 2),
            )
        except Exception as e:
            logger.error("AASIST inference failed for session %s: %s", session_id, e)
            return SpoofResult(
                session_id=session_id,
                status=BranchStatus.FAILED,
                spoof_score=0.0,
                is_spoofed=False,
                model_version=MODEL_VERSION,
                confidence=0.0,
                processing_time_ms=0.0,
                error_message=f"AASIST inference failure: {e}",
            )

    # 6. Fallback to deterministic SHA-256 stub for simulated mock sessions
    from branches.antispoof.stub import analyze_spoof as stub_analyze
    result = stub_analyze(
        session_id=session_id,
        override_score=override_score,
        status=status,
        error_message=error_message,
        delay_ms=delay_ms,
    )
    result.model_version = MODEL_VERSION
    return result
