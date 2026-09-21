"""
Multilingual Scam-Intent Scanner.

Detects telecommunication fraud, digital arrest, financial coercion, and urgency
patterns across English, Hindi, Tamil, and Telugu (including code-switched Hinglish).

Adheres strictly to the IntentClassifier interface.
Uses regex word boundaries for Romanized keywords to prevent substring false-positives.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from branches.asr_intent.interface import IntentClassifier
from schemas.models import IntentCategory, Language


class RuleBasedIntentClassifier(IntentClassifier):
    """
    Multilingual and code-switched rule-based scam intent classifier.
    """

    # Structured keywords categorized by fraud vector
    KEYWORDS: Dict[str, List[str]] = {
        "urgent_request": [
            # English
            r"\bimmediately\b", r"\burgent\b", r"\bright now\b", r"\bact now\b",
            r"\bwithin (?:10|5|15|30) minutes\b", r"\bhurry\b", r"\bemergency\b",
            # Hindi (Devanagari + Hinglish)
            "तुरंत", "जल्दी", "अभी", "जलदी", r"\bturant\b", r"\bjaldi\b", r"\bfauran\b", r"\babhi\b",
            # Tamil (Script + Romanized)
            "உடனடியாக", "இப்போதே", "சீக்கிரம்", r"\budanadiyaga\b", r"\bseekiram\b",
            # Telugu (Script + Romanized)
            "వెంటనే", "త్వరగా", "ఇప్పుడే", r"\bventane\b", r"\btvaraga\b", r"\bippude\b",
        ],
        "financial_pressure": [
            # English
            r"\botp\b", r"\bone[ -]time password\b", r"\bcvv\b", r"\bpin\b", r"\bpassword\b",
            r"\bbank transfer\b", r"\bkyc expired\b", r"\baccount blocked\b", r"\baccount freeze\b",
            r"\bcredit card\b", r"\bdebit card\b", r"\belectricity bill\b", r"\bsim deactivation\b",
            # Hindi (Devanagari + Hinglish)
            "ओटीपी", "खाता", "बैंक", "पैसे", "ट्रांसफर", "केवाईसी", "पिन",
            r"\bkhata\b", r"\bpaise\b", r"\brokda\b", r"\btransfer\b", r"\bband ho jayega\b",
            # Tamil (Script + Romanized)
            "கணக்கு", "ஓடிபி", "வங்கி", "பணம்", "கடவுச்சொல்",
            r"\bkanakku\b", r"\bvangi\b", r"\bpanam\b",
            # Telugu (Script + Romanized)
            "ఖాతా", "ఓటీపీ", "బ్యాంకు", "డబ్బులు", "రహస్య కోడ్",
            r"\bkhata\b", r"\bdabbu\b", r"\bbanku\b",
        ],
        "impersonation_language": [
            # English
            r"\bpolice\b", r"\bcbi\b", r"\brbi\b", r"\btrai\b", r"\benforcement directorate\b",
            r"\bed officer\b", r"\btax authority\b", r"\bcustoms\b", r"\bcyber cell\b",
            r"\bofficer\b", r"\barrest warrant\b", r"\bdigital arrest\b", r"\bcourt order\b",
            r"\bnarcotics\b", r"\bfedex courier\b", r"\billegal parcel\b",
            # Hindi (Devanagari + Hinglish)
            "पुलिस", "सीबीआई", "आरबीआई", "कस्टम्स", "अधिकारी", "वारंट", "गिरफ्तार", "अदालत",
            r"\bdaroga\b", r"\bthana\b", r"\badhikari\b", r"\bgirtaar\b",
            # Tamil (Script + Romanized)
            "காவல்துறை", "போலீஸ்", "அதிகாரி", "நீதிமன்றம்", "கைது",
            r"\bpolice\b", r"\badhikari\b",
            # Telugu (Script + Romanized)
            "పోలీస్", "అధికారి", "కోర్టు", "అరెస్ట్",
            r"\bpolice\b", r"\badhikari\b",
        ],
    }

    def __init__(self) -> None:
        # Precompile regex patterns
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}
        for category, patterns in self.KEYWORDS.items():
            compiled = []
            for p in patterns:
                # If regex pattern with word boundaries or special characters, compile with IGNORECASE
                if "\\" in p:
                    compiled.append(re.compile(p, re.IGNORECASE))
                else:
                    # Literal string match (e.g. Indic script)
                    compiled.append(re.compile(re.escape(p), re.IGNORECASE))
            self._compiled_patterns[category] = compiled

    def classify(self, transcript: str, language: Language = Language.EN) -> Tuple[float, IntentCategory, list[str]]:
        """
        Classify transcript text across multilingual fraud markers.

        Returns:
            Tuple[float, IntentCategory, list[str]]:
                - scam_score: float in [0.0, 1.0]
                - category: IntentCategory
                - indicators: list of detected warning categories
        """
        if not transcript or not transcript.strip():
            return 0.0, IntentCategory.BENIGN, []

        indicators: List[str] = []
        text = transcript.strip()

        for pattern_name, regex_list in self._compiled_patterns.items():
            for regex in regex_list:
                if regex.search(text):
                    indicators.append(pattern_name)
                    break  # One hit per category is sufficient

        # Multi-signal cumulative scoring
        has_impersonation = "impersonation_language" in indicators
        has_financial = "financial_pressure" in indicators
        has_urgent = "urgent_request" in indicators

        if has_impersonation and (has_financial or has_urgent):
            score = 0.85
            category = IntentCategory.SCAM_CONFIRMED
        elif has_financial and has_urgent:
            score = 0.75
            category = IntentCategory.SCAM_CONFIRMED
        elif has_financial or has_urgent:
            score = 0.55
            category = IntentCategory.SCAM_LIKELY
        elif has_impersonation:
            score = 0.45
            category = IntentCategory.SUSPICIOUS
        elif indicators:
            score = 0.35
            category = IntentCategory.SUSPICIOUS
        else:
            score = 0.10
            category = IntentCategory.BENIGN

        return score, category, indicators


# Singleton scanner instance
_default_scanner = RuleBasedIntentClassifier()


def get_default_scanner() -> RuleBasedIntentClassifier:
    """Return singleton scanner instance."""
    return _default_scanner
