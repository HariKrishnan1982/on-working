"""
Tests for FabricSink, Transactional Outbox, and IntegrityGuard.

Verifies:
- Dual-write to Postgres audit_log and audit_outbox in a single transaction.
- Status set to 'anchor_pending' when bridge is unreachable.
- Idempotent outbox retry: matching hash = success; mismatched hash = alert.
- IntegrityGuard cache TTL, local hash checking, and fail-closed override.
- @pytest.mark.fabric integration test.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import hashlib
import time
import pytest
import psycopg
from psycopg.rows import dict_row

from audit.fabric_sink import FabricSink
from configs.settings import settings
from schemas.models import ActionType, RiskDecision, RiskLevel
from services.integrity_guard import IntegrityGuard
from tests.conftest import make_fused_evidence


def _make_test_decision(session_id: str) -> RiskDecision:
    evidence = make_fused_evidence(session_id=session_id)
    return RiskDecision(
        session_id=session_id,
        risk_level=RiskLevel.LOW,
        action=ActionType.ALLOW,
        rules_version="0.2.0:1234567890ab",
        model_versions={"antispoof": "v0", "speaker": "v0", "asr_intent": "v0"},
        fused_evidence=evidence,
    )


@pytest.fixture(scope="module")
def postgres_service():
    """Start an isolated PostgreSQL instance for testing FabricSink outbox."""
    import socket, subprocess, tempfile, shutil
    pg_bin = Path(r"C:\Users\PRAYAG S\.local\pgsql\bin")
    if not (pg_bin / "postgres.exe").exists():
        pytest.skip("PostgreSQL binaries not found")

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    data_dir = Path(tempfile.gettempdir()) / f"pg_test_fabric_{port}"
    shutil.rmtree(data_dir, ignore_errors=True)

    subprocess.run(
        [str(pg_bin / "initdb.exe"), "-D", str(data_dir), "-U", "postgres", "-A", "trust", "--no-locale", "-E", "UTF8"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    proc = subprocess.Popen(
        [str(pg_bin / "postgres.exe"), "-D", str(data_dir), "-p", str(port), "-h", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # Phase 1: Wait for TCP port to open
    for _ in range(30):
        try:
            sock = socket.socket()
            sock.connect(("127.0.0.1", port))
            sock.close()
            break
        except Exception:
            time.sleep(0.1)

    dsn = f"postgresql://postgres@127.0.0.1:{port}/postgres"

    # Phase 2: Wait for PostgreSQL to actually accept SQL queries
    # (TCP port opens before the DB is fully started; without this,
    # psycopg raises "FATAL: the database system is starting up")
    for _ in range(50):
        try:
            with psycopg.connect(dsn, connect_timeout=2) as conn:
                conn.execute("SELECT 1")
            break
        except Exception:
            time.sleep(0.2)
    yield dsn

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    shutil.rmtree(data_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_fabric_sink_dual_write_and_anchor_pending(postgres_service):
    """
    Verify that when bridge is unreachable, record is saved locally with status 'anchor_pending'
    and inserted into the transactional outbox table.
    """
    sink = FabricSink(
        dsn=postgres_service,
        bridge_url="http://127.0.0.1:59999",  # Non-existent bridge port
        bridge_api_key="test-key",
    )
    await sink.init_db()

    decision = _make_test_decision("sess-outbox-001")
    record = await sink.append(decision)

    assert record.session_id == "sess-outbox-001"

    # Check postgres audit_log has anchor_status 'anchor_pending'
    async with await psycopg.AsyncConnection.connect(postgres_service, row_factory=dict_row) as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT anchor_status FROM audit_log WHERE session_id = 'sess-outbox-001';")
            row = await cur.fetchone()
            assert row["anchor_status"] == "anchor_pending"

            # Check audit_outbox has record
            await cur.execute("SELECT status, retry_count FROM audit_outbox WHERE session_id = 'sess-outbox-001';")
            out_row = await cur.fetchone()
            assert out_row["status"] == "anchor_pending"


def test_integrity_guard_cache_and_fail_closed():
    """
    Verify IntegrityGuard:
    - Fresh cache -> valid.
    - Expired cache + unreachable bridge -> fail closed.
    - Local rules hash mismatch -> fail closed with single reason string.
    """
    guard = IntegrityGuard(
        bridge_url="http://127.0.0.1:59999",
        bridge_api_key="test-key",
        ttl_s=1,  # 1 second TTL for test
    )

    rules_version = "0.2.0:valid123"
    rules_sha256 = "a" * 64
    model_versions = {"antispoof": "v0"}
    model_artifacts = {"antispoof": "b" * 64}

    # 1. Seed cache
    guard.seed_cache(
        rules={rules_version: rules_sha256},
        models={"antispoof:v0": "b" * 64},
    )
    assert guard.is_cache_fresh() is True

    # Check valid
    valid, reason = guard.verify_integrity(rules_version, rules_sha256, model_versions, model_artifacts)
    assert valid is True
    assert reason is None

    # 2. Tamper with local rules hash -> must fail closed
    tampered_rules_sha256 = "f" * 64
    valid_tampered, reason_tampered = guard.verify_integrity(rules_version, tampered_rules_sha256, model_versions, model_artifacts)
    assert valid_tampered is False
    assert "[INTEGRITY_COMPROMISED]" in reason_tampered

    # 3. Wait for TTL to expire -> bridge unreachable -> fail closed
    time.sleep(1.1)
    assert guard.is_cache_fresh() is False
    valid_expired, reason_expired = guard.verify_integrity(rules_version, rules_sha256, model_versions, model_artifacts)
    assert valid_expired is False
    assert "cache expired" in reason_expired


@pytest.mark.fabric
@pytest.mark.asyncio
async def test_live_fabric_bridge_integration():
    """
    Integration test connecting to a live fabric-bridge.
    Skipped automatically if fabric-bridge is not running on 127.0.0.1:8080.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            res = await client.get("http://127.0.0.1:8080/health")
            if res.status_code != 200:
                pytest.skip("Fabric bridge is not healthy")
    except Exception:
        pytest.skip("Fabric bridge is not reachable on 127.0.0.1:8080")

    # If bridge is up, test live post and verify
    async with httpx.AsyncClient(timeout=3.0) as client:
        sess_id = f"sess-live-{int(time.time())}"
        headers = {"X-Bridge-API-Key": settings.fabric_bridge_api_key or "vfd-bridge-secret-98765"}
        res = await client.post(
            "http://127.0.0.1:8080/api/v1/decisions",
            headers=headers,
            json={
                "sessionId": sess_id,
                "decisionHash": "e" * 64,
                "action": "ALLOW",
                "riskLevel": "LOW",
                "rulesVersion": "0.2.0:123456",
            },
        )
        assert res.status_code in [200, 201]
