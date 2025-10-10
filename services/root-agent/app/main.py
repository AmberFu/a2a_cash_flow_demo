from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
import os

# a2a_cash_flow_demo/services/root-agent/app/main.py

import uuid
import logging
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

from a2a.graph import get_graph_app
from langchain_core.messages import HumanMessage, ToolMessage

# --- Application Setup ---
app = FastAPI(
    title="A2A Root Agent API",
    description="Manages and dispatches tasks for the A2A Cash Flow Demo",
    version="1.0.0",
)

# Initialize the LangGraph Application
# This creates the compiled graph with its checkpointer
graph_app = get_graph_app()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

# --- API Endpoints ---

@app.get("/")
def read_root():
    return {"message": "Root Agent is running."}

@app.post("/tasks", response_model=CreateTaskResponse, status_code=202)
async def create_task(request: CreateTaskRequest):
    """
    Creates a new task and starts the workflow.
    """
    task_id = str(uuid.uuid4())
    logging.info(f"Received request to create task for loan case: {request.loan_case_id}. Assigned Task ID: {task_id}")

    # The config dictionary links a run to a persistent thread_id
    config = {"configurable": {"thread_id": task_id}}

    # Initial state for the graph
    initial_state = {
        "task_id": task_id,
        "loan_case_id": request.loan_case_id,
        "status": "new",
        "messages": [HumanMessage(content=f"Start processing for loan case ID: {request.loan_case_id}")],
    }

    try:
        # `invoke` will run the graph until the first interruption
        graph_app.invoke(initial_state, config)
        
        # We can also update the state directly if needed, for instance, to store the initial payload
        # graph_app.update_state(config, initial_state)
        # graph_app.invoke(None, config) # Then invoke with no input to trigger the entrypoint
        
    except Exception as e:
        logging.error(f"Failed to start graph for task {task_id}. Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {e}")

    return {"task_id": task_id, "message": "Task created and workflow initiated."}

@app.post("/callbacks", status_code=200)
async def handle_callback(request: CallbackRequest):
    """
    Endpoint to receive results from remote agents (via an SQS consumer).
    This resumes the graph execution.
    """
    task_id = request.task_id
    logging.info(f"Received callback for task {task_id} from {request.source} with status '{request.status}'")

    config = {"configurable": {"thread_id": task_id}}

    try:
        # Check if the task exists by trying to get its state
        current_state = graph_app.get_state(config)
        if not current_state:
            raise HTTPException(status_code=404, detail=f"Task with ID '{task_id}' not found.")
        
        # Prepare the state update
        state_update = {
            "status": request.status,
        }
        if request.needs_info:
            state_update["needs_info"] = request.needs_info
            state_update["status"] = "awaiting_human_input" # Override status if HITL is needed
        
        # Update the state with the new status from the callback
        graph_app.update_state(config, state_update)

        # Create a message representing the callback result and invoke the graph
        # This will make the graph resume from its interrupted state
        tool_message = ToolMessage(
            content=f"Received result from {request.source}: {request.result}",
            name=request.source
        )
        
        # Resume the graph. The router will direct it to the next step based on the new status.
        graph_app.invoke({"messages": [tool_message]}, config)

    except Exception as e:
        logging.error(f"Error processing callback for task {task_id}. Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process callback: {e}")

    return {"message": f"Callback for task {task_id} processed."}


@app.post("/tasks/{task_id}/answers", status_code=200)
async def submit_hitl_answer(task_id: str, request: HITLAnswerRequest):
    """
    Endpoint for a human to submit required information, resuming the graph.
    """
    logging.info(f"Received HITL answer for task {task_id}.")
    config = {"configurable": {"thread_id": task_id}}
    
    try:
        current_state = graph_app.get_state(config)
        if not current_state:
            raise HTTPException(status_code=404, detail=f"Task with ID '{task_id}' not found.")
        
        if current_state.values.get("status") != "needs_human_input":
             raise HTTPException(status_code=400, detail=f"Task '{task_id}' is not awaiting human input.")

        # Update the state with the human's answer and change status to resume
        # The specific next status depends on your workflow logic. Let's assume after HITL,
        # it might need to go back to Agent A or B. We'll set a generic "resuming" status
        # and let the router decide.
        graph_app.update_state(
            config,
            {
                "human_answer": request.answer,
                "status": "resuming_after_hitl" # A new status for the router to catch
            }
        )

        # Resume the graph with the human's answer as input
        human_message = HumanMessage(content=f"Human provided answer: {request.answer}")
        graph_app.invoke({"messages": [human_message]}, config)
        
    except Exception as e:
        logging.error(f"Error processing HITL answer for task {task_id}. Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process HITL answer: {e}")

    return {"message": f"HITL answer for task {task_id} submitted and workflow resumed."}


# pip install prometheus-fastapi-instrumentator
from prometheus_fastapi_instrumentator import Instrumentator

@app.on_event("startup")
async def _startup():
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")


if __name__ == "__main__":
    # 這裡就用你指定的寫法；注意：reload 在容器內要搭配掛載原始碼才看得到變更
    uvicorn.run(app="main:app", host="0.0.0.0", port=PORT, reload=True)
