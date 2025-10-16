# a2a_cash_flow_demo/services/root-agent/app/a2a/tools.py

import boto3
import json
import os
import logging
from typing import Dict, Any

# --- Configuration ---
# It's recommended to manage these via environment variables
# 您的實際區域 ap-southeast-1
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1") 
# 您實際 Event Bus 的名稱
EVENT_BUS_NAME = os.getenv("EVENT_BUS_NAME", "a2a-cash-flow-demo-bus") 

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