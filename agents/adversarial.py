"""Adversarial Agent — responsible for red-teaming.

This agent applies adversarial perturbations to test the robustness
of the pipeline.

Phase 5: Structural definition.
"""

AGENT_CONFIG = {
    "name": "adversarial",
    "description": "Applies codec, noise, and RawBoost perturbations to audio",
    "mcp_tools": ["run_full_analysis"],
    "responsibilities": [
        "Perturb input audio",
        "Re-run pipeline to observe score drift",
        "Report robustness metrics",
    ],
}
