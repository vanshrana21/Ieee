"""
backend/exceptions.py
Phase 10.1: Custom Exceptions for AI Context & Guardrails

Provides typed exceptions for:
- Access control violations
- Context validation failures
- Scope enforcement
"""


class JurisException(Exception):
    """Base exception for Juris AI"""
    status_code: int = 500
    
    def __init__(self, message: str, status_code: int = None):
        self.message = message
        if status_code:
            self.status_code = status_code
        super().__init__(self.message)


class ForbiddenError(JurisException):
    """
    Raised when user attempts to access unauthorized resources.
    
    Examples:
    - Accessing subject not in curriculum
    - Module not belonging to subject
    - Content outside current scope
    """
    status_code = 403
    
    def __init__(self, message: str = "Access forbidden"):
        super().__init__(message, self.status_code)


class ScopeViolationError(JurisException):
    """
    Raised when AI query goes outside allowed scope.
    
    Examples:
    - Asking about subjects not enrolled
    - Questions outside current module
    - Random legal topics not in syllabus
    """
    status_code = 400
    
    def __init__(self, message: str = "This question is outside your current study scope."):
        super().__init__(message, self.status_code)


class ContextValidationError(JurisException):
    """
    Raised when AI context cannot be validated.
    
    Examples:
    - Invalid subject_id
    - Module doesn't belong to subject
    - Content doesn't belong to module
    """
    status_code = 400
    
    def __init__(self, message: str = "Invalid context parameters"):
        super().__init__(message, self.status_code)


class NotFoundError(JurisException):
    """
    Raised when requested resource doesn't exist.
    """
    status_code = 404
    
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, self.status_code)
