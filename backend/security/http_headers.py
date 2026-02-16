"""
Phase 10 — HTTP Security Headers

Comprehensive security headers middleware.
Implements OWASP recommended headers with strict values.
"""
from typing import Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds comprehensive security headers to all responses.
    
    Headers added:
    - Strict-Transport-Security (HSTS)
    - Content-Security-Policy (CSP)
    - X-Content-Type-Options
    - X-Frame-Options
    - X-XSS-Protection
    - Referrer-Policy
    - Permissions-Policy
    - Cross-Origin-Embedder-Policy
    - Cross-Origin-Opener-Policy
    - Cross-Origin-Resource-Policy
    """
    
    def __init__(
        self,
        app: ASGIApp,
        csp_policy: Optional[str] = None,
        hsts_max_age: int = 31536000,
        hsts_include_subdomains: bool = True,
        hsts_preload: bool = True
    ):
        super().__init__(app)
        
        # Content Security Policy
        self.csp_policy = csp_policy or (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "media-src 'self'; "
            "object-src 'none'; "
            "frame-src 'none'; "
            "worker-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "upgrade-insecure-requests;"
        )
        
        # HSTS configuration
        self.hsts_max_age = hsts_max_age
        self.hsts_include_subdomains = hsts_include_subdomains
        self.hsts_preload = hsts_preload
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Add security headers to response."""
        response = await call_next(request)
        
        # Strict-Transport-Security (HSTS)
        hsts_value = f"max-age={self.hsts_max_age}"
        if self.hsts_include_subdomains:
            hsts_value += "; includeSubDomains"
        if self.hsts_preload:
            hsts_value += "; preload"
        response.headers["Strict-Transport-Security"] = hsts_value
        
        # Content-Security-Policy
        response.headers["Content-Security-Policy"] = self.csp_policy
        
        # X-Content-Type-Options (prevent MIME sniffing)
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # X-Frame-Options (clickjacking protection)
        response.headers["X-Frame-Options"] = "DENY"
        
        # X-XSS-Protection (legacy browser protection)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Referrer-Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions-Policy (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "payment=(), "
            "usb=(), "
            "interest-cohort=()"  # Disable FLoC
        )
        
        # Cross-Origin policies
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        
        # Additional headers
        response.headers["X-DNS-Prefetch-Control"] = "off"
        response.headers["X-Download-Options"] = "noopen"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        
        return response


class SecureCacheMiddleware(BaseHTTPMiddleware):
    """
    Adds cache-control headers for sensitive endpoints.
    """
    
    def __init__(self, app: ASGIApp, no_cache_paths: Optional[list] = None):
        super().__init__(app)
        self.no_cache_paths = no_cache_paths or [
            "/auth",
            "/login",
            "/api/auth",
            "/user",
            "/admin",
        ]
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Add cache control headers."""
        response = await call_next(request)
        
        path = request.url.path.lower()
        
        # Check if path should not be cached
        for no_cache_path in self.no_cache_paths:
            if no_cache_path in path:
                response.headers["Cache-Control"] = (
                    "no-store, no-cache, must-revalidate, max-age=0"
                )
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                break
        
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Adds unique request ID to all requests for tracing.
    """
    
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID"):
        super().__init__(app)
        self.header_name = header_name
        self._counter = 0
    
    def _generate_request_id(self) -> str:
        """Generate deterministic request ID."""
        import hashlib
        import time
        
        self._counter += 1
        data = f"{time.time()}|{self._counter}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Add request ID to request and response."""
        # Get or generate request ID
        request_id = request.headers.get(self.header_name)
        if not request_id:
            request_id = self._generate_request_id()
        
        # Add to request state
        request.state.request_id = request_id
        
        # Process request
        response = await call_next(request)
        
        # Add to response headers
        response.headers[self.header_name] = request_id
        
        return response
