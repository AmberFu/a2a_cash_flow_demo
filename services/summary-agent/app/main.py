"""摘要代理服務：整合遠端代理的結果並產生旅遊建議。"""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_fastapi_instrumentator import Instrumentator
import uvicorn

from .config import get_settings
from .models import SummaryRequest, SummaryResponse
from .summarizer import craft_summary_response

settings = get_settings()
METRICS_ENABLED = os.environ.get("METRICS_ENABLED", "true").lower() == "true"
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


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(CloudWatchJsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(LOG_LEVEL)


configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """初始化與釋放摘要代理需要的資源。"""

    logger.info("Summary Agent is starting up on port %s", settings.port)
    yield
    logger.info("Summary Agent is shutting down")


app = FastAPI(title="Summary Agent", version="0.2.0", lifespan=lifespan)
if METRICS_ENABLED:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
else:
    logger.info("Prometheus instrumentation disabled via METRICS_ENABLED=false")

    @app.get("/metrics", include_in_schema=False)
    async def metrics_disabled() -> PlainTextResponse:  # pragma: no cover - simple stub
        """Return an empty 204 response so health probes do not trigger 404 errors."""

        return PlainTextResponse("", status_code=204)


@app.get("/")
def healthcheck() -> JSONResponse:
    """回傳服務狀態與當前模型設定。"""

    logger.debug("Healthcheck requested")
    return JSONResponse(
        {
            "status": "OK",
            "agent": "Summary Agent",
            "port": settings.port,
            "llm_provider": settings.llm_provider,
            "llm_model_id": settings.llm_model_id,
        }
    )


@app.post("/summaries", response_model=SummaryResponse)
def summarize(request: SummaryRequest) -> SummaryResponse:
    """整合遠端代理結果並產出建議與提醒。"""

    logger.info(
        "Generating summary for task_id=%s, origin=%s, destination=%s",
        request.task_id,
        request.user_requirement.origin,
        request.user_requirement.destination,
        extra={
            "task_id": request.task_id,
            "origin": request.user_requirement.origin,
            "destination": request.user_requirement.destination,
        },
    )
    response = craft_summary_response(
        request,
        provider=settings.llm_provider,
        model_id=settings.llm_model_id,
    )
    logger.debug(
        "Summary response prepared for task_id=%s",
        request.task_id,
        extra={"task_id": request.task_id},
    )
    return response


if __name__ == "__main__":
    uvicorn.run(app="main:app", host="0.0.0.0", port=settings.port)
