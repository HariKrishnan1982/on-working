"""
Intent Classifier Interface.

Provides a pluggable contract for conversational scam-intent classification.
Phase 0/4 starts with deterministic keyword/regex rules, allowing seamless
upgrade to fine-tuned multilingual transformer models (e.g. IndicBERT) later.
"""

from abc import ABC, abstractmethod
from typing import Tuple

from schemas.models import IntentCategory, Language


class IntentClassifier(ABC):
    """Abstract interface for analyzing transcript text for scam intent."""

    @abstractmethod
    def classify(self, transcript: str, language: Language) -> Tuple[float, IntentCategory, list[str]]:
        """
        Classify transcript text.

        Returns:
            Tuple[float, IntentCategory, list[str]]:
                - scam_score: float in [0.0, 1.0] (higher = more fraudulent)
                - category: IntentCategory
                - indicators: list of detected warning patterns/phrases
        """
        pass
