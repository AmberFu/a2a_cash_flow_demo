# a2a_cash_flow_demo/services/root-agent/app/a2a/tools.py

import boto3
import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional

import httpx

# --- Configuration ---
# It's recommended to manage these via environment variables
# 您的實際區域 ap-southeast-1
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
# 您實際 Event Bus 的名稱
EVENT_BUS_NAME = os.getenv("EVENT_BUS_NAME", "a2a-cash-flow-demo-bus")

REMOTE1_URL = os.getenv("REMOTE1_URL", "http://remote-agent-1-service:50001")
REMOTE2_URL = os.getenv("REMOTE2_URL", "http://remote-agent-2-service:50002")
SUMMARY_URL = os.getenv("SUMMARY_URL", "http://summary-agent-service:50003")

WORKFLOW_MODE = os.getenv("A2A_WORKFLOW_MODE", "eventbridge").lower()
USE_DDB_CHECKPOINTER = os.getenv("A2A_USE_DDB_CHECKPOINTER", "true").lower() == "true"
HTTP_TIMEOUT = float(os.getenv("A2A_HTTP_TIMEOUT", "10"))
DEFAULT_TRANSPORT_RESULTS = int(os.getenv("A2A_TRANSPORT_RESULTS", "3"))

# Initialize boto3 client
try:
    eventbridge_client = boto3.client("events", region_name=AWS_REGION)
except Exception as e:
    logging.error(f"Failed to initialize boto3 client: {e}")
    eventbridge_client = None

# --- Tool Definitions ---

def dispatch_to_remote_agent(
    task_id: str,
    loan_case_id: str,
    agent_name: str,
    detail_type: str
) -> Dict[str, Any]:
    """
    Sends a task to a remote agent via AWS EventBridge.
    """
    if not is_eventbridge_mode():
        logging.info(
            "Skipping EventBridge dispatch for task %s because workflow mode is '%s'",
            task_id,
            WORKFLOW_MODE,
        )
        return {
            "status": "skipped",
            "message": "EventBridge mode disabled; running in local direct-call mode.",
        }

    if not eventbridge_client:
        error_msg = "EventBridge client is not initialized."
        logging.error(error_msg)
        return {"status": "error", "message": error_msg}

    event_detail = {
        "task_id": task_id,
        "loan_case_id": loan_case_id,
    }

    try:
        logging.info(f"Dispatching task {task_id} for case {loan_case_id} to {agent_name}...")
        response = eventbridge_client.put_events(
            Entries=[
                {
                    "Source": "a2a.root-agent",
                    "DetailType": detail_type, # e.g., "Task.RecognizeTransactions"
                    "Detail": json.dumps(event_detail),
                    # 使用正確的 EventBusName
                    "EventBusName": EVENT_BUS_NAME, 
                }
            ]
        )
        
        failed_count = response.get("FailedEntryCount", 0)
        if failed_count > 0:
            error_message = f"Failed to send event to EventBridge for task {task_id}. Response: {response}"
            logging.error(error_message)
            return {"status": "error", "message": error_message}

        logging.info(f"Successfully dispatched task {task_id} to {agent_name}. EventID: {response['Entries'][0]['EventId']}")
        return {
            "status": "success",
            "message": f"Task {task_id} dispatched to {agent_name}.",
            "event_id": response["Entries"][0]["EventId"],
        }
    except Exception as e:
        error_message = f"An exception occurred while dispatching task {task_id}: {e}"
        logging.error(error_message)
        return {"status": "error", "message": error_message}


def is_eventbridge_mode() -> bool:
    return WORKFLOW_MODE == "eventbridge"


def use_ddb_checkpointer() -> bool:
    return USE_DDB_CHECKPOINTER


def _compute_time_range(requirement: Dict[str, Any]) -> str:
    explicit = requirement.get("time_range")
    if explicit:
        return explicit

    arrival = requirement.get("desired_arrival_time")
    if arrival:
        try:
            hour = int(str(arrival).split(":")[0])
        except (ValueError, IndexError):
            hour = None
        if hour is not None:
            if hour < 12:
                return "上午"
            if hour < 18:
                return "下午"
            return "晚上"

    return "全天"


def _normalize_arrival_time(value: Optional[str]) -> str:
    if not value:
        return "17:00:00"

    text = str(value)
    if len(text.split(":")) == 2:
        return f"{text}:00"
    return text


def _default_travel_date(requirement: Dict[str, Any]) -> str:
    date_value = requirement.get("travel_date")
    if date_value:
        return str(date_value)
    return datetime.utcnow().date().isoformat()


def fetch_weather_report(requirement: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "city": requirement.get("destination") or requirement.get("origin") or "台北",
        "date": _default_travel_date(requirement),
        "time_range": _compute_time_range(requirement),
    }
    endpoint = f"{REMOTE1_URL.rstrip('/')}/weather/report"
    logging.info("Calling Weather Remote Agent: %s", endpoint)
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            response = client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logging.error("Weather agent call failed: %s", exc)
        raise RuntimeError(f"Weather agent request failed: {exc}") from exc

    logging.debug("Weather agent response: %s", data)
    return data


def fetch_transport_plans(requirement: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "destination": requirement.get("destination") or "台北",
        "arrival_time": _normalize_arrival_time(requirement.get("desired_arrival_time")),
        "date": _default_travel_date(requirement),
        "results": requirement.get("transport_results", DEFAULT_TRANSPORT_RESULTS),
    }
    endpoint = f"{REMOTE2_URL.rstrip('/')}/transport/plans"
    logging.info("Calling Transport Remote Agent: %s", endpoint)
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            response = client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logging.error("Transport agent call failed: %s", exc)
        raise RuntimeError(f"Transport agent request failed: {exc}") from exc

    logging.debug("Transport agent response: %s", data)
    return data


def request_summary(
    task_id: str,
    requirement: Dict[str, Any],
    weather_report: Dict[str, Any],
    transport_payload: Dict[str, Any],
) -> Dict[str, Any]:
    payload = {
        "task_id": task_id,
        "user_requirement": {
            "origin": requirement.get("origin") or "台北",
            "destination": requirement.get("destination")
            or weather_report.get("city")
            or "台北",
            "travel_date": _default_travel_date(requirement),
            "desired_arrival_time": _normalize_arrival_time(
                requirement.get("desired_arrival_time")
            ),
            "transport_note": requirement.get("transport_note"),
        },
        "weather_report": weather_report,
        "transport": transport_payload,
    }
    endpoint = f"{SUMMARY_URL.rstrip('/')}/summaries"
    logging.info("Calling Summary Agent: %s", endpoint)
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            response = client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logging.error("Summary agent call failed: %s", exc)
        raise RuntimeError(f"Summary agent request failed: {exc}") from exc

    logging.debug("Summary agent response: %s", data)
    return data