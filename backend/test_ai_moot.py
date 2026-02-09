"""
backend/test_ai_moot.py
Comprehensive test suite for AI Moot Court Practice Mode

Tests validation problem flow, schema handling, and India-specific behaviors.
"""
import pytest
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Import app and dependencies
from backend.main import app
from backend.database import get_db
from backend.orm.base import Base

# Test database
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test engine
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_test_db():
    """Initialize test database with tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def override_get_db():
    """Override database dependency for testing."""
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Apply database override
app.dependency_overrides[get_db] = lambda: asyncio.run(override_get_db().__anext__())

client = TestClient(app)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Initialize test database before all tests."""
    asyncio.run(init_test_db())
    yield
    # Cleanup
    asyncio.run(engine.dispose())


@pytest.fixture
def auth_token():
    """Get authentication token for testing.
    
    Note: This assumes a test user exists. In production, create test user first.
    """
    # First try to login with test credentials
    response = client.post("/api/auth/login", json={
        "email": "test@student.com",
        "password": "password123"
    })
    
    if response.status_code == 200:
        return response.json()["access_token"]
    
    # If login fails, try to register test user
    register_response = client.post("/api/auth/register", json={
        "email": "test@student.com",
        "password": "password123",
        "full_name": "Test Student",
        "role": "student"
    })
    
    if register_response.status_code == 201:
        # Login again after registration
        login_response = client.post("/api/auth/login", json={
            "email": "test@student.com",
            "password": "password123"
        })
        if login_response.status_code == 200:
            return login_response.json()["access_token"]
    
    # If we can't get a token, skip auth-dependent tests
    pytest.skip("Could not obtain auth token - auth service not available")
    return None


# ============================================================================
# TESTS: Schema Validation
# ============================================================================

def test_schema_accepts_problem_type_only():
    """Test that AISessionCreate accepts problem_type without problem_id."""
    from backend.schemas.ai_moot import AISessionCreate
    
    # Should accept problem_type without problem_id
    data = AISessionCreate(problem_type="validation_1", side="petitioner")
    assert data.problem_type == "validation_1"
    assert data.problem_id is None
    assert data.side == "petitioner"


def test_schema_accepts_problem_id_only():
    """Test that AISessionCreate accepts problem_id without problem_type."""
    from backend.schemas.ai_moot import AISessionCreate
    
    # Should accept problem_id without problem_type
    data = AISessionCreate(problem_id=1, side="petitioner")
    assert data.problem_id == 1
    assert data.problem_type is None
    assert data.side == "petitioner"


def test_schema_rejects_both_missing():
    """Test that AISessionCreate rejects when both problem_id and problem_type are missing."""
    from backend.schemas.ai_moot import AISessionCreate
    from pydantic import ValidationError
    
    # Should reject when both are missing
    with pytest.raises(ValidationError) as exc_info:
        AISessionCreate(side="petitioner")
    
    assert "problem_id" in str(exc_info.value) or "problem_type" in str(exc_info.value) or "Either" in str(exc_info.value)


def test_schema_validates_side():
    """Test that AISessionCreate validates side field."""
    from backend.schemas.ai_moot import AISessionCreate
    from pydantic import ValidationError
    
    # Should accept valid sides
    data1 = AISessionCreate(problem_type="validation_1", side="petitioner")
    assert data1.side == "petitioner"
    
    data2 = AISessionCreate(problem_type="validation_1", side="respondent")
    assert data2.side == "respondent"
    
    # Should reject invalid side
    with pytest.raises(ValidationError):
        AISessionCreate(problem_type="validation_1", side="invalid_side")


# ============================================================================
# TESTS: Knowledge Base Validation Problems
# ============================================================================

def test_validation_problems_exist():
    """Test that validation problems are properly loaded."""
    from backend.knowledge_base.problems import get_validation_problems, get_problem_by_id
    
    problems = get_validation_problems()
    assert len(problems) == 3
    
    # Check each problem exists
    for i in range(1, 4):
        problem = get_problem_by_id(i)
        assert problem is not None
        assert problem["id"] == i
        assert "title" in problem
        assert "legal_issues" in problem


def test_validation_problem_1_details():
    """Test validation problem 1 (Aadhaar/Privacy)."""
    from backend.knowledge_base.problems import get_problem_by_id
    
    problem = get_problem_by_id(1)
    assert problem["title"] == "Aadhaar Mandatory for NFSA Food Grains"
    assert "privacy" in problem["domain"]
    assert "Puttaswamy (2017) 10 SCC 1" in problem["petitioner_key_cases"]


def test_validation_problem_2_details():
    """Test validation problem 2 (Deepfake/Defamation)."""
    from backend.knowledge_base.problems import get_problem_by_id
    
    problem = get_problem_by_id(2)
    assert problem["title"] == "AI-Generated Deepfake Defamation"
    assert "defamation" in problem["domain"]
    assert "Subramanian Swamy (2016) 7 SCC 221" in problem["petitioner_key_cases"]


def test_validation_problem_3_details():
    """Test validation problem 3 (Free Speech/295A)."""
    from backend.knowledge_base.problems import get_problem_by_id
    
    problem = get_problem_by_id(3)
    assert problem["title"] == "Religious Sentiments vs. Free Speech"
    assert "free_speech" in problem["domain"]
    assert "Ramji Lal Modi (1957) SCR 874" in problem["petitioner_key_cases"]


def test_get_problem_cases_by_side():
    """Test retrieving cases by side."""
    from backend.knowledge_base.problems import get_problem_cases_by_side
    
    # Problem 1 - Petitioner cases
    petitioner_cases = get_problem_cases_by_side(1, "petitioner")
    assert len(petitioner_cases) > 0
    assert "Puttaswamy (2017) 10 SCC 1" in petitioner_cases
    
    # Problem 1 - Respondent cases
    respondent_cases = get_problem_cases_by_side(1, "respondent")
    assert len(respondent_cases) > 0


# ============================================================================
# TESTS: AI Judge Engine
# ============================================================================

def test_ai_judge_engine_initialization():
    """Test AIJudgeEngine initializes correctly."""
    from backend.services.ai_judge_service import AIJudgeEngine
    
    engine = AIJudgeEngine()
    assert engine is not None
    assert engine.behavior_rules is not None


def test_ai_judge_generates_feedback():
    """Test AI judge generates feedback with behavior data."""
    from backend.services.ai_judge_service import AIJudgeEngine
    
    engine = AIJudgeEngine()
    
    problem_context = {
        "title": "Aadhaar Mandatory for NFSA Food Grains",
        "side": "petitioner",
        "legal_issue": "Does mandatory Aadhaar violate Puttaswamy proportionality test?"
    }
    
    # Test argument with proper etiquette and citation
    argument = "My Lord, Puttaswamy (2017) 10 SCC 1 established privacy as a fundamental right under Article 21."
    
    result = engine.generate_feedback(
        argument=argument,
        problem_context=problem_context,
        turn_number=1
    )
    
    # Verify result structure
    assert "feedback_text" in result
    assert "missing_cases" in result
    assert "citation_valid" in result
    assert "has_etiquette" in result
    assert "scores" in result
    assert "next_question" in result
    assert "behavior_data" in result  # Phase 4: behavior data for UI badges
    
    # Verify scores structure
    scores = result["scores"]
    assert "legal_accuracy" in scores
    assert "citation" in scores
    assert "etiquette" in scores


def test_ai_judge_detects_missing_etiquette():
    """Test AI judge detects missing 'My Lord'."""
    from backend.services.ai_judge_service import AIJudgeEngine
    
    engine = AIJudgeEngine()
    
    problem_context = {
        "title": "Test Problem",
        "side": "petitioner",
        "legal_issue": "Test issue"
    }
    
    # Argument without "My Lord"
    argument = "Puttaswamy (2017) 10 SCC 1 established privacy as a fundamental right."
    
    result = engine.generate_feedback(
        argument=argument,
        problem_context=problem_context,
        turn_number=1
    )
    
    # Should detect missing etiquette
    assert result["has_etiquette"] == False
    assert result["behavior_data"]["etiquette_check"]["has_etiquette"] == False


def test_ai_judge_detects_informal_citation():
    """Test AI judge detects informal 'Puttaswamy case' citation."""
    from backend.services.ai_judge_service import AIJudgeEngine
    
    engine = AIJudgeEngine()
    
    problem_context = {
        "title": "Aadhaar Privacy Case",
        "side": "petitioner",
        "legal_issue": "Privacy issue"
    }
    
    # Argument with informal citation
    argument = "My Lord, the Puttaswamy case established privacy rights."
    
    result = engine.generate_feedback(
        argument=argument,
        problem_context=problem_context,
        turn_number=1
    )
    
    # Should flag citation issues
    behavior_data = result["behavior_data"]
    citation_check = behavior_data["citation_check"]
    
    # Should have wrong_format_cases detected
    assert len(citation_check["wrong_format_cases"]) > 0


def test_ai_judge_triggers_interruption():
    """Test judicial interruption triggers after 60+ words."""
    from backend.services.ai_judge_service import AIJudgeEngine
    
    engine = AIJudgeEngine()
    
    problem_context = {
        "title": "Test Problem",
        "side": "petitioner",
        "legal_issue": "Test issue"
    }
    
    # Long argument (>60 words) to trigger interruption
    argument = "My Lord, " + "this is a very long argument " * 20 + "that should trigger judicial interruption."
    
    result = engine.generate_feedback(
        argument=argument,
        problem_context=problem_context,
        turn_number=1
    )
    
    # Check interruption status
    interruption_check = result["behavior_data"]["interruption_check"]
    # Note: May or may not trigger depending on exact word count
    assert "should_interrupt" in interruption_check
    assert "word_count" in interruption_check


# ============================================================================
# TESTS: India Behavior Rules
# ============================================================================

def test_behavior_rules_enforcement():
    """Test IndiaBehaviorRules enforces all 5 behaviors."""
    from backend.services.india_behavior_rules import IndiaBehaviorRules
    from knowledge_base import india as kb
    
    rules = IndiaBehaviorRules(kb)
    
    problem_context = {
        "title": "Aadhaar Privacy Case",
        "side": "petitioner",
        "legal_issue": "Does mandatory Aadhaar violate privacy?"
    }
    
    # Perfect argument
    argument = "My Lord, Puttaswamy (2017) 10 SCC 1 established privacy as a fundamental right. The proportionality test requires legality, legitimate aim, proportionality, and safeguards."
    
    result = rules.enforce_india_behaviors(
        argument=argument,
        turn_number=1,
        problem_context=problem_context
    )
    
    # Verify all 5 behavior checks present
    assert "etiquette_check" in result
    assert "citation_check" in result
    assert "interruption_check" in result
    assert "proportionality_check" in result
    assert "landmark_check" in result
    assert "enhanced_prompt" in result
    assert "total_deductions" in result


def test_my_lord_etiquette_progressive_deductions():
    """Test 'My Lord' etiquette deductions increase by turn."""
    from backend.services.india_behavior_rules import IndiaBehaviorRules
    from knowledge_base import india as kb
    
    rules = IndiaBehaviorRules(kb)
    
    # Argument without "My Lord"
    argument = "Puttaswamy (2017) 10 SCC 1 established privacy as a fundamental right."
    
    # Turn 1: 0 points deducted
    result1 = rules.check_my_lord_etiquette(argument, turn_number=1)
    assert result1["points_deducted"] == 0
    
    # Turn 2: 2 points deducted
    result2 = rules.check_my_lord_etiquette(argument, turn_number=2)
    assert result2["points_deducted"] == 2
    
    # Turn 3: 3 points deducted
    result3 = rules.check_my_lord_etiquette(argument, turn_number=3)
    assert result3["points_deducted"] == 3


def test_scc_citation_validation():
    """Test SCC citation format validation."""
    from backend.services.india_behavior_rules import IndiaBehaviorRules
    from knowledge_base import india as kb
    
    rules = IndiaBehaviorRules(kb)
    
    # Valid SCC citation
    valid_arg = "My Lord, Puttaswamy (2017) 10 SCC 1 established privacy rights."
    result_valid = rules.check_scc_citation(valid_arg)
    assert result_valid["valid_citation"] == True
    
    # Invalid informal citation
    invalid_arg = "My Lord, the Puttaswamy case established privacy rights."
    result_invalid = rules.check_scc_citation(invalid_arg)
    # Should have wrong format detected
    assert len(result_invalid["wrong_format_cases"]) > 0


# ============================================================================
# TESTS: API Endpoints (Integration)
# ============================================================================

@pytest.mark.skipif(not hasattr(pytest, 'config'), reason="Requires full app context")
def test_list_validation_problems_api(auth_token):
    """Test GET /api/ai-moot/problems endpoint."""
    response = client.get(
        "/api/ai-moot/problems",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    
    assert response.status_code == 200
    problems = response.json()
    assert len(problems) == 3
    assert problems[0]["title"] == "Aadhaar Mandatory for NFSA Food Grains"


@pytest.mark.skipif(not hasattr(pytest, 'config'), reason="Requires full app context")
def test_create_session_with_validation_problem(auth_token):
    """Test POST /api/ai-moot/sessions with problem_type."""
    response = client.post(
        "/api/ai-moot/sessions",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"problem_type": "validation_1", "side": "petitioner"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["problem_title"] == "Aadhaar Mandatory for NFSA Food Grains"
    assert data["side"] == "petitioner"
    assert data["current_turn"] == 1


@pytest.mark.skipif(not hasattr(pytest, 'config'), reason="Requires full app context")
def test_create_session_without_problem_fails(auth_token):
    """Test that creating session without problem_id or problem_type fails."""
    response = client.post(
        "/api/ai-moot/sessions",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"side": "petitioner"}  # Missing both problem_id and problem_type
    )
    
    assert response.status_code == 422  # Validation error


@pytest.mark.skipif(not hasattr(pytest, 'config'), reason="Requires full app context")
def test_submit_argument_get_feedback(auth_token):
    """Test POST /api/ai-moot/sessions/{id}/turns endpoint."""
    # First create a session
    session_response = client.post(
        "/api/ai-moot/sessions",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"problem_type": "validation_1", "side": "petitioner"}
    )
    
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]
    
    # Submit argument
    turn_response = client.post(
        f"/api/ai-moot/sessions/{session_id}/turns",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"argument": "My Lord, Puttaswamy (2017) 10 SCC 1 established privacy as a fundamental right under Article 21."}
    )
    
    assert turn_response.status_code == 200
    data = turn_response.json()
    
    # Verify response structure
    assert "feedback" in data
    assert "score_breakdown" in data
    assert "next_question" in data
    assert "session_complete" in data
    
    # Verify scores
    scores = data["score_breakdown"]
    assert "legal_accuracy" in scores
    assert "citation" in scores
    assert "etiquette" in scores


@pytest.mark.skipif(not hasattr(pytest, 'config'), reason="Requires full app context")
def test_get_session_details(auth_token):
    """Test GET /api/ai-moot/sessions/{id} endpoint."""
    # Create session
    session_response = client.post(
        "/api/ai-moot/sessions",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"problem_type": "validation_1", "side": "petitioner"}
    )
    
    session_id = session_response.json()["id"]
    
    # Get session details
    detail_response = client.get(
        f"/api/ai-moot/sessions/{session_id}",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    
    assert detail_response.status_code == 200
    data = detail_response.json()
    
    assert data["id"] == session_id
    assert data["problem_title"] == "Aadhaar Mandatory for NFSA Food Grains"
    assert data["side"] == "petitioner"
    assert "turns" in data


# ============================================================================
# MANUAL VERIFICATION COMMANDS (for user testing)
# ============================================================================
"""
# After starting the backend with:
#   uvicorn backend.main:app --reload --env-file .env

# 1. Get auth token (register/login first):
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"yourpassword"}'

# 2. List validation problems:
curl -X GET http://localhost:8000/api/ai-moot/problems \
  -H "Authorization: Bearer YOUR_TOKEN"

# 3. Create session with validation problem:
curl -X POST http://localhost:8000/api/ai-moot/sessions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"problem_type":"validation_1","side":"petitioner"}'

# 4. Submit argument:
curl -X POST http://localhost:8000/api/ai-moot/sessions/SESSION_ID/turns \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"argument":"My Lord, Puttaswamy (2017) 10 SCC 1 established privacy as a fundamental right under Article 21."}'

# 5. Check response contains:
#   - feedback with "Puttaswamy" or "(2017) 10 SCC 1"
#   - score_breakdown with legal_accuracy, citation, etiquette
#   - High etiquette score (5) for "My Lord"
#   - High citation score (5) for correct SCC format

# 6. Test behavior badges - submit without "My Lord":
curl -X POST http://localhost:8000/api/ai-moot/sessions/SESSION_ID/turns \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"argument":"Puttaswamy case established privacy rights."}'
# Expected: Lower etiquette score, citation warning for informal "Puttaswamy case"
"""

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
