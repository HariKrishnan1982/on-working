"""Voice Deepfake Agent — responsible for anti-spoofing.

This agent uses the MCP server's anti-spoofing tools to determine
whether a caller's voice is synthetic, cloned, or played back.

Phase 0: Structural definition only.
"""

AGENT_CONFIG = {
    "name": "voice_deepfake",
    "description": "Detects voice deepfakes and spoofing attacks",
    "mcp_tools": ["run_antispoof"],
    "responsibilities": [
        "Analyze audio for synthetic generation artifacts",
        "Detect replay attacks",
        "Report spoofing probability scores",
    ],
}
