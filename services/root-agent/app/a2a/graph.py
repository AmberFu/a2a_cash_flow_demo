# a2a_cash_flow_demo/services/root-agent/app/a2a/graph.py

import os
import logging
import operator
from typing import TypedDict, Annotated, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, AIMessage
from langgraph_checkpoint_dynamodb import DynamoDBSaver, DynamoDBConfig, DynamoDBTableConfig
import redis 
from . import tools

# --- 從環境變數讀取配置 ---
AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
DDB_TABLE_NAME = os.environ.get("DDB_A2A_TASKS_TABLE_NAME", "ds_demo_a2a_tasks")

# # 短期記憶 Redis
# REDIS_HOST = os.environ.get("REDIS_HOST")
# REDIS_PORT = os.environ.get("REDIS_PORT", "6379")

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)
logging.getLogger("langgraph").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

# --- State Definition ---
class AgentState(TypedDict):
    task_id: str
    loan_case_id: str
    status: str
    messages: Annotated[List[BaseMessage], operator.add]
    needs_info: List[str]
    human_answer: str

# --- Graph Nodes ---

def start_node(state: AgentState) -> dict:
    """Entry point of the graph. Dispatches the first task."""
    logging.info(f"[Task: {state['task_id']}] Starting process for loan case: {state['loan_case_id']}")
    
    logger.debug("Enter node=start_node", extra={"state": state})

    dispatch_result = tools.dispatch_to_remote_agent(
        task_id=state["task_id"],
        loan_case_id=state["loan_case_id"],
        agent_name="Remote Agent A",
        detail_type="Task.RecognizeTransactions"
    )
    
    if dispatch_result["status"] == "error":
        new_status = "error_dispatch_a"
        message = AIMessage(content=f"Error: Failed to dispatch task to Remote Agent A. Reason: {dispatch_result['message']}")
    else:
        new_status = "recognizing_transactions"
        message = AIMessage(content="Task has been dispatched to Remote Agent A to recognize transaction details. Awaiting callback.")

    logger.debug("Leave node=start_node")

    return {"status": new_status, "messages": [message]}

def draft_response_node(state: AgentState) -> dict:
    """Dispatches task to Remote Agent B to draft a customer response."""
    logging.info(f"[Task: {state['task_id']}] Dispatching to Remote Agent B to draft response.")

    logger.debug("Enter node=draft_response_node", extra={"state": state})

    dispatch_result = tools.dispatch_to_remote_agent(
        task_id=state["task_id"],
        loan_case_id=state["loan_case_id"],
        agent_name="Remote Agent B",
        detail_type="Task.DraftResponse"
    )
    
    if dispatch_result["status"] == "error":
        new_status = "error_dispatch_b"
        message = AIMessage(content=f"Error: Failed to dispatch task to Remote Agent B. Reason: {dispatch_result['message']}")
    else:
        new_status = "drafting_response"
        message = AIMessage(content="Task has been dispatched to Remote Agent B to draft a response. Awaiting callback.")

    logger.debug("Leave node=draft_response_node")

    return {"status": new_status, "messages": [message]}

def human_in_the_loop_node(state: AgentState) -> dict:
    """Pauses the graph and waits for human input."""
    logging.info(f"[Task: {state['task_id']}] Process requires human input.")

    logger.debug("Enter node=human_in_the_loop_node", extra={"state": state})

    message = AIMessage(content=f"Awaiting human input for the following: {state['needs_info']}")

    logger.debug("Leave node=human_in_the_loop_node")

    return {"status": "awaiting_human_input", "messages": [message]}

def finish_node(state: AgentState) -> dict:
    """Marks the task as complete."""
    logging.info(f"[Task: {state['task_id']}] Process completed for loan case: {state['loan_case_id']}")
    
    logger.debug("Enter node=finish_node", extra={"state": state})

    message = AIMessage(content="The process has been successfully completed.")

    logger.debug("Leave node=finish_node")

    return {"status": "completed", "messages": [message]}

# --- Conditional Edges ---

def router(state: AgentState) -> str:
    """Determines the next step in the workflow."""
    logging.info(f"[Task: {state['task_id']}] Routing based on status: '{state['status']}'")

    if state["status"] == "awaiting_human_input":
        return "human_in_the_loop_node"

    if state["status"] == "transactions_recognized":
        return "draft_response_node"
        
    if state["status"] == "response_drafted":
        return "finish_node"
        
    if state["status"] == "new":
        return "start_node"
    
    return END

# --- Graph Assembly ---

def get_graph_app():
    """
    Builds and compiles the LangGraph application with a DynamoDB checkpointer.
    """
    
    # -------------------------------------------------------------
    # 1. 設置 DynamoDB Checkpointer (正確配置)
    # -------------------------------------------------------------
    logging.info(f">>> Start get_graph_app()...")
    if not DDB_TABLE_NAME:
        raise ValueError("DDB_A2A_TASKS_TABLE_NAME must be set for LangGraph Checkpoint.")

    try:
        logging.info(f">>> 1. 設定 DynamoDB Table 配置")
        # 1.1 設定 DynamoDB Table 配置
        table_config = DynamoDBTableConfig(
            table_name=DDB_TABLE_NAME,
        )

        logging.info(f">>> 2. 設定 DynamoDB 連接配置")
        # 1.2 設定 DynamoDB 連接配置
        config = DynamoDBConfig(
            table_config=table_config,
            region_name=AWS_REGION,
            # 使用 EKS Pod 的 IAM Role，不需要手動設置憑證
            # aws_access_key_id、aws_secret_access_key、aws_session_token 保持 None
        )

        logging.info(f">>> 3. 初始化 Checkpointer")
        # 1.3 初始化 Checkpointer
        # deploy=False: 假設表格已透過 Terraform 創建
        # 如果需要自動創建表格，設置為 deploy=True
        checkpointer = DynamoDBSaver(config, deploy=False)
        
        logging.info(f"✅ DynamoDBSaver initialized successfully for table: {DDB_TABLE_NAME}")

    except Exception as e:
        logging.error(f"❌ Failed to initialize DynamoDBSaver: {e}")
        logging.error("Please check:")
        logging.error("  - DynamoDB table exists and is accessible")
        logging.error("  - EKS Pod has correct IAM permissions")
        logging.error("  - Environment variables are set correctly")
        raise 

    # # -------------------------------------------------------------
    # # 2. 初始化 Redis 短期記憶客戶端 (獨立於 LangGraph)
    # # -------------------------------------------------------------
    # if REDIS_HOST:
    #     try:
    #         redis_client = redis.StrictRedis(host=REDIS_HOST, port=int(REDIS_PORT))
    #         redis_client.ping()
    #         logging.info(f"✅ Redis connected successfully at {REDIS_HOST}:{REDIS_PORT}")
    #     except Exception as e:
    #         logging.warning(f"⚠️ Redis connection failed: {e}")
    #         logging.warning("Short-term memory features will be unavailable.")

    # -------------------------------------------------------------
    # 3. 定義與編譯 Graph
    # -------------------------------------------------------------
    logging.info(f">>> StateGraph(AgentState)")
    workflow = StateGraph(AgentState)
    
    # Add nodes
    logging.info(f">>> Add nodes...")
    workflow.add_node("start_node", start_node)
    workflow.add_node("draft_response_node", draft_response_node)
    workflow.add_node("human_in_the_loop_node", human_in_the_loop_node)
    workflow.add_node("finish_node", finish_node)
    
    # Set entry and exit points
    logging.info(f">>> Set entry and exit points...")
    workflow.set_entry_point("start_node")
    workflow.add_edge("finish_node", END)
    
    # Add conditional edges
    logging.info(f">>> Add conditional edges...")
    workflow.add_conditional_edges("start_node", router)
    workflow.add_conditional_edges("draft_response_node", router)
    workflow.add_conditional_edges("human_in_the_loop_node", router)
    
    # # Compile the graph with checkpointer
    # logging.info(f">>> workflow.compile()...")
    # app = workflow.compile(
    #     checkpointer=checkpointer,
    #     # 在這些節點執行後中斷，等待外部 callback 恢復
    #     interrupt_after=["start_node", "draft_response_node", "human_in_the_loop_node"]
    # )
    
    # logging.info("✅ LangGraph application compiled successfully")
    logger.info(">>> workflow.compile()...", extra={
        "ddb_table": os.getenv("DDB_A2A_TASKS_TABLE_NAME"),
        "region": os.getenv("AWS_REGION"),
        "checkpoint_ns": os.getenv("LG_CHECKPOINT_NS", "default")
    })
    app = workflow.compile(
        checkpointer=checkpointer,
        interrupt_after=["start_node", "draft_response_node", "human_in_the_loop_node"])
    logger.info("✅ LangGraph application compiled successfully")
    
    return app 
