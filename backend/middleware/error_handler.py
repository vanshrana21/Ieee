"""
Phase 0: Virtual Courtroom Infrastructure - Error Handler Middleware

Global error handling for all uncaught exceptions.
Provides graceful degradation and user-friendly error messages.
"""
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import ValidationError
from typing import Optional, Dict, Any, Callable
import logging
import traceback
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


# Error categories with HTTP status codes
class ErrorCategory:
    """Error categories with corresponding HTTP status codes."""
    VALIDATION_ERROR = ("VALIDATION_ERROR", 400)
    AUTHENTICATION_ERROR = ("AUTHENTICATION_ERROR", 401)
    AUTHORIZATION_ERROR = ("AUTHORIZATION_ERROR", 403)
    NOT_FOUND_ERROR = ("NOT_FOUND_ERROR", 404)
    CONFLICT_ERROR = ("CONFLICT_ERROR", 409)
    RATE_LIMIT_ERROR = ("RATE_LIMIT_ERROR", 429)
    SERVER_ERROR = ("SERVER_ERROR", 500)
    WEBSOCKET_ERROR = ("WEBSOCKET_ERROR", 4000)  # Custom close code


class CourtroomError(Exception):
    """Base exception for courtroom-specific errors."""
    
    def __init__(
        self,
        message: str,
        category: tuple = ErrorCategory.SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
        log_id: Optional[str] = None
    ):
        self.message = message
        self.category = category
        self.details = details or {}
        self.log_id = log_id or str(uuid.uuid4())[:8]
        self.timestamp = datetime.utcnow().isoformat()
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for API responses."""
        return {
            "error_code": self.category[0],
            "message": self.message,
            "details": self.details,
            "log_id": self.log_id,
            "timestamp": self.timestamp
        }


class ValidationError(CourtroomError):
    """Invalid input data (400)."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, ErrorCategory.VALIDATION_ERROR, details)


class AuthenticationError(CourtroomError):
    """Invalid or expired token (401)."""
    def __init__(self, message: str = "Authentication required", details: Optional[Dict] = None):
        super().__init__(message, ErrorCategory.AUTHENTICATION_ERROR, details)


class AuthorizationError(CourtroomError):
    """Insufficient permissions (403)."""
    def __init__(self, message: str = "Permission denied", details: Optional[Dict] = None):
        super().__init__(message, ErrorCategory.AUTHORIZATION_ERROR, details)


class NotFoundError(CourtroomError):
    """Resource not found (404)."""
    def __init__(self, resource: str, resource_id: Optional[str] = None):
        message = f"{resource} not found"
        if resource_id:
            message += f": {resource_id}"
        super().__init__(message, ErrorCategory.NOT_FOUND_ERROR, {"resource": resource, "id": resource_id})


class ConflictError(CourtroomError):
    """Resource conflict, e.g., duplicate (409)."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, ErrorCategory.CONFLICT_ERROR, details)


class WebSocketError(CourtroomError):
    """WebSocket-specific error with custom close code."""
    def __init__(self, message: str, close_code: int = 4000, details: Optional[Dict] = None):
        super().__init__(message, ("WEBSOCKET_ERROR", close_code), details)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Global error handling middleware.
    
    Catches all uncaught exceptions and returns structured error responses.
    Logs errors with context for debugging.
    """
    
    def __init__(self, app, debug: bool = False):
        super().__init__(app)
        self.debug = debug
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and handle any exceptions."""
        try:
            response = await call_next(request)
            return response
            
        except CourtroomError as e:
            # Our custom errors - return structured response
            self._log_error(request, e)
            return self._create_error_response(e)
            
        except ValidationError as e:
            # Pydantic validation errors
            log_id = str(uuid.uuid4())[:8]
            self._log_error(request, e, log_id)
            return JSONResponse(
                status_code=400,
                content={
                    "error_code": "VALIDATION_ERROR",
                    "message": "Invalid input data",
                    "details": {"errors": e.errors()},
                    "log_id": log_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
        except Exception as e:
            # Unexpected errors - log full details but return generic message
            log_id = str(uuid.uuid4())[:8]
            self._log_error(request, e, log_id, is_unexpected=True)
            
            if self.debug:
                # In debug mode, include stack trace
                return JSONResponse(
                    status_code=500,
                    content={
                        "error_code": "SERVER_ERROR",
                        "message": str(e),
                        "details": {
                            "traceback": traceback.format_exc(),
                            "type": type(e).__name__
                        },
                        "log_id": log_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            else:
                # Production - generic message with log_id for support
                return JSONResponse(
                    status_code=500,
                    content={
                        "error_code": "SERVER_ERROR",
                        "message": "An internal error occurred. Please try again or contact support.",
                        "details": {},
                        "log_id": log_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
    
    def _log_error(
        self,
        request: Request,
        error: Exception,
        log_id: Optional[str] = None,
        is_unexpected: bool = False
    ):
        """Log error with request context."""
        log_id = log_id or getattr(error, 'log_id', str(uuid.uuid4())[:8])
        
        # Build context
        context = {
            "log_id": log_id,
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }
        
        # Try to get user info
        try:
            if hasattr(request.state, "user"):
                context["user_id"] = request.state.user.get("id")
                context["user_role"] = request.state.user.get("role")
        except:
            pass
        
        # Log with appropriate level
        if is_unexpected:
            logger.error(
                f"Unexpected error [{log_id}]: {str(error)}\n"
                f"Context: {context}\n"
                f"Traceback:\n{traceback.format_exc()}"
            )
        else:
            logger.warning(
                f"Handled error [{log_id}]: {str(error)} | Context: {context}"
            )
    
    def _create_error_response(self, error: CourtroomError) -> JSONResponse:
        """Create JSON response from CourtroomError."""
        status_code = error.category[1]
        
        # Don't expose internal details for 500 errors in production
        if status_code >= 500 and not self.debug:
            return JSONResponse(
                status_code=status_code,
                content={
                    "error_code": error.category[0],
                    "message": "An internal error occurred. Please try again or contact support.",
                    "details": {},
                    "log_id": error.log_id,
                    "timestamp": error.timestamp
                }
            )
        
        return JSONResponse(
            status_code=status_code,
            content=error.to_dict()
        )


# Decorator for route-level error handling
def handle_errors(func: Callable) -> Callable:
    """
    Decorator to catch and convert exceptions to CourtroomError.
    
    Usage:
        @handle_errors
        async def my_endpoint():
            raise ValueError("Something wrong")  # Converted to CourtroomError
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except CourtroomError:
            raise
        except ValueError as e:
            raise ValidationError(str(e))
        except PermissionError as e:
            raise AuthorizationError(str(e))
        except FileNotFoundError as e:
            raise NotFoundError("Resource", str(e))
        except Exception as e:
            # Wrap unexpected errors
            log_id = str(uuid.uuid4())[:8]
            logger.exception(f"Unexpected error [{log_id}] in {func.__name__}")
            raise CourtroomError(
                "An unexpected error occurred",
                ErrorCategory.SERVER_ERROR,
                {"original_error": str(e)},
                log_id
            )
    return wrapper


# FastAPI exception handlers
def setup_error_handlers(app, debug: bool = False):
    """
    Setup error handlers for FastAPI application.
    
    Args:
        app: FastAPI application instance
        debug: Enable debug mode (includes stack traces)
    """
    
    @app.exception_handler(CourtroomError)
    async def courtroom_error_handler(request: Request, exc: CourtroomError):
        """Handle CourtroomError exceptions."""
        status_code = exc.category[1]
        
        content = exc.to_dict()
        if status_code >= 500 and not debug:
            content["message"] = "An internal error occurred. Please try again or contact support."
            content["details"] = {}
        
        return JSONResponse(status_code=status_code, content=content)
    
    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError):
        """Handle Pydantic validation errors."""
        log_id = str(uuid.uuid4())[:8]
        return JSONResponse(
            status_code=400,
            content={
                "error_code": "VALIDATION_ERROR",
                "message": "Invalid input data",
                "details": {"errors": exc.errors()},
                "log_id": log_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        """Handle all other exceptions."""
        log_id = str(uuid.uuid4())[:8]
        logger.exception(f"Unhandled exception [{log_id}]")
        
        content = {
            "error_code": "SERVER_ERROR",
            "message": str(exc) if debug else "An internal error occurred",
            "details": {"traceback": traceback.format_exc()} if debug else {},
            "log_id": log_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return JSONResponse(status_code=500, content=content)
    
    # Add middleware
    app.add_middleware(ErrorHandlerMiddleware, debug=debug)
    
    logger.info("Error handlers configured")
