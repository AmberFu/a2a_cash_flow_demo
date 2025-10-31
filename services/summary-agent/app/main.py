"""摘要代理服務：整合遠端代理的結果並產生旅遊建議。"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
import uvicorn
from jsonrpcserver import dispatch

from .config import get_settings
from .models import SummaryRequest, SummaryResponse
from .summarizer import craft_summary_response

settings = get_settings()
METRICS_ENABLED = os.environ.get("METRICS_ENABLED", "true").lower() == "true"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
)
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


def summarize_impl(request: SummaryRequest) -> SummaryResponse:
    """Core logic for generating a summary."""
    logger.info(
        "Generating summary for task_id=%s, origin=%s, destination=%s",
        request.task_id,
        request.user_requirement.origin,
        request.user_requirement.destination,
    )
    response = craft_summary_response(
        request,
        provider=settings.llm_provider,
        model_id=settings.llm_model_id,
    )
    logger.debug("Summary response prepared for task_id=%s", request.task_id)
    return response


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
def summarize_endpoint(request: SummaryRequest) -> SummaryResponse:
    """RESTful endpoint for summaries."""
    return summarize_impl(request)


async def summarize_rpc(
    task_id: str,
    user_requirement: dict,
    weather_report: dict,
    transport: dict,
) -> dict:
    """JSON-RPC method for summaries."""
    request = SummaryRequest(
        task_id=task_id,
        user_requirement=user_requirement,
        weather_report=weather_report,
        transport=transport,
    )
    response = summarize_impl(request)
    return response.model_dump()


@app.post("/jsonrpc")
async def jsonrpc_endpoint(request: Request):
    """JSON-RPC endpoint."""
    req_str = await request.body()
    response = await dispatch(
        req_str.decode(), methods={"summaries.create": summarize_rpc}
    )
    if response.wanted:
        return JSONResponse(content=response.deserialized(), status_code=response.http_status)
    return JSONResponse(content=None, status_code=204)


if __name__ == "__main__":
    uvicorn.run(app="main:app", host="0.0.0.0", port=settings.port)
