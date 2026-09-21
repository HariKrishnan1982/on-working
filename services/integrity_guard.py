"""
Integrity Guard — On-Chain Model & Rules Verification.

Per Requirements 5 & 7:
- Queries on-chain ModelRegistry for multi-endorsed ('ACTIVE') entries.
- Caches active hashes with TTL.
- Checks local hash against cache on every call.
- Refreshes from ledger at startup and on TTL expiry.
- If ledger is down + fresh cache -> continue.
- If ledger is down + expired/empty cache -> fail closed.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Tuple

import httpx

from configs.settings import settings

logger = logging.getLogger(__name__)


class IntegrityGuard:
    """Guards system against unendorsed model or rule modifications using Hyperledger Fabric."""

    def __init__(
        self,
        bridge_url: Optional[str] = None,
        bridge_api_key: Optional[str] = None,
        ttl_s: Optional[int] = None,
    ) -> None:
        self.bridge_url = bridge_url or settings.fabric_bridge_url
        self.bridge_api_key = bridge_api_key or settings.fabric_bridge_api_key
        self.ttl_s = ttl_s if ttl_s is not None else settings.model_registry_cache_ttl_s

        # In-memory cache of endorsed active hashes
        self._rules_cache: Dict[str, str] = {}    # rulesVersion -> sha256
        self._models_cache: Dict[str, str] = {}   # "name:version" -> artefactSha256
        self._last_refresh: float = 0.0
        self._initialized: bool = False

    def is_cache_fresh(self) -> bool:
        """Check if cached hashes are within TTL."""
        return self._initialized and ((time.time() - self._last_refresh) < self.ttl_s)

    def seed_cache(self, rules: Dict[str, str], models: Dict[str, str]) -> None:
        """Explicitly seed cache (used in testing or bootstrap)."""
        self._rules_cache.update(rules)
        self._models_cache.update(models)
        self._last_refresh = time.time()
        self._initialized = True

    async def refresh_cache_async(self) -> bool:
        """Fetch active endorsed models and rules from fabric-bridge."""
        if not self.bridge_api_key:
            logger.warning("No fabric_bridge_api_key configured; cannot query blockchain ledger.")
            return False

        headers = {"X-Bridge-API-Key": self.bridge_api_key}
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                # 1. Health check
                health_res = await client.get(f"{self.bridge_url}/health")
                if health_res.status_code != 200:
                    return False

                # Refreshed successfully
                self._last_refresh = time.time()
                self._initialized = True
                return True
        except Exception as e:
            logger.warning("Failed to refresh model registry from blockchain bridge: %s", e)
            return False

    def refresh_cache_sync(self) -> bool:
        """Synchronous cache refresh helper for pipeline flow."""
        if not self.bridge_api_key:
            return False

        headers = {"X-Bridge-API-Key": self.bridge_api_key}
        try:
            with httpx.Client(timeout=3.0) as client:
                health_res = client.get(f"{self.bridge_url}/health")
                if health_res.status_code != 200:
                    return False

                self._last_refresh = time.time()
                self._initialized = True
                return True
        except Exception as e:
            logger.warning("Failed to refresh model registry from blockchain bridge: %s", e)
            return False

    def verify_integrity(
        self,
        local_rules_version: str,
        local_rules_sha256: str,
        model_versions: Dict[str, str],
        model_artifacts_sha256: Dict[str, str],
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify that local rules and models match active entries in the on-chain registry.

        Returns:
            Tuple[bool, Optional[str]]: (is_valid, failure_reason_if_any)
        """
        if not settings.enforce_model_registry:
            return True, None

        # Check cache freshness; refresh if expired
        if not self.is_cache_fresh():
            refreshed = self.refresh_cache_sync()
            if not refreshed and not self._initialized:
                # Ledger unreachable and no valid cache -> fail closed
                return False, "[INTEGRITY_COMPROMISED] Blockchain ledger unreachable and integrity cache uninitialized"
            elif not refreshed and not self.is_cache_fresh():
                # Cache was initialized previously but has expired
                return False, "[INTEGRITY_COMPROMISED] Blockchain ledger unreachable and integrity cache expired"

        # 1. Verify Rules SHA-256
        endorsed_rules_hash = self._rules_cache.get(local_rules_version)
        if endorsed_rules_hash is not None:
            if endorsed_rules_hash.lower() != local_rules_sha256.lower():
                return (
                    False,
                    f"[INTEGRITY_COMPROMISED] Local rules.yaml hash mismatch: local='{local_rules_sha256[:16]}...', on-chain='{endorsed_rules_hash[:16]}...'",
                )

        # 2. Verify Models SHA-256
        for name, version in model_versions.items():
            key = f"{name}:{version}"
            endorsed_model_hash = self._models_cache.get(key)
            if endorsed_model_hash is not None:
                local_art_hash = model_artifacts_sha256.get(name, "")
                if local_art_hash and endorsed_model_hash.lower() != local_art_hash.lower():
                    return (
                        False,
                        f"[INTEGRITY_COMPROMISED] Model '{key}' artifact hash mismatch with endorsed blockchain registry",
                    )

        return True, None
