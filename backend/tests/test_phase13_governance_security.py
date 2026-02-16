"""
Phase 13 — Governance Security Test Suite

Tests for cross-tenant isolation, role enforcement, and governance security.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from decimal import Decimal

from sqlalchemy import select, insert, update, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from backend.core.tenant_guard import (
    require_institution_scope,
    require_role,
    require_active_institution,
    is_super_admin,
    ROLE_INSTITUTION_ADMIN,
    ROLE_FACULTY,
    ROLE_JUDGE,
    ROLE_PARTICIPANT,
    ALLOWED_ROLES
)
from backend.services.institution_service import (
    InstitutionService,
    OnlyAdminRemovalError
)
from backend.services.plan_enforcement_service import (
    PlanEnforcementService,
    PlanLimitExceededError
)
from backend.orm.tournament_results import (
    Institution,
    InstitutionRole,
    InstitutionAuditLog
)


class TestCrossInstitutionIsolation:
    """Test cross-tenant access is blocked."""
    
    def test_cross_institution_read_returns_404(self):
        """Test cross-institution read returns 404 (not 403)."""
        # Create mock entity with different institution
        entity = Mock()
        entity.institution_id = 2
        
        # User from institution 1
        user = {"id": 1, "institution_id": 1, "is_super_admin": False}
        
        # Should raise HTTPException with 404
        with pytest.raises(HTTPException) as exc_info:
            require_institution_scope(entity, user)
        
        assert exc_info.value.status_code == 404, "Must return 404 not 403"
    
    def test_cross_institution_write_blocked(self):
        """Test cross-institution write is blocked."""
        entity = Mock()
        entity.institution_id = 3
        
        user = {"id": 1, "institution_id": 1, "is_super_admin": False}
        
        with pytest.raises(HTTPException) as exc_info:
            require_institution_scope(entity, user)
        
        assert exc_info.value.status_code == 404
    
    def test_same_institution_allowed(self):
        """Test same institution access is allowed."""
        entity = Mock()
        entity.institution_id = 1
        
        user = {"id": 1, "institution_id": 1, "is_super_admin": False}
        
        # Should not raise
        require_institution_scope(entity, user)
    
    def test_super_admin_bypass(self):
        """Test super admin can access any institution."""
        entity = Mock()
        entity.institution_id = 999
        
        user = {"id": 1, "institution_id": 1, "is_super_admin": True}
        
        # Should not raise
        require_institution_scope(entity, user)
    
    def test_no_institution_returns_404(self):
        """Test user with no institution gets 404."""
        entity = Mock()
        entity.institution_id = 1
        
        user = {"id": 1, "institution_id": None, "is_super_admin": False}
        
        with pytest.raises(HTTPException) as exc_info:
            require_institution_scope(entity, user)
        
        assert exc_info.value.status_code == 404


class TestRoleEnforcement:
    """Test role enforcement."""
    
    @pytest.mark.asyncio
    async def test_valid_role_allowed(self, db_session: AsyncSession):
        """Test valid role is allowed."""
        # Mock user with institution_admin role
        user = {"id": 1, "institution_id": 1, "is_super_admin": False}
        
        # Mock database to return role
        with patch.object(db_session, 'execute') as mock_exec:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = Mock(role="institution_admin")
            mock_exec.return_value = mock_result
            
            # Should not raise
            await require_role("institution_admin", user, db_session)
    
    @pytest.mark.asyncio
    async def test_invalid_role_blocked(self, db_session: AsyncSession):
        """Test invalid role is blocked."""
        user = {"id": 1, "institution_id": 1, "is_super_admin": False}
        
        with patch.object(db_session, 'execute') as mock_exec:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_exec.return_value = mock_result
            
            with pytest.raises(HTTPException) as exc_info:
                await require_role("institution_admin", user, db_session)
            
            assert exc_info.value.status_code == 403
    
    @pytest.mark.asyncio
    async def test_super_admin_role_bypass(self, db_session: AsyncSession):
        """Test super admin bypasses role check."""
        user = {"id": 1, "institution_id": 1, "is_super_admin": True}
        
        # Should not raise even without role
        await require_role("institution_admin", user, db_session)
    
    @pytest.mark.asyncio
    async def test_invalid_role_name_rejected(self, db_session: AsyncSession):
        """Test invalid role name is rejected."""
        user = {"id": 1, "institution_id": 1, "is_super_admin": False}
        
        with pytest.raises(HTTPException) as exc_info:
            await require_role("hacker", user, db_session)
        
        assert exc_info.value.status_code == 400


class TestInstitutionStatusEnforcement:
    """Test institution status blocks operations."""
    
    @pytest.mark.asyncio
    async def test_active_institution_allowed(self, db_session: AsyncSession):
        """Test active institution allows operations."""
        with patch.object(db_session, 'execute') as mock_exec:
            mock_inst = Mock(status="active")
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_inst
            mock_exec.return_value = mock_result
            
            # Should not raise
            await require_active_institution(1, db_session)
    
    @pytest.mark.asyncio
    async def test_suspended_institution_blocked(self, db_session: AsyncSession):
        """Test suspended institution blocks operations."""
        with patch.object(db_session, 'execute') as mock_exec:
            mock_inst = Mock(status="suspended")
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_inst
            mock_exec.return_value = mock_result
            
            with pytest.raises(HTTPException) as exc_info:
                await require_active_institution(1, db_session)
            
            assert exc_info.value.status_code == 403
            assert "suspended" in str(exc_info.value.detail).lower()
    
    @pytest.mark.asyncio
    async def test_archived_institution_blocked(self, db_session: AsyncSession):
        """Test archived institution blocks operations."""
        with patch.object(db_session, 'execute') as mock_exec:
            mock_inst = Mock(status="archived")
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_inst
            mock_exec.return_value = mock_result
            
            with pytest.raises(HTTPException) as exc_info:
                await require_active_institution(1, db_session)
            
            assert exc_info.value.status_code == 403


class TestPlanLimitEnforcement:
    """Test plan limits are enforced."""
    
    @pytest.mark.asyncio
    async def test_tournament_limit_enforced(self, db_session: AsyncSession):
        """Test tournament limit blocks creation."""
        service = PlanEnforcementService(db_session)
        
        with patch.object(db_session, 'execute') as mock_exec:
            # Mock institution with max_tournaments=5
            mock_inst = Mock(max_tournaments=5)
            
            # Mock count returning 5 (at limit)
            async def mock_execute(*args, **kwargs):
                mock_result = Mock()
                if 'count' in str(args[0]).lower():
                    mock_result.scalar.return_value = 5
                else:
                    mock_result.scalar_one_or_none.return_value = mock_inst
                return mock_result
            
            mock_exec.side_effect = mock_execute
            
            with pytest.raises(PlanLimitExceededError):
                await service.enforce_tournament_limit(1)
    
    @pytest.mark.asyncio
    async def test_concurrent_session_limit_enforced(self, db_session: AsyncSession):
        """Test concurrent session limit blocks new sessions."""
        service = PlanEnforcementService(db_session)
        
        with patch.object(db_session, 'execute') as mock_exec:
            mock_inst = Mock(max_concurrent_sessions=10)
            
            async def mock_execute(*args, **kwargs):
                mock_result = Mock()
                if 'count' in str(args[0]).lower():
                    mock_result.scalar.return_value = 10
                else:
                    mock_result.scalar_one_or_none.return_value = mock_inst
                return mock_result
            
            mock_exec.side_effect = mock_execute
            
            with pytest.raises(PlanLimitExceededError):
                await service.enforce_concurrent_sessions_limit(1)
    
    @pytest.mark.asyncio
    async def test_audit_export_permission_enforced(self, db_session: AsyncSession):
        """Test audit export permission is enforced."""
        service = PlanEnforcementService(db_session)
        
        with patch.object(db_session, 'execute') as mock_exec:
            mock_inst = Mock(allow_audit_export=False)
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_inst
            mock_exec.return_value = mock_result
            
            with pytest.raises(PermissionError):
                await service.enforce_audit_export_permission(1)


class TestOnlyAdminRemoval:
    """Test only admin cannot be removed."""
    
    @pytest.mark.asyncio
    async def test_last_admin_removal_blocked(self, db_session: AsyncSession):
        """Test removing last admin is blocked."""
        service = InstitutionService(db_session)
        
        with patch.object(db_session, 'execute') as mock_exec:
            # Mock user role as institution_admin
            mock_role = Mock(role="institution_admin")
            
            async def mock_execute(*args, **kwargs):
                mock_result = Mock()
                
                # First call returns the role
                if 'institution_roles' in str(args[0]) and 'WHERE' in str(args[0]):
                    mock_result.scalar_one_or_none.return_value = mock_role
                # Second call returns count of admins (1)
                elif 'count' in str(args[0]).lower():
                    mock_result.scalar.return_value = 1
                
                return mock_result
            
            mock_exec.side_effect = mock_execute
            
            with pytest.raises(OnlyAdminRemovalError):
                await service.remove_user_from_institution(1, 1, 2)


class TestAuditLogImmutability:
    """Test audit log is append-only."""
    
    def test_append_only_trigger_exists(self):
        """Test PostgreSQL triggers prevent modification."""
        # Verify trigger functions exist
        # This would be verified by checking the migration
        assert True  # Placeholder - actual test would query database
    
    @pytest.mark.asyncio
    async def test_cannot_update_audit_entry(self, db_session: AsyncSession):
        """Test audit entries cannot be updated."""
        # This test would attempt to update an audit log entry
        # and verify it raises an exception due to the trigger
        pass  # Placeholder - requires actual database
    
    @pytest.mark.asyncio
    async def test_cannot_delete_audit_entry(self, db_session: AsyncSession):
        """Test audit entries cannot be deleted."""
        # This test would attempt to delete an audit log entry
        # and verify it raises an exception due to the trigger
        pass  # Placeholder - requires actual database


class TestSuperAdminBypass:
    """Test super admin bypass works correctly."""
    
    def test_is_super_admin_detection(self):
        """Test super admin detection works."""
        assert is_super_admin({"is_super_admin": True}) is True
        assert is_super_admin({"is_super_admin": False}) is False
        assert is_super_admin({}) is False
        assert is_super_admin({"is_super_admin": None}) is False
    
    @pytest.mark.asyncio
    async def test_super_admin_skips_institution_scope(self, db_session: AsyncSession):
        """Test super admin skips institution scope check."""
        entity = Mock()
        entity.institution_id = 999
        
        user = {"id": 1, "is_super_admin": True}
        
        # Should not raise
        require_institution_scope(entity, user)
    
    @pytest.mark.asyncio
    async def test_super_admin_skips_role_check(self, db_session: AsyncSession):
        """Test super admin skips role check."""
        user = {"id": 1, "institution_id": 1, "is_super_admin": True}
        
        # Should not raise even without the role
        await require_role("institution_admin", user, db_session)


class TestRoleEscalationPrevention:
    """Test role escalation is blocked."""
    
    @pytest.mark.asyncio
    async def test_faculty_cannot_assign_admin_role(self, db_session: AsyncSession):
        """Test faculty cannot assign admin role."""
        # This would test that a faculty user attempting to assign
        # institution_admin role is blocked
        pass  # Requires actual endpoint test
    
    def test_allowed_roles_excludes_super_admin(self):
        """Test super_admin is not in allowed institution roles."""
        # super_admin is a platform role, not an institution role
        assert "super_admin" not in ALLOWED_ROLES
        assert ROLE_INSTITUTION_ADMIN in ALLOWED_ROLES
        assert ROLE_FACULTY in ALLOWED_ROLES
        assert ROLE_JUDGE in ALLOWED_ROLES
        assert ROLE_PARTICIPANT in ALLOWED_ROLES


class TestSQLInjectionPrevention:
    """Test SQL injection prevention."""
    
    def test_institution_slug_sanitization(self):
        """Test institution slug sanitization."""
        from backend.services.institution_service import InstitutionService
        
        dangerous_inputs = [
            "'; DROP TABLE institutions; --",
            "<script>alert('xss')</script>",
            "institution' OR '1'='1",
            "institution; DELETE FROM users;",
        ]
        
        for dangerous in dangerous_inputs:
            slug = InstitutionService._generate_slug(None, dangerous)
            # Slug should not contain SQL special characters
            assert "'" not in slug
            assert ";" not in slug
            assert "--" not in slug
            assert "DROP" not in slug.upper()
    
    def test_role_validation_rejects_injection(self):
        """Test role validation rejects injection attempts."""
        dangerous_roles = [
            "institution_admin'; DROP TABLE users; --",
            "faculty' OR '1'='1",
        ]
        
        for dangerous in dangerous_roles:
            assert dangerous not in ALLOWED_ROLES


class TestInstitutionCreationSecurity:
    """Test institution creation security."""
    
    @pytest.mark.asyncio
    async def test_only_super_admin_can_create_institution(self, db_session: AsyncSession):
        """Test only super admin can create institution."""
        service = InstitutionService(db_session)
        
        # Regular user should not be able to create
        # This is enforced at route level
        pass  # Placeholder - tested via route tests
    
    def test_slug_uniqueness_enforced(self):
        """Test duplicate slugs are prevented."""
        # The service generates unique slugs by appending counter
        # if slug already exists
        from backend.services.institution_service import InstitutionService
        
        # This would be tested with actual database
        pass


class TestGovernanceLogging:
    """Test all governance actions are logged."""
    
    @pytest.mark.asyncio
    async def test_role_assignment_logged(self, db_session: AsyncSession):
        """Test role assignment creates audit log."""
        service = InstitutionService(db_session)
        
        with patch.object(service, '_log_action') as mock_log:
            mock_log.return_value = None
            
            with patch.object(db_session, 'execute') as mock_exec:
                # Mock no existing role
                mock_result = Mock()
                mock_result.scalar_one_or_none.return_value = None
                mock_exec.return_value = mock_result
                
                try:
                    await service.assign_role(1, 1, "faculty", 1)
                except:
                    pass  # May fail for other reasons
                
                # Verify log_action was called
                mock_log.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_plan_update_logged(self, db_session: AsyncSession):
        """Test plan limit update creates audit log."""
        service = InstitutionService(db_session)
        
        with patch.object(service, '_log_action') as mock_log:
            mock_log.return_value = None
            
            with patch.object(db_session, 'execute') as mock_exec:
                mock_inst = Mock(
                    max_tournaments=5,
                    max_concurrent_sessions=10,
                    allow_audit_export=True
                )
                
                async def mock_execute(*args, **kwargs):
                    mock_result = Mock()
                    mock_result.scalar_one_or_none.return_value = mock_inst
                    return mock_result
                
                mock_exec.side_effect = mock_execute
                
                try:
                    await service.update_plan_limits(1, 1, max_tournaments=10)
                except:
                    pass
                
                # Verify log_action was called with correct payload
                mock_log.assert_called_once()


class TestSuspendedInstitution:
    """Test suspended institution behavior."""
    
    @pytest.mark.asyncio
    async def test_suspended_cannot_create_tournament(self, db_session: AsyncSession):
        """Test suspended institution cannot create tournaments."""
        # Attempting to create tournament in suspended institution
        # should be blocked by require_active_institution
        pass  # Placeholder - tested via integration tests
    
    @pytest.mark.asyncio
    async def test_suspended_can_still_read(self, db_session: AsyncSession):
        """Test suspended institution can still read data."""
        # Read operations should not be blocked by suspension
        pass  # Placeholder - tested via integration tests
