"""
Integration tests for the Audit Trail against live PostgreSQL.

Verifies:
- Serialized chain writes using PostgreSQL advisory transaction locks
- Chain integrity verification (genesis record, link hashes, canonical JSON)
- Immutability enforcement: PostgreSQL trigger blocks any UPDATE or DELETE operations
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import os
import shutil
import socket
import subprocess
import tempfile
import time
import pytest
import psycopg

from audit.local_hash_chain import PostgresHashChainSink
from schemas.models import (
    ActionType,
    BranchStatus,
    FusedEvidence,
    IntentCategory,
    IntentResult,
    Language,
    RiskDecision,
    RiskLevel,
    SpeakerResult,
    SpoofResult,
)


@pytest.fixture(scope="session")
def event_loop_policy():
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


def _find_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def postgres_service():
    """Spin up an isolated PostgreSQL 16 instance for the audit test suite."""
    pg_bin = Path(r"C:\Users\PRAYAG S\.local\pgsql\bin")
    if not (pg_bin / "postgres.exe").exists():
        pytest.skip("PostgreSQL binaries not found at expected path")

    port = _find_free_port()
    data_dir = Path(tempfile.gettempdir()) / f"pg_test_audit_{port}"
    if data_dir.exists():
        shutil.rmtree(data_dir, ignore_errors=True)

    # 1. Initialize cluster
    subprocess.run(
        [
            str(pg_bin / "initdb.exe"),
            "-D",
            str(data_dir),
            "-U",
            "postgres",
            "-A",
            "trust",
            "--no-locale",
            "-E",
            "UTF8",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 2. Start server
    proc = subprocess.Popen(
        [
            str(pg_bin / "postgres.exe"),
            "-D",
            str(data_dir),
            "-p",
            str(port),
            "-h",
            "127.0.0.1",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for readiness
    connected = False
    for _ in range(30):
        try:
            s = socket.socket()
            s.connect(("127.0.0.1", port))
            s.close()
            connected = True
            break
        except Exception:
            time.sleep(0.1)

    if not connected:
        proc.terminate()
        pytest.fail(f"PostgreSQL failed to bind to 127.0.0.1:{port}")

    dsn = f"postgresql://postgres@127.0.0.1:{port}/postgres"

    # Wait for PostgreSQL to accept SQL queries (not just TCP connections)
    for _ in range(50):
        try:
            with psycopg.connect(dsn, connect_timeout=2) as conn:
                conn.execute("SELECT 1")
            break
        except Exception:
            time.sleep(0.2)

    yield dsn

    # Teardown
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    shutil.rmtree(data_dir, ignore_errors=True)


def _make_dummy_decision(session_id: str, action: ActionType = ActionType.ALLOW) -> RiskDecision:
    spoof = SpoofResult(
        session_id=session_id,
        status=BranchStatus.OK,
        spoof_score=0.1,
        is_spoofed=False,
        confidence=0.9,
        processing_time_ms=10.0,
    )
    speaker = SpeakerResult(
        session_id=session_id,
        status=BranchStatus.OK,
        similarity_score=0.8,
        is_match=True,
        threshold_used=0.65,
        processing_time_ms=10.0,
    )
    intent = IntentResult(
        session_id=session_id,
        status=BranchStatus.OK,
        transcript="Test transcript",
        transcript_hash_sha256="abc" * 21 + "a",
        language_detected=Language.EN,
        scam_score=0.1,
        processing_time_ms=10.0,
    )
    evidence = FusedEvidence(
        session_id=session_id,
        spoof_result=spoof,
        speaker_result=speaker,
        intent_result=intent,
    )
    return RiskDecision(
        session_id=session_id,
        risk_level=RiskLevel.LOW,
        action=action,
        fired_rules=[],
        reasons=["Baseline clean call"],
        rules_version="0.2.0:ruleshash12",
        model_versions={"antispoof": "v0", "speaker": "v0", "asr_intent": "v0"},
        fused_evidence=evidence,
    )


@pytest.mark.asyncio
async def test_postgres_append_single_record(postgres_service):
    sink = PostgresHashChainSink(postgres_service)
    await sink.init_db()

    decision = _make_dummy_decision("sess-pg-1")
    record = await sink.append(decision, operator_notes="First test record")

    assert record.chain_position == 0
    assert record.previous_hash == "0" * 64
    assert len(record.record_hash) == 64
    assert record.session_id == "sess-pg-1"

    latest = await sink.get_latest()
    assert latest is not None
    assert latest.record_hash == record.record_hash


@pytest.mark.asyncio
async def test_postgres_chain_integrity(postgres_service):
    sink = PostgresHashChainSink(postgres_service)
    
    # Append 3 more records
    for i in range(2, 5):
        d = _make_dummy_decision(f"sess-pg-{i}")
        await sink.append(d)

    chain = await sink.get_chain(limit=10)
    assert len(chain) >= 4

    # Verify each block links to the previous block's hash
    for idx in range(1, len(chain)):
        assert chain[idx].previous_hash == chain[idx - 1].record_hash
        assert chain[idx].chain_position == chain[idx - 1].chain_position + 1

    # Validate full mathematical hash chain
    assert await sink.verify_chain() is True


@pytest.mark.asyncio
async def test_postgres_serialized_concurrent_writes(postgres_service):
    """
    Verify that concurrent appends are serialized via PostgreSQL advisory locks
    and produce a strictly ordered, valid chain without forks.
    """
    sink = PostgresHashChainSink(postgres_service)

    # Launch 5 concurrent appends simultaneously
    tasks = [
        sink.append(_make_dummy_decision(f"sess-concurrent-{i}"))
        for i in range(5)
    ]
    records = await asyncio.gather(*tasks)
    assert len(records) == 5

    # Chain must still be completely unbroken and valid
    assert await sink.verify_chain() is True


@pytest.mark.asyncio
async def test_postgres_immutability_trigger_blocks_update_delete(postgres_service):
    """
    Verify requirement 5: revoke UPDATE/DELETE on the audit table.
    Attempts to update or delete rows MUST trigger a database exception.
    """
    async with await psycopg.AsyncConnection.connect(postgres_service, autocommit=True) as conn:
        async with conn.cursor() as cur:
            # 1. Attempt UPDATE
            with pytest.raises(psycopg.ProgrammingError, match="strictly forbidden"):
                await cur.execute("UPDATE audit_log SET record_hash = 'tampered' WHERE chain_position = 0;")

            # 2. Attempt DELETE
            with pytest.raises(psycopg.ProgrammingError, match="strictly forbidden"):
                await cur.execute("DELETE FROM audit_log WHERE chain_position = 0;")
