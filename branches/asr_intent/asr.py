"""
Faster-Whisper Speech-to-Text Module.

Engine: faster-whisper (CTranslate2 INT8 quantization on CPU).
Supported Languages: English (en), Hindi (hi), Tamil (ta), Telugu (te), and 95+ others.

Known Limitation & Named Upgrade Path:
- Accuracy Tradeoff: Generic Whisper has higher Word Error Rate (WER) on Dravidian
  languages (Tamil, Telugu) than on Indo-Aryan / English (Hindi, English) due to training
  corpus distribution.
- Named Upgrade Path: Fine-tuning or converting AI4Bharat's IndicWhisper (ai4bharat/indicwhisper-v2)
  via ct2-transformers-converter with IndicNLP token normalization for GPU production deployment.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional, Tuple

from faster_whisper import WhisperModel

from schemas.models import Language

logger = logging.getLogger(__name__)

# Suppress HuggingFace symlinks warning on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

DEFAULT_WHISPER_DIR = Path("models/weights/whisper")
DEFAULT_MODEL_SIZE = "base"

_CACHED_ASR_MODEL: Optional[WhisperModel] = None

# Language mapping from ISO code to Language enum
_LANG_MAP = {
    "en": Language.EN,
    "hi": Language.HI,
    "ta": Language.TA,
    "te": Language.TE,
    "ml": Language.ML,
    "kn": Language.KN,
}


def get_asr_model(
    model_size: str = DEFAULT_MODEL_SIZE,
    download_root: Path = DEFAULT_WHISPER_DIR,
) -> WhisperModel:
    """Lazy-load and cache the faster-whisper model."""
    global _CACHED_ASR_MODEL

    # Bypass cache if a custom or test directory is passed
    if model_size != DEFAULT_MODEL_SIZE or Path(download_root) != DEFAULT_WHISPER_DIR:
        return WhisperModel(
            model_size_or_path=model_size,
            device="cpu",
            compute_type="int8",
            download_root=str(download_root),
        )

    if _CACHED_ASR_MODEL is not None:
        return _CACHED_ASR_MODEL

    try:
        model = WhisperModel(
            model_size_or_path=model_size,
            device="cpu",
            compute_type="int8",
            download_root=str(download_root),
        )
        _CACHED_ASR_MODEL = model
        logger.info("Faster-Whisper (%s) model loaded successfully.", model_size)
        return _CACHED_ASR_MODEL
    except Exception as e:
        logger.error("Failed to load Faster-Whisper model (%s): %s", model_size, e)
        raise RuntimeError(f"Faster-Whisper model loading failed: {e}") from e


def transcribe_audio(
    audio_path: str | Path,
    model: Optional[WhisperModel] = None,
    language_hint: Optional[Language] = None,
) -> Tuple[str, Language, float]:
    """
    Transcribe audio file using faster-whisper.

    Returns:
        Tuple[str, Language, float]: (transcript, detected_language, duration_ms)
    """
    start_time = time.time()
    asr = model or get_asr_model()

    lang_code = None
    if language_hint:
        lang_code = language_hint.value.lower()

    segments, info = asr.transcribe(
        str(audio_path),
        beam_size=5,
        language=lang_code,
    )

    text_parts = [segment.text.strip() for segment in segments if segment.text.strip()]
    full_transcript = " ".join(text_parts).strip()

    detected_lang = _LANG_MAP.get(info.language)
    if detected_lang is None:
        detected_lang = language_hint or Language.EN

    elapsed_ms = (time.time() - start_time) * 1000.0
    return full_transcript, detected_lang, elapsed_ms
