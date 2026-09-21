"""
Tests verifying tamper detection capabilities across modify, delete, and insert attack vectors.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.verify_audit import verify_audit_reconciliation


def test_tamper_detection_modify_delete_insert():
    ledger_state = {
        "sess-1": {"sessionId": "sess-1", "decisionHash": "1" * 64},
        "sess-2": {"sessionId": "sess-2", "decisionHash": "2" * 64},
        "sess-3": {"sessionId": "sess-3", "decisionHash": "3" * 64},
    }

    # Attack A: sess-1 has altered hash in Postgres
    # Attack B: sess-2 was deleted from Postgres
    # Attack C: sess-999 was inserted into Postgres without blockchain anchoring
    postgres_state = {
        "sess-1": {"session_id": "sess-1", "record_hash": "f" * 64},
        # sess-2 deleted
        "sess-3": {"session_id": "sess-3", "record_hash": "3" * 64},
        "sess-999": {"session_id": "sess-999", "record_hash": "9" * 64},
    }

    report = verify_audit_reconciliation(postgres_state, ledger_state)

    assert report["is_tamper_free"] is False
    assert report["matched_count"] == 1  # only sess-3 matches

    # Check Attack A
    assert len(report["tampered_modified"]) == 1
    assert report["tampered_modified"][0]["session_id"] == "sess-1"

    # Check Attack B
    assert len(report["tampered_deleted_from_pg"]) == 1
    assert report["tampered_deleted_from_pg"][0] == "sess-2"

    # Check Attack C
    assert len(report["tampered_inserted_in_pg"]) == 1
    assert report["tampered_inserted_in_pg"][0] == "sess-999"
