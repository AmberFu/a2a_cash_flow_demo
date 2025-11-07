"""交通規劃 Remote Agent 服務 (Async JSON-RPC)。"""
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

from models import TransportPlanRequest, TransportPlanResponse
from transport_service import generate_transport_plans

# --- Agent Configuration ---
PORT = int(os.environ.get("PORT", 50002))
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
    """初始化與釋放 Remote Agent 需要的資源。"""
    logger.info("--- SERVICE IDENTIFICATION ---")
    logger.info("SERVICE NAME: Transport Remote Agent (remote-agent-2)")
    logger.info(f"LISTENING ON PORT: {PORT}")
    logger.info("-----------------------------")
    logger.info("Transport Remote Agent (Async) is starting up on port %s", PORT)
    logger.info(f"Registered JSON-RPC methods: {jsonrpcserver.methods.global_methods}")
    yield
    logger.info("Transport Remote Agent (Async) is shutting down")

app = FastAPI(
    title="Transport Remote Agent (Async)",
    version="1.0.0",
    description="提供交通規劃的非同步 JSON-RPC 服務。",
    lifespan=lifespan,
)

if METRICS_ENABLED:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# --- Core Business Logic ---
def execute_transport_plan_task(task_id: str, params: Dict[str, Any]):
    """
    Executes the transport plan generation in a background thread.
    Updates the task status in the shared 'tasks' dictionary.
    """
    logger.info(f"Starting task {task_id} in background thread.")
    try:
        # 1. Update status to IN_PROGRESS
        with tasks_lock:
            tasks[task_id]["status"] = "IN_PROGRESS"

        # Simulate some work
        time.sleep(8) # Simulate a longer task

        # 2. Execute the core logic
        request = TransportPlanRequest(
            destination=params.get("destination", "台南"),
            arrival_time=params.get("desired_arrival_time", "15:30"),
            date=params.get("travel_date", ""),
            results=3
        )
        logger.info(
            "Generating transport plans for task %s: destination=%s, arrival_time=%s",
            task_id,
            request.destination,
            request.arrival_time,
        )
        plans = generate_transport_plans(request)
        result = TransportPlanResponse(
            destination=request.destination,
            requested_arrival_time=request.arrival_time,
            date=request.date,
            plans=plans,
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
    Submits a new task for transport plan generation.
    Returns a task_id immediately.
    """
    task_id = str(uuid.uuid4())
    logger.info(f"Received new task, assigning task_id: {task_id}")

    with tasks_lock:
        tasks[task_id] = {"status": "PENDING", "result": None}

    background_thread = threading.Thread(
        target=execute_transport_plan_task,
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
            "agent": "Transport Remote Agent (Async)",
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
    uvicorn.run(app="main:app", host="0.0.0.0", port=PORT, reload=True)
