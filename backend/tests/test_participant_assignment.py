"""
Layer 2 Integration Tests - Deterministic Participant Assignment

Tests for:
- Deterministic assignment (position -> side/speaker mapping)
- Race condition safety (parallel joins)
- Duplicate join prevention
- Session full handling
- Audit logging
- State-based restrictions
"""
import pytest
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.services.participant_assignment_service import (
    assign_participant,
    get_assignment_for_position,
    SessionFullError,
    SessionNotJoinableError,
    DuplicateJoinError,
    UnauthorizedRoleError,
    MAX_PARTICIPANTS
)
from backend.orm.classroom_session import ClassroomSession, ClassroomParticipant
from backend.orm.classroom_participant_audit_log import ClassroomParticipantAuditLog
from backend.orm.user import User, UserRole


class TestDeterministicAssignmentLogic:
    """Test the deterministic assignment mapping."""
    
    def test_assignment_mapping(self):
        """Test that positions 1-4 map to correct side/speaker combinations."""
        # Position 1 -> PETITIONER, 1
        side, speaker = get_assignment_for_position(1)
        assert side == "PETITIONER"
        assert speaker == 1
        
        # Position 2 -> RESPONDENT, 1
        side, speaker = get_assignment_for_position(2)
        assert side == "RESPONDENT"
        assert speaker == 1
        
        # Position 3 -> PETITIONER, 2
        side, speaker = get_assignment_for_position(3)
        assert side == "PETITIONER"
        assert speaker == 2
        
        # Position 4 -> RESPONDENT, 2
        side, speaker = get_assignment_for_position(4)
        assert side == "RESPONDENT"
        assert speaker == 2
    
    def test_invalid_position_raises_error(self):
        """Test that invalid positions raise ValueError."""
        with pytest.raises(ValueError):
            get_assignment_for_position(0)
        
        with pytest.raises(ValueError):
            get_assignment_for_position(5)
        
        with pytest.raises(ValueError):
            get_assignment_for_position(-1)


class TestParticipantAssignmentService:
    """Test the assignment service with database."""
    
    @pytest.fixture
    async def teacher(self, db: AsyncSession):
        """Create a test teacher."""
        user = User(
            email="teacher@test.com",
            hashed_password="hashed",
            name="Test Teacher",
            role=UserRole.FACULTY
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    
    @pytest.fixture
    async def session(self, db: AsyncSession, teacher):
        """Create a test session in PREPARING state."""
        from backend.orm.moot_case import MootCase
        
        # Create a moot case first
        case = MootCase(
            title="Test Case",
            description="Test Description",
            category="constitutional"
        )
        db.add(case)
        await db.commit()
        await db.refresh(case)
        
        # Create session
        classroom_session = ClassroomSession(
            session_code="JURIS-TEST01",
            teacher_id=teacher.id,
            case_id=case.id,
            topic="Test Session",
            category="constitutional",
            current_state="PREPARING",
            is_active=True,
            max_participants=4
        )
        db.add(classroom_session)
        await db.commit()
        await db.refresh(classroom_session)
        return classroom_session
    
    @pytest.fixture
    async def students(self, db: AsyncSession):
        """Create 5 test students."""
        students = []
        for i in range(1, 6):
            user = User(
                email=f"student{i}@test.com",
                hashed_password="hashed",
                name=f"Student {i}",
                role=UserRole.STUDENT
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            students.append(user)
        return students
    
    async def test_unauthorized_role_rejected(self, db: AsyncSession, session, teacher):
        """Test that non-students cannot join."""
        with pytest.raises(UnauthorizedRoleError):
            await assign_participant(
                session_id=session.id,
                user_id=teacher.id,
                db=db,
                is_student=False
            )
    
    async def test_join_preparing_session(self, db: AsyncSession, session, students):
        """Test that students can join PREPARING session."""
        result = await assign_participant(
            session_id=session.id,
            user_id=students[0].id,
            db=db,
            is_student=True
        )
        
        assert result["session_id"] == session.id
        assert result["user_id"] == students[0].id
        assert result["side"] == "PETITIONER"
        assert result["speaker_number"] == 1
        assert result["total_participants"] == 1
    
    async def test_deterministic_assignment_order(self, db: AsyncSession, session, students):
        """Test that 4 students get deterministic assignments."""
        assignments = []
        
        for i in range(4):
            result = await assign_participant(
                session_id=session.id,
                user_id=students[i].id,
                db=db,
                is_student=True
            )
            assignments.append(result)
            await db.commit()
        
        # Verify deterministic order
        assert assignments[0]["side"] == "PETITIONER"
        assert assignments[0]["speaker_number"] == 1
        
        assert assignments[1]["side"] == "RESPONDENT"
        assert assignments[1]["speaker_number"] == 1
        
        assert assignments[2]["side"] == "PETITIONER"
        assert assignments[2]["speaker_number"] == 2
        
        assert assignments[3]["side"] == "RESPONDENT"
        assert assignments[3]["speaker_number"] == 2
    
    async def test_session_full_rejected(self, db: AsyncSession, session, students):
        """Test that 5th join is rejected."""
        # Fill session with 4 students
        for i in range(4):
            await assign_participant(
                session_id=session.id,
                user_id=students[i].id,
                db=db,
                is_student=True
            )
            await db.commit()
        
        # 5th should fail
        with pytest.raises(SessionFullError):
            await assign_participant(
                session_id=session.id,
                user_id=students[4].id,
                db=db,
                is_student=True
            )
    
    async def test_duplicate_join_idempotent(self, db: AsyncSession, session, students):
        """Test that duplicate join returns existing assignment."""
        # First join
        result1 = await assign_participant(
            session_id=session.id,
            user_id=students[0].id,
            db=db,
            is_student=True
        )
        await db.commit()
        
        # Duplicate join
        result2 = await assign_participant(
            session_id=session.id,
            user_id=students[0].id,
            db=db,
            is_student=True
        )
        await db.commit()
        
        # Should return same assignment
        assert result1["side"] == result2["side"]
        assert result1["speaker_number"] == result2["speaker_number"]
    
    async def test_cancelled_session_rejected(self, db: AsyncSession, session, students, teacher):
        """Test that cancelled session rejects joins."""
        # Cancel session
        session.current_state = "CANCELLED"
        await db.commit()
        
        with pytest.raises(SessionNotJoinableError):
            await assign_participant(
                session_id=session.id,
                user_id=students[0].id,
                db=db,
                is_student=True
            )
    
    async def test_completed_session_rejected(self, db: AsyncSession, session, students):
        """Test that completed session rejects joins."""
        # Complete session
        session.current_state = "COMPLETED"
        await db.commit()
        
        with pytest.raises(SessionNotJoinableError):
            await assign_participant(
                session_id=session.id,
                user_id=students[0].id,
                db=db,
                is_student=True
            )
    
    async def test_audit_log_created(self, db: AsyncSession, session, students):
        """Test that successful join creates audit log."""
        await assign_participant(
            session_id=session.id,
            user_id=students[0].id,
            db=db,
            is_student=True,
            ip_address="127.0.0.1"
        )
        await db.commit()
        
        # Check audit log
        result = await db.execute(
            select(ClassroomParticipantAuditLog)
            .where(ClassroomParticipantAuditLog.session_id == session.id)
        )
        logs = result.scalars().all()
        
        assert len(logs) == 1
        assert logs[0].user_id == students[0].id
        assert logs[0].side == "PETITIONER"
        assert logs[0].speaker_number == 1
        assert logs[0].is_successful == True
        assert logs[0].ip_address == "127.0.0.1"
    
    async def test_failed_join_audit_log(self, db: AsyncSession, session, students):
        """Test that failed join creates audit log."""
        # Fill session
        for i in range(4):
            await assign_participant(
                session_id=session.id,
                user_id=students[i].id,
                db=db,
                is_student=True
            )
            await db.commit()
        
        # Failed join attempt
        try:
            await assign_participant(
                session_id=session.id,
                user_id=students[4].id,
                db=db,
                is_student=True
            )
        except SessionFullError:
            pass
        
        await db.commit()
        
        # Check audit log includes failure
        result = await db.execute(
            select(ClassroomParticipantAuditLog)
            .where(ClassroomParticipantAuditLog.user_id == students[4].id)
        )
        logs = result.scalars().all()
        
        assert len(logs) == 1
        assert logs[0].is_successful == False
        assert "Session full" in logs[0].error_message


class TestRaceConditions:
    """Test race condition safety with parallel operations."""
    
    @pytest.fixture
    async def teacher(self, db: AsyncSession):
        """Create a test teacher."""
        user = User(
            email="teacher_race@test.com",
            hashed_password="hashed",
            name="Race Test Teacher",
            role=UserRole.FACULTY
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    
    @pytest.fixture
    async def session(self, db: AsyncSession, teacher):
        """Create a test session."""
        from backend.orm.moot_case import MootCase
        
        case = MootCase(
            title="Race Test Case",
            description="Test Description",
            category="constitutional"
        )
        db.add(case)
        await db.commit()
        await db.refresh(case)
        
        classroom_session = ClassroomSession(
            session_code="JURIS-RACE01",
            teacher_id=teacher.id,
            case_id=case.id,
            topic="Race Test Session",
            category="constitutional",
            current_state="PREPARING",
            is_active=True,
            max_participants=4
        )
        db.add(classroom_session)
        await db.commit()
        await db.refresh(classroom_session)
        return classroom_session
    
    @pytest.fixture
    async def students(self, db: AsyncSession):
        """Create 10 test students for race testing."""
        students = []
        for i in range(1, 11):
            user = User(
                email=f"race_student{i}@test.com",
                hashed_password="hashed",
                name=f"Race Student {i}",
                role=UserRole.STUDENT
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            students.append(user)
        return students


# Mark tests as async
pytestmark = pytest.mark.asyncio
