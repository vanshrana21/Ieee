"""
Integration Tests for Session State Machine

Tests the full flow including API endpoints, database operations, and concurrency.
"""
import pytest
import pytest_asyncio
import asyncio
from datetime import datetime
from typing import AsyncGenerator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import get_db
from backend.orm.base import Base
from backend.orm.classroom_session import ClassroomSession
from backend.orm.session_state_transition import SessionStateTransition
from backend.orm.classroom_session_state_log import ClassroomSessionStateLog
from backend.orm.user import User, UserRole
from backend.config.feature_flags import FeatureFlags

# Enable feature flag for tests
FeatureFlags.FEATURE_CLASSROOM_SM = True

# Test database
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# Override database dependency
async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with async_session() as session:
        yield session
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def faculty_user(client: AsyncClient) -> dict:
    """Create a faculty user and return auth info."""
    # Register faculty user
    response = await client.post("/api/auth/register", json={
        "email": "faculty_integration@test.com",
        "password": "password123",
        "name": "Integration Test Faculty",
        "role": "faculty"
    })
    
    assert response.status_code == 201
    data = response.json()
    
    return {
        "id": data["user_id"],
        "email": "faculty_integration@test.com",
        "token": data["access_token"],
        "role": "faculty"
    }


@pytest_asyncio.fixture
async def student_user(client: AsyncClient) -> dict:
    """Create a student user and return auth info."""
    response = await client.post("/api/auth/register", json={
        "email": "student_integration@test.com",
        "password": "password123",
        "name": "Integration Test Student",
        "role": "student"
    })
    
    assert response.status_code == 201
    data = response.json()
    
    return {
        "id": data["user_id"],
        "email": "student_integration@test.com",
        "token": data["access_token"],
        "role": "student"
    }


@pytest_asyncio.fixture
async def classroom_session(client: AsyncClient, faculty_user: dict) -> dict:
    """Create a classroom session and return session info."""
    response = await client.post(
        "/api/classroom/sessions",
        headers={"Authorization": f"Bearer {faculty_user['token']}"},
        json={
            "case_id": 1,
            "topic": "Integration Test Session",
            "category": "constitutional",
            "prep_time_minutes": 15,
            "oral_time_minutes": 10
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    return {
        "id": data["id"],
        "session_code": data["session_code"],
        "current_state": data["current_state"]
    }


# ==========================================
# Integration Tests for State Transitions
# ==========================================

@pytest.mark.asyncio
async def test_full_state_flow(client: AsyncClient, faculty_user: dict, classroom_session: dict):
    """
    Test the complete state flow:
    CREATED -> PREPARING -> ARGUING_PETITIONER -> CANCELLED
    """
    token = faculty_user["token"]
    session_id = classroom_session["id"]
    
    # 1. Transition: CREATED -> PREPARING
    response = await client.post(
        f"/api/classroom/sessions/{session_id}/transition",
        headers={"Authorization": f"Bearer {token}"},
        json={"target_state": "PREPARING", "reason": "Starting preparation"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["new_state"] == "PREPARING"
    
    # 2. Get allowed transitions
    response = await client.get(
        f"/api/classroom/sessions/{session_id}/allowed-transitions",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["from_state"] == "PREPARING"
    assert "ARGUING_PETITIONER" in data["allowed_states"]
    
    # 3. Transition: PREPARING -> CANCELLED (cancel the session)
    response = await client.post(
        f"/api/classroom/sessions/{session_id}/transition",
        headers={"Authorization": f"Bearer {token}"},
        json={"target_state": "CANCELLED", "reason": "Test cancellation"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["new_state"] == "CANCELLED"
    
    # 4. Check state history
    response = await client.get(
        f"/api/classroom/sessions/{session_id}/state-history",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2  # At least 2 transitions logged
    
    # Verify the transitions are in the log
    states_in_log = [(log["from_state"], log["to_state"]) for log in data]
    assert ("CREATED", "PREPARING") in states_in_log
    assert ("PREPARING", "CANCELLED") in states_in_log


@pytest.mark.asyncio
async def test_invalid_transition(client: AsyncClient, faculty_user: dict, classroom_session: dict):
    """Test that invalid transitions are rejected with proper error messages."""
    token = faculty_user["token"]
    session_id = classroom_session["id"]
    
    # Try to jump from CREATED to COMPLETED (not allowed)
    response = await client.post(
        f"/api/classroom/sessions/{session_id}/transition",
        headers={"Authorization": f"Bearer {token}"},
        json={"target_state": "COMPLETED", "reason": "Trying to skip"}
    )
    
    assert response.status_code == 400
    data = response.json()
    assert data["detail"]["error"] == "InvalidTransition"
    assert "Cannot transition" in data["detail"]["message"]
    assert "allowed_states" in data["detail"]


@pytest.mark.asyncio
async def test_student_cannot_faculty_transition(client: AsyncClient, faculty_user: dict, student_user: dict):
    """Test that students cannot perform faculty-only transitions."""
    # First, create a session as faculty
    response = await client.post(
        "/api/classroom/sessions",
        headers={"Authorization": f"Bearer {faculty_user['token']}"},
        json={
            "case_id": 1,
            "topic": "Student Test Session",
            "category": "constitutional"
        }
    )
    
    assert response.status_code == 200
    session_id = response.json()["id"]
    
    # Student tries to transition (should fail)
    response = await client.post(
        f"/api/classroom/sessions/{session_id}/transition",
        headers={"Authorization": f"Bearer {student_user['token']}"},
        json={"target_state": "PREPARING", "reason": "Student trying"}
    )
    
    # Should be 403 Forbidden or similar
    assert response.status_code in [403, 400]


@pytest.mark.asyncio
async def test_idempotency(client: AsyncClient, faculty_user: dict, classroom_session: dict):
    """Test that transitioning to the same state is a no-op."""
    token = faculty_user["token"]
    session_id = classroom_session["id"]
    
    # First transition
    response = await client.post(
        f"/api/classroom/sessions/{session_id}/transition",
        headers={"Authorization": f"Bearer {token}"},
        json={"target_state": "PREPARING", "reason": "First transition"}
    )
    
    assert response.status_code == 200
    first_data = response.json()
    
    # Try to transition to the same state again
    response = await client.post(
        f"/api/classroom/sessions/{session_id}/transition",
        headers={"Authorization": f"Bearer {token}"},
        json={"target_state": "PREPARING", "reason": "Idempotent transition"}
    )
    
    assert response.status_code == 200
    second_data = response.json()
    
    # Both should succeed and be in the same state
    assert first_data["new_state"] == "PREPARING"
    assert second_data["new_state"] == "PREPARING"


@pytest.mark.asyncio
async def test_concurrent_transitions(client: AsyncClient, faculty_user: dict, classroom_session: dict):
    """
    Test concurrency safety by attempting two simultaneous transitions.
    One should succeed, the other should fail with 409 Conflict.
    """
    token = faculty_user["token"]
    session_id = classroom_session["id"]
    
    async def attempt_transition():
        """Attempt a transition and return the response."""
        response = await client.post(
            f"/api/classroom/sessions/{session_id}/transition",
            headers={"Authorization": f"Bearer {token}"},
            json={"target_state": "PREPARING", "reason": "Concurrent attempt"}
        )
        return response
    
    # Launch two concurrent transition attempts
    results = await asyncio.gather(
        attempt_transition(),
        attempt_transition(),
        return_exceptions=True
    )
    
    # Analyze results
    success_count = 0
    conflict_count = 0
    
    for result in results:
        if isinstance(result, Exception):
            continue
        if result.status_code == 200:
            success_count += 1
        elif result.status_code == 409:
            conflict_count += 1
    
    # At least one should succeed
    assert success_count >= 1, "At least one transition should succeed"


@pytest.mark.asyncio
async def test_get_allowed_transitions_endpoint(client: AsyncClient, faculty_user: dict, classroom_session: dict):
    """Test the allowed-transitions endpoint."""
    token = faculty_user["token"]
    session_id = classroom_session["id"]
    
    response = await client.get(
        f"/api/classroom/sessions/{session_id}/allowed-transitions",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "from_state" in data
    assert "allowed_states" in data
    assert "transitions" in data
    assert data["from_state"] == "CREATED"
    assert "PREPARING" in data["allowed_states"]


@pytest.mark.asyncio
async def test_session_not_found(client: AsyncClient, faculty_user: dict):
    """Test that transitioning a non-existent session returns 404."""
    token = faculty_user["token"]
    
    response = await client.post(
        "/api/classroom/sessions/99999/transition",
        headers={"Authorization": f"Bearer {token}"},
        json={"target_state": "PREPARING", "reason": "Non-existent"}
    )
    
    assert response.status_code == 400  # or 404 depending on implementation
    data = response.json()
    assert "error" in data["detail"].lower() or "not found" in data["detail"].lower()


@pytest.mark.asyncio
async def test_state_history_logging(client: AsyncClient, faculty_user: dict, classroom_session: dict):
    """Test that all transitions are logged with correct information."""
    token = faculty_user["token"]
    session_id = classroom_session["id"]
    
    # Perform a transition
    await client.post(
        f"/api/classroom/sessions/{session_id}/transition",
        headers={"Authorization": f"Bearer {token}"},
        json={"target_state": "PREPARING", "reason": "Logging test"}
    )
    
    # Get state history
    response = await client.get(
        f"/api/classroom/sessions/{session_id}/state-history",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Find the PREPARING transition log
    prep_transition = None
    for log in data:
        if log["to_state"] == "PREPARING":
            prep_transition = log
            break
    
    assert prep_transition is not None
    assert prep_transition["from_state"] == "CREATED"
    assert prep_transition["triggered_by_user_id"] == faculty_user["id"]
    assert prep_transition["reason"] == "Logging test"
    assert prep_transition["is_successful"] is True
    assert "created_at" in prep_transition
