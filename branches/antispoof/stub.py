"""
Stub anti-spoofing branch returning mock SpoofResult.
Seeded deterministically using hashlib.sha256.
Model version tracks ASVspoof 5 baseline.
"""

import hashlib
from typing import Optional

from schemas.models import BranchStatus, SpoofResult


def _seed_score(session_id: str, salt: str = "antispoof") -> float:
    """Derive deterministic float score in [0.0, 1.0] from SHA-256."""
    h = hashlib.sha256(f"{salt}:{session_id}".encode("utf-8")).hexdigest()
    val = int(h[:16], 16)
    return round((val % 1000) / 1000.0, 3)


def analyze_spoof(
    session_id: str,
    override_score: Optional[float] = None,
    status: BranchStatus = BranchStatus.OK,
    error_message: Optional[str] = None,
    delay_ms: float = 0.0,
) -> SpoofResult:
    """Return deterministic mock SpoofResult using SHA-256 seeding."""
    if status != BranchStatus.OK:
        return SpoofResult(
            session_id=session_id,
            status=status,
            spoof_score=0.0,
            is_spoofed=False,
            model_version="aasist-asvspoof2019-v0",
            confidence=0.0,
            processing_time_ms=delay_ms or 5.0,
            error_message=error_message or f"Branch execution state: {status.value}",
        )

    score = max(0.0, min(1.0, override_score)) if override_score is not None else _seed_score(session_id)
    return SpoofResult(
        session_id=session_id,
        status=BranchStatus.OK,
        spoof_score=score,
        is_spoofed=score >= 0.60,
        model_version="aasist-asvspoof2019-v0",
        confidence=0.92,
        processing_time_ms=delay_ms or 12.0,
    )
