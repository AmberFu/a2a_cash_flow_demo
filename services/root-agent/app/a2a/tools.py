# a2a_cash_flow_demo/services/root-agent/app/a2a/tools.py

import os
import logging
from typing import Dict, Any
import httpx
from jsonrpcclient import request as jsonrpc_request_creator

# --- Configuration ---
REMOTE1_URL = os.getenv("REMOTE1_URL", "http://remote-agent-1-service:50001")
REMOTE2_URL = os.getenv("REMOTE2_URL", "http://remote-agent-2-service:50002")
SUMMARY_URL = os.getenv("SUMMARY_URL", "http://summary-agent-service:50003")
WORKFLOW_MODE = os.getenv("A2A_WORKFLOW_MODE", "local").lower()


# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _send_jsonrpc_request(endpoint: str, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Helper function to send a JSON-RPC request using httpx."""
    payload = jsonrpc_request_creator(method, params)
    logger.info(f"Sending JSON-RPC request to {endpoint}: {payload}")
    try:
        with httpx.Client() as client:
            http_response = client.post(endpoint, json=payload, timeout=20.0)
            http_response.raise_for_status()
            response_json = http_response.json()
            logger.info(f"Received JSON-RPC response: {response_json}")
            return response_json
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}", exc_info=True)
        raise RuntimeError(f"HTTP error calling {endpoint}") from e
    except httpx.RequestError as e:
        logger.error(f"Request error occurred: {e}", exc_info=True)
        raise RuntimeError(f"Request error calling {endpoint}") from e


# --- Generic JSON-RPC Client Tools ---

def submit_task_to_remote_agent(agent_url: str, user_requirement: Dict[str, Any]) -> str:
    """Submits a task to a remote agent and returns the task ID."""
    endpoint = f"{agent_url.rstrip('/')}/jsonrpc"
    method = "a2a.submit_task"
    params = {"user_requirement": user_requirement}

    response = _send_jsonrpc_request(endpoint, method, params)

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

def get_task_status_from_remote_agent(agent_url: str, task_id: str) -> str:
    """Gets the status of a task from a remote agent."""
    endpoint = f"{agent_url.rstrip('/')}/jsonrpc"
    method = "a2a.get_task_status"
    params = {"task_id": task_id}

    try:
        response = _send_jsonrpc_request(endpoint, method, params)
        if "error" in response:
            logger.error(f"Remote agent at {agent_url} returned an error while getting status: {response['error']}")
            return "UNKNOWN"
        if "result" in response and "status" in response["result"]:
            status = response["result"]["status"]
            logger.debug(f"Status for task {task_id} at {agent_url} is: {status}")
            return status
        else:
            logger.error(f"Invalid status response from {agent_url}: {response}")
            return "UNKNOWN"
    except Exception:
        logger.error(f"Failed to get task status from {agent_url} for task {task_id}", exc_info=True)
        return "UNKNOWN"

def get_task_result_from_remote_agent(agent_url: str, task_id: str) -> Dict[str, Any]:
    """Gets the result of a completed task from a remote agent."""
    endpoint = f"{agent_url.rstrip('/')}/jsonrpc"
    method = "a2a.get_task_result"
    params = {"task_id": task_id}

    response = _send_jsonrpc_request(endpoint, method, params)

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


def submit_summary_task(
    root_task_id: str,
    user_requirement: Dict[str, Any],
    weather_result: Dict[str, Any],
    transport_result: Dict[str, Any],
) -> str:
    """Submits the collected results to the summary agent."""
    endpoint = f"{SUMMARY_URL.rstrip('/')}/jsonrpc"
    method = "a2a.submit_task"
    params = {
        "task_id": root_task_id,
        "user_requirement": user_requirement,
        "weather_report": weather_result,
        "transport": transport_result,
    }

    response = _send_jsonrpc_request(endpoint, method, params)

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

# --- Workflow Mode Helper ---
def is_local_mode() -> bool:
    """Determines if the workflow is in local JSON-RPC mode."""
    return WORKFLOW_MODE == "local"
