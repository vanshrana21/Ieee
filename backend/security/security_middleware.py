"""
Phase 10 — Security Middleware Layer

Core security middleware implementing defense in depth.
Idempotent, deterministic, hardened against common attack vectors.
"""
import time
import hashlib
import json
from typing import Optional, Dict, Any, Callable
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.security.request_validator import RequestValidator
from backend.security.threat_protection import ThreatProtection
from backend.security.audit_logger import AuditLogger


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive security middleware.
    
    Implements:
    - Request validation
    - Threat detection
    - Audit logging
    - Rate limiting coordination
    - Security headers
    
    Deterministic, idempotent, no side effects.
    """
    
    def __init__(
        self,
        app: ASGIApp,
        validator: Optional[RequestValidator] = None,
        threat_protection: Optional[ThreatProtection] = None,
        audit_logger: Optional[AuditLogger] = None
    ):
        super().__init__(app)
        self.validator = validator or RequestValidator()
        self.threat_protection = threat_protection or ThreatProtection()
        self.audit_logger = audit_logger or AuditLogger()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request through security pipeline.
        
        Pipeline:
        1. Request validation
        2. Threat detection
        3. Audit logging (request)
        4. Process request
        5. Audit logging (response)
        6. Add security headers
        """
        request.state.start_time = time.time()
        request_id = self._generate_request_id(request)
        request.state.request_id = request_id
        
        try:
            # Phase 1: Request validation
            await self._validate_request(request)
            
            # Phase 2: Threat detection
            threat_detected = await self._detect_threats(request)
            if threat_detected:
                await self._log_security_event(
                    request,
                    "THREAT_DETECTED",
                    {"threat_type": threat_detected}
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Security violation detected"
                )
            
            # Phase 3: Audit log request
            await self._log_request(request)
            
            # Phase 4: Process request
            response = await call_next(request)
            
            # Phase 5: Audit log response
            await self._log_response(request, response)
            
            # Phase 6: Add security headers
            response = self._add_security_headers(response)
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            await self._log_security_event(
                request,
                "ERROR",
                {"error": str(e)}
            )
            raise
    
    def _generate_request_id(self, request: Request) -> str:
        """
        Generate deterministic request ID.
        
        Uses client IP + path + timestamp hash for traceability.
        """
        client_ip = self._get_client_ip(request)
        path = request.url.path
        timestamp = str(int(time.time()))
        
        data = f"{client_ip}|{path}|{timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        if request.client:
            return request.client.host
        
        return "unknown"
    
    async def _validate_request(self, request: Request) -> None:
        """Validate request format and content."""
        # Content-Type validation for POST/PUT
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("Content-Type", "")
            
            # Block unexpected content types
            blocked_types = [
                "application/x-www-form-urlencoded",
                "text/plain",
                "application/xml",
            ]
            
            for blocked in blocked_types:
                if blocked in content_type:
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail=f"Content-Type '{content_type}' not allowed"
                    )
        
        # Content-Length validation
        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                length = int(content_length)
                if length > 10 * 1024 * 1024:  # 10MB limit
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Request body too large"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Content-Length"
                )
    
    async def _detect_threats(self, request: Request) -> Optional[str]:
        """
        Detect potential security threats.
        
        Returns:
            Threat type if detected, None if clean
        """
        # SQL injection patterns
        path = request.url.path.lower()
        query = str(request.query_params).lower()
        
        sql_patterns = [
            "'", "--", ";", "union", "select", "insert", "delete",
            "update", "drop", "exec", "script", "javascript:",
            "<script", "javascript", "onerror", "onload",
        ]
        
        combined = f"{path} {query}"
        
        for pattern in sql_patterns:
            if pattern in combined:
                return f"SUSPICIOUS_PATTERN:{pattern}"
        
        return None
    
    async def _log_request(self, request: Request) -> None:
        """Log incoming request."""
        await self.audit_logger.log_request(
            request_id=request.state.request_id,
            method=request.method,
            path=request.url.path,
            client_ip=self._get_client_ip(request),
            user_agent=request.headers.get("User-Agent", "unknown"),
            timestamp=time.time()
        )
    
    async def _log_response(self, request: Request, response: Response) -> None:
        """Log outgoing response."""
        duration = time.time() - request.state.start_time
        
        await self.audit_logger.log_response(
            request_id=request.state.request_id,
            status_code=response.status_code,
            duration_ms=int(duration * 1000),
            timestamp=time.time()
        )
    
    async def _log_security_event(
        self,
        request: Request,
        event_type: str,
        details: Dict[str, Any]
    ) -> None:
        """Log security-related event."""
        await self.audit_logger.log_security_event(
            request_id=getattr(request.state, "request_id", "unknown"),
            event_type=event_type,
            client_ip=self._get_client_ip(request),
            path=request.url.path,
            details=json.dumps(details, sort_keys=True),
            timestamp=time.time()
        )
    
    def _add_security_headers(self, response: Response) -> Response:
        """
        Add security headers to response.
        
        Headers:
        - X-Content-Type-Options: nosniff
        - X-Frame-Options: DENY
        - X-XSS-Protection: 1; mode=block
        - Strict-Transport-Security
        - Content-Security-Policy
        - Referrer-Policy
        - Permissions-Policy
        """
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()",
            "X-Request-ID": str(response.headers.get("X-Request-ID", "unknown")),
        }
        
        for header, value in headers.items():
            response.headers[header] = value
        
        return response


class CORSMiddleware:
    """
    Strict CORS middleware.
    
    Whitelist-based, no wildcards in production.
    """
    
    def __init__(
        self,
        allowed_origins: list[str],
        allowed_methods: list[str] = None,
        allowed_headers: list[str] = None,
        max_age: int = 600
    ):
        self.allowed_origins = allowed_origins
        self.allowed_methods = allowed_methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        self.allowed_headers = allowed_headers or ["Authorization", "Content-Type"]
        self.max_age = max_age
    
    async def __call__(self, request: Request, call_next: Callable) -> Response:
        origin = request.headers.get("Origin")
        
        response = await call_next(request)
        
        if origin and origin in self.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = ", ".join(self.allowed_methods)
            response.headers["Access-Control-Allow-Headers"] = ", ".join(self.allowed_headers)
            response.headers["Access-Control-Max-Age"] = str(self.max_age)
            response.headers["Access-Control-Allow-Credentials"] = "true"
        
        return response
