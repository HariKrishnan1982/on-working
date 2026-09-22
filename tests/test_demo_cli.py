"""
Smoke tests for the demo CLI (demo.py).

These tests verify that the CLI wires together all pipeline stages correctly
and doesn't crash — they are NOT re-testing branch-level correctness (that's
covered exhaustively in test_aasist.py, test_ecapa.py, test_asr_intent.py, etc.).

Test scope:
1. Bonafide audio processes end-to-end and exits 0.
2. Scam audio processes end-to-end, exits 0, and output contains BLOCK / scam indicators.
3. Missing audio file exits non-zero with a clear error message.
4. --json flag produces valid parseable JSON output.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_SCRIPT = PROJECT_ROOT / "demo.py"
BONAFIDE_WAV = PROJECT_ROOT / "test_vectors" / "audio" / "bonafide_sample.wav"
SCAM_WAV = PROJECT_ROOT / "test_vectors" / "audio" / "scam_sample.wav"


def _run_demo(*args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    """Run demo.py and capture output."""
    cmd = [sys.executable, str(DEMO_SCRIPT), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=timeout,
    )


def test_demo_cli_bonafide_sample_exits_zero():
    """
    Bonafide audio (real human speech) processes through all 7 stages and exits 0.
    The output should show BONA-FIDE detection and BENIGN scam intent.
    """
    result = _run_demo(str(BONAFIDE_WAV), "--no-color")
    assert result.returncode == 0, f"Demo failed with stderr:\n{result.stderr}"

    out = result.stdout
    # Phase 1 ran
    assert "Voice Activity Detection" in out or "VAD" in out or "Speech Segments" in out
    # Phase 2 ran and detected bonafide
    assert "BONA-FIDE" in out or "bonafide" in out.lower()
    # Phase 4 ran and detected benign intent
    assert "BENIGN" in out
    # Audit trail section appeared
    assert "Audit Trail" in out or "Decision SHA-256" in out
    # Pipeline completed with a final action
    assert "FINAL SYSTEM ACTION" in out


def test_demo_cli_scam_sample_detected_and_blocked():
    """
    Scam audio (TTS police impersonation) processes through all stages, exits 0,
    and is correctly identified as a scam / spoofed call with BLOCK or ESCALATE action.
    """
    result = _run_demo(str(SCAM_WAV), "--no-color")
    assert result.returncode == 0, f"Demo failed with stderr:\n{result.stderr}"

    out = result.stdout
    # Phase 2: detected as spoofed
    assert "SPOOFED" in out or "SYNTHETIC" in out
    # Phase 4: scam confirmed
    assert "SCAM" in out
    # Scam indicators fired
    assert "impersonation_language" in out or "financial_pressure" in out
    # Final action is BLOCK or ESCALATE (not ALLOW)
    assert "BLOCK" in out or "ESCALATE" in out
    assert "ALLOW" not in out.split("FINAL SYSTEM ACTION")[-1]


def test_demo_cli_missing_file_exits_nonzero():
    """Missing audio file produces a clear error and exits non-zero."""
    result = _run_demo("nonexistent_audio_file_12345.wav", "--no-color")
    assert result.returncode != 0


def test_demo_cli_json_flag_produces_valid_json():
    """--json flag outputs valid parseable JSON with expected structure."""
    result = _run_demo(str(BONAFIDE_WAV), "--json")
    assert result.returncode == 0, f"Demo --json failed with stderr:\n{result.stderr}"

    data = json.loads(result.stdout)
    assert "session_id" in data
    assert "timing_ms" in data
    assert "decision" in data
    assert "audit" in data
    assert data["timing_ms"]["total_elapsed_ms"] > 0
    assert data["decision"]["action"] in ["ALLOW", "FLAG", "ESCALATE", "BLOCK"]
    assert data["audit"]["decision_hash"]
