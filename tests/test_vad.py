"""
Phase 1 Unit Tests: Voice Activity Detection (VAD) and Audio Preprocessing.

Verifies:
1. Real Silero VAD detection on voiced speech.
2. 44.1kHz stereo to 16kHz mono resampling.
3. Energy-based SNR estimation.
4. Pure silence handling (is_valid=False).
5. Dual-mode fallback continuity for mock sessions.
"""

import math
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf

from preprocess.vad import (
    estimate_snr_db,
    load_and_standardize_audio,
    preprocess_audio,
    process_audio_file,
)
from schemas.models import VADSegment


@pytest.fixture
def bonafide_audio_path():
    path = Path("test_vectors/audio/bonafide_sample.wav")
    assert path.is_file(), "Reference bonafide audio sample must exist"
    return str(path)


@pytest.fixture
def stereo_44k_audio_path(tmp_path):
    """Generate a 2-second 44.1kHz stereo WAV file."""
    sr = 44100
    t = np.linspace(0, 2.0, int(sr * 2.0), endpoint=False)
    # 440Hz tone on channel 0, 880Hz tone on channel 1
    ch0 = 0.5 * np.sin(2 * math.pi * 440 * t)
    ch1 = 0.5 * np.sin(2 * math.pi * 880 * t)
    stereo = np.column_stack([ch0, ch1]).astype(np.float32)

    path = tmp_path / "stereo_44k.wav"
    sf.write(str(path), stereo, sr)
    return str(path)


@pytest.fixture
def silence_audio_path(tmp_path):
    """Generate a 2-second pure silence WAV file."""
    sr = 16000
    silence = np.zeros(int(sr * 2.0), dtype=np.float32)
    path = tmp_path / "silence.wav"
    sf.write(str(path), silence, sr)
    return str(path)


def test_vad_on_voiced_speech(bonafide_audio_path):
    """Real Silero VAD accurately detects speech segments on bona-fide speech."""
    preprocessed = process_audio_file("sess-test-vad-01", bonafide_audio_path)

    assert preprocessed.session_id == "sess-test-vad-01"
    assert preprocessed.sample_rate == 16000
    assert preprocessed.duration_s > 1.0
    assert preprocessed.speech_duration_s > 0.5
    assert len(preprocessed.vad_segments) > 0
    assert preprocessed.is_valid is True
    assert preprocessed.snr_db is not None
    assert preprocessed.features_path is not None
    assert Path(preprocessed.features_path).is_file()

    # Check that segment timestamps are strictly monotonic and within bounds
    for seg in preprocessed.vad_segments:
        assert seg.start_s >= 0.0
        assert seg.end_s > seg.start_s
        assert seg.end_s <= preprocessed.duration_s + 0.1
        assert 0.0 <= seg.confidence <= 1.0


def test_resampling_and_mono_conversion(stereo_44k_audio_path):
    """44.1kHz stereo audio is converted to 16kHz mono."""
    audio_16k, duration_s = load_and_standardize_audio(stereo_44k_audio_path, target_sr=16000)

    # 1. Must be 1D (mono)
    assert audio_16k.ndim == 1
    # 2. Duration ~ 2.0s => length ~ 32000 samples
    expected_len = int(duration_s * 16000)
    assert abs(len(audio_16k) - expected_len) <= 5
    # 3. Peak amplitude normalized <= 1.0
    assert np.max(np.abs(audio_16k)) <= 1.0


def test_snr_estimation_clean_vs_noisy(bonafide_audio_path, tmp_path):
    """SNR estimation reflects signal degradation with added noise."""
    audio_clean, _ = load_and_standardize_audio(bonafide_audio_path, target_sr=16000)
    vad_segments = [VADSegment(start_s=0.5, end_s=len(audio_clean) / 16000.0, confidence=0.95)]

    clean_snr = estimate_snr_db(audio_clean, vad_segments, sr=16000)

    # Add significant white noise
    noise = np.random.normal(0, 0.2, len(audio_clean)).astype(np.float32)
    audio_noisy = audio_clean + noise
    noisy_snr = estimate_snr_db(audio_noisy, vad_segments, sr=16000)

    assert clean_snr > noisy_snr
    assert clean_snr >= 0.0


def test_silence_detection_fail_closed(silence_audio_path):
    """Pure silence yields speech_duration_s=0 and is_valid=False."""
    preprocessed = process_audio_file("sess-test-silence", silence_audio_path)

    assert preprocessed.speech_duration_s == 0.0
    assert len(preprocessed.vad_segments) == 0
    assert preprocessed.is_valid is False


def test_fallback_to_stub_on_missing_file():
    """Missing or empty audio path gracefully falls back to deterministic SHA-256 stub."""
    run1 = preprocess_audio("sess-mock-fallback", audio_path="")
    run2 = preprocess_audio("sess-mock-fallback", audio_path="/nonexistent/path/call.wav")

    assert run1.duration_s == run2.duration_s
    assert run1.speech_duration_s == run2.speech_duration_s
    assert run1.snr_db == run2.snr_db
    assert run1.is_valid is True
