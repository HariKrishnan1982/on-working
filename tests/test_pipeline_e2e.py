"""
End-to-end integration tests for the FastAPI Gateway.

Covers:
- API-Key security verification (401 on missing/invalid key)
- Upload size and MIME-type restrictions
- Synchronous POST /analyze endpoint
- Asynchronous POST /jobs & GET /jobs/{job_id} workflow
- Unauthenticated GET /health
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import io
import pytest
from fastapi.testclient import TestClient

from configs.settings import settings
from gateway.app import app

client = TestClient(app)

VALID_HEADERS = {"X-API-Key": settings.api_key}


def test_health_check():
    """Health check is publicly accessible without API key."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_api_key_required():
    """Requests without valid X-API-Key must be rejected with 401."""
    res = client.post("/analyze", json={"caller_id": "+91123", "audio_path": "/call.wav"})
    assert res.status_code == 401

    res_bad = client.post(
        "/analyze",
        json={"caller_id": "+91123", "audio_path": "/call.wav"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert res_bad.status_code == 401


def test_analyze_call_sync_with_api_key():
    """Direct sync analysis returns full RiskDecision with versioning and fired rules."""
    payload = {
        "caller_id": "+919876543210",
        "audio_path": "/data/audio/sample_hindi.wav",
        "claimed_identity": "user_priya",
        "language_hint": "HI",
    }
    res = client.post("/analyze", json=payload, headers=VALID_HEADERS)
    assert res.status_code == 200
    data = res.json()

    assert "risk_level" in data
    assert "action" in data
    assert "fired_rules" in data
    assert "reasons" in data
    assert "rules_version" in data
    assert "model_versions" in data
    assert "fused_evidence" in data
    assert data["fused_evidence"]["spoof_result"]["status"] == "ok"


def test_async_job_api_flow():
    """Verify asynchronous job creation (202) and retrieval workflow."""
    # 1. Create Job
    job_payload = {
        "caller_id": "+919876543210",
        "claimed_identity": "user_aarav",
        "language_hint": "HI",
        "audio_path": "/data/audio/call_async.wav",
    }
    create_res = client.post("/jobs", data=job_payload, headers=VALID_HEADERS)
    assert create_res.status_code == 202
    job_info = create_res.json()
    job_id = job_info["job_id"]
    assert job_info["status"] in ["PENDING", "PROCESSING", "COMPLETED"]

    # 2. Retrieve Job Status
    get_res = client.get(f"/jobs/{job_id}", headers=VALID_HEADERS)
    assert get_res.status_code == 200
    status_data = get_res.json()
    assert status_data["job_id"] == job_id
    assert status_data["status"] == "COMPLETED"
    assert status_data["decision"] is not None
    assert status_data["decision"]["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def test_file_upload_type_restriction():
    """Verify gateway rejects unapproved MIME types."""
    bad_file = io.BytesIO(b"executable content")
    res = client.post(
        "/jobs",
        data={"caller_id": "+919876543210"},
        files={"audio_file": ("malware.exe", bad_file, "application/x-msdownload")},
        headers=VALID_HEADERS,
    )
    assert res.status_code == 415
    assert "is not allowed" in res.json()["detail"]


def test_file_upload_valid_audio():
    """Verify valid audio file upload succeeds through async job API."""
    wav_content = b"RIFF....WAVEfmt ...."
    audio_file = io.BytesIO(wav_content)
    res = client.post(
        "/jobs",
        data={"caller_id": "+919876543210", "claimed_identity": "user_kavita"},
        files={"audio_file": ("test_recording.wav", audio_file, "audio/wav")},
        headers=VALID_HEADERS,
    )
    assert res.status_code == 202
    assert "job_id" in res.json()
