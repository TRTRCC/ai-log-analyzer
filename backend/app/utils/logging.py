"""
Logging utilities for AI Log Analyzer
"""

import sys
import logging
from typing import Any
import structlog
from pathlib import Path

from app.config import settings


def setup_logging():
    """Configure structured logging for the application"""

    # Create logs directory if it doesn't exist
    log_dir = Path(settings.audit_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = Path(settings.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Configure structlog processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # Console renderer
    console_renderer = structlog.dev.ConsoleRenderer(colors=True)

    # JSON renderer for file output
    json_renderer = structlog.processors.JSONRenderer()

    # Configure structlog
    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Set up Python logging
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.log_level)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    ))
    root_logger.addHandler(console_handler)

    # File handler
    try:
        file_handler = logging.FileHandler(settings.log_file)
        file_handler.setLevel(settings.log_level)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        ))
        root_logger.addHandler(file_handler)
    except Exception:
        pass  # Ignore if file logging fails


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance"""
    return structlog.get_logger(name)


class LogContext:
    """Helper class for managing log context"""

    def __init__(self, logger: structlog.stdlib.BoundLogger):
        self.logger = logger
        self.context = {}

    def bind(self, **kwargs: Any) -> "LogContext":
        """Bind additional context to the logger"""
        self.context.update(kwargs)
        self.logger = self.logger.bind(**kwargs)
        return self

    def unbind(self, key: str) -> "LogContext":
        """Remove a context key"""
        if key in self.context:
            del self.context[key]
        return self

    def info(self, msg: str, **kwargs: Any):
        """Log info message"""
        self.logger.info(msg, **kwargs)

    def error(self, msg: str, **kwargs: Any):
        """Log error message"""
        self.logger.error(msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any):
        """Log warning message"""
        self.logger.warning(msg, **kwargs)

    def debug(self, msg: str, **kwargs: Any):
        """Log debug message"""
        self.logger.debug(msg, **kwargs)