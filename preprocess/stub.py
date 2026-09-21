"""Stub preprocessor returning mock PreprocessedAudio using hashlib.sha256 seeding."""

import hashlib
from schemas.models import PreprocessedAudio, VADSegment


def _seed_fraction(seed_str: str) -> float:
    """Derive deterministic float in [0.0, 1.0) using SHA-256."""
    h = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    # Use first 8 bytes (16 hex chars)
    val = int(h[:16], 16)
    return (val % 10000) / 10000.0


def preprocess_audio(
    session_id: str,
    audio_path: str = "",
    delay_ms: float = 0.0,
) -> PreprocessedAudio:
    """Return deterministic mock PreprocessedAudio seeded via hashlib.sha256."""
    frac = _seed_fraction(f"preprocess:{session_id}")
    duration = 5.0 + (frac * 25.0)  # 5.0 - 30.0 seconds
    speech_duration = max(1.0, duration - 1.0)
    snr = 10.0 + (frac * 30.0)      # 10.0 - 40.0 dB

    return PreprocessedAudio(
        session_id=session_id,
        sample_rate=16000,
        duration_s=round(duration, 2),
        speech_duration_s=round(speech_duration, 2),
        vad_segments=[
            VADSegment(start_s=0.5, end_s=round(duration - 0.5, 2), confidence=0.95),
        ],
        snr_db=round(snr, 1),
        features_path=f"/encrypted_storage/features/{session_id}.npy",
        is_valid=True,
    )
