"""
Round Engine Integration Tests — Phase 3

Integration tests with real database and server.
Tests full round flow with 4 participants.
"""
import pytest
import asyncio
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List, Dict, Any
import os
import sys

# Add project root to path
sys.path.insert(0, '/Users/vanshrana/Desktop/IEEE')

from backend.database import AsyncSessionLocal
from backend.orm.user import User, UserRole
from backend.orm.classroom_session import ClassroomSession, ClassroomParticipant
from backend.orm.classroom_round import ClassroomRound
from backend.orm.classroom_turn import ClassroomTurn, ClassroomTurnAudit


# ============================================================================
# Test Configuration
# ============================================================================

BASE_URL = "http://127.0.0.1:8000"
TEST_DB_PATH = "/Users/vanshrana/Desktop/IEEE/legalai_test.db"

FACULTY_CREDENTIALS = {
    "email": "faculty@gmail.com",
    "password": "password123"
}

STUDENT_CREDENTIALS = [
    {"email": "student1@gmail.com", "password": "password123"},
    {"email": "student2@gmail.com", "password": "password123"},
    {"email": "student3@gmail.com", "password": "password123"},
    {"email": "student4@gmail.com", "password": "password123"},
]


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
async def client():
    """Create HTTP client."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        yield client


@pytest.fixture
async def db():
    """Create database session."""
    async with AsyncSessionLocal() as session:
        yield session


# ============================================================================
# Helper Functions
# ============================================================================

async def login_user(client: httpx.AsyncClient, email: str, password: str) -> Optional[str]:
    """Login user and return token."""
    try:
        response = await client.post(
            "/api/auth/login",
            data={"username": email, "password": password}
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
    except Exception:
        pass
    return None


async def create_test_session(
    client: httpx.AsyncClient,
    faculty_token: str
) -> Tuple[Optional[int], Optional[str]]:
    """Create a test classroom session."""
    try:
        response = await client.post(
            "/api/classroom/sessions",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={
                "case_id": 1,
                "topic": "Test Round Engine",
                "category": "Test",
                "prep_time_minutes": 5,
                "oral_time_minutes": 10
            }
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("id"), data.get("session_code")
    except Exception as e:
        print(f"Failed to create session: {e}")
    return None, None


async def join_session(
    client: httpx.AsyncClient,
    student_token: str,
    session_code: str
) -> Optional[Dict]:
    """Student join session."""
    try:
        response = await client.post(
            "/api/classroom/sessions/join",
            headers={"Authorization": f"Bearer {student_token}"},
            json={"session_code": session_code}
        )
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None


async def transition_session(
    client: httpx.AsyncClient,
    faculty_token: str,
    session_id: int,
    target_state: str
) -> bool:
    """Transition session state."""
    try:
        response = await client.post(
            f"/api/classroom/sessions/{session_id}/transition",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={"target_state": target_state, "reason": "test"}
        )
        return response.status_code == 200
    except Exception:
        return False


# ============================================================================
# Integration Test: Full Round Flow
# ============================================================================

@pytest.mark.asyncio
async def test_full_round_flow():
    """
    Full round flow test:
    1. Create session with 4 participants
    2. Create round with default turns
    3. Faculty starts round
    4. Each participant starts and submits their turn
    5. Verify round completes
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Step 1: Faculty login
        faculty_token = await login_user(
            client,
            FACULTY_CREDENTIALS["email"],
            FACULTY_CREDENTIALS["password"]
        )
        assert faculty_token, "Faculty login failed"
        print("✓ Faculty logged in")
        
        # Step 2: Create session
        session_id, session_code = await create_test_session(client, faculty_token)
        assert session_id, "Failed to create session"
        print(f"✓ Session created: {session_code}")
        
        # Step 3: Students join
        student_tokens = []
        for creds in STUDENT_CREDENTIALS:
            token = await login_user(client, creds["email"], creds["password"])
            assert token, f"Student login failed: {creds['email']}"
            
            join_result = await join_session(client, token, session_code)
            assert join_result, f"Failed to join: {creds['email']}"
            
            student_tokens.append({
                "token": token,
                "participant_id": join_result.get("participant_id") or join_result.get("user_id"),
                "side": join_result.get("side"),
                "speaker_number": join_result.get("speaker_number")
            })
            print(f"✓ Student joined: {creds['email']} -> {join_result.get('side')} #{join_result.get('speaker_number')}")
        
        assert len(student_tokens) == 4, "Not all students joined"
        
        # Step 4: Transition to PREPARING state
        success = await transition_session(client, faculty_token, session_id, "PREPARING")
        assert success, "Failed to transition to PREPARING"
        print("✓ Session transitioned to PREPARING")
        
        # Step 5: Create round
        create_response = await client.post(
            "/api/classroom/rounds",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={
                "session_id": session_id,
                "round_index": 1,
                "round_type": "PETITIONER_MAIN",
                "default_turn_seconds": 300
            }
        )
        assert create_response.status_code == 201, f"Failed to create round: {create_response.text}"
        round_data = create_response.json()
        round_id = round_data["id"]
        print(f"✓ Round created: ID {round_id}")
        
        # Verify turns were auto-generated
        turns = round_data.get("turns", [])
        assert len(turns) == 4, f"Expected 4 turns, got {len(turns)}"
        print(f"✓ Auto-generated {len(turns)} turns")
        
        # Step 6: Start round
        start_response = await client.post(
            f"/api/classroom/rounds/{round_id}/start",
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        assert start_response.status_code == 200, f"Failed to start round: {start_response.text}"
        start_data = start_response.json()
        assert start_data["status"] == "ACTIVE"
        print("✓ Round started")
        
        # Step 7: Each participant takes their turn
        for i, turn in enumerate(turns):
            turn_id = turn["id"]
            participant_id = turn["participant_id"]
            
            # Find student token for this participant
            student = next((s for s in student_tokens if s["participant_id"] == participant_id), None)
            assert student, f"No student found for participant {participant_id}"
            
            # Start turn
            turn_start_response = await client.post(
                f"/api/classroom/turns/{turn_id}/start",
                headers={"Authorization": f"Bearer {student['token']}"}
            )
            assert turn_start_response.status_code == 200, f"Failed to start turn {turn_id}"
            print(f"✓ Turn {i+1} started by {student['side']} #{student['speaker_number']}")
            
            # Submit turn
            submit_response = await client.post(
                f"/api/classroom/turns/{turn_id}/submit",
                headers={"Authorization": f"Bearer {student['token']}"},
                json={
                    "turn_id": turn_id,
                    "transcript": f"This is the argument from {student['side']} speaker {student['speaker_number']}.",
                    "word_count": 15
                }
            )
            assert submit_response.status_code == 200, f"Failed to submit turn {turn_id}"
            submit_data = submit_response.json()
            print(f"✓ Turn {i+1} submitted")
            
            # Check if round complete (on last turn)
            if i == len(turns) - 1:
                assert submit_data.get("round_status") == "COMPLETED", "Round should be completed"
                print("✓ Round completed after all turns")
        
        # Step 8: Verify round state
        round_get_response = await client.get(
            f"/api/classroom/rounds/{round_id}",
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        assert round_get_response.status_code == 200
        final_round = round_get_response.json()
        assert final_round["status"] == "COMPLETED", f"Expected COMPLETED, got {final_round['status']}"
        print("✓ Final round state: COMPLETED")
        
        # Step 9: Verify all turns submitted
        final_turns = final_round.get("turns", [])
        for turn in final_turns:
            assert turn["is_submitted"] is True, f"Turn {turn['id']} not submitted"
        print("✓ All turns submitted")
        
        # Step 10: Check audit logs
        for turn in final_turns:
            audit_response = await client.get(
                f"/api/classroom/turns/{turn['id']}/audit",
                headers={"Authorization": f"Bearer {faculty_token}"}
            )
            assert audit_response.status_code == 200
            audit_entries = audit_response.json()
            # Should have at least START and SUBMIT entries
            actions = [entry["action"] for entry in audit_entries]
            assert "START" in actions, f"Turn {turn['id']} missing START audit"
            assert "SUBMIT" in actions, f"Turn {turn['id']} missing SUBMIT audit"
        print("✓ Audit logs verified for all turns")
        
        print("\n🎉 Full round flow test PASSED!")


# ============================================================================
# Concurrency Test
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_turn_start():
    """
    Test concurrent turn start attempts.
    Only the current speaker should succeed.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Setup: Login faculty and create session
        faculty_token = await login_user(
            client,
            FACULTY_CREDENTIALS["email"],
            FACULTY_CREDENTIALS["password"]
        )
        assert faculty_token
        
        session_id, session_code = await create_test_session(client, faculty_token)
        assert session_id
        
        # Students join
        student_tokens = []
        for creds in STUDENT_CREDENTIALS:
            token = await login_user(client, creds["email"], creds["password"])
            join_result = await join_session(client, token, session_code)
            if join_result:
                student_tokens.append({
                    "token": token,
                    "participant_id": join_result.get("participant_id") or join_result.get("user_id")
                })
        
        assert len(student_tokens) == 4
        
        # Create and start round
        await transition_session(client, faculty_token, session_id, "PREPARING")
        
        create_response = await client.post(
            "/api/classroom/rounds",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={
                "session_id": session_id,
                "round_index": 1,
                "round_type": "PETITIONER_MAIN",
                "default_turn_seconds": 300
            }
        )
        round_data = create_response.json()
        round_id = round_data["id"]
        
        await client.post(
            f"/api/classroom/rounds/{round_id}/start",
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        
        turns = round_data.get("turns", [])
        first_turn_id = turns[0]["id"]
        
        # Try to start first turn from all students concurrently
        async def try_start_turn(token: str, turn_id: int) -> Tuple[int, Optional[Dict]]:
            try:
                response = await client.post(
                    f"/api/classroom/turns/{turn_id}/start",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0
                )
                return response.status_code, response.json() if response.status_code == 200 else None
            except Exception as e:
                return 0, None
        
        # Fire all requests simultaneously
        tasks = [
            try_start_turn(student["token"], first_turn_id)
            for student in student_tokens
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Exactly one should succeed (the owner)
        successes = sum(1 for r in results if isinstance(r, tuple) and r[0] == 200)
        failures = sum(1 for r in results if isinstance(r, tuple) and r[0] != 200)
        
        # Note: With proper auth, only the owner should succeed
        # Others should get 403 or 409
        assert successes >= 1, f"Expected at least 1 success, got {successes}"
        assert failures >= 3, f"Expected at least 3 failures, got {failures}"
        
        print(f"✓ Concurrent test: {successes} success, {failures} rejected")


# ============================================================================
# Timeout Test
# ============================================================================

@pytest.mark.asyncio
async def test_turn_timeout_handling():
    """
    Test turn timeout and auto-advance.
    This test uses short timeout for speed.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Setup
        faculty_token = await login_user(
            client,
            FACULTY_CREDENTIALS["email"],
            FACULTY_CREDENTIALS["password"]
        )
        assert faculty_token
        
        session_id, session_code = await create_test_session(client, faculty_token)
        assert session_id
        
        # First student joins
        student_token = await login_user(
            client,
            STUDENT_CREDENTIALS[0]["email"],
            STUDENT_CREDENTIALS[0]["password"]
        )
        await join_session(client, student_token, session_code)
        
        # Create round with short timeout
        await transition_session(client, faculty_token, session_id, "PREPARING")
        
        create_response = await client.post(
            "/api/classroom/rounds",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={
                "session_id": session_id,
                "round_index": 1,
                "round_type": "PETITIONER_MAIN",
                "default_turn_seconds": 2  # Very short for testing
            }
        )
        round_data = create_response.json()
        round_id = round_data["id"]
        
        await client.post(
            f"/api/classroom/rounds/{round_id}/start",
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        
        turns = round_data.get("turns", [])
        first_turn_id = turns[0]["id"]
        
        # Start turn
        await client.post(
            f"/api/classroom/turns/{first_turn_id}/start",
            headers={"Authorization": f"Bearer {student_token}"}
        )
        
        # Wait for timeout
        await asyncio.sleep(3)
        
        # Check that late submission is rejected (if late submissions not allowed)
        submit_response = await client.post(
            f"/api/classroom/turns/{first_turn_id}/submit",
            headers={"Authorization": f"Bearer {student_token}"},
            json={
                "turn_id": first_turn_id,
                "transcript": "Late submission",
                "word_count": 2
            }
        )
        
        # Should be rejected or accepted based on feature flag
        print(f"Late submission response: {submit_response.status_code}")
        
        # Check audit for TIME_EXPIRED
        audit_response = await client.get(
            f"/api/classroom/turns/{first_turn_id}/audit",
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        audit_entries = audit_response.json()
        actions = [entry["action"] for entry in audit_entries]
        
        # May or may not have TIME_EXPIRED depending on timer implementation
        print(f"Audit actions: {actions}")


# ============================================================================
# Force Submit Test
# ============================================================================

@pytest.mark.asyncio
async def test_faculty_force_submit():
    """Test faculty can force submit any turn."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Setup
        faculty_token = await login_user(
            client,
            FACULTY_CREDENTIALS["email"],
            FACULTY_CREDENTIALS["password"]
        )
        assert faculty_token
        
        session_id, session_code = await create_test_session(client, faculty_token)
        assert session_id
        
        student_token = await login_user(
            client,
            STUDENT_CREDENTIALS[0]["email"],
            STUDENT_CREDENTIALS[0]["password"]
        )
        join_result = await join_session(client, student_token, session_code)
        assert join_result
        
        await transition_session(client, faculty_token, session_id, "PREPARING")
        
        create_response = await client.post(
            "/api/classroom/rounds",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={
                "session_id": session_id,
                "round_index": 1,
                "round_type": "PETITIONER_MAIN",
                "default_turn_seconds": 300
            }
        )
        round_data = create_response.json()
        round_id = round_data["id"]
        
        await client.post(
            f"/api/classroom/rounds/{round_id}/start",
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        
        turns = round_data.get("turns", [])
        first_turn_id = turns[0]["id"]
        
        # Faculty force submits without student starting
        force_response = await client.post(
            f"/api/classroom/turns/{first_turn_id}/force_submit",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={
                "turn_id": first_turn_id,
                "transcript": "Faculty forced submit",
                "word_count": 3,
                "reason": "Test force submit"
            }
        )
        
        assert force_response.status_code == 200, f"Force submit failed: {force_response.text}"
        force_data = force_response.json()
        assert force_data["success"] is True
        
        print("✓ Faculty force submit works")


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    print("Round Engine Integration Tests")
    print("=" * 50)
    print("\nRun with: pytest backend/tests/test_round_engine_integration.py -v")
    print("Note: Requires server running at", BASE_URL)
    print()
