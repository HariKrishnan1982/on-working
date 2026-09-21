"""Anti-spoofing and deepfake voice detection branch (AASIST)."""

from branches.antispoof.aasist import analyze_spoof, run_aasist_inference, get_aasist_model

__all__ = ["analyze_spoof", "run_aasist_inference", "get_aasist_model"]
