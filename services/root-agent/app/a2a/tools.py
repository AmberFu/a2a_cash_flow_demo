# a2a_cash_flow_demo/services/root-agent/app/a2a/tools.py

import os
import logging
from typing import Dict, Any

from jsonrpcclient import request as jsonrpc_request

# --- Configuration ---
REMOTE1_URL = os.getenv("REMOTE1_URL", "http://remote-agent-1-service:50001")
REMOTE2_URL = os.getenv("REMOTE2_URL", "http://remote-agent-2-service:50002")
SUMMARY_URL = os.getenv("SUMMARY_URL", "http://summary-agent-service:50003")
WORKFLOW_MODE = os.getenv("A2A_WORKFLOW_MODE", "local").lower()


# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# --- Generic JSON-RPC Client Tools ---

def submit_task_to_remote_agent(agent_url: str, user_requirement: Dict[str, Any]) -> str:
    """
    Submits a task to a remote agent and returns the task ID.
    """
    endpoint = f"{agent_url.rstrip('/')}/jsonrpc"
    method = "a2a.submit_task"
    params = {"user_requirement": user_requirement}

    logger.info(f"Submitting task to {endpoint} with method '{method}' and params: {params}")
    try:
        response = jsonrpc_request(endpoint, method, params)
        if "error" in response:
            logger.error(f"Remote agent at {agent_url} returned an error: {response['error']}")
            raise ValueError(f"Error from remote agent: {response['error']}")
        if "result" in response and "task_id" in response["result"]:
            task_id = response["result"]["task_id"]
            logger.info(f"Successfully submitted task to {agent_url}, received task_id: {task_id}")
            return task_id
        else:
            logger.error(f"Invalid response from {agent_url}: {response}")
            raise ValueError("Invalid response from agent: 'task_id' not found.")
    except Exception as e:
        logger.error(f"Failed to submit task to {agent_url}: {e}", exc_info=True)
        raise RuntimeError(f"Could not submit task to {agent_url}") from e

def get_task_status_from_remote_agent(agent_url: str, task_id: str) -> str:
    """
    Gets the status of a task from a remote agent.
    """
    endpoint = f"{agent_url.rstrip('/')}/jsonrpc"
    method = "a2a.get_task_status"
    params = {"task_id": task_id}

    logger.info(f"Checking task status from {endpoint} with params: {params}")
    try:
        response = jsonrpc_request(endpoint, method, params)
        if "error" in response:
            logger.error(f"Remote agent at {agent_url} returned an error while getting status: {response['error']}")
            return "UNKNOWN" # Return a safe status on error
        if "result" in response and "status" in response["result"]:
            status = response["result"]["status"]
            logger.debug(f"Status for task {task_id} at {agent_url} is: {status}")
            return status
        else:
            logger.error(f"Invalid status response from {agent_url}: {response}")
            return "UNKNOWN"
    except Exception as e:
        logger.error(f"Failed to get task status from {agent_url} for task {task_id}: {e}", exc_info=True)
        # In case of failure, returning a non-DONE status is safer
        return "UNKNOWN"

def get_task_result_from_remote_agent(agent_url: str, task_id: str) -> Dict[str, Any]:
    """
    Gets the result of a completed task from a remote agent.
    """
    endpoint = f"{agent_url.rstrip('/')}/jsonrpc"
    method = "a2a.get_task_result"
    params = {"task_id": task_id}

    logger.info(f"Fetching task result from {endpoint} for task_id: {task_id} with params: {params}")
    try:
        response = jsonrpc_request(endpoint, method, params)
        if "error" in response:
            logger.error(f"Remote agent at {agent_url} returned an error while getting result: {response['error']}")
            raise ValueError(f"Error from remote agent: {response['error']}")
        if "result" in response and "result" in response["result"]:
            task_result = response["result"]["result"]
            logger.info(f"Successfully fetched result for task {task_id} from {agent_url}")
            return task_result
        else:
            logger.error(f"Invalid result response from {agent_url}: {response}")
            raise ValueError("Invalid response from agent: 'result' not found.")
    except Exception as e:
        logger.error(f"Failed to get task result from {agent_url} for task {task_id}: {e}", exc_info=True)
        raise RuntimeError(f"Could not get result for task {task_id} from {agent_url}") from e


def submit_summary_task(
    root_task_id: str,
    user_requirement: Dict[str, Any],
    weather_result: Dict[str, Any],
    transport_result: Dict[str, Any],
) -> str:
    """
    Submits the collected results to the summary agent.
    """
    endpoint = f"{SUMMARY_URL.rstrip('/')}/jsonrpc"
    method = "a2a.submit_task"
    params = {
        "task_id": root_task_id, # Pass the root task_id
        "user_requirement": user_requirement,
        "weather_report": weather_result,
        "transport": transport_result,
    }

    logger.info(f"Submitting final results to Summary Agent for task_id: {root_task_id} with params: {params}")
    try:
        response = jsonrpc_request(endpoint, method, params)
        if "error" in response:
            logger.error(f"Summary agent returned an error: {response['error']}")
            raise ValueError(f"Error from summary agent: {response['error']}")
        if "result" in response and "task_id" in response["result"]:
            summary_task_id = response["result"]["task_id"]
            logger.info(f"Successfully submitted to summary agent, received task_id: {summary_task_id}")
            return summary_task_id
        else:
            logger.error(f"Invalid response from summary agent: {response}")
            raise ValueError("Invalid response from summary agent: 'task_id' not found.")
    except Exception as e:
        logger.error(f"Failed to submit to summary agent for task {root_task_id}: {e}", exc_info=True)
        raise RuntimeError("Could not submit task to summary agent") from e

# --- Workflow Mode Helper ---
def is_local_mode() -> bool:
    """Determines if the workflow is in local JSON-RPC mode."""
    return WORKFLOW_MODE == "local"
