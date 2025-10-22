"""Summary Agent service entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
import uvicorn

from .config import get_settings
from .models import SummaryRequest, SummaryResponse
from .summarizer import craft_summary_response


LOG_FORMAT = "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Summary Agent is starting up on port %s", settings.port)
    try:
        yield
    finally:
        logger.info("Summary Agent is shutting down")


app = FastAPI(
    title="Summary Agent",
    description="Aggregates weather and transport recommendations into actionable advice.",
    version="1.0.0",
    lifespan=lifespan,
)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/")
def healthcheck() -> JSONResponse:
    """Return basic health information for observability."""

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
    """Craft a travel summary combining remote agent outputs."""

    logger.info(
        "Creating summary for task %s with destination %s",
        request.task_id,
        request.user_requirement.destination,
    )
    return craft_summary_response(request, settings.llm_provider, settings.llm_model_id)


if __name__ == "__main__":
    uvicorn.run(app="main:app", host="0.0.0.0", port=settings.port)

