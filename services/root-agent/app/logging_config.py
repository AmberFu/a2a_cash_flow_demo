"""Logging helpers for CloudWatch-friendly JSON output."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


class CloudWatchJsonFormatter(logging.Formatter):
    """Emit JSON logs so CloudWatch can filter on structured fields like task_id."""

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
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat(timespec="milliseconds") + "Z",
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


class TaskIdContextFilter(logging.Filter):
    """確保所有日誌都帶有 `task_id` 欄位，方便在 CloudWatch 過濾。"""

    def __init__(self, default_value: str = "n/a") -> None:
        super().__init__()
        self._default_value = default_value

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - trivial guard
        if not hasattr(record, "task_id") or record.task_id in (None, ""):
            record.task_id = self._default_value
        return True


class SuppressMetricsAccessFilter(logging.Filter):
    """過濾掉健康檢查對 `/metrics` 的存取日誌。"""

    _BLOCK_TOKENS = (
        '"GET /metrics',
        "GET /metrics HTTP",
        "GET /metrics?",
    )

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - simple predicate
        message: Any
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            message = record.msg

        if isinstance(message, str):
            return not any(token in message for token in self._BLOCK_TOKENS)

        return True


def configure_logging(
    log_level: str | None = None,
    *,
    default_task_id: str = "n/a",
    suppress_metrics_access_logs: bool = True,
) -> None:
    """Configure root logging with the CloudWatch JSON formatter."""

    handler = logging.StreamHandler()
    handler.setFormatter(CloudWatchJsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.addFilter(TaskIdContextFilter(default_value=default_task_id))

    level = (log_level or LOG_LEVEL).upper()
    root_logger.setLevel(level)

    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers.clear()
    uvicorn_access.propagate = True
    if suppress_metrics_access_logs:
        uvicorn_access.addFilter(SuppressMetricsAccessFilter())


__all__ = ["CloudWatchJsonFormatter", "configure_logging"]
