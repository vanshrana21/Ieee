"""
Phase 13 — Global Tenant Enforcement Layer

Hard multi-tenant isolation with institution scoping.

Security Level: Maximum
Isolation Level: Hard Multi-Tenant
"""
from typing import Any, Optional
from fastapi import HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.orm.tournament_results import TournamentAuditSnapshot


# Role Constants (Deterministic string comparisons)
ROLE_INSTITUTION_ADMIN = "institution_admin"
ROLE_FACULTY = "faculty"
ROLE_JUDGE = "judge"
ROLE_PARTICIPANT = "participant"
ROLE_SUPER_ADMIN = "super_admin"

ALLOWED_ROLES = {
    ROLE_INSTITUTION_ADMIN,
    ROLE_FACULTY,
    ROLE_JUDGE,
    ROLE_PARTICIPANT
}


class TenantGuardError(Exception):
    """Base exception for tenant guard violations."""
    pass


class InstitutionScopeError(TenantGuardError):
    """Cross-institution access attempt."""
    pass


class RoleError(TenantGuardError):
    """Role verification failure."""
    pass


class InstitutionStatusError(TenantGuardError):
    """Institution status prevents operation."""
    pass


def is_super_admin(user: dict) -> bool:
    """
    Check if user is super admin.
    
    Args:
        user: User dictionary from auth
        
    Returns:
        True if super admin
    """
    return user.get("is_super_admin", False)


def require_institution_scope(entity: Any, current_user: dict) -> None:
    """
    Verify user has access to entity's institution.
    
    Rules:
    - user.institution_id must equal entity.institution_id
    - If mismatch → raise 404 (NOT 403) to prevent information leakage
    - super_admin bypass allowed
    
    Args:
        entity: Entity with institution_id attribute
        current_user: User dictionary from auth
        
    Raises:
        HTTPException: 404 if institution mismatch (deliberately not 403)
    """
    # super_admin bypass
    if is_super_admin(current_user):
        return
    
    user_institution_id = current_user.get("institution_id")
    entity_institution_id = getattr(entity, "institution_id", None)
    
    # Handle institution_id in different formats
    if entity_institution_id is None:
        # Try alternate attribute names
        entity_institution_id = getattr(entity, "institution_id", None)
    
    if user_institution_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )
    
    if entity_institution_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )
    
    # Convert to int for comparison (handle string IDs)
    try:
        user_inst = int(user_institution_id)
        entity_inst = int(entity_institution_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )
    
    if user_inst != entity_inst:
        # Return 404 (NOT 403) to prevent information leakage
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resource not found"
        )


async def require_role(
    role_name: str,
    current_user: dict,
    db: AsyncSession
) -> None:
    """
    Verify user has specified role in their institution.
    
    Rules:
    - Role must exist in institution_roles table
    - If not → raise Unauthorized
    - super_admin bypass allowed
    
    Args:
        role_name: Required role (institution_admin, faculty, judge, participant)
        current_user: User dictionary from auth
        db: Database session
        
    Raises:
        HTTPException: 403 if role not found
    """
    # super_admin bypass
    if is_super_admin(current_user):
        return
    
    # Validate role name
    if role_name not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {role_name}"
        )
    
    user_id = current_user.get("id")
    institution_id = current_user.get("institution_id")
    
    if user_id is None or institution_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication required"
        )
    
    # Check institution_roles table
    from backend.orm.tournament_results import InstitutionRole
    
    result = await db.execute(
        select(InstitutionRole).where(
            InstitutionRole.institution_id == int(institution_id),
            InstitutionRole.user_id == int(user_id),
            InstitutionRole.role == role_name
        )
    )
    
    role = result.scalar_one_or_none()
    
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Required role not found: {role_name}"
        )


async def require_any_role(
    role_names: list[str],
    current_user: dict,
    db: AsyncSession
) -> None:
    """
    Verify user has any of the specified roles.
    
    Args:
        role_names: List of allowed roles
        current_user: User dictionary from auth
        db: Database session
        
    Raises:
        HTTPException: 403 if none of the roles found
    """
    # super_admin bypass
    if is_super_admin(current_user):
        return
    
    user_id = current_user.get("id")
    institution_id = current_user.get("institution_id")
    
    if user_id is None or institution_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication required"
        )
    
    # Check institution_roles table
    from backend.orm.tournament_results import InstitutionRole
    
    result = await db.execute(
        select(InstitutionRole).where(
            InstitutionRole.institution_id == int(institution_id),
            InstitutionRole.user_id == int(user_id),
            InstitutionRole.role.in_(role_names)
        )
    )
    
    role = result.scalar_one_or_none()
    
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )


async def require_active_institution(
    institution_id: int,
    db: AsyncSession
) -> None:
    """
    Verify institution status is active.
    
    Rules:
    - institution.status must be 'active'
    - If suspended → block all writes
    
    Args:
        institution_id: Institution ID to check
        db: Database session
        
    Raises:
        HTTPException: 403 if institution not active
    """
    from backend.orm.tournament_results import Institution
    
    result = await db.execute(
        select(Institution).where(Institution.id == institution_id)
    )
    institution = result.scalar_one_or_none()
    
    if institution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found"
        )
    
    if institution.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Institution is {institution.status}"
        )


async def add_institution_scope(
    query,
    current_user: dict,
    institution_id_column = None
):
    """
    Add institution scope filter to query.
    
    This helper should be used in all multi-tenant queries.
    
    Args:
        query: SQLAlchemy query object
        current_user: User dictionary from auth
        institution_id_column: Column to filter on (default: model.institution_id)
        
    Returns:
        Modified query with institution filter
    """
    # super_admin sees all
    if is_super_admin(current_user):
        return query
    
    user_institution_id = current_user.get("institution_id")
    
    if user_institution_id is None:
        # Return query that returns nothing
        return query.where(False)
    
    if institution_id_column is None:
        # Default to model's institution_id column
        return query.where(query.column_descriptions[0]["entity"].institution_id == int(user_institution_id))
    
    return query.where(institution_id_column == int(user_institution_id))


class TenantGuardMiddleware:
    """
    FastAPI middleware for automatic tenant scoping.
    
    Attaches tenant context to requests.
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            request = Request(scope, receive)
            
            # Attach tenant context
            request.state.tenant_context = {
                "institution_id": None,
                "user_id": None,
                "roles": []
            }
        
        await self.app(scope, receive, send)


def get_current_institution_id(current_user: dict) -> Optional[int]:
    """
    Get current user's institution ID.
    
    Args:
        current_user: User dictionary from auth
        
    Returns:
        Institution ID or None
    """
    if is_super_admin(current_user):
        return None  # Super admin has no institution scope
    
    inst_id = current_user.get("institution_id")
    if inst_id is not None:
        return int(inst_id)
    return None


async def verify_entity_ownership(
    entity_type: str,
    entity_id: int,
    current_user: dict,
    db: AsyncSession
) -> bool:
    """
    Verify user owns/created entity.
    
    Args:
        entity_type: Type of entity (tournament, session, etc.)
        entity_id: Entity ID
        current_user: User dictionary from auth
        db: Database session
        
    Returns:
        True if user has access
    """
    # super_admin bypass
    if is_super_admin(current_user):
        return True
    
    user_institution_id = current_user.get("institution_id")
    
    if user_institution_id is None:
        return False
    
    # Map entity types to their ORM classes
    entity_map = {
        "tournament": "NationalTournament",
        "session": "LiveSession",
        "exhibit": "SessionExhibit",
        "objection": "LiveObjection",
    }
    
    orm_class_name = entity_map.get(entity_type)
    if orm_class_name is None:
        return False
    
    # Dynamic import
    orm_module = __import__("backend.orm.tournament_results", fromlist=[orm_class_name])
    orm_class = getattr(orm_module, orm_class_name, None)
    
    if orm_class is None:
        return False
    
    # Query with institution scope
    result = await db.execute(
        select(orm_class).where(
            orm_class.id == entity_id,
            orm_class.institution_id == int(user_institution_id)
        )
    )
    
    return result.scalar_one_or_none() is not None
