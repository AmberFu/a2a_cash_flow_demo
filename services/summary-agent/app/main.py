"""摘要代理服務 (Async JSON-RPC)。"""
from __future__ import annotations

import logging
import os
import uuid
import threading
import time
import json
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
import uvicorn
import jsonrpcserver
from jsonrpcserver import async_dispatch, method, Success, Error

from .config import get_settings
from .models import SummaryRequest, SummaryResponse
from .summarizer import craft_summary_response

# --- Agent Configuration ---
settings = get_settings()
METRICS_ENABLED = os.environ.get("METRICS_ENABLED", "true").lower() == "true"

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(threadName)s - %(filename)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger(__name__)

# --- In-Memory Task Storage ---
tasks: Dict[str, Dict[str, Any]] = {}
tasks_lock = threading.Lock()


# --- Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """初始化與釋放摘要代理需要的資源。"""
    logger.info("Summary Agent (Async) is starting up on port %s", settings.port)
    logger.info(f"Registered JSON-RPC methods: {jsonrpcserver.methods.global_methods}")
    yield
    logger.info("Summary Agent (Async) is shutting down")

app = FastAPI(
    title="Summary Agent (Async)",
    version="1.0.0",
    description="提供整合性旅遊建議的非同步 JSON-RPC 服務。",
    lifespan=lifespan,
)

if METRICS_ENABLED:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# --- Core Business Logic ---
def execute_summary_task(task_id: str, params: Dict[str, Any]):
    """
    Executes the summary generation in a background thread.
    Updates the task status in the shared 'tasks' dictionary.
    """
    logger.info(f"Starting summary task {task_id} in background thread.")
    try:
        with tasks_lock:
            tasks[task_id]["status"] = "IN_PROGRESS"

        # Simulate some work
        time.sleep(3)

        # Gracefully handle cases where weather or transport data might be missing
        if not params.get("weather_report"):
            logger.warning(f"Task {task_id}: Weather report is missing. Proceeding without it.")
        if not params.get("transport"):
            logger.warning(f"Task {task_id}: Transport plan is missing. Proceeding without it.")

        request = SummaryRequest(**params)
        logger.info(
            "Generating summary for task %s: destination=%s",
            task_id,
            request.user_requirement.destination,
        )
        response = craft_summary_response(
            request,
            provider=settings.llm_provider,
            model_id=settings.llm_model_id,
        )
        result = response.model_dump()

        with tasks_lock:
            tasks[task_id]["status"] = "DONE"
            tasks[task_id]["result"] = result
        logger.info(f"Summary task {task_id} completed successfully.")

    except Exception as e:
        logger.error(f"Error executing summary task {task_id}: {e}", exc_info=True)
        with tasks_lock:
            tasks[task_id]["status"] = "FAILED"
            tasks[task_id]["result"] = {"error": str(e)}


# --- JSON-RPC Method Implementations ---

@method(name="a2a.submit_task")
async def a2a_submit_task(
    task_id: str, # root-agent will pass its own task_id
    user_requirement: dict,
    weather_report: dict,
    transport: dict,
) -> Dict[str, str]:
    """
    Submits a new task for summary generation.
    Returns the same task_id immediately.
    """
    summary_task_id = task_id # Use the ID from the root agent
    logger.info(f"Received new summary task, using task_id: {summary_task_id}")

    with tasks_lock:
        tasks[summary_task_id] = {"status": "PENDING", "result": None}

    params = {
        "task_id": summary_task_id,
        "user_requirement": user_requirement,
        "weather_report": weather_report,
        "transport": transport,
    }
    background_thread = threading.Thread(
        target=execute_summary_task,
        args=(summary_task_id, params),
        name=f"SummaryTask-{summary_task_id}"
    )
    background_thread.start()

    return Success({"task_id": summary_task_id})


@method(name="a2a.get_task_status")
async def a2a_get_task_status(task_id: str) -> Dict[str, str]:
    """Checks the status of a previously submitted summary task."""
    logger.debug(f"Checking status for summary task_id: {task_id}")
    with tasks_lock:
        task = tasks.get(task_id)

    if not task:
        logger.warning(f"Task status requested for unknown summary task_id: {task_id}")
        return Error(code=404, message="Task not found", data={"task_id": task_id})

    return Success({"task_id": task_id, "status": task["status"]})


@method(name="a2a.get_task_result")
async def a2a_get_task_result(task_id: str) -> Dict[str, Any]:
    """Retrieves the result of a completed summary task."""
    logger.debug(f"Requesting result for summary task_id: {task_id}")
    with tasks_lock:
        task = tasks.get(task_id)

    if not task:
        logger.warning(f"Task result requested for unknown summary task_id: {task_id}")
        return Error(code=404, message="Task not found", data={"task_id": task_id})

    if task["status"] != "DONE":
        logger.info(f"Result for summary task {task_id} is not ready. Status: {task['status']}")
        return Error(
            code=202,
            message="Task result is not ready",
            data={"task_id": task_id, "status": task["status"]},
        )

    return Success({
        "task_id": task_id,
        "status": task["status"],
        "result": task["result"]
    })


# --- FastAPI Endpoints ---

@app.get("/")
def healthcheck() -> JSONResponse:
    """Provides a basic health check of the service."""
    logger.debug("Healthcheck requested")
    return JSONResponse(
        {
            "status": "OK",
            "agent": "Summary Agent (Async)",
            "port": settings.port,
        }
    )

@app.post("/jsonrpc")
async def jsonrpc_endpoint(request: Request):
    """The main JSON-RPC endpoint that dispatches to the registered methods."""
    req_str = await request.body()
    try:
        req_data = json.loads(req_str.decode())
        logger.info(f"Received JSON-RPC request: {req_data}")
    except json.JSONDecodeError:
        logger.warning(f"Received non-JSON request body: {req_str.decode()}")

    response_str = await async_dispatch(req_str.decode())
    if response_str:
        response_json = json.loads(response_str)
        return JSONResponse(content=response_json)
    return JSONResponse(content=None, status_code=204)

if __name__ == "__main__":
    uvicorn.run(app="main:app", host="0.0.0.0", port=settings.port, reload=True)
