"""Speaker verification branch (ECAPA-TDNN)."""

from branches.speaker.ecapa import (
    MODEL_VERSION,
    compute_similarity,
    extract_embedding,
    get_ecapa_classifier,
    verify_speaker,
)
from branches.speaker.registry import SpeakerEnrollmentStore, get_enrollment_store

__all__ = [
    "verify_speaker",
    "extract_embedding",
    "compute_similarity",
    "get_ecapa_classifier",
    "SpeakerEnrollmentStore",
    "get_enrollment_store",
    "MODEL_VERSION",
]
