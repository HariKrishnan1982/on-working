"""
Cryptographic & Canonical Hashing Utilities for Blockchain Anchoring.

Per Requirement 3 & 9:
- Client (Python) computes decision hashes.
- Hash payload avoids raw floats by using fixed-precision 3-decimal strings ("0.750").
- Uses strictly sorted keys, no whitespace, and ensure_ascii=False.
- subjectRef and consentHash use HMAC-SHA256 with an off-chain secret salt.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Optional

from schemas.models import ConsentRecord, RiskDecision


def canonical_json_str(data: Any) -> str:
    """Produce deterministic canonical JSON string: sorted keys, compact separators, UTF-8 friendly."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_model_versions_hash(model_versions: dict[str, str]) -> str:
    """Compute SHA-256 hash of canonical model_versions map."""
    payload_str = canonical_json_str(dict(sorted(model_versions.items())))
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def build_canonical_decision_payload(decision: RiskDecision, caller_id: Optional[str] = None) -> dict[str, Any]:
    """
    Build the exact canonical dictionary for on-chain anchoring.
    Floats are formatted as fixed 3-decimal strings to avoid IEEE 754 precision drift.
    """
    fe = decision.fused_evidence
    spoof_score_str = f"{fe.spoof_result.spoof_score:.3f}"
    similarity_score_str = f"{fe.speaker_result.similarity_score:.3f}"
    scam_score_str = f"{fe.intent_result.scam_score:.3f}"

    model_versions_hash = compute_model_versions_hash(decision.model_versions)
    fired_rule_ids = sorted([r.rule_id for r in decision.fired_rules])

    return {
        "action": decision.action.value,
        "caller_id": caller_id or "unknown",
        "fired_rules": fired_rule_ids,
        "model_versions_hash": model_versions_hash,
        "risk_level": decision.risk_level.value,
        "rules_version": decision.rules_version,
        "scores": {
            "scam_score": scam_score_str,
            "similarity_score": similarity_score_str,
            "spoof_score": spoof_score_str,
        },
        "session_id": decision.session_id,
    }


def compute_decision_hash(decision: RiskDecision, caller_id: Optional[str] = None) -> str:
    """Compute deterministic SHA-256 decision hash for Fabric DecisionLedger."""
    payload = build_canonical_decision_payload(decision, caller_id=caller_id)
    canonical = canonical_json_str(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_pseudonymous_subject_ref(subject_id: str, hmac_secret: str) -> str:
    """
    Compute pseudonymous subjectRef via HMAC-SHA256.
    Ensures zero PII or phone numbers appear on the blockchain.
    """
    key_bytes = hmac_secret.encode("utf-8")
    msg_bytes = subject_id.strip().encode("utf-8")
    return hmac.new(key_bytes, msg_bytes, hashlib.sha256).hexdigest()


def compute_consent_hash(consent: ConsentRecord, hmac_secret: str) -> str:
    """
    Compute keyed consentHash via HMAC-SHA256 on canonical consent payload.
    """
    consent_dict = {
        "consent_id": consent.consent_id,
        "consent_scope": consent.consent_scope,
        "consent_timestamp": consent.consent_timestamp.isoformat(),
        "consented_by": consent.consented_by,
        "speaker_id": consent.speaker_id,
    }
    canonical_bytes = canonical_json_str(consent_dict).encode("utf-8")
    key_bytes = hmac_secret.encode("utf-8")
    return hmac.new(key_bytes, canonical_bytes, hashlib.sha256).hexdigest()
