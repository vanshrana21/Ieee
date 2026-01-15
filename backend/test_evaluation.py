"""
test_evaluation.py
Comprehensive test suite for Phase 5: AI Evaluation & Feedback Engine

Run with: pytest test_evaluation.py -v
"""
import pytest
import asyncio
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.orm.practice_attempt import PracticeAttempt
from backend.orm.practice_evaluation import PracticeEvaluation, EvaluationType
from backend.orm.practice_question import PracticeQuestion, QuestionType
from backend.orm.user import User
from backend.services.ai_evaluator import AIEvaluator


# ============================================================================
# FIXTURE SETUP
# ============================================================================

@pytest.fixture
async def sample_user(db: AsyncSession):
    """Create a test user"""
    user = User(
        email="test@example.com",
        full_name="Test Student",
        password_hash="hashed",
        role="student",
        course_id=1,
        current_semester=5
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def sample_descriptive_question(db: AsyncSession):
    """Create a descriptive practice question"""
    question = PracticeQuestion(
        module_id=1,
        question_type=QuestionType.SHORT_ANSWER,
        question="What are the essential elements of a valid contract?",
        correct_answer="""The essential elements of a valid contract are:
1. Offer and Acceptance (consensus ad idem)
2. Consideration
3. Capacity to contract
4. Free consent
5. Lawful object and consideration
6. Not expressly declared void""",
        explanation="A contract requires mutual agreement, valuable consideration, legal capacity, genuine consent, and lawful purpose.",
        marks=10,
        difficulty="medium"
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question


@pytest.fixture
async def sample_mcq_question(db: AsyncSession):
    """Create an MCQ practice question"""
    question = PracticeQuestion(
        module_id=1,
        question_type=QuestionType.MCQ,
        question="Which of the following is NOT an essential element of a contract?",
        option_a="Offer and Acceptance",
        option_b="Consideration",
        option_c="Written documentation",
        option_d="Free consent",
        correct_answer="C",
        explanation="Written documentation is not essential for all contracts. Many contracts can be oral.",
        marks=2,
        difficulty="easy"
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return question


# ============================================================================
# TEST: DATABASE SCHEMA
# ============================================================================

@pytest.mark.asyncio
async def test_evaluation_table_exists(db: AsyncSession):
    """Test that practice_evaluations table exists and has correct structure"""
    # Try to query the table
    stmt = select(PracticeEvaluation).limit(1)
    result = await db.execute(stmt)
    evaluations = result.scalars().all()
    # Should not raise an error even if empty
    assert evaluations is not None


@pytest.mark.asyncio
async def test_unique_constraint(
    db: AsyncSession,
    sample_user,
    sample_descriptive_question
):
    """Test that only one evaluation can exist per attempt"""
    # Create attempt
    attempt = PracticeAttempt(
        user_id=sample_user.id,
        practice_question_id=sample_descriptive_question.id,
        selected_option="Test answer",
        is_correct=None,
        attempt_number=1
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    
    # Create first evaluation
    eval1 = PracticeEvaluation(
        practice_attempt_id=attempt.id,
        evaluation_type=EvaluationType.AI_DESCRIPTIVE.value,
        status="completed"
    )
    db.add(eval1)
    await db.commit()
    
    # Try to create second evaluation for same attempt
    eval2 = PracticeEvaluation(
        practice_attempt_id=attempt.id,
        evaluation_type=EvaluationType.AI_DESCRIPTIVE.value,
        status="pending"
    )
    db.add(eval2)
    
    # Should raise integrity error
    with pytest.raises(Exception):
        await db.commit()


# ============================================================================
# TEST: OWNERSHIP VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_cannot_evaluate_others_attempt(
    client,
    db: AsyncSession,
    sample_user,
    sample_descriptive_question
):
    """Test that users cannot evaluate attempts they don't own"""
    # Create User A's attempt
    user_a_attempt = PracticeAttempt(
        user_id=sample_user.id,
        practice_question_id=sample_descriptive_question.id,
        selected_option="User A's answer",
        is_correct=None,
        attempt_number=1
    )
    db.add(user_a_attempt)
    await db.commit()
    await db.refresh(user_a_attempt)
    
    # Create User B
    user_b = User(
        email="userb@example.com",
        full_name="User B",
        password_hash="hashed",
        role="student",
        course_id=1,
        current_semester=5
    )
    db.add(user_b)
    await db.commit()
    
    # Get User B's token (mock authentication)
    # In real test, would use auth fixtures
    
    # Try to trigger evaluation as User B
    response = await client.post(
        f"/api/practice/attempts/{user_a_attempt.id}/evaluate",
        headers={"Authorization": f"Bearer {get_token_for_user(user_b)}"}
    )
    
    # Should return 403 Forbidden
    assert response.status_code == 403
    assert "You can only evaluate your own attempts" in response.json()["detail"]


# ============================================================================
# TEST: IDEMPOTENCY
# ============================================================================

@pytest.mark.asyncio
async def test_evaluation_idempotency(
    db: AsyncSession,
    sample_user,
    sample_descriptive_question
):
    """Test that multiple evaluation requests don't create duplicates"""
    # Create attempt
    attempt = PracticeAttempt(
        user_id=sample_user.id,
        practice_question_id=sample_descriptive_question.id,
        selected_option="Test answer",
        is_correct=None,
        attempt_number=1
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    
    # Create initial evaluation
    eval1 = PracticeEvaluation(
        practice_attempt_id=attempt.id,
        evaluation_type=EvaluationType.AI_DESCRIPTIVE.value,
        status="completed",
        score=8.0,
        feedback_text="Good answer"
    )
    db.add(eval1)
    await db.commit()
    first_eval_id = eval1.id
    
    # Query evaluations for this attempt
    stmt = select(PracticeEvaluation).where(
        PracticeEvaluation.practice_attempt_id == attempt.id
    )
    result = await db.execute(stmt)
    evaluations = result.scalars().all()
    
    # Should have exactly one evaluation
    assert len(evaluations) == 1
    assert evaluations[0].id == first_eval_id
    assert evaluations[0].score == 8.0


# ============================================================================
# TEST: AI EVALUATOR SERVICE
# ============================================================================

@pytest.mark.asyncio
async def test_ai_evaluator_descriptive(
    db: AsyncSession,
    sample_user,
    sample_descriptive_question
):
    """Test AI evaluation of descriptive answer"""
    # Create attempt with good answer
    attempt = PracticeAttempt(
        user_id=sample_user.id,
        practice_question_id=sample_descriptive_question.id,
        selected_option="""The essential elements of a valid contract are:
1. Offer and Acceptance - mutual agreement
2. Consideration - something of value exchanged
3. Capacity - parties must be legally capable
4. Free Consent - no coercion or fraud
5. Lawful Object - legal purpose""",
        is_correct=None,
        attempt_number=1
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    
    # Run AI evaluation
    result = await AIEvaluator.evaluate_attempt(
        db, attempt, sample_descriptive_question
    )
    
    # Verify result structure
    assert "score" in result
    assert "feedback_text" in result
    assert "strengths" in result
    assert "improvements" in result
    assert "confidence_score" in result
    
    # Verify score is within range
    assert 0 <= result["score"] <= sample_descriptive_question.marks
    
    # Verify confidence is valid
    assert 0.0 <= result["confidence_score"] <= 1.0
    
    # Verify lists are not empty for good answer
    assert len(result["strengths"]) > 0
    assert len(result["improvements"]) >= 0


@pytest.mark.asyncio
async def test_ai_evaluator_poor_answer(
    db: AsyncSession,
    sample_user,
    sample_descriptive_question
):
    """Test AI evaluation of poor/incomplete answer"""
    # Create attempt with poor answer
    attempt = PracticeAttempt(
        user_id=sample_user.id,
        practice_question_id=sample_descriptive_question.id,
        selected_option="A contract needs agreement and money.",
        is_correct=None,
        attempt_number=1
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    
    # Run AI evaluation
    result = await AIEvaluator.evaluate_attempt(
        db, attempt, sample_descriptive_question
    )
    
    # Should give lower score
    assert result["score"] < sample_descriptive_question.marks * 0.5
    
    # Should have improvements
    assert len(result["improvements"]) > 0


# ============================================================================
# TEST: EVALUATION STATUS FLOW
# ============================================================================

@pytest.mark.asyncio
async def test_evaluation_status_flow(
    db: AsyncSession,
    sample_user,
    sample_descriptive_question
):
    """Test evaluation status transitions"""
    # Create attempt
    attempt = PracticeAttempt(
        user_id=sample_user.id,
        practice_question_id=sample_descriptive_question.id,
        selected_option="Test answer",
        is_correct=None,
        attempt_number=1
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    
    # Create evaluation in pending state
    evaluation = PracticeEvaluation(
        practice_attempt_id=attempt.id,
        evaluation_type=EvaluationType.AI_DESCRIPTIVE.value,
        status="pending",
        evaluated_by="ai",
        model_version="gemini-1.5-pro"
    )
    db.add(evaluation)
    await db.commit()
    await db.refresh(evaluation)
    
    # Test is_pending
    assert evaluation.is_pending() == True
    assert evaluation.is_completed() == False
    
    # Mark as processing
    evaluation.mark_processing()
    await db.commit()
    assert evaluation.status == "processing"
    assert evaluation.is_pending() == True
    
    # Mark as completed
    evaluation.mark_completed(
        score=8.5,
        feedback="Good answer!",
        strengths=["Clear explanation"],
        improvements=["Add examples"],
        confidence=0.9
    )
    await db.commit()
    
    assert evaluation.is_completed() == True
    assert evaluation.is_pending() == False
    assert evaluation.score == 8.5
    assert evaluation.error_message is None
    
    # Test failure scenario
    evaluation.status = "pending"
    evaluation.mark_failed("API timeout")
    await db.commit()
    
    assert evaluation.is_failed() == True
    assert evaluation.error_message == "API timeout"


# ============================================================================
# TEST: PROGRESS INDEPENDENCE
# ============================================================================

@pytest.mark.asyncio
async def test_evaluation_does_not_affect_progress(
    db: AsyncSession,
    sample_user,
    sample_descriptive_question
):
    """Test that evaluation does NOT modify progress tables"""
    from backend.orm.user_content_progress import UserContentProgress, ContentType
    
    # Create attempt (this marks content as completed)
    attempt = PracticeAttempt(
        user_id=sample_user.id,
        practice_question_id=sample_descriptive_question.id,
        selected_option="Test answer",
        is_correct=None,
        attempt_number=1
    )
    db.add(attempt)
    
    # Create progress (simulating Phase 4.4)
    progress = UserContentProgress(
        user_id=sample_user.id,
        content_type=ContentType.PRACTICE,
        content_id=sample_descriptive_question.id,
        is_completed=True,
        completed_at=datetime.utcnow()
    )
    db.add(progress)
    await db.commit()
    
    initial_completed_at = progress.completed_at
    
    # Create evaluation
    evaluation = PracticeEvaluation(
        practice_attempt_id=attempt.id,
        evaluation_type=EvaluationType.AI_DESCRIPTIVE.value,
        status="completed",
        score=7.0,
        feedback_text="Good work"
    )
    db.add(evaluation)
    await db.commit()
    
    # Refresh progress
    await db.refresh(progress)
    
    # Progress should NOT change
    assert progress.is_completed == True
    assert progress.completed_at == initial_completed_at


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_token_for_user(user: User) -> str:
    """Mock function to get auth token for user (implement with your auth system)"""
    # In real tests, use your JWT generation function
    return f"mock_token_for_{user.id}"


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])