"""Context Fraud Agent — responsible for ASR and intent analysis.

This agent uses the MCP server's intent analysis tools to transcribe
and detect scam or fraudulent intents.

Phase 0: Structural definition only.
"""

AGENT_CONFIG = {
    "name": "context_fraud",
    "description": "Transcribes audio and detects fraudulent intent",
    "mcp_tools": ["run_intent_analysis"],
    "responsibilities": [
        "Transcribe audio using Whisper",
        "Analyze transcript for scam keywords and patterns",
        "Report intent probability scores",
    ],
}
