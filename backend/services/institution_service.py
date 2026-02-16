"""
Phase 13 — Institution Service

SaaS institution management with governance controls.

Security Level: Maximum
Determinism: Mandatory
"""
import hashlib
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from decimal import Decimal

from sqlalchemy import select, insert, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.orm.tournament_results import (
    Institution,
    InstitutionRole,
    InstitutionAuditLog
)
from backend.core.tenant_guard import (
    is_super_admin,
    ALLOWED_ROLES,
    ROLE_INSTITUTION_ADMIN
)


class InstitutionServiceError(Exception):
    """Base exception for institution service."""
    pass


class OnlyAdminRemovalError(InstitutionServiceError):
    """Raised when trying to remove the only admin."""
    pass


class UserAlreadyAssignedError(InstitutionServiceError):
    """Raised when user already has role in institution."""
    pass


class InstitutionService:
    """
    Service for institution lifecycle and governance.
    
    All mutations are logged to institution_audit_log.
    All plan limit changes use SERIALIZABLE isolation.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _generate_slug(self, name: str) -> str:
        """
        Generate deterministic slug from name.
        
        Rules:
        - Lowercase
        - Replace spaces with hyphens
        - Remove non-alphanumeric
        - Must be deterministic
        
        Args:
            name: Institution name
            
        Returns:
            Deterministic slug
        """
        # Lowercase
        slug = name.lower()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r'[\s_]+', '-', slug)
        # Remove non-alphanumeric except hyphens
        slug = re.sub(r'[^a-z0-9-]', '', slug)
        # Remove consecutive hyphens
        slug = re.sub(r'-+', '-', slug)
        # Trim hyphens from ends
        slug = slug.strip('-')
        
        return slug[:100]  # Max 100 chars
    
    def _compute_payload_hash(self, payload: Dict[str, Any]) -> str:
        """
        Compute SHA256 hash of deterministic JSON payload.
        
        Args:
            payload: Dictionary to hash
            
        Returns:
            64-character hex hash
        """
        # Deterministic JSON with sorted keys
        serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(serialized.encode()).hexdigest()
    
    async def _log_action(
        self,
        institution_id: int,
        actor_user_id: int,
        action_type: str,
        entity_type: str,
        entity_id: Optional[int],
        payload: Dict[str, Any]
    ) -> None:
        """
        Log governance action to institution_audit_log.
        
        Args:
            institution_id: Institution being acted upon
            actor_user_id: User performing action
            action_type: Type of action
            entity_type: Type of entity
            entity_id: Entity ID (optional)
            payload: Action details (must be sorted for determinism)
        """
        # Ensure payload is sorted
        sorted_payload = dict(sorted(payload.items()))
        
        # Compute hash
        payload_hash = self._compute_payload_hash(sorted_payload)
        
        # Insert log entry
        await self.db.execute(
            insert(InstitutionAuditLog).values(
                institution_id=institution_id,
                actor_user_id=actor_user_id,
                action_type=action_type,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=sorted_payload,
                payload_hash=payload_hash,
                created_at=datetime.utcnow()
            )
        )
    
    async def create_institution(
        self,
        name: str,
        created_by_user_id: int,
        max_tournaments: int = 5,
        max_concurrent_sessions: int = 10,
        allow_audit_export: bool = True
    ) -> Institution:
        """
        Create new institution.
        
        Rules:
        - super_admin only (verified by caller)
        - Slug auto-generated deterministic
        - Audit log entry created
        - SERIALIZABLE isolation enforced by caller
        
        Args:
            name: Institution name
            created_by_user_id: User creating (super_admin)
            max_tournaments: Plan limit
            max_concurrent_sessions: Plan limit
            allow_audit_export: Feature flag
            
        Returns:
            Created Institution
        """
        # Generate slug
        slug = self._generate_slug(name)
        
        # Check slug uniqueness
        existing = await self.db.execute(
            select(Institution).where(Institution.slug == slug)
        )
        if existing.scalar_one_or_none():
            # Append counter to make unique
            counter = 1
            base_slug = slug
            while True:
                slug = f"{base_slug}-{counter}"
                existing = await self.db.execute(
                    select(Institution).where(Institution.slug == slug)
                )
                if not existing.scalar_one_or_none():
                    break
                counter += 1
        
        # Create institution
        result = await self.db.execute(
            insert(Institution).values(
                name=name,
                slug=slug,
                status="active",
                max_tournaments=max_tournaments,
                max_concurrent_sessions=max_concurrent_sessions,
                allow_audit_export=allow_audit_export,
                created_at=datetime.utcnow()
            ).returning(Institution)
        )
        
        institution = result.scalar_one()
        
        # Log creation
        await self._log_action(
            institution_id=institution.id,
            actor_user_id=created_by_user_id,
            action_type="institution_created",
            entity_type="institution",
            entity_id=institution.id,
            payload={
                "name": name,
                "slug": slug,
                "max_tournaments": max_tournaments,
                "max_concurrent_sessions": max_concurrent_sessions,
                "allow_audit_export": allow_audit_export
            }
        )
        
        return institution
    
    async def assign_role(
        self,
        institution_id: int,
        user_id: int,
        role: str,
        assigned_by_user_id: int
    ) -> InstitutionRole:
        """
        Assign role to user in institution.
        
        Rules:
        - institution_admin only (verified by caller)
        - Lock institution_roles FOR UPDATE
        - Idempotent: return existing if present
        - Log action
        
        Args:
            institution_id: Target institution
            user_id: User to assign role
            role: Role to assign
            assigned_by_user_id: Admin performing assignment
            
        Returns:
            InstitutionRole (new or existing)
        """
        # Validate role
        if role not in ALLOWED_ROLES:
            raise ValueError(f"Invalid role: {role}")
        
        # Check existing role with lock
        existing = await self.db.execute(
            select(InstitutionRole).where(
                and_(
                    InstitutionRole.institution_id == institution_id,
                    InstitutionRole.user_id == user_id
                )
            ).with_for_update()
        )
        existing_role = existing.scalar_one_or_none()
        
        if existing_role:
            # Idempotent: update role if different
            if existing_role.role != role:
                old_role = existing_role.role
                await self.db.execute(
                    update(InstitutionRole)
                    .where(InstitutionRole.id == existing_role.id)
                    .values(role=role)
                )
                
                # Log role change
                await self._log_action(
                    institution_id=institution_id,
                    actor_user_id=assigned_by_user_id,
                    action_type="role_changed",
                    entity_type="institution_role",
                    entity_id=existing_role.id,
                    payload={
                        "user_id": user_id,
                        "old_role": old_role,
                        "new_role": role
                    }
                )
            
            # Return updated role
            result = await self.db.execute(
                select(InstitutionRole).where(InstitutionRole.id == existing_role.id)
            )
            return result.scalar_one()
        
        # Create new role
        result = await self.db.execute(
            insert(InstitutionRole).values(
                institution_id=institution_id,
                user_id=user_id,
                role=role,
                created_at=datetime.utcnow()
            ).returning(InstitutionRole)
        )
        
        new_role = result.scalar_one()
        
        # Log assignment
        await self._log_action(
            institution_id=institution_id,
            actor_user_id=assigned_by_user_id,
            action_type="role_assigned",
            entity_type="institution_role",
            entity_id=new_role.id,
            payload={
                "user_id": user_id,
                "role": role
            }
        )
        
        return new_role
    
    async def remove_user_from_institution(
        self,
        institution_id: int,
        user_id: int,
        removed_by_user_id: int
    ) -> None:
        """
        Remove user from institution.
        
        Rules:
        - institution_admin only (verified by caller)
        - Prevent removal if user is only admin
        - Log action
        
        Args:
            institution_id: Target institution
            user_id: User to remove
            removed_by_user_id: Admin performing removal
            
        Raises:
            OnlyAdminRemovalError: If user is only admin
        """
        # Get user's role
        user_role = await self.db.execute(
            select(InstitutionRole).where(
                and_(
                    InstitutionRole.institution_id == institution_id,
                    InstitutionRole.user_id == user_id
                )
            )
        )
        role_to_remove = user_role.scalar_one_or_none()
        
        if role_to_remove is None:
            return  # User not in institution, idempotent
        
        # Check if user is institution_admin and is the only one
        if role_to_remove.role == ROLE_INSTITUTION_ADMIN:
            admin_count = await self.db.execute(
                select(func.count(InstitutionRole.id)).where(
                    and_(
                        InstitutionRole.institution_id == institution_id,
                        InstitutionRole.role == ROLE_INSTITUTION_ADMIN
                    )
                )
            )
            admin_count_val = admin_count.scalar() or 0
            
            if admin_count_val <= 1:
                raise OnlyAdminRemovalError(
                    "Cannot remove the only institution admin"
                )
        
        # Remove user
        await self.db.execute(
            delete(InstitutionRole).where(
                and_(
                    InstitutionRole.institution_id == institution_id,
                    InstitutionRole.user_id == user_id
                )
            )
        )
        
        # Log removal
        await self._log_action(
            institution_id=institution_id,
            actor_user_id=removed_by_user_id,
            action_type="user_removed",
            entity_type="institution_role",
            entity_id=None,
            payload={
                "user_id": user_id,
                "previous_role": role_to_remove.role
            }
        )
    
    async def update_plan_limits(
        self,
        institution_id: int,
        updated_by_user_id: int,
        max_tournaments: Optional[int] = None,
        max_concurrent_sessions: Optional[int] = None,
        allow_audit_export: Optional[bool] = None
    ) -> Institution:
        """
        Update institution plan limits.
        
        Rules:
        - super_admin only (verified by caller)
        - Lock institution FOR UPDATE
        - Log previous + new values
        - payload_json must be sorted
        - SERIALIZABLE isolation enforced by caller
        
        Args:
            institution_id: Target institution
            updated_by_user_id: Super admin performing update
            max_tournaments: New limit (None = no change)
            max_concurrent_sessions: New limit (None = no change)
            allow_audit_export: New flag (None = no change)
            
        Returns:
            Updated Institution
        """
        # Lock institution row
        result = await self.db.execute(
            select(Institution).where(
                Institution.id == institution_id
            ).with_for_update()
        )
        institution = result.scalar_one_or_none()
        
        if institution is None:
            raise ValueError(f"Institution {institution_id} not found")
        
        # Store previous values
        previous_values = {
            "max_tournaments": institution.max_tournaments,
            "max_concurrent_sessions": institution.max_concurrent_sessions,
            "allow_audit_export": institution.allow_audit_export
        }
        
        # Build update dict
        update_values = {}
        if max_tournaments is not None:
            update_values["max_tournaments"] = max_tournaments
        if max_concurrent_sessions is not None:
            update_values["max_concurrent_sessions"] = max_concurrent_sessions
        if allow_audit_export is not None:
            update_values["allow_audit_export"] = allow_audit_export
        
        if not update_values:
            return institution  # Nothing to update
        
        # Apply update
        await self.db.execute(
            update(Institution)
            .where(Institution.id == institution_id)
            .values(**update_values)
        )
        
        # Log update with sorted payload
        new_values = {
            "max_tournaments": max_tournaments if max_tournaments is not None else institution.max_tournaments,
            "max_concurrent_sessions": max_concurrent_sessions if max_concurrent_sessions is not None else institution.max_concurrent_sessions,
            "allow_audit_export": allow_audit_export if allow_audit_export is not None else institution.allow_audit_export
        }
        
        payload = {
            "new_values": dict(sorted(new_values.items())),
            "previous_values": dict(sorted(previous_values.items()))
        }
        
        await self._log_action(
            institution_id=institution_id,
            actor_user_id=updated_by_user_id,
            action_type="plan_limits_updated",
            entity_type="institution",
            entity_id=institution_id,
            payload=payload
        )
        
        # Return updated institution
        result = await self.db.execute(
            select(Institution).where(Institution.id == institution_id)
        )
        return result.scalar_one()
    
    async def update_institution_status(
        self,
        institution_id: int,
        new_status: str,
        updated_by_user_id: int
    ) -> Institution:
        """
        Update institution status.
        
        Rules:
        - super_admin only (verified by caller)
        - Allowed: active, suspended, archived
        - Log action
        
        Args:
            institution_id: Target institution
            new_status: New status
            updated_by_user_id: Super admin performing update
            
        Returns:
            Updated Institution
        """
        # Validate status
        allowed_statuses = {"active", "suspended", "archived"}
        if new_status not in allowed_statuses:
            raise ValueError(f"Invalid status: {new_status}")
        
        # Lock and update
        result = await self.db.execute(
            select(Institution).where(
                Institution.id == institution_id
            ).with_for_update()
        )
        institution = result.scalar_one_or_none()
        
        if institution is None:
            raise ValueError(f"Institution {institution_id} not found")
        
        old_status = institution.status
        
        await self.db.execute(
            update(Institution)
            .where(Institution.id == institution_id)
            .values(status=new_status)
        )
        
        # Log status change
        await self._log_action(
            institution_id=institution_id,
            actor_user_id=updated_by_user_id,
            action_type="status_changed",
            entity_type="institution",
            entity_id=institution_id,
            payload={
                "new_status": new_status,
                "previous_status": old_status
            }
        )
        
        # Return updated
        result = await self.db.execute(
            select(Institution).where(Institution.id == institution_id)
        )
        return result.scalar_one()
    
    async def get_institution_users(
        self,
        institution_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all users in institution with their roles.
        
        Args:
            institution_id: Institution to query
            
        Returns:
            List of user dictionaries with roles
        """
        result = await self.db.execute(
            select(InstitutionRole).where(
                InstitutionRole.institution_id == institution_id
            )
        )
        roles = result.scalars().all()
        
        return [
            {
                "user_id": role.user_id,
                "role": role.role,
                "assigned_at": role.created_at.isoformat() if role.created_at else None
            }
            for role in roles
        ]
    
    async def get_audit_log(
        self,
        institution_id: int,
        limit: int = 100
    ) -> List[InstitutionAuditLog]:
        """
        Get institution audit log entries.
        
        Args:
            institution_id: Institution to query
            limit: Maximum entries to return
            
        Returns:
            List of audit log entries
        """
        result = await self.db.execute(
            select(InstitutionAuditLog)
            .where(InstitutionAuditLog.institution_id == institution_id)
            .order_by(InstitutionAuditLog.created_at.desc())
            .limit(limit)
        )
        
        return result.scalars().all()
    
    async def verify_audit_log_integrity(
        self,
        institution_id: int
    ) -> Dict[str, Any]:
        """
        Verify integrity of institution audit log entries.
        
        Recomputes payload hashes and verifies they match stored values.
        
        Args:
            institution_id: Institution to verify
            
        Returns:
            Verification report
        """
        result = await self.db.execute(
            select(InstitutionAuditLog)
            .where(InstitutionAuditLog.institution_id == institution_id)
            .order_by(InstitutionAuditLog.created_at)
        )
        entries = result.scalars().all()
        
        invalid_entries = []
        
        for entry in entries:
            # Recompute hash
            sorted_payload = dict(sorted(entry.payload_json.items()))
            expected_hash = self._compute_payload_hash(sorted_payload)
            
            if expected_hash != entry.payload_hash:
                invalid_entries.append({
                    "entry_id": entry.id,
                    "stored_hash": entry.payload_hash,
                    "computed_hash": expected_hash
                })
        
        return {
            "institution_id": institution_id,
            "total_entries": len(entries),
            "valid": len(invalid_entries) == 0,
            "invalid_count": len(invalid_entries),
            "invalid_entries": invalid_entries
        }
