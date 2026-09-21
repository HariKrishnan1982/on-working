"""
Test verifying that Python canonical hash computation matches test_vectors/decision_hash_vectors.json byte-for-byte.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import hashlib
from schemas.hash_utils import canonical_json_str, compute_pseudonymous_subject_ref


def test_cross_platform_test_vectors():
    vectors_file = Path(__file__).resolve().parent.parent / "test_vectors" / "decision_hash_vectors.json"
    data = json.loads(vectors_file.read_text(encoding="utf-8"))

    for vec in data["vectors"]:
        if "payload" in vec:
            payload = vec["payload"]
            canonical = canonical_json_str(payload)
            assert canonical == vec["canonical_json"], f"Canonical JSON mismatch for {vec['name']}"
            computed_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            assert computed_hash == vec["expected_sha256"], f"SHA256 mismatch for {vec['name']}"
        elif "subject_id" in vec:
            ref = compute_pseudonymous_subject_ref(vec["subject_id"], vec["hmac_secret"])
            assert ref == vec["expected_subject_ref"], f"HMAC subjectRef mismatch for {vec['name']}"
