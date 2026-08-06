import logging

import structlog

from shared.config import get_settings


def _parse_log_level(level_name: str, fallback: int) -> int:
    level = getattr(logging, (level_name or "").upper(), None)
    return level if isinstance(level, int) else fallback


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    azure_level = _parse_log_level(settings.azure_sdk_log_level, logging.WARNING)
    for logger_name in (
        "azure",
        "azure.cosmos",
        "azure.cosmos._cosmos_http_logging_policy",
        "azure.core.pipeline.policies.http_logging_policy",
    ):
        logging.getLogger(logger_name).setLevel(azure_level)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
