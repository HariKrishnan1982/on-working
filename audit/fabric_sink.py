"""
Hyperledger Fabric Blockchain Sink with PostgreSQL Transactional Outbox.

Per Requirements 6 & 10:
- Writes audit log and outbox entry within a single PostgreSQL transaction.
- Anchors to fabric-bridge via REST API.
- If ledger is unreachable: decision remains 'anchor_pending' in Postgres.
- Idempotent retry worker: matching hash = success; mismatch = security alert.
- Zero raw audio, transcripts, or voice embeddings sent on-chain.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import psycopg
from psycopg.rows import dict_row

from audit.sink import AuditSink
from configs.settings import settings
from schemas.hash_utils import build_canonical_decision_payload, compute_decision_hash
from schemas.models import (
    ActionType,
    AuditRecord,
    RiskDecision,
    RiskLevel,
    canonical_json_bytes,
)

logger = logging.getLogger(__name__)

ADVISORY_LOCK_ID = 984729184719284712


class FabricSink(AuditSink):
    """Dual-write AuditSink that anchors immutable decision hashes into Hyperledger Fabric."""

    def __init__(
        self,
        dsn: Optional[str] = None,
        bridge_url: Optional[str] = None,
        bridge_api_key: Optional[str] = None,
    ) -> None:
        self.dsn = dsn or settings.database_url
        self.bridge_url = bridge_url or settings.fabric_bridge_url
        self.bridge_api_key = bridge_api_key or settings.fabric_bridge_api_key
        self._initialized = False
        self._init_lock: Optional[asyncio.Lock] = None

    def _get_init_lock(self) -> asyncio.Lock:
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        return self._init_lock

    async def init_db(self) -> None:
        """Create audit tables and transactional outbox in PostgreSQL."""
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
                # 1. Audit Log Table with anchor_status
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
                        operator_notes TEXT,
                        anchor_status VARCHAR(32) NOT NULL DEFAULT 'anchor_pending'
                    );
                    """
                )

                # 2. Transactional Outbox Table
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_outbox (
                        outbox_id BIGSERIAL PRIMARY KEY,
                        session_id VARCHAR(64) NOT NULL,
                        decision_hash VARCHAR(64) NOT NULL,
                        payload JSONB NOT NULL,
                        status VARCHAR(32) NOT NULL DEFAULT 'anchor_pending',
                        retry_count INT NOT NULL DEFAULT 0,
                        last_error TEXT,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL
                    );
                    """
                )

                # 3. Immutability trigger on audit_log
                await cur.execute(
                    """
                    CREATE OR REPLACE FUNCTION reject_audit_tampering()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        -- Allow internal update of anchor_status only
                        IF TG_OP = 'UPDATE' AND (OLD.record_hash = NEW.record_hash AND OLD.chain_position = NEW.chain_position) THEN
                            RETURN NEW;
                        END IF;
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
        self._initialized = True

    async def append(self, decision: RiskDecision, operator_notes: Optional[str] = None) -> AuditRecord:
        """
        Atomically write to PostgreSQL and dispatch anchor payload to Hyperledger Fabric.
        """
        if not self._initialized:
            await self.init_db()

        decision_hash = compute_decision_hash(decision)
        canonical_payload = build_canonical_decision_payload(decision)

        # 1. Transactional Write to Postgres
        async with await psycopg.AsyncConnection.connect(self.dsn, row_factory=dict_row) as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute("SELECT pg_advisory_xact_lock(%s);", (ADVISORY_LOCK_ID,))
                    await cur.execute("SELECT chain_position, record_hash FROM audit_log ORDER BY chain_position DESC LIMIT 1;")
                    latest = await cur.fetchone()

                    previous_hash = "0" * 64 if latest is None else latest["record_hash"]
                    chain_position = 0 if latest is None else latest["chain_position"] + 1

                    fe = decision.fused_evidence
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
                            embedding_hash_sha256, embedding_ref, canonical_json, created_at, operator_notes, anchor_status
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, 'anchor_pending'
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

                    # Insert to transactional outbox
                    await cur.execute(
                        """
                        INSERT INTO audit_outbox (
                            session_id, decision_hash, payload, status, created_at, updated_at
                        ) VALUES (%s, %s, %s, 'anchor_pending', NOW(), NOW());
                        """,
                        (decision.session_id, decision_hash, json.dumps(canonical_payload)),
                    )

        # 2. Attempt Immediate Anchoring to Fabric Bridge
        await self._attempt_anchor(decision.session_id, decision_hash, canonical_payload)
        return record

    async def _attempt_anchor(self, session_id: str, decision_hash: str, payload: dict) -> bool:
        """Call fabric-bridge to record decision. Handles idempotency & mismatches."""
        if not self.bridge_api_key:
            return False

        headers = {
            "X-Bridge-API-Key": self.bridge_api_key,
            "Content-Type": "application/json",
        }
        body = {
            "sessionId": session_id,
            "decisionHash": decision_hash,
            "action": payload.get("action"),
            "riskLevel": payload.get("risk_level"),
            "rulesVersion": payload.get("rules_version"),
            "modelVersionsHash": payload.get("model_versions_hash"),
            "clientTimestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.post(f"{self.bridge_url}/api/v1/decisions", headers=headers, json=body)
                
                if res.status_code in [200, 201]:
                    # Anchored successfully or already existed with identical hash
                    await self._mark_anchored(session_id)
                    return True
                elif res.status_code == 409:
                    logger.critical(
                        "SECURITY ALERT: Hash mismatch for session '%s' on blockchain ledger!", session_id
                    )
                    await self._mark_outbox_status(session_id, "hash_mismatch", res.text)
                    return False
                else:
                    await self._mark_outbox_status(session_id, "anchor_pending", res.text)
                    return False
        except Exception as e:
            logger.debug("Fabric bridge unreachable for session %s (will retry via outbox): %s", session_id, e)
            return False

    async def _mark_anchored(self, session_id: str) -> None:
        async with await psycopg.AsyncConnection.connect(self.dsn, autocommit=True) as conn:
            async with conn.cursor() as cur:
                await cur.execute("UPDATE audit_log SET anchor_status = 'anchored' WHERE session_id = %s;", (session_id,))
                await cur.execute("UPDATE audit_outbox SET status = 'anchored', updated_at = NOW() WHERE session_id = %s;", (session_id,))

    async def _mark_outbox_status(self, session_id: str, status: str, err: str) -> None:
        async with await psycopg.AsyncConnection.connect(self.dsn, autocommit=True) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE audit_outbox 
                    SET status = %s, retry_count = retry_count + 1, last_error = %s, updated_at = NOW() 
                    WHERE session_id = %s;
                    """,
                    (status, err, session_id),
                )

    async def process_outbox(self, limit: int = 20) -> int:
        """Idempotent retry worker: processes pending outbox records."""
        if not self._initialized:
            await self.init_db()

        processed = 0
        async with await psycopg.AsyncConnection.connect(self.dsn, row_factory=dict_row) as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT outbox_id, session_id, decision_hash, payload 
                        FROM audit_outbox 
                        WHERE status = 'anchor_pending' 
                        ORDER BY outbox_id ASC 
                        LIMIT %s 
                        FOR UPDATE SKIP LOCKED;
                        """,
                        (limit,),
                    )
                    rows = await cur.fetchall()

        for r in rows:
            payload = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
            success = await self._attempt_anchor(r["session_id"], r["decision_hash"], payload)
            if success:
                processed += 1

        return processed

    async def get_latest(self) -> Optional[AuditRecord]:
        if not self._initialized:
            await self.init_db()
        async with await psycopg.AsyncConnection.connect(self.dsn, row_factory=dict_row) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM audit_log ORDER BY chain_position DESC LIMIT 1;")
                row = await cur.fetchone()
                return None if not row else self._row_to_record(row)

    async def get_chain(self, limit: int = 100) -> list[AuditRecord]:
        if not self._initialized:
            await self.init_db()
        async with await psycopg.AsyncConnection.connect(self.dsn, row_factory=dict_row) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT * FROM audit_log ORDER BY chain_position ASC LIMIT %s;", (limit,))
                rows = await cur.fetchall()
                return [self._row_to_record(r) for r in rows]

    async def verify_chain(self) -> bool:
        """Local hash chain verification."""
        records = await self.get_chain(limit=10000)
        if not records:
            return True
        for i, record in enumerate(records):
            if i == 0:
                if record.previous_hash != "0" * 64:
                    return False
            else:
                if record.previous_hash != records[i - 1].record_hash:
                    return False
            if record.record_hash != record.compute_hash():
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
