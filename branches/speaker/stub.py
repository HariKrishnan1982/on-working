"""
Stub speaker verification branch returning mock SpeakerResult.
Seeded deterministically using hashlib.sha256.
Normalizes raw ECAPA cosine similarity into [0.0, 1.0] contract range.
"""

import hashlib
from typing import Optional

from schemas.models import BranchStatus, SpeakerResult, normalize_ecapa_cosine


def _seed_cosine(session_id: str, salt: str = "speaker") -> float:
    """Derive deterministic raw cosine similarity in [-1.0, 1.0] from SHA-256."""
    h = hashlib.sha256(f"{salt}:{session_id}".encode("utf-8")).hexdigest()
    val = int(h[:16], 16)
    # Map into range [-0.5, 0.95] representing typical speaker embeddings
    scaled = -0.5 + ((val % 1450) / 1000.0)
    return round(max(-1.0, min(1.0, scaled)), 3)


def verify_speaker(
    session_id: str,
    claimed_identity: Optional[str] = "unknown",
    override_score: Optional[float] = None,
    override_raw_cosine: Optional[float] = None,
    status: BranchStatus = BranchStatus.OK,
    error_message: Optional[str] = None,
    delay_ms: float = 0.0,
) -> SpeakerResult:
    """Return deterministic mock SpeakerResult with normalized similarity score."""
    threshold = 0.65

    # If caller has no claimed identity, mark as NOT_ENROLLED
    if claimed_identity is None or claimed_identity == "":
        status = BranchStatus.NOT_ENROLLED

    if status != BranchStatus.OK:
        return SpeakerResult(
            session_id=session_id,
            status=status,
            similarity_score=0.0,
            raw_cosine=None,
            is_match=False,
            claimed_identity=claimed_identity,
            threshold_used=threshold,
            model_version="ecapa-tdnn-voxceleb-v0",
            processing_time_ms=delay_ms or 5.0,
            error_message=error_message or f"Speaker branch state: {status.value}",
        )

    if override_score is not None:
        norm_score = max(0.0, min(1.0, override_score))
        raw_cos = override_raw_cosine if override_raw_cosine is not None else (norm_score * 2.0 - 1.0)
    elif override_raw_cosine is not None:
        raw_cos = override_raw_cosine
        norm_score = normalize_ecapa_cosine(raw_cos)
    else:
        raw_cos = _seed_cosine(session_id)
        norm_score = normalize_ecapa_cosine(raw_cos)

    # Derive embedding hash and pointer deterministically
    emb_hash = hashlib.sha256(f"emb:{session_id}".encode("utf-8")).hexdigest()

    return SpeakerResult(
        session_id=session_id,
        status=BranchStatus.OK,
        similarity_score=round(norm_score, 3),
        raw_cosine=round(raw_cos, 3),
        is_match=norm_score >= threshold,
        claimed_identity=claimed_identity,
        threshold_used=threshold,
        embedding_hash_sha256=emb_hash,
        embedding_ref=f"/encrypted_storage/embeddings/{session_id}.enc",
        model_version="ecapa-tdnn-voxceleb-v0",
        processing_time_ms=delay_ms or 15.0,
    )
