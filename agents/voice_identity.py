"""Voice Identity Agent — responsible for speaker verification.

This agent uses the MCP server's speaker verification tools to determine
whether a caller's voice matches their claimed identity.

Phase 0: Structural definition only. Full agent logic in Phase 3+.
"""

AGENT_CONFIG = {
    "name": "voice_identity",
    "description": "Verifies caller identity using ECAPA-TDNN speaker embeddings",
    "mcp_tools": ["run_speaker_verification"],
    "responsibilities": [
        "Extract speaker embeddings from call audio",
        "Compare against enrolled speaker profiles",
        "Report similarity scores and match decisions",
    ],
}
