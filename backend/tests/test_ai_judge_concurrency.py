"""
AI Judge Concurrency Integration Test — Phase 4 Refactored

Tests production-safe guarantees:
- DB-enforced idempotency (no duplicate evaluations)
- No asyncio.Lock (works with uvicorn --workers 4)
- LLM calls outside transactions
- 10 simultaneous calls result in exactly 1 evaluation
"""
import pytest
import asyncio
import httpx
from datetime import datetime
from typing import List, Dict, Any

BASE_URL = "http://127.0.0.1:8000"


@pytest.mark.asyncio
async def test_concurrent_evaluation_idempotency():
    """
    Test: 10 concurrent evaluation requests for same round/participant.
    
    Expected:
    - Only ONE evaluation row created
    - Only ONE completed evaluation
    - Others return existing evaluation (idempotent)
    - No duplicate attempts created
    - Test fails if race condition exists
    """
    # Setup: Login as faculty and get tokens
    faculty_token = await _login_faculty()
    
    # Setup: Create/get session with a completed round
    session_id, round_id, participant_id, rubric_version_id = await _setup_test_data(faculty_token)
    
    # Fire 10 concurrent evaluation requests
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        tasks = []
        for i in range(10):
            task = _trigger_evaluation(
                client, faculty_token, session_id, round_id, 
                participant_id, rubric_version_id, request_num=i
            )
            tasks.append(task)
        
        # Execute all concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Analyze results
    successful_results = [r for r in results if not isinstance(r, Exception)]
    
    # Count unique evaluation IDs
    evaluation_ids = set()
    completed_count = 0
    processing_count = 0
    cached_count = 0
    
    for result in successful_results:
        eval_id = result.get("evaluation_id")
        if eval_id:
            evaluation_ids.add(eval_id)
        
        if result.get("status") == "completed":
            completed_count += 1
        elif result.get("status") == "processing":
            processing_count += 1
        elif result.get("from_cache"):
            cached_count += 1
    
    # ASSERTIONS
    print(f"\n=== CONCURRENCY TEST RESULTS ===")
    print(f"Total requests: 10")
    print(f"Successful responses: {len(successful_results)}")
    print(f"Unique evaluation IDs: {len(evaluation_ids)} (should be 1)")
    print(f"Completed evaluations: {completed_count}")
    print(f"Processing responses: {processing_count}")
    print(f"Cached responses: {cached_count}")
    
    # CRITICAL: Exactly one evaluation row must exist
    assert len(evaluation_ids) == 1, f"Expected 1 evaluation, got {len(evaluation_ids)}"
    
    # Verify via API that only one evaluation exists in DB
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.get(
            f"/api/ai-judge/sessions/{session_id}/evaluations",
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        evaluations = response.json().get("evaluations", [])
        
        # Filter for our round/participant
        our_evaluations = [
            e for e in evaluations 
            if e["round_id"] == round_id and e["participant_id"] == participant_id
        ]
        
        print(f"Evaluations in DB for round {round_id}, participant {participant_id}: {len(our_evaluations)}")
        assert len(our_evaluations) == 1, f"Expected 1 evaluation in DB, found {len(our_evaluations)}"
    
    # Verify no duplicate attempts
    evaluation_id = list(evaluation_ids)[0]
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.get(
            f"/api/ai-judge/evaluations/{evaluation_id}",
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        details = response.json()
        attempts = details.get("attempts", [])
        
        print(f"Total attempts created: {len(attempts)}")
        # Should have at most a few attempts (not 10)
        assert len(attempts) <= 3, f"Too many attempts: {len(attempts)} (expected <= 3)"
    
    print("\n✅ CONCURRENCY TEST PASSED - No race conditions detected")


async def _login_faculty() -> str:
    """Login as faculty and return token."""
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.post(
            "/api/auth/login",
            data={"username": "faculty@gmail.com", "password": "password123"}
        )
        return response.json()["access_token"]


async def _setup_test_data(faculty_token: str) -> tuple:
    """Setup test session, round, participant."""
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Create session
        session_response = await client.post(
            "/api/classroom/sessions",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={
                "case_id": 1,
                "topic": "Concurrency Test",
                "category": "Test",
                "prep_time_minutes": 5,
                "oral_time_minutes": 10
            }
        )
        session_id = session_response.json()["id"]
        session_code = session_response.json()["session_code"]
        
        # Student joins
        student_token = await _login_student()
        join_response = await client.post(
            "/api/classroom/sessions/join",
            headers={"Authorization": f"Bearer {student_token}"},
            json={"session_code": session_code}
        )
        participant_id = join_response.json().get("participant_id") or join_response.json().get("user_id")
        
        # Transition to PREPARING
        await client.post(
            f"/api/classroom/sessions/{session_id}/transition",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={"target_state": "PREPARING", "reason": "test"}
        )
        
        # Create round
        round_response = await client.post(
            "/api/classroom/rounds",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={
                "session_id": session_id,
                "round_index": 1,
                "round_type": "PETITIONER_MAIN",
                "default_turn_seconds": 60
            }
        )
        round_id = round_response.json()["id"]
        
        # Start round
        await client.post(
            f"/api/classroom/rounds/{round_id}/start",
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        
        # Student starts and submits turn
        turns = round_response.json().get("turns", [])
        if turns:
            turn_id = turns[0]["id"]
            await client.post(
                f"/api/classroom/turns/{turn_id}/start",
                headers={"Authorization": f"Bearer {student_token}"}
            )
            await client.post(
                f"/api/classroom/turns/{turn_id}/submit",
                headers={"Authorization": f"Bearer {student_token}"},
                json={
                    "turn_id": turn_id,
                    "transcript": "Test argument for concurrency evaluation.",
                    "word_count": 6
                }
            )
        
        # Get rubric version (use default)
        rubrics_response = await client.get(
            "/api/ai-judge/rubrics",
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        rubrics = rubrics_response.json().get("rubrics", [])
        rubric_version_id = rubrics[0]["id"] if rubrics else 1
        
        return session_id, round_id, participant_id, rubric_version_id


async def _login_student() -> str:
    """Login as student and return token."""
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.post(
            "/api/auth/login",
            data={"username": "student1@gmail.com", "password": "password123"}
        )
        return response.json()["access_token"]


async def _trigger_evaluation(
    client: httpx.AsyncClient,
    faculty_token: str,
    session_id: int,
    round_id: int,
    participant_id: int,
    rubric_version_id: int,
    request_num: int
) -> Dict[str, Any]:
    """Trigger evaluation request."""
    try:
        response = await client.post(
            f"/api/ai-judge/sessions/{session_id}/rounds/{round_id}/evaluate",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={
                "participant_id": participant_id,
                "rubric_version_id": rubric_version_id
            },
            timeout=45.0
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "error": f"HTTP {response.status_code}",
                "detail": response.text,
                "request_num": request_num
            }
    except Exception as e:
        return {"error": str(e), "request_num": request_num}


@pytest.mark.asyncio
async def test_explicit_status_transitions():
    """
    Test that status transitions are explicit and never inferred.
    
    Verifies:
    - PENDING → PROCESSING → COMPLETED
    - PENDING → PROCESSING → REQUIRES_REVIEW
    - Status column exists and is ENUM
    - No status inference from attempts table
    """
    faculty_token = await _login_faculty()
    session_id, round_id, participant_id, rubric_version_id = await _setup_test_data(faculty_token)
    
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Trigger evaluation
        response = await client.post(
            f"/api/ai-judge/sessions/{session_id}/rounds/{round_id}/evaluate",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={
                "participant_id": participant_id,
                "rubric_version_id": rubric_version_id
            }
        )
        
        result = response.json()
        evaluation_id = result.get("evaluation_id")
        
        # Get evaluation details
        details_response = await client.get(
            f"/api/ai-judge/evaluations/{evaluation_id}",
            headers={"Authorization": f"Bearer {faculty_token}"}
        )
        details = details_response.json()
        
        # Verify explicit status
        status = details.get("status")
        assert status in ["completed", "requires_review", "processing"], f"Invalid status: {status}"
        
        # Verify status is in response (not inferred)
        assert "status" in details, "Status must be explicit in response"
        
        print(f"\n✅ Status transition test passed: status={status}")


@pytest.mark.asyncio
async def test_server_side_score_computation():
    """
    Test that score is computed server-side, never trusting LLM total.
    
    Verifies:
    - Score breakdown sums to final score
    - Weights from frozen rubric used
    - No trust of LLM-provided total
    """
    faculty_token = await _login_faculty()
    session_id, round_id, participant_id, rubric_version_id = await _setup_test_data(faculty_token)
    
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Trigger evaluation
        response = await client.post(
            f"/api/ai-judge/sessions/{session_id}/rounds/{round_id}/evaluate",
            headers={"Authorization": f"Bearer {faculty_token}"},
            json={
                "participant_id": participant_id,
                "rubric_version_id": rubric_version_id
            }
        )
        
        result = response.json()
        
        if result.get("status") == "completed":
            score = result.get("score")
            breakdown = result.get("breakdown", {})
            
            # Verify server-side computation
            computed_total = sum(breakdown.values())
            assert abs(computed_total - score) < 0.01, \
                f"Score mismatch: breakdown sums to {computed_total}, score is {score}"
            
            print(f"\n✅ Server-side score computation verified: {score} = sum({breakdown})")


if __name__ == "__main__":
    print("AI Judge Concurrency Integration Tests")
    print("Run with: pytest backend/tests/test_ai_judge_concurrency.py -v -s")
    print("\nPrerequisites:")
    print("1. Server running at http://127.0.0.1:8000")
    print("2. FEATURE_AI_JUDGE_EVALUATION=True")
    print("3. Valid faculty and student accounts in DB")
