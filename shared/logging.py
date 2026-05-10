import logging
from logging.config import dictConfig


def configure_logging(service_name: str, level: str | int = "INFO") -> None:
    """Configure structured logging for the application.

    Produces logs with timestamp, level, service name, and message.
    """

    if isinstance(level, str):
        level = level.upper()

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": f"%(asctime)s %(levelname)s [%(name)s|{service_name}] %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S%z",
            }
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": level,
            }
        },
        "root": {"handlers": ["default"], "level": level},
    }

    dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
