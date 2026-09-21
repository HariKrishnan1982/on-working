"""
Blockchain Audit Verification Script.

Per Requirement 8:
- Enumerates ledger decisions (paginated) from Hyperledger Fabric.
- Compares against PostgreSQL audit_log table.
- Detects:
  1. Modified rows (hash mismatch).
  2. Deleted rows (present on blockchain ledger, absent from Postgres).
  3. Inserted rows (present in Postgres, absent from blockchain ledger).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import psycopg
from psycopg.rows import dict_row

from configs.settings import settings

logger = logging.getLogger("verify_audit")


async def fetch_all_ledger_decisions(bridge_url: str, api_key: str) -> Dict[str, dict]:
    """Paginate and fetch all decisions from Fabric bridge."""
    ledger_decisions = {}
    headers = {"X-Bridge-API-Key": api_key}
    bookmark = ""

    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            params = {"pageSize": "100", "bookmark": bookmark}
            res = await client.get(f"{bridge_url}/api/v1/decisions", headers=headers, params=params)
            if res.status_code != 200:
                raise RuntimeError(f"Failed to fetch ledger decisions: {res.status_code} - {res.text}")

            data = res.json()
            records = data.get("records", [])
            for r in records:
                ledger_decisions[r["sessionId"]] = r

            bookmark = data.get("bookmark", "")
            if not bookmark or len(records) == 0:
                break

    return ledger_decisions


async def fetch_all_postgres_records(dsn: str) -> Dict[str, dict]:
    """Fetch all records from PostgreSQL audit_log."""
    pg_records = {}
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row) as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM audit_log ORDER BY chain_position ASC;")
            rows = await cur.fetchall()
            for r in rows:
                pg_records[r["session_id"]] = dict(r)
    return pg_records


def verify_audit_reconciliation(
    pg_records: Dict[str, dict],
    ledger_decisions: Dict[str, dict],
) -> Dict[str, Any]:
    """
    Cross-reconcile PostgreSQL audit_log and Fabric blockchain ledger.
    """
    matched: List[str] = []
    modified: List[Dict[str, str]] = []
    deleted_from_pg: List[str] = []
    inserted_into_pg: List[str] = []

    # 1. Check all Postgres records against Ledger
    for sess_id, pg_row in pg_records.items():
        if sess_id not in ledger_decisions:
            inserted_into_pg.append(sess_id)
        else:
            ledger_rec = ledger_decisions[sess_id]
            # Check decisionHash
            # Note: For verification, we compare stored canonical record_hash or decisionHash
            pg_hash = pg_row.get("record_hash")
            on_chain_hash = ledger_rec.get("decisionHash")

            # Check if hash matches
            if on_chain_hash and pg_hash and on_chain_hash.lower() != pg_hash.lower():
                modified.append({
                    "session_id": sess_id,
                    "postgres_hash": pg_hash,
                    "on_chain_hash": on_chain_hash,
                })
            else:
                matched.append(sess_id)

    # 2. Check for records on ledger that were deleted from Postgres
    for sess_id in ledger_decisions:
        if sess_id not in pg_records:
            deleted_from_pg.append(sess_id)

    is_tamper_free = (len(modified) == 0 and len(deleted_from_pg) == 0 and len(inserted_into_pg) == 0)

    report = {
        "is_tamper_free": is_tamper_free,
        "total_postgres": len(pg_records),
        "total_ledger": len(ledger_decisions),
        "matched_count": len(matched),
        "tampered_modified": modified,
        "tampered_deleted_from_pg": deleted_from_pg,
        "tampered_inserted_in_pg": inserted_into_pg,
    }
    return report


async def run_verification() -> Dict[str, Any]:
    pg_records = await fetch_all_postgres_records(settings.database_url)
    ledger_records = await fetch_all_ledger_decisions(settings.fabric_bridge_url, settings.fabric_bridge_api_key or "")
    report = verify_audit_reconciliation(pg_records, ledger_records)
    return report


if __name__ == "__main__":
    rep = asyncio.run(run_verification())
    print(json.dumps(rep, indent=2))
    sys.exit(0 if rep["is_tamper_free"] else 1)
