"""天氣規劃 Remote Agent 服務 (Async JSON-RPC)。"""
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

from llm import synthesize_weather_summary
from models import WeatherReportRequest, WeatherReportResponse
from weather_generator import generate_city_weather_variables

# --- Agent Configuration ---
PORT = int(os.environ.get("PORT", 50001))
METRICS_ENABLED = os.environ.get("METRICS_ENABLED", "true").lower() == "true"

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(threadName)s - %(filename)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger(__name__)

# --- In-Memory Task Storage ---
# Note: This is a simple in-memory store. For production, use Redis, a database, or another persistent store.
tasks: Dict[str, Dict[str, Any]] = {}
tasks_lock = threading.Lock()


# --- Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """初始化與釋放 Remote Agent 需要的資源。"""
    logger.info("Weather Remote Agent (Async) is starting up on port %s", PORT)
    logger.info(f"Registered JSON-RPC methods: {jsonrpcserver.methods.global_methods}")
    yield
    logger.info("Weather Remote Agent (Async) is shutting down")

app = FastAPI(
    title="Weather Remote Agent (Async)",
    version="1.0.0",
    description="提供天氣摘要的非同步 JSON-RPC 服務。",
    lifespan=lifespan,
)

if METRICS_ENABLED:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# --- Core Business Logic ---
def execute_weather_report_task(task_id: str, params: Dict[str, Any]):
    """
    Executes the weather report generation in a background thread.
    Updates the task status in the shared 'tasks' dictionary.
    """
    logger.info(f"Starting task {task_id} in background thread.")
    try:
        # 1. Update status to IN_PROGRESS
        with tasks_lock:
            tasks[task_id]["status"] = "IN_PROGRESS"

        # Simulate some work
        time.sleep(5)

        # 2. Execute the core logic
        # Adapt params from user_requirement to WeatherReportRequest
        request = WeatherReportRequest(
            city=params.get("destination", "台北"),
            date=params.get("travel_date", ""),
            time_range="全天" # Simplified for this example
        )
        logger.info(
            "Generating weather report for task %s: city=%s, date=%s",
            task_id,
            request.city,
            request.date.isoformat(),
        )
        variables = generate_city_weather_variables(request.city)
        summary = synthesize_weather_summary(request, variables)
        result = WeatherReportResponse(
            city=request.city,
            date=request.date,
            time_range=request.time_range,
            variables=variables,
            summary=summary,
        ).model_dump()

        # 3. Update status to DONE with the result
        with tasks_lock:
            tasks[task_id]["status"] = "DONE"
            tasks[task_id]["result"] = result
        logger.info(f"Task {task_id} completed successfully.")

    except Exception as e:
        logger.error(f"Error executing task {task_id}: {e}", exc_info=True)
        with tasks_lock:
            tasks[task_id]["status"] = "FAILED"
            tasks[task_id]["result"] = {"error": str(e)}


# --- JSON-RPC Method Implementations ---

@method(name="a2a.submit_task")
async def a2a_submit_task(user_requirement: Dict[str, Any]) -> Dict[str, str]:
    """
    Submits a new task for weather report generation.
    Returns a task_id immediately.
    """
    task_id = str(uuid.uuid4())
    logger.info(f"Received new task, assigning task_id: {task_id}")

    with tasks_lock:
        tasks[task_id] = {"status": "PENDING", "result": None}

    # Start the actual work in a background thread to not block the response
    background_thread = threading.Thread(
        target=execute_weather_report_task,
        args=(task_id, user_requirement),
        name=f"Task-{task_id}"
    )
    background_thread.start()

    return Success({"task_id": task_id})


@method(name="a2a.get_task_status")
async def a2a_get_task_status(task_id: str) -> Dict[str, str]:
    """Checks the status of a previously submitted task."""
    logger.debug(f"Checking status for task_id: {task_id}")
    with tasks_lock:
        task = tasks.get(task_id)

    if not task:
        logger.warning(f"Task status requested for unknown task_id: {task_id}")
        return Error(code=404, message="Task not found", data={"task_id": task_id})

    return Success({"task_id": task_id, "status": task["status"]})


@method(name="a2a.get_task_result")
async def a2a_get_task_result(task_id: str) -> Dict[str, Any]:
    """Retrieves the result of a completed task."""
    logger.debug(f"Requesting result for task_id: {task_id}")
    with tasks_lock:
        task = tasks.get(task_id)

    if not task:
        logger.warning(f"Task result requested for unknown task_id: {task_id}")
        return Error(code=404, message="Task not found", data={"task_id": task_id})

    if task["status"] != "DONE":
        logger.info(f"Result for task {task_id} is not ready yet. Status: {task['status']}")
        return Error(
            code=202, # Accepted but not completed
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
            "agent": "Weather Remote Agent (Async)",
            "port": PORT,
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
    # Note: Uvicorn is a single-process, multi-threaded server.
    # The in-memory 'tasks' dictionary is shared across all requests handled by this process.
    uvicorn.run(app="main:app", host="0.0.0.0", port=PORT, reload=True)
