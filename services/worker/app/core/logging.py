import logging

import structlog

from app.core.config import settings


def setup_logging():
    """Configure structured logging based on the env"""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if settings.ENV == "production":
        # Use of Json logs for prod (better for Grafana and Datadog)
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Pretty printend logs for dev env
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
