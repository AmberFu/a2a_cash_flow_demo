from contextlib import asynccontextmanager
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
import uvicorn

from a2a.graph import get_graph_app
from a2a import tools as agent_tools
from langchain_core.messages import HumanMessage, ToolMessage
from logging_config import configure_logging
from models import (
    CallbackRequest,
    CreateTaskRequest,
    CreateTaskResponse,
    HITLAnswerRequest,
    UserRequirement,
)


# --- Application Setup ---
PORT = int(os.environ.get("PORT", 50000))
JSONRPC_ENABLED = os.environ.get("JSONRPC_ENABLED", "false").lower() == "true"
JSONRPC_BASE_PATH = os.environ.get("JSONRPC_BASE_PATH", "/jsonrpc")
JSONRPC_BIND = os.environ.get("JSONRPC_BIND", "0.0.0.0")
JSONRPC_PORT = int(os.environ.get("JSONRPC_PORT", PORT))
SUMMARY_URL = os.environ.get("SUMMARY_URL", "http://summary-agent-service")
REMOTE1_URL = os.environ.get("REMOTE1_URL", "http://remote-agent-1-service")
REMOTE2_URL = os.environ.get("REMOTE2_URL", "http://remote-agent-2-service")
ROOT_LLM_PROVIDER = os.environ.get("ROOT_LLM_PROVIDER", "bedrock")
ROOT_LLM_MODEL_ID = os.environ.get(
    "ROOT_LLM_MODEL_ID", "anthropic.claude-3-opus-20240229-v1:0"
)
REMOTE1_MODEL_PROVIDER = os.environ.get("REMOTE1_MODEL_PROVIDER", "bedrock")
REMOTE1_MODEL_ID = os.environ.get(
    "REMOTE1_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"
)
REMOTE2_MODEL_PROVIDER = os.environ.get("REMOTE2_MODEL_PROVIDER", "bedrock")
REMOTE2_MODEL_ID = os.environ.get(
    "REMOTE2_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
)
SUMMARY_MODEL_PROVIDER = os.environ.get("SUMMARY_MODEL_PROVIDER", "bedrock")
SUMMARY_MODEL_ID = os.environ.get(
    "SUMMARY_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
)
METRICS_ENABLED = os.environ.get("METRICS_ENABLED", "true").lower() == "true"

configure_logging()
logging.getLogger("langgraph").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application is starting up...")
    try:
        yield
    finally:
        logger.info("Application is shutting down...")


app = FastAPI(
    title="A2A Root Agent API",
    description="Manages and dispatches tasks for the A2A Cash Flow Demo",
    version="1.0.0",
    lifespan=lifespan,
)
if METRICS_ENABLED:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
else:
    logger.info("Prometheus instrumentation disabled via METRICS_ENABLED=false")

# Initialize the LangGraph Application
# This creates the compiled graph with its checkpointer
graph_app = get_graph_app()


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
            {
                "id": "task.dispatch.weather",
                "target": REMOTE1_URL,
                "llm": {"provider": REMOTE1_MODEL_PROVIDER, "id": REMOTE1_MODEL_ID},
            },
            {
                "id": "task.dispatch.train",
                "target": REMOTE2_URL,
                "llm": {"provider": REMOTE2_MODEL_PROVIDER, "id": REMOTE2_MODEL_ID},
            },
            {
                "id": "task.summarize",
                "target": SUMMARY_URL,
                "llm": {"provider": SUMMARY_MODEL_PROVIDER, "id": SUMMARY_MODEL_ID},
            },
        ],
        "model": {"provider": ROOT_LLM_PROVIDER, "id": ROOT_LLM_MODEL_ID},
        "maintainer": {"team": "A2A Demo", "email": "a2a@example.com"},
    }


def get_task_state_snapshot(task_id: str) -> Tuple[str, Dict[str, Any]]:
    """Fetch the latest state from LangGraph and return status plus payload."""
    config = {"configurable": {"thread_id": task_id}}
    state = graph_app.get_state(config)
    if not state:
        raise KeyError(task_id)

    if isinstance(state, dict):
        values: Dict[str, Any] = state
    elif hasattr(state, "values"):
        values_attr = getattr(state, "values")
        if callable(values_attr):
            values = values_attr()
        else:
            values = values_attr
    else:
        values = {"raw": state}

    status = values.get("status", "unknown")
    return status, values


def build_expected_step_sequence(workflow_mode: str) -> List[Dict[str, str]]:
    if workflow_mode == "eventbridge":
        return [
            {"order": 1, "description": "Root Agent receives task creation request"},
            {"order": 2, "description": "Root Agent start_node dispatches task to Remote Agent A via EventBridge"},
            {"order": 3, "description": "Remote Agent A processes the EventBridge payload and sends result through SQS callback"},
            {"order": 4, "description": "Root Agent resumes graph and draft_response_node dispatches to Remote Agent B via EventBridge"},
            {"order": 5, "description": "Remote Agent B processes the EventBridge payload and sends result through SQS callback"},
            {"order": 6, "description": "Root Agent finishes workflow and marks task as completed"},
        ]

    return [
        {"order": 1, "description": "Root Agent receives task creation request"},
        {"order": 2, "description": "Root Agent start_node calls Weather Remote Agent via HTTP"},
        {"order": 3, "description": "Root Agent draft_response_node calls Transport Remote Agent via HTTP"},
        {"order": 4, "description": "Root Agent finish_node calls Summary Agent via HTTP and returns result"},
    ]


def log_expected_steps(task_id: str, workflow_mode: str) -> None:
    expected_steps = build_expected_step_sequence(workflow_mode)
    serialized_steps = " -> ".join(
        f"{step['order']}. {step['description']}" for step in expected_steps
    )
    logger.info(
        "[Task %s][Expected Flow] %s",
        task_id,
        serialized_steps,
        extra={
            "task_id": task_id,
            "workflow_mode": workflow_mode,
            "expected_steps": expected_steps,
        },
    )


async def start_graph_run(
    loan_case_id: str, user_requirement: Optional[UserRequirement]
) -> CreateTaskResponse:
    task_id = str(uuid.uuid4())
    workflow_mode = "eventbridge" if agent_tools.is_eventbridge_mode() else "direct-http"
    logger.info(
        "[Task %s][Step 1] Received task creation request for loan case %s (mode=%s)",
        task_id,
        loan_case_id,
        workflow_mode,
        extra={
            "task_id": task_id,
            "loan_case_id": loan_case_id,
            "workflow_mode": workflow_mode,
        },
    )
    log_expected_steps(task_id, workflow_mode)
    config = {"configurable": {"thread_id": task_id}}

    requirement_payload: Dict[str, Any] = {}
    if user_requirement is not None:
        requirement_payload = user_requirement.model_dump()

    travel_summary = (
        f"Start processing for loan case ID: {loan_case_id}."
        if not requirement_payload
        else (
            "Start processing for loan case ID: "
            f"{loan_case_id} with travel requirement: {requirement_payload}."
        )
    )
    initial_state = {
        "task_id": task_id,
        "loan_case_id": loan_case_id,
        "status": "new",
        "messages": [HumanMessage(content=travel_summary)],
        "needs_info": [],
        "human_answer": "",
        "user_requirement": requirement_payload,
        "weather_report": {},
        "transport": {},
        "summary": {},
    }
    result_state: Optional[Any] = None
    try:
        logger.info(
            "[Task %s][Graph Invoke][Enter] Starting graph_app.invoke (mode=%s)",
            task_id,
            workflow_mode,
            extra={"task_id": task_id, "workflow_mode": workflow_mode},
        )
        result_state = graph_app.invoke(initial_state, config=config)
        logger.info(
            "[Task %s][Graph Invoke][Exit] graph_app.invoke returned",
            task_id,
            extra={"task_id": task_id, "workflow_mode": workflow_mode},
        )
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.error(
            "Failed to start graph for task %s. Error: %s",
            task_id,
            exc,
            extra={"task_id": task_id, "workflow_mode": workflow_mode},
        )
        if "events" in str(exc) or "PutEvents" in str(exc):
            raise HTTPException(
                status_code=503,
                detail=f"Workflow failed to start due to external AWS service error (EventBridge/DynamoDB): {exc}",
            ) from exc
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {exc}") from exc

    summary_payload: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    if not agent_tools.is_eventbridge_mode():
        values: Dict[str, Any] = {}
        if result_state is not None:
            if isinstance(result_state, dict):
                values = result_state
            elif hasattr(result_state, "values"):
                values_attr = getattr(result_state, "values")
                if callable(values_attr):
                    values = values_attr()
                else:
                    values = values_attr
        summary_payload = values.get("summary")
        status = values.get("status")
        if not values:
            logger.warning(
                "Task %s returned empty state in local mode; summary may be unavailable",
                task_id,
                extra={"task_id": task_id, "workflow_mode": workflow_mode},
            )

    return CreateTaskResponse(
        task_id=task_id,
        message="Task created and workflow initiated.",
        status=status,
        summary=summary_payload,
    )


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
        requirement_payload = payload.get("user_requirement") or params.get("user_requirement")
        requirement_model: Optional[UserRequirement] = None
        if requirement_payload:
            requirement_model = UserRequirement(**requirement_payload)
        response = await start_graph_run(loan_case_id, requirement_model)
        return {
            "task_id": response.task_id,
            "message": response.message,
            "status": response.status,
            "summary": response.summary,
            "channels": ["eventbridge", "jsonrpc"],
        }
    raise NotImplementedError(f"Method {method} not found")


# --- API Endpoints ---
@app.get("/")
def read_root():
    return {"message": "Root Agent is running."}


@app.post("/tasks", response_model=CreateTaskResponse, status_code=202)
async def create_task(request: CreateTaskRequest):
    response = await start_graph_run(request.loan_case_id, request.user_requirement)
    return response


@app.post("/callbacks", status_code=200)
async def handle_callback(request: CallbackRequest):
    """Endpoint to receive results from remote agents via SQS."""
    task_id = request.task_id
    logger.info(
        "[Task %s][EventBridge Callback][Enter] Received callback from %s with status '%s'",
        task_id,
        request.source,
        request.status,
        extra={
            "task_id": task_id,
            "source": request.source,
            "status": request.status,
            "needs_info": request.needs_info,
        },
    )

    config = {"configurable": {"thread_id": task_id}}

    try:
        current_state = graph_app.get_state(config)
        if not current_state:
            raise HTTPException(status_code=404, detail=f"Task with ID '{task_id}' not found.")

        state_update: Dict[str, Any] = {"status": request.status}
        if request.needs_info:
            state_update["needs_info"] = request.needs_info
            state_update["status"] = "awaiting_human_input"

        logger.info(
            "[Task %s][EventBridge Callback] Applying state update: %s",
            task_id,
            state_update,
            extra={"task_id": task_id, "state_update": state_update},
        )

        graph_app.update_state(config, state_update)

        tool_message = ToolMessage(
            content=f"Received result from {request.source}: {request.result}",
            name=request.source,
        )

        logger.info(
            "[Task %s][EventBridge Callback] Resuming graph with ToolMessage from %s",
            task_id,
            request.source,
            extra={"task_id": task_id, "source": request.source},
        )

        graph_app.invoke({"messages": [tool_message]}, config)

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.error(
            "Error processing callback for task %s. Error: %s",
            task_id,
            exc,
            extra={"task_id": task_id, "source": request.source},
        )
        raise HTTPException(status_code=500, detail=f"Failed to process callback: {exc}") from exc

    logger.info(
        "[Task %s][EventBridge Callback][Exit] Completed callback processing for %s",
        task_id,
        request.source,
        extra={"task_id": task_id, "source": request.source},
    )

    return {"message": f"Callback for task {task_id} processed."}


@app.post("/tasks/{task_id}/answers", status_code=200)
async def submit_hitl_answer(task_id: str, request: HITLAnswerRequest):
    """Endpoint for a human to submit required information, resuming the graph."""
    truncated_answer = (request.answer[:50] + "...") if len(request.answer) > 50 else request.answer
    logger.info(
        "[Task %s][HITL][Enter] Received human answer snippet='%s'",
        task_id,
        truncated_answer,
        extra={"task_id": task_id, "answer_preview": truncated_answer},
    )
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
        logger.info(
            "[Task %s][HITL] Resuming graph after human input",
            task_id,
            extra={"task_id": task_id},
        )
        graph_app.invoke({"messages": [human_message]}, config)

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.error(
            "Error processing HITL answer for task %s. Error: %s",
            task_id,
            exc,
            extra={"task_id": task_id},
        )
        raise HTTPException(status_code=500, detail=f"Failed to process HITL answer: {exc}") from exc

    logger.info(
        "[Task %s][HITL][Exit] Completed processing human answer",
        task_id,
        extra={"task_id": task_id},
    )

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
