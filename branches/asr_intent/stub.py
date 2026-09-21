"""
Stub ASR + scam-intent analysis branch returning mock IntentResult.
Seeded deterministically using hashlib.sha256.
Implements RuleBasedIntentClassifier adhering to IntentClassifier interface.
"""

import hashlib
from typing import Optional, Tuple

from branches.asr_intent.interface import IntentClassifier
from schemas.models import BranchStatus, IntentCategory, IntentResult, Language


class RuleBasedIntentClassifier(IntentClassifier):
    """Rule-based scam-intent classifier scanning for urgent and financial fraud markers."""

    KEYWORDS = {
        "urgent_request": ["immediately", "urgent", "right now", "act now", "जलदी", "உடனடியாக"],
        "financial_pressure": ["otp", "bank transfer", "kyc expired", "account blocked", "खाता", "கணக்கு"],
        "impersonation_language": ["police", "cbi", "tax authority", "customs", "officer", "अधिकारी"],
    }

    def classify(self, transcript: str, language: Language) -> Tuple[float, IntentCategory, list[str]]:
        lower = transcript.lower()
        indicators = []
        score = 0.0

        for pattern_name, words in self.KEYWORDS.items():
            if any(w in lower for w in words):
                indicators.append(pattern_name)

        if "impersonation_language" in indicators and "financial_pressure" in indicators:
            score = 0.85
            category = IntentCategory.SCAM_CONFIRMED
        elif "financial_pressure" in indicators or "urgent_request" in indicators:
            score = 0.65
            category = IntentCategory.SCAM_LIKELY
        elif indicators:
            score = 0.35
            category = IntentCategory.SUSPICIOUS
        else:
            score = 0.10
            category = IntentCategory.BENIGN

        return score, category, indicators


_classifier = RuleBasedIntentClassifier()


def _seed_score(session_id: str, salt: str = "asr_intent") -> float:
    """Derive deterministic float in [0.0, 1.0] from SHA-256."""
    h = hashlib.sha256(f"{salt}:{session_id}".encode("utf-8")).hexdigest()
    val = int(h[:16], 16)
    return round((val % 1000) / 1000.0, 3)


def analyze_intent(
    session_id: str,
    language_hint: Language = Language.EN,
    transcript_override: Optional[str] = None,
    override_scam_score: Optional[float] = None,
    status: BranchStatus = BranchStatus.OK,
    error_message: Optional[str] = None,
    delay_ms: float = 0.0,
) -> IntentResult:
    """Return deterministic mock IntentResult using SHA-256 seeding."""
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
            model_version="whisper-largev3-rules-v0",
            processing_time_ms=delay_ms or 5.0,
            error_message=error_message or f"ASR intent branch state: {status.value}",
        )

    transcript = transcript_override or "This is an automated verification call regarding your account."
    transcript_hash = hashlib.sha256(transcript.encode("utf-8")).hexdigest()

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
    elif transcript_override is not None:
        score, category, indicators = _classifier.classify(transcript, language_hint)
    else:
        score = _seed_score(session_id)
        if score >= 0.80:
            category = IntentCategory.SCAM_CONFIRMED
            indicators = ["impersonation_language", "financial_pressure"]
        elif score >= 0.50:
            category = IntentCategory.SCAM_LIKELY
            indicators = ["urgent_request"]
        elif score >= 0.30:
            category = IntentCategory.SUSPICIOUS
            indicators = []
        else:
            category = IntentCategory.BENIGN
            indicators = []

    return IntentResult(
        session_id=session_id,
        status=BranchStatus.OK,
        transcript=transcript,
        transcript_hash_sha256=transcript_hash,
        transcript_ref=f"/encrypted_storage/transcripts/{session_id}.txt",
        language_detected=language_hint,
        scam_score=round(score, 3),
        scam_indicators=indicators,
        intent_category=category,
        model_version="whisper-largev3-rules-v0",
        processing_time_ms=delay_ms or 25.0,
    )
