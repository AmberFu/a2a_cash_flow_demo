# Remote Agent 1: Weather Service

## 1. Service Purpose

**Remote Agent 1** is a specialized agent responsible for providing weather forecasts and related advice. It operates as a standalone service that receives requests, processes them asynchronously, and provides a weather report.

-   **Function**: It takes a city, date, and time range as input.
-   **Processing**: It generates a simulated weather forecast (e.g., temperature, conditions) and uses a Large Language Model (LLM) to synthesize a human-readable summary and travel advice based on the weather.
-   **Asynchronous Pattern**: The service follows a `submit` -> `status` -> `result` asynchronous pattern, allowing clients like the Root Agent to submit a task and check back later for the result without blocking.

## 2. Environment Variables

-   `PORT`: The port on which the FastAPI application will run. Default: `50001`.
-   `REMOTE1_MODEL_PROVIDER`: The provider for the LLM used for synthesis. Default: `bedrock`.
-   `REMOTE1_MODEL_ID`: The specific model ID for the LLM.
-   `METRICS_ENABLED`: Set to `true` to expose a `/metrics` endpoint for Prometheus.

## 3. JSON-RPC API Usage

All interactions are via JSON-RPC calls to the `/jsonrpc` endpoint.

### Method: `a2a.submit_task`

Submits a new request to generate a weather report.

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "a2a.submit_task",
  "params": {
    "user_requirement": {
      "destination": "台南",
      "travel_date": "2024-10-25"
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
    "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  },
  "id": 1
}
```

### Method: `a2a.get_task_status`

Checks the status of the weather report generation task.

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

The status will progress from `PENDING` -> `IN_PROGRESS` -> `DONE`.

```json
{
  "jsonrpc": "2.0",
  "result": {
    "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "status": "IN_PROGRESS"
  },
  "id": 2
}
```

### Method: `a2a.get_task_result`

Retrieves the final weather report.

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
    "status": "DONE",
    "result": {
      "city": "台南",
      "date": "2024-10-25",
      "time_range": "全天",
      "variables": {
        "temperature_celsius": 28,
        "conditions": "晴時多雲",
        "precipitation_chance": 15
      },
      "summary": "台南在 2024-10-25 將會是晴時多雲的好天氣..."
    }
  },
  "id": 3
}
```

## 4. Local Testing Guide

To test this agent directly (after deploying it to Kubernetes and using `kubectl port-forward`), you can use `curl`.

1.  **Submit the task:**

    ```bash
    curl -X POST http://127.0.0.1:50001/jsonrpc \
      -H "Content-Type: application/json" \
      -d '{
            "jsonrpc": "2.0",
            "method": "a2a.submit_task",
            "params": {
              "user_requirement": { "destination": "台南", "travel_date": "2024-10-25" }
            },
            "id": 1
          }'
    ```

    (Save the `task_id` from the response)

2.  **Check the status (wait a few seconds):**

    ```bash
    curl -X POST http://127.0.0.1:50001/jsonrpc \
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

3.  **Get the result (once status is 'DONE'):**

    ```bash
    curl -X POST http://127.0.0.1:50001/jsonrpc \
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
