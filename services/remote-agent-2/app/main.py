"""Transport plan Remote Agent service entrypoint."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse, Response
from prometheus_fastapi_instrumentator import Instrumentator
import uvicorn

from logging_config import configure_logging
from models import TransportPlanRequest, TransportPlanResponse
from transport_service import generate_transport_plans


PORT = int(os.environ.get("PORT", 50002))
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "bedrock")
LLM_MODEL_ID = os.environ.get(
    "LLM_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
)
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
    logger.info("Remote Agent 2 is starting up...")
    try:
        yield
    finally:
        logger.info("Remote Agent 2 is shutting down...")


app = FastAPI(
    title="Transport Remote Agent",
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
def status() -> JSONResponse:
    """回傳服務狀態。"""

    logger.debug("Status endpoint called")
    return JSONResponse(
        {
            "status": "OK",
            "agent": "Remote Agent 2",
            "port": PORT,
            "llm_provider": LLM_PROVIDER,
            "llm_model_id": LLM_MODEL_ID,
        }
    )


@app.post("/transport/plans", response_model=TransportPlanResponse)
def generate_transport_plan_endpoint(
    request: TransportPlanRequest,
    task_id: str | None = Header(default=None, alias="X-A2A-Task-Id"),
) -> TransportPlanResponse:
    """依據使用者輸入生成交通資訊方案。"""

    task_label = task_id or "n/a"
    log_extra = _extra(
        task_id,
        destination=request.destination,
        arrival_time=request.arrival_time,
        requested_results=request.results,
    )
    logger.info(
        "[Task %s] Generating %s transport plans for destination %s by %s",
        task_label,
        request.results,
        request.destination,
        request.arrival_time,
        extra=log_extra,
    )
    plans = generate_transport_plans(request)
    logger.debug("Transport plans generated", extra={**log_extra, "plan_count": len(plans)})
    return TransportPlanResponse(
        destination=request.destination,
        requested_arrival_time=request.arrival_time,
        date=request.date,
        plans=plans,
    )


if __name__ == "__main__":
    uvicorn.run(app="main:app", host="0.0.0.0", port=PORT)
