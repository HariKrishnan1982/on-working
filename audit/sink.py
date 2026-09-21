"""AuditSink abstract interface for auditable append-only ledgers."""

from abc import ABC, abstractmethod
from typing import Optional

from schemas.models import AuditRecord, RiskDecision


class AuditSink(ABC):
    """Abstract sink interface for writing and verifying immutable audit records."""

    @abstractmethod
    async def append(self, decision: RiskDecision, operator_notes: Optional[str] = None) -> AuditRecord:
        """Append a RiskDecision to the tamper-evident audit ledger."""
        pass

    @abstractmethod
    async def get_latest(self) -> Optional[AuditRecord]:
        """Return the most recent record in the chain, or None if empty."""
        pass

    @abstractmethod
    async def get_chain(self, limit: int = 100) -> list[AuditRecord]:
        """Retrieve recent audit records ordered by chain position."""
        pass

    @abstractmethod
    async def verify_chain(self) -> bool:
        """Walk the chain and verify mathematical hash integrity."""
        pass
