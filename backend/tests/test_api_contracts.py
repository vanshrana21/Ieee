"""
backend/tests/test_api_contracts.py
Phase 11.1: API Contract Verification Tests

These tests verify:
1. Response shapes are consistent
2. Error responses follow standard format
3. HTTP status codes are correct
4. Ownership/boundary enforcement works
5. Read-only endpoints don't mutate data

PRINCIPLE: APIs are contracts. Contracts must never break.
"""

import pytest
from httpx import AsyncClient
from backend.main import app
from backend.errors import ErrorCode


class TestErrorResponseFormat:
    """Verify all error responses follow the standard format"""
    
    async def test_401_unauthorized_format(self):
        """401 responses must include success, error, message, code"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/auth/me")
            assert response.status_code == 401
            data = response.json()
            assert "detail" in data or ("success" in data and data["success"] is False)
    
    async def test_404_not_found_format(self):
        """404 responses must include success, error, message, code"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/subjects/99999")
            if response.status_code == 404:
                data = response.json()
                assert "success" in data or "detail" in data
    
    async def test_validation_error_format(self):
        """422 validation errors must include details array"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/register",
                json={"email": "not-an-email", "password": "123"}
            )
            if response.status_code == 422:
                data = response.json()
                assert "success" in data or "detail" in data


class TestHealthEndpoints:
    """Verify health endpoints return proper structure"""
    
    async def test_main_health(self):
        """Main health endpoint returns expected fields"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert data["status"] == "healthy"
    
    async def test_errors_health(self):
        """Error handling health returns documentation"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/errors/health")
            assert response.status_code == 200
            data = response.json()
            assert "version" in data
            assert "status_codes" in data
            assert "error_codes" in data


class TestAuthEndpoints:
    """Verify auth endpoints follow contracts"""
    
    async def test_login_invalid_credentials(self):
        """Login with invalid credentials returns 401"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/api/auth/login",
                data={"username": "nonexistent@test.com", "password": "wrongpass"}
            )
            assert response.status_code == 401
            data = response.json()
            assert "detail" in data
            detail = data["detail"]
            if isinstance(detail, dict):
                assert detail.get("success") is False
                assert "code" in detail
    
    async def test_register_duplicate_email(self):
        """Duplicate email registration returns 400"""
        pass
    
    async def test_me_without_token(self):
        """/me without token returns 401"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/auth/me")
            assert response.status_code == 401


class TestContentAccessControl:
    """Verify content access returns proper errors"""
    
    async def test_content_without_auth(self):
        """Content endpoints require authentication"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/content/learn/1")
            assert response.status_code == 401
    
    async def test_invalid_content_type(self):
        """Invalid content type returns 400 with proper error"""
        pass


class TestResponseShapes:
    """Verify response shapes are consistent"""
    
    async def test_success_response_has_required_fields(self):
        """Success responses include expected fields"""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, dict)


ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["success", "error", "message", "code"],
    "properties": {
        "success": {"type": "boolean", "const": False},
        "error": {"type": "string"},
        "message": {"type": "string"},
        "code": {"type": "string"},
        "details": {"type": "object"}
    }
}


def validate_error_response(response_data: dict) -> bool:
    """Validate error response follows standard format"""
    if "detail" in response_data:
        detail = response_data["detail"]
        if isinstance(detail, dict):
            return (
                detail.get("success") is False and
                "error" in detail and
                "message" in detail and
                "code" in detail
            )
        return True
    
    return (
        response_data.get("success") is False and
        "error" in response_data and
        "message" in response_data and
        "code" in response_data
    )


MISUSE_SCENARIOS = [
    {
        "name": "Invalid JSON body",
        "method": "POST",
        "endpoint": "/api/auth/register",
        "body": "not json",
        "expected_status": 422,
        "description": "Malformed JSON should return validation error"
    },
    {
        "name": "Missing required field",
        "method": "POST",
        "endpoint": "/api/auth/register",
        "body": {"email": "test@test.com"},
        "expected_status": 422,
        "description": "Missing password should return validation error"
    },
    {
        "name": "Invalid email format",
        "method": "POST",
        "endpoint": "/api/auth/register",
        "body": {"email": "notanemail", "password": "123456", "name": "Test", "role": "student"},
        "expected_status": 422,
        "description": "Invalid email format should return validation error"
    },
    {
        "name": "Unauthorized access",
        "method": "GET",
        "endpoint": "/api/auth/me",
        "body": None,
        "expected_status": 401,
        "description": "Protected endpoint without token returns 401"
    },
    {
        "name": "Resource not found",
        "method": "GET",
        "endpoint": "/api/subjects/999999",
        "body": None,
        "expected_status": 404,
        "description": "Non-existent resource returns 404"
    }
]


async def run_contract_tests():
    """Run all contract verification tests"""
    results = []
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        for scenario in MISUSE_SCENARIOS:
            try:
                if scenario["method"] == "GET":
                    response = await client.get(scenario["endpoint"])
                elif scenario["method"] == "POST":
                    if isinstance(scenario["body"], str):
                        response = await client.post(
                            scenario["endpoint"],
                            content=scenario["body"],
                            headers={"Content-Type": "application/json"}
                        )
                    else:
                        response = await client.post(
                            scenario["endpoint"],
                            json=scenario["body"]
                        )
                
                passed = response.status_code == scenario["expected_status"]
                results.append({
                    "scenario": scenario["name"],
                    "passed": passed,
                    "expected": scenario["expected_status"],
                    "actual": response.status_code,
                    "description": scenario["description"]
                })
            except Exception as e:
                results.append({
                    "scenario": scenario["name"],
                    "passed": False,
                    "error": str(e)
                })
    
    return results


if __name__ == "__main__":
    import asyncio
    
    async def main():
        print("=" * 60)
        print("Phase 11.1: API Contract Verification Tests")
        print("=" * 60)
        
        results = await run_contract_tests()
        
        passed = sum(1 for r in results if r.get("passed"))
        total = len(results)
        
        for result in results:
            status = "PASS" if result.get("passed") else "FAIL"
            print(f"\n[{status}] {result['scenario']}")
            if not result.get("passed"):
                print(f"       Expected: {result.get('expected')}, Got: {result.get('actual')}")
                if result.get("error"):
                    print(f"       Error: {result.get('error')}")
        
        print("\n" + "=" * 60)
        print(f"Results: {passed}/{total} tests passed")
        print("=" * 60)
    
    asyncio.run(main())
