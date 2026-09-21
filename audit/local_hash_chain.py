"""
Audit Trail — Append-Only Hash Chain Sink with PostgreSQL.

Implements serialized writes with PostgreSQL advisory locks to guarantee
strict linear chain sequencing without forks.
Enforces database-level immutability by revoking and triggering exceptions
on any UPDATE or DELETE operations.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, List, Optional

import psycopg
from psycopg.rows import dict_row

from audit.sink import AuditSink
from schemas.models import (
    ActionType,
    AuditRecord,
    RiskDecision,
    RiskLevel,
    canonical_json_bytes,
)

ADVISORY_LOCK_ID = 847291048201948172  # 64-bit integer lock id for audit chain serialization


class PostgresHashChainSink(AuditSink):
    """
    PostgreSQL-backed append-only cryptographic hash chain.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._initialized = False
        self._init_lock: Optional[asyncio.Lock] = None

    def _get_init_lock(self) -> asyncio.Lock:
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        return self._init_lock

    async def init_db(self) -> None:
        """Create audit table and attach tamper-prevention trigger."""
        if self._initialized:
            return
        async with self._get_init_lock():
            if self._initialized:
                return
            await self._run_init_ddl()
            self._initialized = True

    async def _run_init_ddl(self) -> None:
        async with await psycopg.AsyncConnection.connect(self.dsn, autocommit=True) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_log (
                        chain_position BIGINT PRIMARY KEY,
                        record_id VARCHAR(64) UNIQUE NOT NULL,
                        session_id VARCHAR(64) NOT NULL,
                        previous_hash VARCHAR(64) NOT NULL,
                        record_hash VARCHAR(64) NOT NULL,
                        risk_level VARCHAR(32) NOT NULL,
                        action VARCHAR(32) NOT NULL,
                        fired_rule_ids JSONB NOT NULL,
                        reasons JSONB NOT NULL,
                        rules_version VARCHAR(128) NOT NULL,
                        model_versions JSONB NOT NULL,
                        audio_hash_sha256 VARCHAR(64) NOT NULL,
                        transcript_hash_sha256 VARCHAR(64),
                        transcript_ref TEXT,
                        embedding_hash_sha256 VARCHAR(64),
                        embedding_ref TEXT,
                        canonical_json TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        operator_notes TEXT
                    );
                    """
                )
                await cur.execute(
                    """
                    CREATE OR REPLACE FUNCTION reject_audit_tampering()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        RAISE EXCEPTION 'Audit records are immutable. UPDATE and DELETE are strictly forbidden on audit_log table.';
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )
                await cur.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_trigger WHERE tgname = 'audit_log_immutability_trigger'
                        ) THEN
                            CREATE TRIGGER audit_log_immutability_trigger
                            BEFORE UPDATE OR DELETE ON audit_log
                            FOR EACH ROW EXECUTE FUNCTION reject_audit_tampering();
                        END IF;
                    END;
                    $$;
                    """
                )
                # Revoke direct updates and deletes
                try:
                    await cur.execute("REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;")
                except Exception:
                    pass
        self._initialized = True

    async def append(self, decision: RiskDecision, operator_notes: Optional[str] = None) -> AuditRecord:
        """
        Serialize chain writes using PostgreSQL advisory transaction lock,
        compute cryptographic hash, and insert immutable record.
        """
        if not self._initialized:
            await self.init_db()

        # Connect with transaction
        async with await psycopg.AsyncConnection.connect(self.dsn, row_factory=dict_row) as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    # 1. Acquire exclusive advisory lock for the duration of this transaction
                    await cur.execute("SELECT pg_advisory_xact_lock(%s);", (ADVISORY_LOCK_ID,))

                    # 2. Fetch the latest record in the serialized chain
                    await cur.execute(
                        "SELECT chain_position, record_hash FROM audit_log ORDER BY chain_position DESC LIMIT 1;"
                    )
                    latest = await cur.fetchone()

                    if latest is None:
                        previous_hash = "0" * 64
                        chain_position = 0
                    else:
                        previous_hash = latest["record_hash"]
                        chain_position = latest["chain_position"] + 1

                    fe = decision.fused_evidence
                    audio_hash = (
                        fe.session_id
                        if not hasattr(fe, "audio_hash_sha256")
                        else getattr(fe, "audio_hash_sha256")
                    )

                    record = AuditRecord(
                        session_id=decision.session_id,
                        risk_level=decision.risk_level,
                        action=decision.action,
                        fired_rule_ids=[r.rule_id for r in decision.fired_rules],
                        reasons=decision.reasons,
                        rules_version=decision.rules_version,
                        model_versions=decision.model_versions,
                        audio_hash_sha256=getattr(fe, "audio_hash_sha256", "0" * 64),
                        transcript_hash_sha256=fe.intent_result.transcript_hash_sha256,
                        transcript_ref=fe.intent_result.transcript_ref,
                        embedding_hash_sha256=fe.speaker_result.embedding_hash_sha256,
                        embedding_ref=fe.speaker_result.embedding_ref,
                        previous_hash=previous_hash,
                        chain_position=chain_position,
                        operator_notes=operator_notes,
                    )

                    canonical_json = canonical_json_bytes(record.canonical_payload_dict()).decode("utf-8")

                    await cur.execute(
                        """
                        INSERT INTO audit_log (
                            chain_position, record_id, session_id, previous_hash, record_hash,
                            risk_level, action, fired_rule_ids, reasons, rules_version, model_versions,
                            audio_hash_sha256, transcript_hash_sha256, transcript_ref,
                            embedding_hash_sha256, embedding_ref, canonical_json, created_at, operator_notes
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s
                        );
                        """,
                        (
                            record.chain_position,
                            record.record_id,
                            record.session_id,
                            record.previous_hash,
                            record.record_hash,
                            record.risk_level.value,
                            record.action.value,
                            json.dumps(record.fired_rule_ids),
                            json.dumps(record.reasons),
                            record.rules_version,
                            json.dumps(record.model_versions),
                            record.audio_hash_sha256,
                            record.transcript_hash_sha256,
                            record.transcript_ref,
                            record.embedding_hash_sha256,
                            record.embedding_ref,
                            canonical_json,
                            record.timestamp,
                            record.operator_notes,
                        ),
                    )

        return record

    async def get_latest(self) -> Optional[AuditRecord]:
        if not self._initialized:
            await self.init_db()

        async with await psycopg.AsyncConnection.connect(self.dsn, row_factory=dict_row) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM audit_log ORDER BY chain_position DESC LIMIT 1;")
                row = await cur.fetchone()
                if not row:
                    return None
                return self._row_to_record(row)

    async def get_chain(self, limit: int = 100) -> list[AuditRecord]:
        if not self._initialized:
            await self.init_db()

        async with await psycopg.AsyncConnection.connect(self.dsn, row_factory=dict_row) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT * FROM audit_log ORDER BY chain_position ASC LIMIT %s;", (limit,)
                )
                rows = await cur.fetchall()
                return [self._row_to_record(r) for r in rows]

    async def verify_chain(self) -> bool:
        """Walk the chain and verify mathematical hash integrity."""
        if not self._initialized:
            await self.init_db()

        records = await self.get_chain(limit=10000)
        if not records:
            return True

        for i, record in enumerate(records):
            if i == 0:
                if record.previous_hash != "0" * 64:
                    print(f"DEBUG: Genesis previous_hash != 0*64: {record.previous_hash}")
                    return False
            else:
                if record.previous_hash != records[i - 1].record_hash:
                    print(f"DEBUG: Link mismatch at {i}: {record.previous_hash} != {records[i - 1].record_hash}")
                    return False

            computed = record.compute_hash()
            if record.record_hash != computed:
                print(f"DEBUG: Hash mismatch at {i}: record_hash={record.record_hash} != compute_hash={computed}")
                return False

        return True

    @staticmethod
    def _row_to_record(row: dict) -> AuditRecord:
        fired_rules = row["fired_rule_ids"]
        if isinstance(fired_rules, str):
            fired_rules = json.loads(fired_rules)
        reasons = row["reasons"]
        if isinstance(reasons, str):
            reasons = json.loads(reasons)
        model_versions = row["model_versions"]
        if isinstance(model_versions, str):
            model_versions = json.loads(model_versions)

        return AuditRecord(
            record_id=row["record_id"],
            session_id=row["session_id"],
            risk_level=RiskLevel(row["risk_level"]),
            action=ActionType(row["action"]),
            fired_rule_ids=fired_rules,
            reasons=reasons,
            rules_version=row["rules_version"],
            model_versions=model_versions,
            audio_hash_sha256=row["audio_hash_sha256"],
            transcript_hash_sha256=row["transcript_hash_sha256"],
            transcript_ref=row["transcript_ref"],
            embedding_hash_sha256=row["embedding_hash_sha256"],
            embedding_ref=row["embedding_ref"],
            previous_hash=row["previous_hash"],
            record_hash=row["record_hash"],
            chain_position=row["chain_position"],
            timestamp=row["created_at"].astimezone(timezone.utc) if hasattr(row["created_at"], "astimezone") else row["created_at"],
            operator_notes=row["operator_notes"],
        )


# Provide LocalHashChainSink as alias
LocalHashChainSink = PostgresHashChainSink
