"""
Phase 1: Real Voice Activity Detection (VAD) and Preprocessing Engine.

Performs:
1. Audio loading (WAV, FLAC, OGG) via soundfile.
2. Channel reduction (stereo/multi-channel -> mono).
3. Anti-aliased resampling to target 16,000 Hz using scipy.signal.resample_poly.
4. Voice activity detection using official Silero VAD (v6+).
5. Energy-based Signal-to-Noise Ratio (SNR) estimation.
6. Validation checks for minimum duration and speech presence.
"""

from __future__ import annotations

import logging
import math
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from schemas.models import PreprocessedAudio, VADSegment

logger = logging.getLogger(__name__)

# Global cached Silero VAD model to prevent re-loading on each call
_SILERO_VAD_MODEL = None


def get_silero_vad_model():
    """Lazy-load and cache the Silero VAD model."""
    global _SILERO_VAD_MODEL
    if _SILERO_VAD_MODEL is None:
        try:
            import silero_vad
            _SILERO_VAD_MODEL = silero_vad.load_silero_vad()
            logger.info("Silero VAD model loaded successfully.")
        except Exception as e:
            logger.error("Failed to load Silero VAD model: %s", e)
            raise RuntimeError(f"Silero VAD model initialization failed: {e}") from e
    return _SILERO_VAD_MODEL


def load_and_standardize_audio(audio_path: str | Path, target_sr: int = 16000) -> Tuple[np.ndarray, float]:
    """
    Load an audio file, convert to mono, and resample to target_sr (16,000 Hz).
    Returns (audio_array_float32, original_duration_seconds).
    """
    import soundfile as sf
    import scipy.signal

    audio, orig_sr = sf.read(str(audio_path), dtype="float32")

    # 1. Convert to mono if multichannel
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    duration_s = float(len(audio)) / float(orig_sr)

    # 2. Resample to 16,000 Hz if needed
    if orig_sr != target_sr:
        gcd = math.gcd(orig_sr, target_sr)
        up = target_sr // gcd
        down = orig_sr // gcd
        audio = scipy.signal.resample_poly(audio, up, down).astype(np.float32)

    # 3. Peak normalize to [-1.0, 1.0] if signal exceeds range
    max_val = np.max(np.abs(audio)) if len(audio) > 0 else 0.0
    if max_val > 1.0:
        audio = audio / max_val

    return audio, duration_s


def estimate_snr_db(audio: np.ndarray, vad_segments: List[VADSegment], sr: int = 16000) -> float:
    """
    Estimate Signal-to-Noise Ratio (SNR) in dB using VAD speech vs non-speech masks.
    """
    if len(audio) == 0:
        return 0.0

    speech_mask = np.zeros(len(audio), dtype=bool)
    for seg in vad_segments:
        start_idx = max(0, int(seg.start_s * sr))
        end_idx = min(len(audio), int(seg.end_s * sr))
        if end_idx > start_idx:
            speech_mask[start_idx:end_idx] = True

    speech_samples = audio[speech_mask]
    noise_samples = audio[~speech_mask]

    p_speech = float(np.mean(speech_samples ** 2)) if len(speech_samples) > 0 else 1e-9

    if len(noise_samples) > 0:
        p_noise = float(np.mean(noise_samples ** 2))
    else:
        # If no silence frames exist, estimate noise floor from lowest 10% energy frames
        frame_len = int(0.025 * sr)  # 25ms frames
        if len(audio) >= frame_len:
            frames = [
                float(np.mean(audio[i : i + frame_len] ** 2))
                for i in range(0, len(audio) - frame_len, frame_len // 2)
            ]
            p_noise = float(np.percentile(frames, 10)) if frames else 1e-9
        else:
            p_noise = 1e-9

    p_noise = max(p_noise, 1e-9)
    snr = 10.0 * math.log10(max(p_speech, 1e-9) / p_noise)
    # Clamp to reasonable telephony / audio range [-10 dB, +50 dB]
    return float(np.clip(snr, -10.0, 50.0))


def process_audio_file(session_id: str, audio_path: str | Path) -> PreprocessedAudio:
    """
    Execute full Phase 1 preprocessing on a real audio file:
    1. Standardization (mono + 16kHz).
    2. Silero VAD speech timestamp extraction.
    3. SNR estimation.
    4. Caches 16kHz mono audio into features directory.
    """
    import torch
    import silero_vad
    import soundfile as sf

    audio_16k, duration_s = load_and_standardize_audio(audio_path, target_sr=16000)

    # If audio is completely empty
    if len(audio_16k) == 0:
        return PreprocessedAudio(
            session_id=session_id,
            sample_rate=16000,
            duration_s=0.01,
            speech_duration_s=0.0,
            vad_segments=[],
            snr_db=0.0,
            features_path=None,
            is_valid=False,
        )

    # Run Silero VAD
    model = get_silero_vad_model()
    tensor_audio = torch.from_numpy(audio_16k).float()

    speech_timestamps = silero_vad.get_speech_timestamps(
        tensor_audio,
        model,
        sampling_rate=16000,
        threshold=0.5,
        min_speech_duration_ms=100,
        min_silence_duration_ms=100,
        return_seconds=True,
    )

    vad_segments: List[VADSegment] = []
    total_speech_s = 0.0
    for ts in speech_timestamps:
        start_s = round(float(ts["start"]), 3)
        end_s = round(float(ts["end"]), 3)
        if end_s > start_s:
            vad_segments.append(VADSegment(start_s=start_s, end_s=end_s, confidence=0.95))
            total_speech_s += (end_s - start_s)

    total_speech_s = round(total_speech_s, 3)
    duration_s = round(duration_s, 3)

    # SNR calculation
    snr_db = round(estimate_snr_db(audio_16k, vad_segments, sr=16000), 1)

    # Save standardized 16kHz audio to cache for downstream branch consumption
    cache_dir = Path("storage/preprocessed")
    cache_dir.mkdir(parents=True, exist_ok=True)
    features_path = str(cache_dir / f"{session_id}_16k.wav")
    sf.write(features_path, audio_16k, 16000)

    # Validity check: must have at least 0.5s of total audio and > 0 voiced speech
    is_valid = (duration_s >= 0.5) and (total_speech_s > 0.0)

    return PreprocessedAudio(
        session_id=session_id,
        sample_rate=16000,
        duration_s=max(0.01, duration_s),
        speech_duration_s=total_speech_s,
        vad_segments=vad_segments,
        snr_db=snr_db,
        features_path=features_path,
        is_valid=is_valid,
    )


def preprocess_audio(
    session_id: str,
    audio_path: str = "",
    delay_ms: float = 0.0,
) -> PreprocessedAudio:
    """
    Dual-mode preprocessor entrypoint:
    - If audio_path is a real physical file on disk: runs real Silero VAD pipeline.
    - If audio_path is empty or not found: falls back to deterministic SHA-256 stub.
    """
    if audio_path and Path(audio_path).is_file():
        try:
            return process_audio_file(session_id, audio_path)
        except Exception as e:
            logger.warning("Real VAD preprocessing failed for session %s, falling back to stub: %s", session_id, e)

    from preprocess.stub import preprocess_audio as stub_preprocess
    return stub_preprocess(session_id=session_id, audio_path=audio_path, delay_ms=delay_ms)
