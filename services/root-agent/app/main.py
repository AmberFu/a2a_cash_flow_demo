# services/root-agent/app/main.py
"""Root Agent (Async JSON-RPC): Manages and dispatches tasks."""
from __future__ import annotations

import logging
import os
import uuid
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
import jsonrpcserver
from jsonrpcserver import async_dispatch, method, Success, Error

from a2a.graph import get_graph_app, AgentState
from a2a import tools as agent_tools

# --- Application Setup ---
PORT = int(os.environ.get("PORT", 50000))
METRICS_ENABLED = os.environ.get("METRICS_ENABLED", "true").lower() == "true"

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger(__name__)

# --- FastAPI Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Root Agent (Async) is starting up...")
    logger.info(f"Registered JSON-RPC methods: {jsonrpcserver.methods.global_methods}")
    yield
    logger.info("Root Agent (Async) is shutting down...")

app = FastAPI(
    title="A2A Root Agent (Async)",
    description="Manages and orchestrates tasks via async JSON-RPC.",
    version="1.0.0",
    lifespan=lifespan,
)

if METRICS_ENABLED:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Initialize the LangGraph Application
graph_app = get_graph_app()


# --- JSON-RPC Method Implementations ---

@method(name="a2a.submit_task")
async def a2a_submit_task(loan_case_id: str, user_requirement: Dict[str, Any]) -> Dict[str, Any]:
    """
    Starts the asynchronous agent workflow.
    """
    task_id = str(uuid.uuid4())
    logger.info(f"Received task for loan_case_id={loan_case_id}. Assigned root_task_id={task_id}")

    config = {"configurable": {"thread_id": task_id}}
    initial_state = AgentState(
        task_id=task_id,
        loan_case_id=loan_case_id,
        user_requirement=user_requirement,
        status="new",
        messages=[],
        remote1_task_id="",
        remote2_task_id="",
        summary_task_id="",
        remote1_result={},
        remote2_result={},
        summary_result={},
    )

    # Run the graph in the background without blocking the response to the user.
    # asyncio.create_task is used to schedule the coroutine to run on the event loop.
    asyncio.create_task(graph_app.ainvoke(initial_state, config))

    return Success({"task_id": task_id, "message": "Workflow started."})

@method(name="a2a.get_task_status")
async def a2a_get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Checks the status of the entire workflow.
    """
    config = {"configurable": {"thread_id": task_id}}
    try:
        state = graph_app.get_state(config)
        if not state:
            return Error(code=404, message="Task not found", data={"task_id": task_id})

        # The state object from get_state is a StateSnapshot, we need its values
        status = state.values.get("status", "UNKNOWN")
        return Success({"task_id": task_id, "status": status})

    except Exception as e:
        logger.error(f"Error getting status for task {task_id}: {e}", exc_info=True)
        return Error(code=500, message="Internal server error")

@method(name="a2a.get_task_result")
async def a2a_get_task_result(task_id: str) -> Dict[str, Any]:
    """
    Retrieves the final result from the summary agent once the workflow is complete.
    """
    config = {"configurable": {"thread_id": task_id}}
    try:
        state_snapshot = graph_app.get_state(config)
        if not state_snapshot:
            return Error(code=404, message="Task not found", data={"task_id": task_id})

        state = state_snapshot.values
        if state.get("status") != "COMPLETED":
            return Error(
                code=202,
                message="Task result is not ready yet.",
                data={"task_id": task_id, "status": state.get("status")},
            )

        summary_task_id = state.get("summary_task_id")
        if not summary_task_id:
            return Error(code=500, message="Summary task ID not found in completed workflow.")

        # The root task ID is the same as the summary task ID in our new graph design
        final_result = agent_tools.get_task_result_from_remote_agent(
            agent_tools.SUMMARY_URL, summary_task_id
        )

        return Success({
            "task_id": task_id,
            "status": "COMPLETED",
            "result": final_result
        })

    except Exception as e:
        logger.error(f"Error getting result for task {task_id}: {e}", exc_info=True)
        return Error(code=500, message=f"Internal server error: {e}")


# --- FastAPI Endpoints ---
@app.get("/")
def read_root():
    return {"message": "Root Agent (Async) is running."}

@app.post("/jsonrpc")
async def jsonrpc_endpoint(request: Request):
    """
    The main JSON-RPC endpoint that dispatches to the registered methods.
    """
    req_str = await request.body()
    try:
        req_data = json.loads(req_str.decode())
        logger.info(f"Received JSON-RPC request: {req_data}")
    except json.JSONDecodeError:
        logger.warning(f"Received non-JSON request body: {req_str.decode()}")

    # logger.info(f"\n>>> globals(): {globals()}\n")
    response_str = await async_dispatch(req_str.decode())
    logger.info(f"response_str: {response_str}")
    if response_str:
        response_json = json.loads(response_str)
        return JSONResponse(content=response_json)
    return JSONResponse(content=None, status_code=204)

if __name__ == "__main__":
    uvicorn.run(app="main:app", host="0.0.0.0", port=PORT, reload=True)
