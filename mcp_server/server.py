"""
Unified Security MCP Server — Agent Tool Facade.

Acts strictly as a facade exposing verification tools to autonomous agents
(Voice Identity, Voice Deepfake, Context & Fraud, Adversarial).
Delegates all execution directly to the deterministic PipelineService.
No agent or LLM participates in or influences the deterministic decision path.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from branches.antispoof.stub import analyze_spoof
from branches.asr_intent.stub import analyze_intent
from branches.speaker.stub import verify_speaker
from gateway.session import create_session
from schemas.models import Language
from services.pipeline_service import PipelineService

try:
    from mcp.server.fastmcp import FastMCP
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

pipeline_service = PipelineService()


def run_pipeline_facade(
    session_id: str,
    caller_id: str = "+910000000000",
    audio_path: str = "/default.wav",
    claimed_identity: Optional[str] = "unknown",
    language_hint: str = "EN",
) -> dict:
    """Facade helper for full pipeline execution via shared service."""
    lang = Language(language_hint) if language_hint in Language.__members__ else Language.EN
    session = create_session(
        caller_id=caller_id,
        audio_path=audio_path,
        claimed_identity=claimed_identity,
        language_hint=lang,
    )
    # Set explicit session ID
    session.session_id = session_id
    decision = pipeline_service.process_call_session(session)
    return decision.model_dump(mode="json")


if MCP_AVAILABLE:
    mcp = FastMCP("VoiceFraudUnifiedMCP")

    @mcp.tool()
    def tool_verify_speaker(session_id: str, claimed_identity: str = "unknown") -> dict:
        """Verify if speaker matches claimed identity via ECAPA-TDNN."""
        res = verify_speaker(session_id, claimed_identity=claimed_identity)
        return res.model_dump(mode="json")

    @mcp.tool()
    def tool_detect_spoof(session_id: str) -> dict:
        """Analyze audio for synthetic speech / deepfake artifacts via AASIST."""
        res = analyze_spoof(session_id)
        return res.model_dump(mode="json")

    @mcp.tool()
    def tool_analyze_intent(session_id: str, language_hint: str = "EN") -> dict:
        """Transcribe and classify scam intent markers via Whisper/Rules."""
        lang = Language(language_hint) if language_hint in Language.__members__ else Language.EN
        res = analyze_intent(session_id, language_hint=lang)
        return res.model_dump(mode="json")

    @mcp.tool()
    def tool_run_full_analysis(
        session_id: str,
        caller_id: str = "+910000000000",
        audio_path: str = "/default.wav",
        claimed_identity: Optional[str] = "unknown",
        language_hint: str = "EN",
    ) -> dict:
        """Run complete deterministic voice-fraud pipeline via PipelineService."""
        return run_pipeline_facade(session_id, caller_id, audio_path, claimed_identity, language_hint)

    if __name__ == "__main__":
        mcp.run(transport="stdio")
