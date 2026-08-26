"""Centralized error handling and consistent error responses."""

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Standard error detail structure."""

    message: str
    code: str
    field: str | None = None
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """Standard error response structure."""

    error: str
    details: list[ErrorDetail] | None = None
    request_id: str | None = None


# Standard error codes
class ErrorCode:
    """Standard error codes for the application."""

    # Authentication & Authorization
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    INVALID_TOKEN = "invalid_token"
    TOKEN_EXPIRED = "token_expired"

    # Validation
    VALIDATION_ERROR = "validation_error"
    INVALID_INPUT = "invalid_input"
    MISSING_FIELD = "missing_field"

    # Resource errors
    NOT_FOUND = "not_found"
    ALREADY_EXISTS = "already_exists"
    CONFLICT = "conflict"

    # Business logic
    INSUFFICIENT_DATA = "insufficient_data"
    OPERATION_FAILED = "operation_failed"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"

    # File processing
    INVALID_FILE_FORMAT = "invalid_file_format"
    FILE_TOO_LARGE = "file_too_large"
    PROCESSING_FAILED = "processing_failed"

    # External services
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    PROVIDER_UNAVAILABLE = "provider_unavailable"

    # Internal errors
    INTERNAL_ERROR = "internal_error"
    DATABASE_ERROR = "database_error"


def create_error_response(
    message: str,
    code: str = ErrorCode.INTERNAL_ERROR,
    field: str | None = None,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Create a standard error response."""
    error_detail = ErrorDetail(message=message, code=code, field=field, details=details)
    response = ErrorResponse(error=message, details=[error_detail], request_id=request_id)
    return response.model_dump(exclude_none=True)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors with consistent format."""
    details = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        details.append(
            ErrorDetail(
                message=error["msg"],
                code=ErrorCode.VALIDATION_ERROR,
                field=field,
                details={"type": error["type"]},
            ).model_dump(exclude_none=True)
        )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error="Validation error", details=details
        ).model_dump(exclude_none=True),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions with consistent format."""
    # Map status codes to error codes
    code_mapping = {
        status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
        status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
        status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
        status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMIT_EXCEEDED,
    }

    error_code = code_mapping.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    response = create_error_response(message=str(exc.detail), code=error_code)

    return JSONResponse(status_code=exc.status_code, content=response)


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    # Log the error (will be implemented with structured logging)
    import traceback

    traceback.print_exc()

    response = create_error_response(
        message="An internal error occurred",
        code=ErrorCode.INTERNAL_ERROR,
        details={"error_type": type(exc).__name__},
    )

    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=response)


def raise_not_found(resource: str, resource_id: int | str | None = None) -> None:
    """Raise a consistent 404 error."""
    message = f"{resource} not found"
    if resource_id is not None:
        message = f"{resource} with id {resource_id} not found"

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=message,
    )


def raise_forbidden(message: str = "You don't have permission to access this resource") -> None:
    """Raise a consistent 403 error."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=message,
    )


def raise_validation_error(message: str, field: str | None = None) -> None:
    """Raise a consistent validation error."""
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=message,
    )


def raise_conflict(message: str) -> None:
    """Raise a consistent 409 conflict error."""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=message,
    )
