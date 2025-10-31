"""Transport plan Remote Agent service entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
import uvicorn
from jsonrpcserver import dispatch

from models import TransportPlanRequest, TransportPlanResponse
from transport_service import generate_transport_plans


LOG_FORMAT = "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


PORT = int(os.environ.get("PORT", 50002))
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "bedrock")
LLM_MODEL_ID = os.environ.get(
    "LLM_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
)
METRICS_ENABLED = os.environ.get("METRICS_ENABLED", "true").lower() == "true"


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


def generate_transport_plan_impl(
    request: TransportPlanRequest,
) -> TransportPlanResponse:
    """Core logic for generating transport plans."""
    logger.info(
        "Generating %s transport plans for destination %s by %s",
        request.results,
        request.destination,
        request.arrival_time,
    )
    plans = generate_transport_plans(request)
    return TransportPlanResponse(
        destination=request.destination,
        requested_arrival_time=request.arrival_time,
        date=request.date,
        plans=plans,
    )


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
) -> TransportPlanResponse:
    """RESTful endpoint for transport plans."""
    return generate_transport_plan_impl(request)


async def transport_plans_rpc(
    destination: str, arrival_time: str, date: str, results: int
) -> dict:
    """JSON-RPC method for transport plans."""
    request = TransportPlanRequest(
        destination=destination,
        arrival_time=arrival_time,
        date=date,
        results=results,
    )
    response = generate_transport_plan_impl(request)
    return response.model_dump()


@app.post("/jsonrpc")
async def jsonrpc_endpoint(request: Request):
    """JSON-RPC endpoint."""
    req_str = await request.body()
    response = await dispatch(
        req_str.decode(), methods={"transport.plans": transport_plans_rpc}
    )
    if response.wanted:
        return JSONResponse(content=response.deserialized(), status_code=response.http_status)
    return JSONResponse(content=None, status_code=204)


if __name__ == "__main__":
    uvicorn.run(app="main:app", host="0.0.0.0", port=PORT)
