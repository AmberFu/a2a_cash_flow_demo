# Summary Agent Service

## 1. Service Purpose

The **Summary Agent** is the final agent in the travel planning workflow. Its primary function is to synthesize information from the other remote agents into a coherent and helpful travel plan for the end-user.

-   **Function**: It receives the user's original travel requirement, the weather report from `remote-agent-1`, and the transportation plans from `remote-agent-2`.
-   **Processing**: It uses a Large Language Model (LLM) to craft a final summary that includes an overview, weather-related advice, and a description of the transport options.
-   **Asynchronous Pattern**: It follows the same `submit` -> `status` -> `result` asynchronous protocol to handle the summarization task.

## 2. Environment Variables

-   `PORT`: The port for the FastAPI application. Default: `50003`.
-   `SUMMARY_MODEL_PROVIDER`: The provider for the LLM used for summarization. Default: `bedrock`.
-   `SUMMARY_MODEL_ID`: The specific model ID for the LLM.
-   `METRICS_ENABLED`: Set to `true` to expose a `/metrics` endpoint for Prometheus.

## 3. JSON-RPC API Usage

All interactions are via JSON-RPC calls to the `/jsonrpc` endpoint.

### Method: `a2a.submit_task`

Submits a new task to generate the final summary. The `task_id` should be the same as the `root-agent`'s main task ID for traceability.

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "a2a.submit_task",
  "params": {
    "task_id": "root-task-id-123",
    "user_requirement": {
      "origin": "台北",
      "destination": "台南",
      "travel_date": "2024-10-25",
      "desired_arrival_time": "15:30"
    },
    "weather_report": {
      "city": "台南",
      "date": "2024-10-25",
      "summary": "天氣晴朗..."
    },
    "transport": {
      "destination": "台南",
      "plans": [ { "type": "高鐵", ... } ]
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
    "task_id": "root-task-id-123"
  },
  "id": 1
}
```

### Method: `a2a.get_task_status`

Checks the status of the summarization task.

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "a2a.get_task_status",
  "params": {
    "task_id": "root-task-id-123"
  },
  "id": 2
}
```

**Success Response (Example):**

The status will progress from `PENDING` -> `IN_PROGRESS` -> `DONE`.

```json
{
  "jsonrpc": "2.0",
  "result": {
    "task_id": "root-task-id-123",
    "status": "IN_PROGRESS"
  },
  "id": 2
}
```

### Method: `a2a.get_task_result`

Retrieves the final, synthesized travel plan.

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "a2a.get_task_result",
  "params": {
    "task_id": "root-task-id-123"
  },
  "id": 3
}
```

**Success Response (when ready):**

```json
{
  "jsonrpc": "2.0",
  "result": {
    "task_id": "root-task-id-123",
    "status": "DONE",
    "result": {
      "task_id": "root-task-id-123",
      "overview": "為您規劃的台南行程...",
      "weather_advice": "天氣很好，建議穿著輕便...",
      "transport_options": "建議您搭乘高鐵 0837 號班次..."
    }
  },
  "id": 3
}
```

## 4. Local Testing Guide

To test this agent directly, you would need to provide it with mock data that simulates the outputs of the other agents.

1.  **Submit the task with mock data:**

    ```bash
    curl -X POST http://127.0.0.1:50003/jsonrpc \
      -H "Content-Type: application/json" \
      -d '{
            "jsonrpc": "2.0",
            "method": "a2a.submit_task",
            "params": {
              "task_id": "manual-summary-test-01",
              "user_requirement": { "origin": "台北", "destination": "台南", "travel_date": "2024-10-25", "desired_arrival_time": "15:30" },
              "weather_report": { "city": "台南", "date": "2024-10-25", "summary": "天氣晴朗，氣溫舒適。" },
              "transport": { "destination": "台南", "plans": [ { "type": "高鐵", "train_number": "0837", "departure_time": "13:55", "arrival_time": "15:31", "note": "最快選項" } ] }
            },
            "id": 1
          }'
    ```

    (Save the `task_id` from the response)

2.  **Check the status and get the result** using the same `a2a.get_task_status` and `a2a.get_task_result` patterns as the other agents, pointing to port `50003`.
