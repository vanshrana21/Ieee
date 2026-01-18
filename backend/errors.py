"""
backend/errors.py
Phase 11.1: API Contract Verification - Centralized Error Handling

CORE PRINCIPLES:
- APIs are contracts. Contracts must never break.
- No 500 errors caused by user input
- All errors follow consistent structure
- Errors are user-safe (no stack traces)
- Errors are machine-readable

ERROR RESPONSE STRUCTURE:
{
    "success": false,
    "error": "ErrorType",
    "message": "Human-readable description",
    "code": "UNIQUE_ERROR_CODE",
    "details": {} (optional, for validation errors)
}

HTTP STATUS CODE DISCIPLINE:
- 200: Successful, valid request
- 400: Invalid input / malformed request
- 401: Authentication missing or expired
- 403: Access forbidden (ownership / scope)
- 404: Resource does not exist
- 422: Validation error (Pydantic)
- 429: Rate limit exceeded
- 500: NEVER caused by user input (internal only)
"""

import logging
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ErrorCode:
    """Unique error codes for machine-readable error handling"""
    
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_FORMAT = "INVALID_FORMAT"
    
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_INVALID = "AUTH_INVALID"
    
    FORBIDDEN = "FORBIDDEN"
    OWNERSHIP_VIOLATION = "OWNERSHIP_VIOLATION"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    
    NOT_FOUND = "NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    SUBJECT_NOT_FOUND = "SUBJECT_NOT_FOUND"
    MODULE_NOT_FOUND = "MODULE_NOT_FOUND"
    CONTENT_NOT_FOUND = "CONTENT_NOT_FOUND"
    QUESTION_NOT_FOUND = "QUESTION_NOT_FOUND"
    ATTEMPT_NOT_FOUND = "ATTEMPT_NOT_FOUND"
    
    INVALID_STATE = "INVALID_STATE"
    STATE_TRANSITION_INVALID = "STATE_TRANSITION_INVALID"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    PREREQUISITE_NOT_MET = "PREREQUISITE_NOT_MET"
    
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    AI_SERVICE_ERROR = "AI_SERVICE_ERROR"


class ErrorResponse(BaseModel):
    """Standard error response model"""
    success: bool = False
    error: str
    message: str
    code: str
    details: Optional[Dict[str, Any]] = None


class APIError(Exception):
    """Base API exception with consistent structure"""
    
    def __init__(
        self,
        status_code: int,
        error: str,
        message: str,
        code: str,
        details: Optional[Dict[str, Any]] = None
    ):
        self.status_code = status_code
        self.error = error
        self.message = message
        self.code = code
        self.details = details
        super().__init__(message)
    
    def to_response(self) -> JSONResponse:
        """Convert to FastAPI JSONResponse"""
        content = {
            "success": False,
            "error": self.error,
            "message": self.message,
            "code": self.code
        }
        if self.details:
            content["details"] = self.details
        return JSONResponse(status_code=self.status_code, content=content)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "success": False,
            "error": self.error,
            "message": self.message,
            "code": self.code
        }
        if self.details:
            result["details"] = self.details
        return result


class BadRequestError(APIError):
    """400 Bad Request - Invalid input"""
    def __init__(self, message: str, code: str = ErrorCode.INVALID_INPUT, details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error="Bad Request",
            message=message,
            code=code,
            details=details
        )


class UnauthorizedError(APIError):
    """401 Unauthorized - Authentication required"""
    def __init__(self, message: str = "Authentication required", code: str = ErrorCode.AUTH_REQUIRED):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error="Unauthorized",
            message=message,
            code=code
        )


class ForbiddenError(APIError):
    """403 Forbidden - Access denied"""
    def __init__(self, message: str, code: str = ErrorCode.FORBIDDEN, details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error="Forbidden",
            message=message,
            code=code,
            details=details
        )


class NotFoundError(APIError):
    """404 Not Found - Resource does not exist"""
    def __init__(self, resource: str, identifier: Any = None, code: str = ErrorCode.NOT_FOUND):
        message = f"{resource} not found"
        if identifier is not None:
            message = f"{resource} with id '{identifier}' not found"
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error="Not Found",
            message=message,
            code=code
        )


class InvalidStateError(APIError):
    """400 Bad Request - Invalid state transition"""
    def __init__(self, message: str, code: str = ErrorCode.INVALID_STATE, details: Optional[Dict] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            error="Invalid State",
            message=message,
            code=code,
            details=details
        )


class RateLimitError(APIError):
    """429 Too Many Requests"""
    def __init__(self, message: str = "Rate limit exceeded. Please try again later.", retry_after: int = 60):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error="Rate Limited",
            message=message,
            code=ErrorCode.RATE_LIMITED,
            details={"retry_after_seconds": retry_after}
        )


class InternalError(APIError):
    """500 Internal Server Error - Use sparingly, only for true internal failures"""
    def __init__(self, message: str = "An internal error occurred", log_id: Optional[str] = None):
        details = {"log_id": log_id} if log_id else None
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error="Internal Error",
            message=message,
            code=ErrorCode.INTERNAL_ERROR,
            details=details
        )


def raise_bad_request(message: str, code: str = ErrorCode.INVALID_INPUT, details: Optional[Dict] = None):
    """Raise 400 Bad Request"""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"success": False, "error": "Bad Request", "message": message, "code": code, "details": details}
    )


def raise_unauthorized(message: str = "Authentication required", code: str = ErrorCode.AUTH_REQUIRED):
    """Raise 401 Unauthorized"""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"success": False, "error": "Unauthorized", "message": message, "code": code}
    )


def raise_forbidden(message: str, code: str = ErrorCode.FORBIDDEN, details: Optional[Dict] = None):
    """Raise 403 Forbidden"""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"success": False, "error": "Forbidden", "message": message, "code": code, "details": details}
    )


def raise_not_found(resource: str, identifier: Any = None, code: str = ErrorCode.NOT_FOUND):
    """Raise 404 Not Found"""
    message = f"{resource} not found"
    if identifier is not None:
        message = f"{resource} with id '{identifier}' not found"
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"success": False, "error": "Not Found", "message": message, "code": code}
    )


def raise_invalid_state(message: str, code: str = ErrorCode.INVALID_STATE, details: Optional[Dict] = None):
    """Raise 400 for invalid state transitions"""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"success": False, "error": "Invalid State", "message": message, "code": code, "details": details}
    )


def validate_ownership(user_id: int, resource_user_id: int, resource_name: str = "resource"):
    """Validate that a resource belongs to the current user"""
    if user_id != resource_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": f"This {resource_name} does not belong to you",
                "code": ErrorCode.OWNERSHIP_VIOLATION
            }
        )


def validate_subject_access(user_course_id: Optional[int], subject_course_id: int, subject_name: str = "subject"):
    """Validate that a subject belongs to the user's course"""
    if user_course_id is None or user_course_id != subject_course_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": "Forbidden",
                "message": f"This {subject_name} does not belong to your course",
                "code": ErrorCode.SCOPE_VIOLATION
            }
        )


def validate_positive_int(value: int, field_name: str):
    """Validate that a value is a positive integer"""
    if value <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "Bad Request",
                "message": f"{field_name} must be a positive integer",
                "code": ErrorCode.INVALID_INPUT,
                "details": {"field": field_name, "value": value}
            }
        )


def validate_not_empty(value: Optional[str], field_name: str):
    """Validate that a string is not empty"""
    if value is None or value.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "Bad Request",
                "message": f"{field_name} cannot be empty",
                "code": ErrorCode.MISSING_FIELD,
                "details": {"field": field_name}
            }
        )


def validate_enum(value: str, allowed_values: List[str], field_name: str):
    """Validate that a value is in an allowed list"""
    if value not in allowed_values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": "Bad Request",
                "message": f"Invalid {field_name}. Must be one of: {', '.join(allowed_values)}",
                "code": ErrorCode.INVALID_INPUT,
                "details": {"field": field_name, "value": value, "allowed": allowed_values}
            }
        )


def safe_get_or_404(result: Any, resource: str, identifier: Any = None):
    """Return result or raise 404 if None"""
    if result is None:
        raise_not_found(resource, identifier)
    return result


def log_and_raise_internal(error: Exception, context: str = ""):
    """Log an internal error and raise a safe 500 response"""
    import uuid
    log_id = str(uuid.uuid4())[:8]
    logger.error(f"[{log_id}] Internal error in {context}: {type(error).__name__}: {str(error)}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "success": False,
            "error": "Internal Error",
            "message": "An internal error occurred. Please try again later.",
            "code": ErrorCode.INTERNAL_ERROR,
            "details": {"log_id": log_id}
        }
    )


ERROR_MAPPING = {
    400: ("Bad Request", ErrorCode.INVALID_INPUT),
    401: ("Unauthorized", ErrorCode.AUTH_REQUIRED),
    403: ("Forbidden", ErrorCode.FORBIDDEN),
    404: ("Not Found", ErrorCode.NOT_FOUND),
    422: ("Validation Error", ErrorCode.VALIDATION_ERROR),
    429: ("Too Many Requests", ErrorCode.RATE_LIMITED),
    500: ("Internal Error", ErrorCode.INTERNAL_ERROR),
}


def get_error_summary() -> Dict[str, Any]:
    """Return summary of error handling system for documentation"""
    return {
        "version": "11.1",
        "service": "api-error-handler",
        "principle": "APIs are contracts. Contracts must never break.",
        "response_structure": {
            "success": "boolean (always false for errors)",
            "error": "string (error type)",
            "message": "string (human-readable)",
            "code": "string (machine-readable)",
            "details": "object (optional)"
        },
        "status_codes": {
            "200": "Successful, valid request",
            "400": "Invalid input / malformed request",
            "401": "Authentication missing or expired",
            "403": "Access forbidden (ownership / scope)",
            "404": "Resource does not exist",
            "422": "Validation error (Pydantic)",
            "429": "Rate limit exceeded",
            "500": "Internal error (NEVER caused by user input)"
        },
        "error_codes": [
            attr for attr in dir(ErrorCode) 
            if not attr.startswith('_')
        ]
    }
