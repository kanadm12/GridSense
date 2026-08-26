"""Structured logging configuration for the application."""

import logging
import sys
from datetime import datetime
from typing import Any

from pythonjsonlogger import jsonlogger


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields."""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)

        # Add timestamp in ISO format
        log_record["timestamp"] = datetime.utcnow().isoformat() + "Z"

        # Add level name
        log_record["level"] = record.levelname

        # Add logger name
        log_record["logger"] = record.name

        # Add module and function
        log_record["module"] = record.module
        log_record["function"] = record.funcName


def setup_logging(debug: bool = False) -> None:
    """Configure structured logging for the application.

    Args:
        debug: If True, set log level to DEBUG, otherwise INFO
    """
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Remove existing handlers
    root_logger.handlers = []

    # Create console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)

    # Use JSON formatting
    formatter = CustomJsonFormatter(
        "%(timestamp)s %(level)s %(logger)s %(module)s %(function)s %(message)s"
    )
    console_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)

    # Set levels for third-party loggers to reduce noise
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("rq").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module.

    Args:
        name: Module name (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# Convenience functions for structured logging
def log_api_request(
    logger: logging.Logger,
    method: str,
    path: str,
    user_id: int | None = None,
    **extra: Any,
) -> None:
    """Log an API request with structured data."""
    logger.info(
        "API request",
        extra={
            "event": "api_request",
            "method": method,
            "path": path,
            "user_id": user_id,
            **extra,
        },
    )


def log_api_response(
    logger: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    user_id: int | None = None,
    **extra: Any,
) -> None:
    """Log an API response with structured data."""
    logger.info(
        "API response",
        extra={
            "event": "api_response",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "user_id": user_id,
            **extra,
        },
    )


def log_db_operation(
    logger: logging.Logger,
    operation: str,
    table: str,
    record_id: int | None = None,
    user_id: int | None = None,
    **extra: Any,
) -> None:
    """Log a database operation with structured data."""
    logger.debug(
        "Database operation",
        extra={
            "event": "db_operation",
            "operation": operation,
            "table": table,
            "record_id": record_id,
            "user_id": user_id,
            **extra,
        },
    )


def log_background_task(
    logger: logging.Logger,
    task_name: str,
    status: str,
    duration_ms: float | None = None,
    **extra: Any,
) -> None:
    """Log a background task execution with structured data."""
    logger.info(
        "Background task",
        extra={
            "event": "background_task",
            "task_name": task_name,
            "status": status,
            "duration_ms": duration_ms,
            **extra,
        },
    )


def log_ml_operation(
    logger: logging.Logger,
    operation: str,
    meter_id: int,
    model_type: str | None = None,
    status: str | None = None,
    **extra: Any,
) -> None:
    """Log an ML operation with structured data."""
    logger.info(
        "ML operation",
        extra={
            "event": "ml_operation",
            "operation": operation,
            "meter_id": meter_id,
            "model_type": model_type,
            "status": status,
            **extra,
        },
    )


def log_external_service(
    logger: logging.Logger,
    service: str,
    operation: str,
    status: str,
    duration_ms: float | None = None,
    **extra: Any,
) -> None:
    """Log an external service call with structured data."""
    logger.info(
        "External service call",
        extra={
            "event": "external_service",
            "service": service,
            "operation": operation,
            "status": status,
            "duration_ms": duration_ms,
            **extra,
        },
    )
