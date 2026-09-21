"""
Tests verifying that no credentials or secrets exist in the repository
and that .gitignore covers all sensitive files per Requirement 1.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.secret_scan import scan_repository


def test_secret_scan():
    repo_root = Path(__file__).resolve().parent.parent
    violations = scan_repository(repo_root)
    assert not violations, f"Secret scan found violations:\n" + "\n".join(violations)
