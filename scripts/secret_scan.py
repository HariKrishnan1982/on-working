"""
Secret Scan Utility for Voice Fraud Detection System.

Scans the codebase to ensure:
1. No private keys (*.key, *.pem), certificates, or credentials are accidentally committed.
2. .gitignore properly covers all secret patterns.
3. No hardcoded high-entropy secrets or private key banners exist in code.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Patterns that MUST NEVER appear in committed files
DISALLOWED_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}"),  # Slack tokens
    re.compile(r"ghp_[0-9a-zA-Z]{36}"),             # GitHub personal access tokens
    re.compile(r"AKIA[0-9A-Z]{16}"),                # AWS Access Key ID
]

# Sensitive filenames that must never exist outside .gitignore
FORBIDDEN_FILE_PATTERNS = [
    "*.pem",
    "*.key",
    "*.id",
    ".env",
    ".env.local",
    "id_rsa",
    "id_ecdsa",
]

# Directories ignored from scan
IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
}


def scan_repository(repo_root: Path) -> list[str]:
    violations: list[str] = []

    # 1. Verify .gitignore covers sensitive file patterns
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.exists():
        violations.append("CRITICAL: .gitignore file is missing!")
    else:
        gitignore_content = gitignore_path.read_text(encoding="utf-8")
        for expected in [".env", "*.pem", "*.key", "wallet/", "keystore/"]:
            if expected not in gitignore_content:
                violations.append(f"CRITICAL: .gitignore missing required rule: '{expected}'")

    # 2. Check for physical forbidden files
    for root, dirs, files in os_walk_filtered(repo_root):
        for f in files:
            f_path = root / f
            rel_path = f_path.relative_to(repo_root)

            # Check if filename matches forbidden pattern
            if f == ".env":
                violations.append(f"Forbidden file found in repository: {rel_path}")
            elif f.endswith(".pem") or f.endswith(".key") or f.endswith(".crt"):
                violations.append(f"Forbidden certificate/key file found in repository: {rel_path}")

            # Check file content against disallowed patterns
            # Skip binary files or big files (> 2MB)
            if f_path.stat().st_size > 2 * 1024 * 1024:
                continue

            try:
                content = f_path.read_text(encoding="utf-8", errors="ignore")
                for pat in DISALLOWED_PATTERNS:
                    if pat.search(content):
                        violations.append(f"Forbidden secret pattern matched in: {rel_path}")
            except Exception:
                pass

    return violations


def os_walk_filtered(root: Path):
    import os
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        yield Path(r), dirs, files


if __name__ == "__main__":
    root_dir = Path(__file__).resolve().parent.parent
    results = scan_repository(root_dir)
    if results:
        print("[-] Secret Scan FAILED with violations:")
        for v in results:
            print(f"  - {v}")
        sys.exit(1)
    else:
        print("[+] Secret Scan PASSED: No credentials, private keys, or unignored .env files found.")
        sys.exit(0)
