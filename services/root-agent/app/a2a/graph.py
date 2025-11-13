# a2a_cash_flow_demo/services/root-agent/app/a2a/graph.py

import os
import logging
import operator
import asyncio
from typing import TypedDict, Annotated, List, Dict, Any

from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, AIMessage
from langgraph_checkpoint_dynamodb import DynamoDBSaver, DynamoDBConfig, DynamoDBTableConfig

from . import tools

# --- Configuration ---
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
DDB_TABLE_NAME = os.environ.get("DDB_A2A_TASKS_TABLE_NAME", "ds_demo_a2a_tasks")

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)
logger = logging.getLogger(__name__)


# --- State Definition ---
class AgentState(TypedDict):
    # IDs
    task_id: str  # The root task ID for the entire process
    loan_case_id: str # Represents the original request identifier
    user_requirement: Dict[str, Any]

    # Status and messages for the overall process
    status: str
    messages: Annotated[List[BaseMessage], operator.add]

    # Sub-task tracking
    remote1_task_id: str
    remote2_task_id: str
    summary_task_id: str

    # Results from sub-tasks
    remote1_result: Dict[str, Any]
    remote2_result: Dict[str, Any]
    summary_result: Dict[str, Any]


# --- Graph Nodes ---

def submit_tasks_node(state: AgentState) -> dict:
    """
    Submits initial tasks to remote agents 1 (weather) and 2 (transport).
    """
    task_id = state['task_id']
    user_requirement = state['user_requirement']
    logger.info(f"[{task_id}] Submitting tasks to remote agents.")

    try:
        # Submit to Weather Agent
        r1_task_id = tools.submit_task_to_remote_agent(tools.REMOTE1_URL, user_requirement)

        # Submit to Transport Agent
        r2_task_id = tools.submit_task_to_remote_agent(tools.REMOTE2_URL, user_requirement)

        message = AIMessage(
            content=f"Tasks submitted. Weather Task ID: {r1_task_id}, Transport Task ID: {r2_task_id}. Now polling for status."
        )
        return {
            "remote1_task_id": r1_task_id,
            "remote2_task_id": r2_task_id,
            "status": "POLLING",
            "messages": [message],
        }
    except Exception as e:
        logger.error(f"[{task_id}] Failed to submit tasks: {e}", exc_info=True)
        return {"status": "ERROR_SUBMISSION", "messages": [AIMessage(content=f"Error submitting tasks: {e}")]}


async def polling_node(state: AgentState) -> dict:
    """
    Polls the remote agents until their tasks are complete.
    """
    r1_task_id = state['remote1_task_id']
    r2_task_id = state['remote2_task_id']
    task_id = state['task_id']
    logger.info(f"[{task_id}] Polling status for tasks: R1={r1_task_id}, R2={r2_task_id}")

    try:
        status1 = tools.get_task_status_from_remote_agent(tools.REMOTE1_URL, r1_task_id)
        status2 = tools.get_task_status_from_remote_agent(tools.REMOTE2_URL, r2_task_id)

        logger.info(f"[{task_id}] Current statuses: Weather={status1}, Transport={status2}")

        if status1 == "DONE" and status2 == "DONE":
            logger.info(f"[{task_id}] Both remote tasks are DONE.")
            message = AIMessage(content="Both remote tasks completed. Fetching results.")
            return {"status": "FETCHING_RESULTS", "messages": [message]}
        else:
            # Not all tasks are done, so we'll loop back to this node.
            # Add a delay to prevent busy-waiting.
            await asyncio.sleep(2)
            message = AIMessage(content=f"Waiting for remote agents... (Weather: {status1}, Transport: {status2})")
            # Return only messages, the status remains "POLLING"
            return {"messages": [message]}

    except Exception as e:
        logger.error(f"[{task_id}] Error during polling: {e}", exc_info=True)
        return {"status": "ERROR_POLLING", "messages": [AIMessage(content=f"Error during polling: {e}")]}


def fetch_results_node(state: AgentState) -> dict:
    """
    Fetches the results from remote agents once they are done.
    """
    r1_task_id = state['remote1_task_id']
    r2_task_id = state['remote2_task_id']
    task_id = state['task_id']
    logger.info(f"[{task_id}] Fetching results for tasks: R1={r1_task_id}, R2={r2_task_id}")

    result1 = None
    result2 = None
    try:
        result1 = tools.get_task_result_from_remote_agent(tools.REMOTE1_URL, r1_task_id)
    except Exception as e:
        logger.error(f"[{task_id}] Failed to fetch results for R1: {e}", exc_info=True)

    try:
        result2 = tools.get_task_result_from_remote_agent(tools.REMOTE2_URL, r2_task_id)
    except Exception as e:
        logger.error(f"[{task_id}] Failed to fetch results for R2: {e}", exc_info=True)

    message = AIMessage(content="Finished fetching results from remote agents. Now submitting for summary.")
    return {
        "remote1_result": result1,
        "remote2_result": result2,
        "status": "SUMMARIZING",
        "messages": [message],
    }


def summarize_node(state: AgentState) -> dict:
    """
    Submits the collected results to the summary agent.
    """
    task_id = state['task_id']
    logger.info(f"[{task_id}] Submitting results to summary agent.")

    try:
        summary_task_id = tools.submit_summary_task(
            root_task_id=task_id,
            user_requirement=state['user_requirement'],
            weather_result=state['remote1_result'],
            transport_result=state['remote2_result'],
        )

        # For this workflow, we consider the submission to the summary agent as the final step.
        # The user can then poll the root agent for the final summary result.
        message = AIMessage(content=f"Successfully submitted to summary agent. Summary Task ID: {summary_task_id}")
        return {
            "summary_task_id": summary_task_id,
            "status": "COMPLETED",
            "messages": [message],
        }
    except Exception as e:
        logger.error(f"[{task_id}] Failed to submit to summary agent: {e}", exc_info=True)
        return {"status": "ERROR_SUMMARY", "messages": [AIMessage(content=f"Error submitting to summary agent: {e}")]}


# --- Conditional Router ---
def router(state: AgentState) -> str:
    """
    Determines the next step based on the current status.
    """
    status = state["status"]
    logger.info(f"[{state['task_id']}] Routing based on status: '{status}'")
    
    if "ERROR" in status:
        return END
    elif status == "POLLING":
        return "polling_node"
    elif status == "FETCHING_RESULTS":
        return "fetch_results_node"
    elif status == "SUMMARIZING":
        return "summarize_node"
    elif status == "COMPLETED":
        return END
    else:
        # Default exit for any unhandled status
        return END


# --- Graph Assembly ---
def get_graph_app():
    """
    Builds and compiles the LangGraph application for async orchestration.
    """
    # Use in-memory checkpointer for simplicity as DDB is complex to set up locally
    # For production, DynamoDBSaver would be used here.
    checkpointer = None

    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("submit_tasks_node", submit_tasks_node)
    workflow.add_node("polling_node", polling_node)
    workflow.add_node("fetch_results_node", fetch_results_node)
    workflow.add_node("summarize_node", summarize_node)

    # Define the workflow edges
    workflow.set_entry_point("submit_tasks_node")
    
    workflow.add_edge("submit_tasks_node", "polling_node")
    
    # The polling node is connected to the router to create a loop
    workflow.add_conditional_edges("polling_node", router, {
        "polling_node": "polling_node", # Loop back if not done
        "fetch_results_node": "fetch_results_node", # Continue if done
        END: END # Exit on error
    })
    
    workflow.add_edge("fetch_results_node", "summarize_node")
    workflow.add_edge("summarize_node", END)

    # Compile the graph
    app = workflow.compile(checkpointer=checkpointer)
    logger.info("✅ Async agent orchestration graph compiled successfully.")
    return app
