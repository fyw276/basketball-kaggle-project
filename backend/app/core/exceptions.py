"""
Custom exception classes for the application
"""

from typing import Any, Dict, Optional


class AppException(Exception):
    """Base exception class for application errors"""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ValidationError(AppException):
    """Raised when input validation fails"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, details=details)


class AuthenticationError(AppException):
    """Raised when authentication fails"""

    def __init__(
        self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, status_code=401, details=details)


class AuthorizationError(AppException):
    """Raised when user lacks permission"""

    def __init__(
        self, message: str = "Permission denied", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, status_code=403, details=details)


class NotFoundError(AppException):
    """Raised when resource is not found"""

    def __init__(
        self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, status_code=404, details=details)


class ConflictError(AppException):
    """Raised when resource conflict occurs"""

    def __init__(
        self, message: str = "Resource conflict", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, status_code=409, details=details)


class ImageProcessingError(AppException):
    """Raised when image processing fails"""

    def __init__(
        self, message: str = "Image processing failed", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, status_code=400, details=details)


class ModelInferenceError(AppException):
    """Raised when ML model inference fails"""

    def __init__(
        self, message: str = "Model inference failed", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, status_code=500, details=details)


class DatabaseError(AppException):
    """Raised when database operation fails"""

    def __init__(
        self, message: str = "Database operation failed", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, status_code=500, details=details)


class CacheError(AppException):
    """Raised when cache operation fails"""

    def __init__(
        self, message: str = "Cache operation failed", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, status_code=500, details=details)
