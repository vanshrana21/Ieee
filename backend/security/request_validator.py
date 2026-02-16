"""
Phase 10 — Request Validator

Strict request validation for API security.
Validates headers, content types, and request structure.
"""
import re
from typing import Optional, Dict, Any, List
from fastapi import Request, HTTPException, status


class RequestValidator:
    """
    Validates incoming HTTP requests for security compliance.
    
    Checks:
    - Content-Type validity
    - Header sanity
    - Request size limits
    - Character encoding
    - Malformed request detection
    """
    
    # Allowed content types for POST/PUT
    ALLOWED_CONTENT_TYPES = [
        "application/json",
        "multipart/form-data",
    ]
    
    # Blocked content types
    BLOCKED_CONTENT_TYPES = [
        "application/x-www-form-urlencoded",
        "text/plain",
        "application/xml",
        "text/xml",
    ]
    
    # Maximum request size (10MB)
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    
    # Blocked path patterns (regex)
    BLOCKED_PATH_PATTERNS = [
        r"\.\.",  # Path traversal
        r"<script",  # XSS attempts
        r"javascript:",  # XSS
        r"on\w+=",  # Event handlers
        r"union\s+select",  # SQL injection
        r";\s*drop",  # SQL injection
        r"exec\s*\(",  # Command injection
    ]
    
    def __init__(self):
        self.blocked_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.BLOCKED_PATH_PATTERNS]
    
    async def validate(self, request: Request) -> Dict[str, Any]:
        """
        Validate request for security compliance.
        
        Args:
            request: FastAPI request object
        
        Returns:
            Validation metadata
        
        Raises:
            HTTPException: If validation fails
        """
        errors = []
        
        # Validate content type for write operations
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("Content-Type", "")
            content_type_valid = self._validate_content_type(content_type)
            if not content_type_valid:
                errors.append(f"Invalid Content-Type: {content_type}")
        
        # Validate content length
        content_length = request.headers.get("Content-Length")
        if content_length:
            length_valid = self._validate_content_length(content_length)
            if not length_valid:
                errors.append("Content-Length exceeds maximum allowed size")
        
        # Validate path
        path_valid, path_error = self._validate_path(request.url.path)
        if not path_valid:
            errors.append(f"Invalid path: {path_error}")
        
        # Validate query parameters
        query_valid, query_error = self._validate_query_params(str(request.query_params))
        if not query_valid:
            errors.append(f"Invalid query parameters: {query_error}")
        
        # Validate headers
        header_valid, header_error = self._validate_headers(dict(request.headers))
        if not header_valid:
            errors.append(f"Invalid headers: {header_error}")
        
        if errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Request validation failed",
                    "errors": errors
                }
            )
        
        return {
            "valid": True,
            "content_type": content_type if request.method in ("POST", "PUT", "PATCH") else None,
            "path": request.url.path,
            "query_params": len(request.query_params),
        }
    
    def _validate_content_type(self, content_type: str) -> bool:
        """
        Validate Content-Type header.
        
        Returns:
            True if allowed, False if blocked
        """
        if not content_type:
            return True  # Allow missing for some requests
        
        # Check blocked types
        for blocked in self.BLOCKED_CONTENT_TYPES:
            if blocked in content_type.lower():
                return False
        
        # Check if explicitly allowed
        for allowed in self.ALLOWED_CONTENT_TYPES:
            if allowed in content_type.lower():
                return True
        
        # Allow if starts with application/ (general rule)
        if content_type.startswith("application/"):
            return True
        
        return True  # Default allow
    
    def _validate_content_length(self, content_length: str) -> bool:
        """
        Validate Content-Length header.
        
        Returns:
            True if within limits, False if exceeded
        """
        try:
            length = int(content_length)
            return 0 <= length <= self.MAX_CONTENT_LENGTH
        except ValueError:
            return False
    
    def _validate_path(self, path: str) -> tuple[bool, Optional[str]]:
        """
        Validate URL path for malicious patterns.
        
        Returns:
            (valid, error_message)
        """
        # Check for null bytes
        if "\x00" in path:
            return False, "Null bytes not allowed"
        
        # Check for path traversal
        if ".." in path:
            return False, "Path traversal detected"
        
        # Check blocked patterns
        path_lower = path.lower()
        for pattern in self.blocked_patterns:
            if pattern.search(path_lower):
                return False, f"Blocked pattern detected: {pattern.pattern}"
        
        # Validate characters
        allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_/-")
        for char in path:
            if char not in allowed_chars and char not in ".":
                return False, f"Invalid character in path: {char}"
        
        return True, None
    
    def _validate_query_params(self, query_string: str) -> tuple[bool, Optional[str]]:
        """
        Validate query string parameters.
        
        Returns:
            (valid, error_message)
        """
        if not query_string:
            return True, None
        
        # Check for null bytes
        if "\x00" in query_string:
            return False, "Null bytes not allowed"
        
        # Check blocked patterns
        query_lower = query_string.lower()
        for pattern in self.blocked_patterns:
            if pattern.search(query_lower):
                return False, "Suspicious pattern in query parameters"
        
        return True, None
    
    def _validate_headers(self, headers: Dict[str, str]) -> tuple[bool, Optional[str]]:
        """
        Validate HTTP headers.
        
        Returns:
            (valid, error_message)
        """
        for name, value in headers.items():
            # Check for null bytes
            if "\x00" in name or "\x00" in value:
                return False, "Null bytes not allowed in headers"
            
            # Validate header name (should be alphanumeric with hyphens)
            if not re.match(r"^[A-Za-z0-9-]+$", name):
                return False, f"Invalid header name: {name}"
        
        return True, None
    
    def sanitize_input(self, value: str) -> str:
        """
        Sanitize string input by removing dangerous characters.
        
        Args:
            value: Input string to sanitize
        
        Returns:
            Sanitized string
        """
        if not value:
            return value
        
        # Remove null bytes
        value = value.replace("\x00", "")
        
        # Remove control characters
        value = "".join(char for char in value if ord(char) >= 32 or char in "\t\n\r")
        
        return value


class InputSanitizer:
    """
    Input sanitization utilities.
    """
    
    @staticmethod
    def sanitize_string(value: str, max_length: int = 1000) -> str:
        """
        Sanitize string input.
        
        Args:
            value: Input string
            max_length: Maximum allowed length
        
        Returns:
            Sanitized string
        """
        if not value:
            return value
        
        # Truncate if too long
        if len(value) > max_length:
            value = value[:max_length]
        
        # Remove dangerous characters
        dangerous = ["\x00", "\x01", "\x02", "\x03", "\x04", "\x05"]
        for char in dangerous:
            value = value.replace(char, "")
        
        return value
    
    @staticmethod
    def sanitize_email(email: str) -> str:
        """
        Sanitize email address.
        
        Args:
            email: Email address
        
        Returns:
            Sanitized email or empty if invalid
        """
        if not email:
            return ""
        
        # Basic email validation regex
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, email):
            return ""
        
        return email.lower().strip()
    
    @staticmethod
    def sanitize_integer(value: Any, min_val: Optional[int] = None, max_val: Optional[int] = None) -> Optional[int]:
        """
        Sanitize integer input.
        
        Args:
            value: Input value
            min_val: Minimum allowed value
            max_val: Maximum allowed value
        
        Returns:
            Sanitized integer or None if invalid
        """
        try:
            num = int(value)
            
            if min_val is not None and num < min_val:
                return None
            
            if max_val is not None and num > max_val:
                return None
            
            return num
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def sanitize_json_keys(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize JSON object keys (prevent prototype pollution).
        
        Args:
            data: Dictionary to sanitize
        
        Returns:
            Sanitized dictionary
        """
        dangerous_keys = ["__proto__", "constructor", "prototype"]
        
        result = {}
        for key, value in data.items():
            if key in dangerous_keys:
                continue
            
            if isinstance(value, dict):
                result[key] = InputSanitizer.sanitize_json_keys(value)
            else:
                result[key] = value
        
        return result
