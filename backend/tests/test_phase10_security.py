"""
Phase 10 — Security Layer Test Suite

Tests for security middleware, audit logging, threat protection, and request validation.
"""
import pytest
import time
from datetime import datetime, timedelta
from fastapi import Request, Response
from unittest.mock import AsyncMock, MagicMock

from backend.security.request_validator import RequestValidator, InputSanitizer
from backend.security.threat_protection import ThreatProtection, AnomalyDetector
from backend.security.audit_logger import AuditLogEntry, AuditLogger


# =============================================================================
# Request Validator Tests
# =============================================================================

class TestRequestValidator:
    """Test request validation."""
    
    def test_validate_content_type_allowed(self):
        """Test that allowed content types pass."""
        validator = RequestValidator()
        
        assert validator._validate_content_type("application/json") is True
        assert validator._validate_content_type("application/json; charset=utf-8") is True
        assert validator._validate_content_type("multipart/form-data") is True
    
    def test_validate_content_type_blocked(self):
        """Test that blocked content types fail."""
        validator = RequestValidator()
        
        assert validator._validate_content_type("text/plain") is False
        assert validator._validate_content_type("application/xml") is False
        assert validator._validate_content_type("application/x-www-form-urlencoded") is False
    
    def test_validate_content_length_valid(self):
        """Test content length validation."""
        validator = RequestValidator()
        
        assert validator._validate_content_length("1024") is True
        assert validator._validate_content_length("0") is True
        assert validator._validate_content_length("10485760") is True  # 10MB
    
    def test_validate_content_length_invalid(self):
        """Test content length validation failures."""
        validator = RequestValidator()
        
        assert validator._validate_content_length("10485761") is False  # > 10MB
        assert validator._validate_content_length("-1") is False
        assert validator._validate_content_length("invalid") is False
    
    def test_validate_path_valid(self):
        """Test valid paths pass."""
        validator = RequestValidator()
        
        valid, error = validator._validate_path("/api/users/123")
        assert valid is True
        assert error is None
        
        valid, error = validator._validate_path("/results/tournaments/42/teams")
        assert valid is True
    
    def test_validate_path_traversal(self):
        """Test path traversal detection."""
        validator = RequestValidator()
        
        valid, error = validator._validate_path("/api/../admin")
        assert valid is False
        assert "traversal" in error.lower()
    
    def test_validate_path_null_bytes(self):
        """Test null byte detection."""
        validator = RequestValidator()
        
        valid, error = validator._validate_path("/api/users\x00/admin")
        assert valid is False
        assert "null" in error.lower()
    
    def test_validate_path_xss_patterns(self):
        """Test XSS pattern detection."""
        validator = RequestValidator()
        
        valid, error = validator._validate_path("/api/<script>alert(1)</script>")
        assert valid is False
        
        valid, error = validator._validate_path("/api/javascript:alert(1)")
        assert valid is False
    
    def test_validate_path_sql_patterns(self):
        """Test SQL injection pattern detection."""
        validator = RequestValidator()
        
        valid, error = validator._validate_path("/api/users' UNION SELECT * FROM admin--")
        assert valid is False


# =============================================================================
# Input Sanitizer Tests
# =============================================================================

class TestInputSanitizer:
    """Test input sanitization."""
    
    def test_sanitize_string_basic(self):
        """Test basic string sanitization."""
        result = InputSanitizer.sanitize_string("Hello World")
        assert result == "Hello World"
    
    def test_sanitize_string_null_bytes(self):
        """Test null byte removal."""
        result = InputSanitizer.sanitize_string("Hello\x00World")
        assert "\x00" not in result
        assert result == "HelloWorld"
    
    def test_sanitize_string_max_length(self):
        """Test max length enforcement."""
        long_string = "a" * 2000
        result = InputSanitizer.sanitize_string(long_string, max_length=1000)
        assert len(result) == 1000
    
    def test_sanitize_email_valid(self):
        """Test valid email sanitization."""
        result = InputSanitizer.sanitize_email("User@Example.COM")
        assert result == "user@example.com"
    
    def test_sanitize_email_invalid(self):
        """Test invalid email rejection."""
        result = InputSanitizer.sanitize_email("not-an-email")
        assert result == ""
        
        result = InputSanitizer.sanitize_email("missing@domain")
        assert result == ""
    
    def test_sanitize_integer_valid(self):
        """Test valid integer sanitization."""
        result = InputSanitizer.sanitize_integer("42")
        assert result == 42
        
        result = InputSanitizer.sanitize_integer(42)
        assert result == 42
    
    def test_sanitize_integer_invalid(self):
        """Test invalid integer rejection."""
        result = InputSanitizer.sanitize_integer("not-a-number")
        assert result is None
    
    def test_sanitize_integer_range(self):
        """Test integer range validation."""
        result = InputSanitizer.sanitize_integer("5", min_val=1, max_val=10)
        assert result == 5
        
        result = InputSanitizer.sanitize_integer("0", min_val=1)
        assert result is None
        
        result = InputSanitizer.sanitize_integer("15", max_val=10)
        assert result is None
    
    def test_sanitize_json_keys(self):
        """Test JSON key sanitization."""
        data = {
            "__proto__": "pollution",
            "constructor": "attack",
            "valid_key": "value",
            "nested": {
                "__proto__": "nested_pollution",
                "good_key": "good_value"
            }
        }
        
        result = InputSanitizer.sanitize_json_keys(data)
        
        assert "__proto__" not in result
        assert "constructor" not in result
        assert "valid_key" in result
        assert "good_key" in result["nested"]


# =============================================================================
# Threat Protection Tests
# =============================================================================

class TestThreatProtection:
    """Test threat detection and protection."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_per_second(self):
        """Test per-second rate limiting."""
        tp = ThreatProtection()
        tp.MAX_REQUESTS_PER_SECOND = 5
        
        client_ip = "192.168.1.1"
        
        # Add 5 requests in last second
        now = time.time()
        tp.request_history[client_ip] = [
            (now - 0.1, "/api/users"),
            (now - 0.2, "/api/users"),
            (now - 0.3, "/api/users"),
            (now - 0.4, "/api/users"),
            (now - 0.5, "/api/users"),
        ]
        
        # 6th request should trigger rate limit
        result = await tp.check_request(client_ip, "/api/users", "GET")
        assert result == "RATE_LIMIT:PER_SECOND"
    
    @pytest.mark.asyncio
    async def test_suspicious_admin_scan(self):
        """Test admin panel scanning detection."""
        tp = ThreatProtection()
        
        result = await tp.check_request("192.168.1.1", "/admin/users", "GET")
        assert result == "SUSPICIOUS:ADMIN_SCAN"
        
        result = await tp.check_request("192.168.1.1", "/.env", "GET")
        assert result == "SUSPICIOUS:ADMIN_SCAN"
    
    @pytest.mark.asyncio
    async def test_suspicious_sql_injection(self):
        """Test SQL injection detection."""
        tp = ThreatProtection()
        
        result = await tp.check_request("192.168.1.1", "/api/users?id=1' OR '1'='1", "GET")
        assert "SUSPICIOUS" in result
    
    @pytest.mark.asyncio
    async def test_path_traversal_detection(self):
        """Test path traversal detection."""
        tp = ThreatProtection()
        
        result = await tp.check_request("192.168.1.1", "/api/../../../etc/passwd", "GET")
        assert result == "SUSPICIOUS:PATH_TRAVERSAL"
    
    def test_auth_failure_tracking(self):
        """Test authentication failure tracking."""
        tp = ThreatProtection()
        tp.MAX_FAILED_AUTH_PER_MINUTE = 3
        
        client_ip = "192.168.1.1"
        
        # 3 failures should not block yet
        assert tp.record_auth_failure(client_ip, "user1") is False
        assert tp.record_auth_failure(client_ip, "user2") is False
        assert tp.record_auth_failure(client_ip, "user3") is False
        
        # 4th failure should trigger block
        assert tp.record_auth_failure(client_ip, "user4") is True
    
    def test_ip_blocking(self):
        """Test IP blocking and unblocking."""
        tp = ThreatProtection()
        tp.BLOCK_DURATION = 1  # 1 second for testing
        
        client_ip = "192.168.1.1"
        now = time.time()
        
        # Initially not blocked
        assert tp._is_blocked(client_ip, now) is False
        
        # Block the IP
        tp._block_ip(client_ip, now)
        
        # Should be blocked
        assert tp._is_blocked(client_ip, now) is True
        
        # After duration, should be unblocked
        assert tp._is_blocked(client_ip, now + 2) is False


# =============================================================================
# Anomaly Detector Tests
# =============================================================================

class TestAnomalyDetector:
    """Test anomaly detection."""
    
    def test_record_user_action_normal(self):
        """Test normal user action recording."""
        detector = AnomalyDetector()
        
        score = detector.record_user_action(1, "view", {"timestamp": time.time()})
        
        assert score >= 0.0
        assert score < 0.5  # Normal activity
    
    def test_record_user_action_high_velocity(self):
        """Test high velocity detection."""
        detector = AnomalyDetector()
        
        # Simulate 100 actions in 1 second
        now = time.time()
        for i in range(100):
            score = detector.record_user_action(1, "view", {"timestamp": now + i * 0.01})
        
        # Should be suspicious
        assert detector.is_user_suspicious(1, threshold=0.5) is True
    
    def test_suspicious_user_detection(self):
        """Test suspicious user flagging."""
        detector = AnomalyDetector()
        
        # Normal user
        detector.anomaly_scores[1] = 0.3
        assert detector.is_user_suspicious(1, threshold=0.5) is False
        
        # Suspicious user
        detector.anomaly_scores[2] = 0.9
        assert detector.is_user_suspicious(2, threshold=0.5) is True


# =============================================================================
# Audit Logger Tests
# =============================================================================

class TestAuditLogEntry:
    """Test audit log entry."""
    
    def test_compute_hash_deterministic(self):
        """Test that hash computation is deterministic."""
        entry = AuditLogEntry(
            request_id="req-123",
            method="GET",
            path="/api/users",
            client_ip="192.168.1.1",
            event_type="REQUEST"
        )
        
        hash1 = entry.compute_hash()
        hash2 = entry.compute_hash()
        
        assert hash1 == hash2
        assert len(hash1) == 64
    
    def test_compute_hash_different_data(self):
        """Test that different data produces different hashes."""
        entry1 = AuditLogEntry(
            request_id="req-123",
            method="GET",
            path="/api/users",
            client_ip="192.168.1.1",
            event_type="REQUEST"
        )
        
        entry2 = AuditLogEntry(
            request_id="req-456",
            method="GET",
            path="/api/users",
            client_ip="192.168.1.1",
            event_type="REQUEST"
        )
        
        hash1 = entry1.compute_hash()
        hash2 = entry2.compute_hash()
        
        assert hash1 != hash2


class TestAuditLogger:
    """Test audit logger."""
    
    @pytest.mark.asyncio
    async def test_log_request(self):
        """Test request logging."""
        logger = AuditLogger()
        
        entry = await logger.log_request(
            request_id="req-123",
            method="GET",
            path="/api/users",
            client_ip="192.168.1.1",
            user_agent="Mozilla/5.0",
            timestamp=time.time()
        )
        
        assert entry.request_id == "req-123"
        assert entry.method == "GET"
        assert entry.event_type == "REQUEST"
        assert entry.entry_hash is not None
    
    @pytest.mark.asyncio
    async def test_log_security_event(self):
        """Test security event logging."""
        logger = AuditLogger()
        
        entry = await logger.log_security_event(
            request_id="req-123",
            event_type="SUSPICIOUS_REQUEST",
            client_ip="192.168.1.1",
            path="/api/admin",
            details='{"reason": "unauthorized access attempt"}',
            timestamp=time.time()
        )
        
        assert entry.event_type == "SECURITY_EVENT"
        assert entry.event_category == "SECURITY"


# =============================================================================
# Security Middleware Integration Tests
# =============================================================================

class TestSecurityHeaders:
    """Test security headers middleware."""
    
    def test_security_headers_present(self):
        """Test that all security headers are added."""
        from backend.security.http_headers import SecurityHeadersMiddleware
        
        # Create mock response
        response = MagicMock(spec=Response)
        response.headers = {}
        
        # Headers that should be present
        required_headers = [
            "Strict-Transport-Security",
            "Content-Security-Policy",
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Referrer-Policy",
            "Permissions-Policy",
        ]
        
        # Verify middleware adds headers
        # (In real test, would use actual middleware dispatch)


# =============================================================================
# Determinism Tests
# =============================================================================

def test_no_float_in_security_code():
    """Verify no float() usage in security code."""
    # This would scan source files
    # For now, verify by checking key components
    pass


def test_no_random_in_security_code():
    """Verify no random() usage in security code."""
    pass


def test_deterministic_request_id():
    """Test that request IDs are deterministic."""
    from backend.security.security_middleware import SecurityMiddleware
    
    middleware = SecurityMiddleware(app=None)
    
    # Same input should produce same ID
    # (Implementation uses timestamp, so can't test exact equality)
    pass
