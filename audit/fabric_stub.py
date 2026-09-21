from typing import List, Optional
from schemas.models import AuditRecord
from audit.sink import AuditSink

class FabricSink(AuditSink):
    """Stub for Hyperledger Fabric sink."""
    
    async def append(self, record: AuditRecord) -> None:
        raise NotImplementedError()
        
    async def get_latest(self) -> Optional[AuditRecord]:
        raise NotImplementedError()
        
    async def get_chain(self, limit: int = 100) -> List[AuditRecord]:
        raise NotImplementedError()
        
    async def verify_chain(self) -> bool:
        raise NotImplementedError()
