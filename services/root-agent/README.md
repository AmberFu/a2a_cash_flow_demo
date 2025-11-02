# Root Agent Service

## 1. Service Purpose

The **Root Agent** is the central orchestrator of the multi-agent travel planning system. It serves as the primary entry point for user requests. Its main responsibilities are:

-   **Receiving User Requests**: It accepts a user's travel requirements (e.g., origin, destination, date).
-   **Task Orchestration**: It breaks down the main request into sub-tasks and dispatches them to the appropriate remote agents (`remote-agent-1` for weather, `remote-agent-2` for transport).
-   **Asynchronous Monitoring**: It asynchronously polls the remote agents to monitor the status of their tasks until they are completed.
-   **Result Aggregation**: Once all remote tasks are done, it fetches the results and submits them to the `summary-agent` for final processing.
-   **Providing Final Results**: It offers endpoints for the end-user to check the overall task status and retrieve the final, summarized travel plan.

The entire workflow is managed by a **LangGraph** state machine, ensuring a robust and traceable process.

## 2. Environment Variables

-   `PORT`: The port on which the FastAPI application will run. Default: `50000`.
-   `REMOTE1_URL`: The full URL for `remote-agent-1` (Weather Agent). Example: `http://remote-agent-1-service:50001`.
-   `REMOTE2_URL`: The full URL for `remote-agent-2` (Transport Agent). Example: `http://remote-agent-2-service:50002`.
-   `SUMMARY_URL`: The full URL for the `summary-agent`. Example: `http://summary-agent-service:50003`.
-   `A2A_WORKFLOW_MODE`: Defines the operational mode. For this version, it should be set to `local`.
-   `METRICS_ENABLED`: Set to `true` to expose a `/metrics` endpoint for Prometheus.

## 3. JSON-RPC API Usage

All interactions with the Root Agent are via JSON-RPC calls to the `/jsonrpc` endpoint.

### Method: `a2a.submit_task`

Submits a new travel planning task. The agent immediately returns a `task_id` and begins processing in the background.

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "a2a.submit_task",
  "params": {
    "loan_case_id": "travel-request-001",
    "user_requirement": {
      "origin": "台北",
      "destination": "台南",
      "travel_date": "2024-10-25",
      "desired_arrival_time": "15:30"
    }
  },
  "id": 1
}
```

**Success Response:**

```json
{
  "jsonrpc": "2.0",
  "result": {
    "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "message": "Workflow started."
  },
  "id": 1
}
```

### Method: `a2a.get_task_status`

Checks the status of a previously submitted task.

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "a2a.get_task_status",
  "params": {
    "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  },
  "id": 2
}
```

**Success Response (Example):**

The status will progress through `POLLING`, `FETCHING_RESULTS`, `SUMMARIZING`, and finally `COMPLETED`.

```json
{
  "jsonrpc": "2.0",
  "result": {
    "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "status": "POLLING"
  },
  "id": 2
}
```

### Method: `a2a.get_task_result`

Retrieves the final summarized travel plan once the task is complete.

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "a2a.get_task_result",
  "params": {
    "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  },
  "id": 3
}
```

**Success Response (when ready):**

```json
{
  "jsonrpc": "2.0",
  "result": {
    "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "status": "COMPLETED",
    "result": {
      // The full summary object from the summary-agent will be here
      "overview": "...",
      "weather_advice": "...",
      "transport_options": "..."
    }
  },
  "id": 3
}
```

**Error Response (if not ready):**

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": 202,
    "message": "Task result is not ready yet.",
    "data": {
      "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "status": "SUMMARIZING"
    }
  },
  "id": 3
}
```

## 4. Local Testing Guide

To test this agent locally (after deploying it to Kubernetes and using `kubectl port-forward`), you can use `curl`.

1.  **Submit the task:**

    ```bash
    curl -X POST http://127.0.0.1:50000/jsonrpc \
      -H "Content-Type: application/json" \
      -d '{
            "jsonrpc": "2.0",
            "method": "a2a.submit_task",
            "params": {
              "loan_case_id": "local-test-01",
              "user_requirement": {
                "origin": "台北",
                "destination": "台南",
                "travel_date": "2024-10-25",
                "desired_arrival_time": "15:30"
              }
            },
            "id": 1
          }'
    ```

    (Save the `task_id` from the response)

2.  **Check the status:**

    ```bash
    curl -X POST http://127.0.0.1:50000/jsonrpc \
      -H "Content-Type: application/json" \
      -d '{
            "jsonrpc": "2.0",
            "method": "a2a.get_task_status",
            "params": {
              "task_id": "YOUR_TASK_ID_HERE"
            },
            "id": 2
          }'
    ```

3.  **Get the result (once status is 'COMPLETED'):**

    ```bash
    curl -X POST http://127.0.0.1:50000/jsonrpc \
      -H "Content-Type: application/json" \
      -d '{
            "jsonrpc": "2.0",
            "method": "a2a.get_task_result",
            "params": {
              "task_id": "YOUR_TASK_ID_HERE"
            },
            "id": 3
          }'
    ```
