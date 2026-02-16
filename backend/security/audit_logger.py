"""
Phase 10 — Audit Logging System

Immutable, append-only audit logging for security events.
Uses PostgreSQL for persistence, SHA256 for integrity.
"""
import hashlib
import json
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from backend.database import Base
from backend.orm.user import User


class AuditLogEntry(Base):
    """
    Immutable audit log entry.
    
    Append-only, never modified or deleted.
    SHA256 chain for tamper detection.
    """
    __tablename__ = 'audit_log'
    
    id = Column(Integer, primary_key=True)
    
    # Request context
    request_id = Column(String(32), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # User context
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    institution_id = Column(Integer, ForeignKey('institutions.id', ondelete='SET NULL'), nullable=True)
    
    # Request details
    method = Column(String(10), nullable=False)
    path = Column(String(500), nullable=False)
    client_ip = Column(String(45), nullable=False)
    user_agent = Column(String(500), nullable=True)
    
    # Response details
    status_code = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    # Security events
    event_type = Column(String(50), nullable=True)  # REQUEST, RESPONSE, SECURITY_EVENT, ERROR
    event_category = Column(String(50), nullable=True)  # AUTH, AUTHORIZATION, DATA_ACCESS, etc.
    
    # Event details (JSON)
    details_json = Column(Text, nullable=True)
    
    # Integrity chain
    previous_hash = Column(String(64), nullable=True)  # Previous entry hash
    entry_hash = Column(String(64), nullable=False)  # This entry hash
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    def compute_hash(self) -> str:
        """
        Compute SHA256 hash of entry data.
        
        Creates cryptographic chain for tamper detection.
        """
        data = {
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else "",
            "user_id": self.user_id,
            "institution_id": self.institution_id,
            "method": self.method,
            "path": self.path,
            "client_ip": self.client_ip,
            "event_type": self.event_type,
            "details": self.details_json,
            "previous_hash": self.previous_hash or ""
        }
        
        serialized = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(serialized.encode()).hexdigest()


class AuditLogger:
    """
    Audit logging service.
    
    Provides:
    - Request logging
    - Response logging
    - Security event logging
    - Query interface
    
    Deterministic, append-only, tamper-evident.
    """
    
    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self._last_hash: Optional[str] = None
    
    async def log_request(
        self,
        request_id: str,
        method: str,
        path: str,
        client_ip: str,
        user_agent: str,
        timestamp: float,
        user_id: Optional[int] = None,
        institution_id: Optional[int] = None
    ) -> AuditLogEntry:
        """Log incoming request."""
        entry = AuditLogEntry(
            request_id=request_id,
            timestamp=datetime.utcnow(),
            user_id=user_id,
            institution_id=institution_id,
            method=method,
            path=path,
            client_ip=client_ip,
            user_agent=user_agent,
            event_type="REQUEST",
            previous_hash=await self._get_last_hash()
        )
        
        entry.entry_hash = entry.compute_hash()
        
        if self.db:
            self.db.add(entry)
            await self.db.flush()
        
        self._last_hash = entry.entry_hash
        return entry
    
    async def log_response(
        self,
        request_id: str,
        status_code: int,
        duration_ms: int,
        timestamp: float
    ) -> AuditLogEntry:
        """Log outgoing response."""
        entry = AuditLogEntry(
            request_id=request_id,
            timestamp=datetime.utcnow(),
            method="RESPONSE",
            path="",
            client_ip="",
            status_code=status_code,
            duration_ms=duration_ms,
            event_type="RESPONSE",
            previous_hash=await self._get_last_hash()
        )
        
        entry.entry_hash = entry.compute_hash()
        
        if self.db:
            self.db.add(entry)
            await self.db.flush()
        
        self._last_hash = entry.entry_hash
        return entry
    
    async def log_security_event(
        self,
        request_id: str,
        event_type: str,
        client_ip: str,
        path: str,
        details: str,
        timestamp: float,
        user_id: Optional[int] = None,
        event_category: str = "SECURITY"
    ) -> AuditLogEntry:
        """Log security-related event."""
        entry = AuditLogEntry(
            request_id=request_id,
            timestamp=datetime.utcnow(),
            user_id=user_id,
            method="EVENT",
            path=path,
            client_ip=client_ip,
            event_type="SECURITY_EVENT",
            event_category=event_category,
            details_json=details,
            previous_hash=await self._get_last_hash()
        )
        
        entry.entry_hash = entry.compute_hash()
        
        if self.db:
            self.db.add(entry)
            await self.db.flush()
        
        self._last_hash = entry.entry_hash
        return entry
    
    async def _get_last_hash(self) -> Optional[str]:
        """Get hash of last audit log entry."""
        if self._last_hash:
            return self._last_hash
        
        if not self.db:
            return None
        
        result = await self.db.execute(
            select(AuditLogEntry)
            .order_by(desc(AuditLogEntry.id))
            .limit(1)
        )
        last_entry = result.scalar_one_or_none()
        
        return last_entry.entry_hash if last_entry else None
    
    async def query_logs(
        self,
        user_id: Optional[int] = None,
        institution_id: Optional[int] = None,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditLogEntry]:
        """
        Query audit logs with filters.
        
        Args:
            user_id: Filter by user
            institution_id: Filter by institution
            event_type: Filter by event type
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum results
        
        Returns:
            List of audit log entries
        """
        if not self.db:
            return []
        
        query = select(AuditLogEntry)
        
        if user_id:
            query = query.where(AuditLogEntry.user_id == user_id)
        
        if institution_id:
            query = query.where(AuditLogEntry.institution_id == institution_id)
        
        if event_type:
            query = query.where(AuditLogEntry.event_type == event_type)
        
        if start_time:
            query = query.where(AuditLogEntry.timestamp >= start_time)
        
        if end_time:
            query = query.where(AuditLogEntry.timestamp <= end_time)
        
        query = query.order_by(desc(AuditLogEntry.timestamp)).limit(limit)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def verify_chain_integrity(self) -> Dict[str, Any]:
        """
        Verify cryptographic chain integrity.
        
        Returns:
            Dict with verification results
        """
        if not self.db:
            return {"valid": False, "error": "No database connection"}
        
        result = await self.db.execute(
            select(AuditLogEntry).order_by(AuditLogEntry.id.asc())
        )
        entries = result.scalars().all()
        
        if not entries:
            return {"valid": True, "entries_checked": 0}
        
        invalid_entries = []
        
        for i, entry in enumerate(entries):
            # Verify entry hash
            computed = entry.compute_hash()
            if computed != entry.entry_hash:
                invalid_entries.append({
                    "id": entry.id,
                    "error": "Hash mismatch",
                    "stored": entry.entry_hash[:16],
                    "computed": computed[:16]
                })
                continue
            
            # Verify chain link (except first entry)
            if i > 0:
                expected_previous = entries[i-1].entry_hash
                if entry.previous_hash != expected_previous:
                    invalid_entries.append({
                        "id": entry.id,
                        "error": "Chain break",
                        "expected_previous": expected_previous[:16],
                        "actual_previous": (entry.previous_hash or "")[:16]
                    })
        
        return {
            "valid": len(invalid_entries) == 0,
            "entries_checked": len(entries),
            "invalid_entries": invalid_entries,
            "tamper_detected": len(invalid_entries) > 0
        }


# Import Column and other SQLAlchemy elements
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
