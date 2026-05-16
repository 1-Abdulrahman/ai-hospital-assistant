"""
Logging configuration module for JSON-formatted structured logging.

This module provides a custom JSON formatter that outputs logs in a structured
JSON format, making them suitable for centralized logging systems and log analysis.
Each log entry includes correlation IDs for request tracing across services.
"""
import json
import logging
import sys
from datetime import datetime, timezone

from app.core.config import settings
from app.core.correlation import get_correlation_id


class JsonFormatter(logging.Formatter):
    """
    Custom formatter that outputs log records as JSON.

    This formatter converts standard Python logging records into JSON format,
    including structured metadata such as timestamps, correlation IDs, and
    exception information. Useful for integration with log aggregation services.
    """
    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record as a JSON string.

        Args:
            record: The log record to format.

        Returns:
            A JSON string representation of the log record with structured metadata.
        """
        # Build the base payload with core logging information
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlationId": get_correlation_id(),  # For distributed tracing
            "module": record.module,
            "function": record.funcName,
        }
        # Include exception details if this is an exception log
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """
    Configure the root logger with JSON formatting and settings from config.

    This function sets up the logging system to output JSON-formatted logs to stdout.
    It respects the log level specified in the application settings and clears any
    existing handlers to ensure a clean logging configuration.

    Note: This function should be called once during application initialization.
    """
    # Get the root logger and configure its level from settings
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())

    # Create a stdout handler with the custom JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    # Clear existing handlers to avoid duplicate logs and ensure clean state
    root_logger.handlers.clear()
    # Register the new handler with JSON formatting
    root_logger.addHandler(handler)