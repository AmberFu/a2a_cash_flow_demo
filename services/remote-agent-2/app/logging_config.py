"""Logging helpers for the transport remote agent."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


class CloudWatchJsonFormatter(logging.Formatter):
    """Emit JSON logs compatible with CloudWatch structured filters."""

    _RESERVED_ATTRS = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }

    def __init__(self) -> None:
        super().__init__()
        self.converter = time.gmtime

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - formatting logic
        payload = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat(timespec="milliseconds")
            + "Z",
            "level": record.levelname,
            "logger": record.name,
            "filename": record.filename,
            "lineno": record.lineno,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        for attr, value in record.__dict__.items():
            if attr in self._RESERVED_ATTRS or attr.startswith("_"):
                continue
            payload[attr] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(log_level: str | None = None) -> None:
    """Configure root logging with the CloudWatch JSON formatter."""

    handler = logging.StreamHandler()
    handler.setFormatter(CloudWatchJsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    level = (log_level or LOG_LEVEL).upper()
    root_logger.setLevel(level)


__all__ = ["CloudWatchJsonFormatter", "configure_logging"]
