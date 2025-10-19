from contextlib import asynccontextmanager
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
import uvicorn

from a2a.graph import get_graph_app
from langchain_core.messages import HumanMessage, ToolMessage


# --- Application Setup ---
PORT = int(os.environ.get("PORT", 50000))
JSONRPC_ENABLED = os.environ.get("JSONRPC_ENABLED", "false").lower() == "true"
JSONRPC_BASE_PATH = os.environ.get("JSONRPC_BASE_PATH", "/jsonrpc")
JSONRPC_BIND = os.environ.get("JSONRPC_BIND", "0.0.0.0")
JSONRPC_PORT = int(os.environ.get("JSONRPC_PORT", PORT))
SUMMARY_URL = os.environ.get("SUMMARY_URL", "http://summary-agent-service")
REMOTE1_URL = os.environ.get("REMOTE1_URL", "http://remote-agent-1-service")
REMOTE2_URL = os.environ.get("REMOTE2_URL", "http://remote-agent-2-service")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
)
logging.getLogger("langgraph").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)


@asynccontextmanager
def lifespan(app: FastAPI):
    print("Application is starting up...")
    yield
    print("Application is shutting down...")


app = FastAPI(
    title="A2A Root Agent API",
    description="Manages and dispatches tasks for the A2A Cash Flow Demo",
    version="1.0.0",
    lifespan=lifespan,
)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Initialize the LangGraph Application
# This creates the compiled graph with its checkpointer
graph_app = get_graph_app()


# --- API Models ---
class CreateTaskRequest(BaseModel):
    loan_case_id: str = Field(..., description="The business identifier for the loan case.")


class CreateTaskResponse(BaseModel):
    task_id: str
    message: str


class CallbackRequest(BaseModel):
    task_id: str
    source: str = Field(..., description="e.g., 'remote-agent-a', 'remote-agent-b'")
    status: str = Field(..., description="The new status to set for the task.")
    result: Dict[str, Any] = Field(description="The output from the remote agent.")
    needs_info: Optional[List[str]] = Field(None, description="Questions for HITL, if any.")


class HITLAnswerRequest(BaseModel):
    answer: str = Field(..., description="The human-provided answer or information.")


# --- Helper functions ---
def build_agent_card() -> Dict[str, Any]:
    """Return Agent Card metadata for JSON-RPC describe_agent."""
    return {
        "agent_id": "root-agent",
        "name": "Root Agent",
        "protocols": [
            {"type": "json-rpc", "version": "2.0", "transport": "https", "endpoint": JSONRPC_BASE_PATH},
            {"type": "eventbridge", "transport": "aws", "callback_queue": "sqs"},
        ],
        "capabilities": [
            {"id": "task.dispatch.weather", "target": REMOTE1_URL},
            {"id": "task.dispatch.train", "target": REMOTE2_URL},
            {"id": "task.summarize", "target": SUMMARY_URL},
        ],
        "maintainer": {"team": "A2A Demo", "email": "a2a@example.com"},
    }


def get_task_state_snapshot(task_id: str) -> Tuple[str, Dict[str, Any]]:
    """Fetch the latest state from LangGraph and return status plus payload."""
    config = {"configurable": {"thread_id": task_id}}
    state = graph_app.get_state(config)
    if not state:
        raise KeyError(task_id)

    if hasattr(state, "values"):
        values: Dict[str, Any] = getattr(state, "values")
    elif isinstance(state, dict):
        values = state
    else:
        values = {"raw": state}

    status = values.get("status", "unknown")
    return status, values


async def start_graph_run(loan_case_id: str) -> CreateTaskResponse:
    task_id = str(uuid.uuid4())
    logger.info(
        "Received request to create task for loan case: %s. Assigned Task ID: %s",
        loan_case_id,
        task_id,
    )
    config = {"configurable": {"thread_id": task_id}}
    initial_state = {
        "task_id": task_id,
        "loan_case_id": loan_case_id,
        "status": "new",
        "messages": [HumanMessage(content=f"Start processing for loan case ID: {loan_case_id}")],
    }
    try:
        logger.info(">>> Start graph_app.invoke via start_graph_run...")
        graph_app.invoke(initial_state, config=config)
        logger.info(">>> Graph finished")
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.error("Failed to start graph for task %s. Error: %s", task_id, exc)
        if "events" in str(exc) or "PutEvents" in str(exc):
            raise HTTPException(
                status_code=503,
                detail=f"Workflow failed to start due to external AWS service error (EventBridge/DynamoDB): {exc}",
            ) from exc
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {exc}") from exc

    return CreateTaskResponse(task_id=task_id, message="Task created and workflow initiated.")


def jsonrpc_error(code: int, message: str, request_id: Any) -> JSONResponse:
    status_code = 400 if code in {-32600, -32601, -32602, -32700} else 500
    return JSONResponse(
        status_code=status_code,
        content={"jsonrpc": "2.0", "error": {"code": code, "message": message}, "id": request_id},
    )


async def handle_jsonrpc_call(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if method == "a2a.describe_agent":
        return build_agent_card()
    if method == "a2a.get_task_status":
        task_id = params.get("task_id")
        if not task_id:
            raise ValueError("task_id is required")
        try:
            status, values = get_task_state_snapshot(task_id)
        except KeyError:
            return {"task_id": task_id, "status": "not_found"}
        return {"task_id": task_id, "status": status, "state": values}
    if method == "a2a.submit_task":
        payload = params.get("payload", {})
        loan_case_id = payload.get("loan_case_id") or params.get("loan_case_id")
        if not loan_case_id:
            raise ValueError("loan_case_id is required")
        response = await start_graph_run(loan_case_id)
        return {
            "task_id": response.task_id,
            "message": response.message,
            "channels": ["eventbridge", "jsonrpc"],
        }
    raise NotImplementedError(f"Method {method} not found")


# --- API Endpoints ---
@app.get("/")
def read_root():
    return {"message": "Root Agent is running."}


@app.post("/tasks", response_model=CreateTaskResponse, status_code=202)
async def create_task(request: CreateTaskRequest):
    response = await start_graph_run(request.loan_case_id)
    return response


@app.post("/callbacks", status_code=200)
async def handle_callback(request: CallbackRequest):
    """Endpoint to receive results from remote agents via SQS."""
    task_id = request.task_id
    logger.info("Received callback for task %s from %s with status '%s'", task_id, request.source, request.status)

    config = {"configurable": {"thread_id": task_id}}

    try:
        current_state = graph_app.get_state(config)
        if not current_state:
            raise HTTPException(status_code=404, detail=f"Task with ID '{task_id}' not found.")

        state_update: Dict[str, Any] = {"status": request.status}
        if request.needs_info:
            state_update["needs_info"] = request.needs_info
            state_update["status"] = "awaiting_human_input"

        graph_app.update_state(config, state_update)

        tool_message = ToolMessage(
            content=f"Received result from {request.source}: {request.result}",
            name=request.source,
        )

        graph_app.invoke({"messages": [tool_message]}, config)

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.error("Error processing callback for task %s. Error: %s", task_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to process callback: {exc}") from exc

    return {"message": f"Callback for task {task_id} processed."}


@app.post("/tasks/{task_id}/answers", status_code=200)
async def submit_hitl_answer(task_id: str, request: HITLAnswerRequest):
    """Endpoint for a human to submit required information, resuming the graph."""
    logger.info("Received HITL answer for task %s.", task_id)
    config = {"configurable": {"thread_id": task_id}}

    try:
        current_state = graph_app.get_state(config)
        if not current_state:
            raise HTTPException(status_code=404, detail=f"Task with ID '{task_id}' not found.")

        if getattr(current_state, "values", {}).get("status") != "needs_human_input":
            raise HTTPException(status_code=400, detail=f"Task '{task_id}' is not awaiting human input.")

        graph_app.update_state(
            config,
            {
                "human_answer": request.answer,
                "status": "resuming_after_hitl",
            },
        )

        human_message = HumanMessage(content=f"Human provided answer: {request.answer}")
        graph_app.invoke({"messages": [human_message]}, config)

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.error("Error processing HITL answer for task %s. Error: %s", task_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to process HITL answer: {exc}") from exc

    return {"message": f"HITL answer for task {task_id} submitted and workflow resumed."}


@app.post(JSONRPC_BASE_PATH)
async def jsonrpc_endpoint(raw_request: Request):
    """Handle JSON-RPC 2.0 calls for synchronous integrations."""
    if not JSONRPC_ENABLED:
        # 仍回應符合 JSON-RPC 2.0 規範的錯誤，以利客戶端診斷。
        return jsonrpc_error(
            -32000,
            "JSON-RPC channel is currently disabled on the Root Agent.",
            None,
        )

    try:
        payload = await raw_request.json()
    except Exception:  # noqa: BLE001 - FastAPI already logs details
        return jsonrpc_error(-32700, "Parse error", None)

    if isinstance(payload, list):
        return jsonrpc_error(-32600, "Batch requests are not supported", None)

    method = payload.get("method")
    request_id = payload.get("id")
    params = payload.get("params") or {}
    if not method:
        return jsonrpc_error(-32600, "method is required", request_id)

    try:
        result = await handle_jsonrpc_call(method, params)
    except ValueError as exc:
        return jsonrpc_error(-32602, str(exc), request_id)
    except NotImplementedError as exc:
        return jsonrpc_error(-32601, str(exc), request_id)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": exc.detail},
                "id": request_id,
            },
        )
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.exception("Unhandled JSON-RPC error: %s", exc)
        return jsonrpc_error(-32603, "Internal error", request_id)

    return {"jsonrpc": "2.0", "result": result, "id": request_id}


if __name__ == "__main__":
    # 注意：reload 在容器內要搭配掛載原始碼才看得到變更
    uvicorn.run(app="main:app", host=JSONRPC_BIND, port=JSONRPC_PORT)
