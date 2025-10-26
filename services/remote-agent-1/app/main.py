"""天氣規劃 Remote Agent 服務。"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse, Response
from prometheus_fastapi_instrumentator import Instrumentator
import uvicorn

from llm import synthesize_weather_summary
from logging_config import configure_logging
from models import WeatherReportRequest, WeatherReportResponse
from weather_generator import generate_city_weather_variables

PORT = int(os.environ.get("PORT", 50001))
METRICS_ENABLED = os.environ.get("METRICS_ENABLED", "true").lower() == "true"

configure_logging()
logger = logging.getLogger(__name__)


def _extra(task_id: str | None, **payload: object) -> dict[str, object]:
    """Construct logging extras with an optional task identifier."""

    extra: dict[str, object] = {"task_id": task_id}
    extra.update(payload)
    return extra


@asynccontextmanager
async def lifespan(app: FastAPI):
    """初始化與釋放 Remote Agent 需要的資源。"""

    logger.info("Weather Remote Agent is starting up on port %s", PORT)
    try:
        yield
    finally:
        logger.info("Weather Remote Agent is shutting down")


app = FastAPI(
    title="Weather Remote Agent",
    version="0.2.0",
    lifespan=lifespan,
)
if METRICS_ENABLED:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
else:
    logger.info("Prometheus instrumentation disabled via METRICS_ENABLED=false")

    @app.get("/metrics", include_in_schema=False)
    def metrics_disabled() -> Response:
        """Return an empty response so health checks do not log 404s."""

        return Response(status_code=204)


@app.get("/")
def healthcheck() -> JSONResponse:
    """回傳服務狀態。"""

    logger.debug("Healthcheck requested")
    return JSONResponse(
        {
            "status": "OK",
            "agent": "Weather Remote Agent",
            "port": PORT,
            "description": "提供隨機天氣摘要與行前提醒。",
        }
    )


@app.post("/weather/report", response_model=WeatherReportResponse)
def weather_report(
    request: WeatherReportRequest,
    task_id: str | None = Header(default=None, alias="X-A2A-Task-Id"),
) -> WeatherReportResponse:
    """回傳指定城市在特定時段的隨機天氣摘要。"""

    task_label = task_id or "n/a"
    log_extra = _extra(
        task_id,
        city=request.city,
        date=request.date.isoformat(),
        time_range=request.time_range,
    )
    logger.info(
        "[Task %s] Generating weather report for city=%s, date=%s, time_range=%s",
        task_label,
        request.city,
        request.date.isoformat(),
        request.time_range,
        extra=log_extra,
    )
    variables = generate_city_weather_variables(request.city)
    summary = synthesize_weather_summary(request, variables)
    logger.debug(
        "Weather variables generated",
        extra={**log_extra, "weather_variables": variables.model_dump()},
    )
    return WeatherReportResponse(
        city=request.city,
        date=request.date,
        time_range=request.time_range,
        variables=variables,
        summary=summary,
    )


if __name__ == "__main__":
    uvicorn.run(app="main:app", host="0.0.0.0", port=PORT)
