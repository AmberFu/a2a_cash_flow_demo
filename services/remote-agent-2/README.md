# Remote Agent 2: Transport Service

## 1. Service Purpose

**Remote Agent 2** is a specialized agent that provides transportation plans. It functions as an independent service, handling requests to generate travel options asynchronously.

-   **Function**: It receives a destination, desired arrival time, and travel date.
-   **Processing**: Based on the inputs, it generates a list of simulated transportation options (e.g., High-Speed Rail, regular train). The logic is designed to be illustrative rather than a real-time query system.
-   **Asynchronous Pattern**: Like the other agents, it adheres to the `submit` -> `status` -> `result` asynchronous protocol, enabling non-blocking task execution.

## 2. Environment Variables

-   `PORT`: The port for the FastAPI application. Default: `50002`.
-   `REMOTE2_MODEL_PROVIDER`: The provider for the LLM (if any is used for generation). Default: `bedrock`.
-   `REMOTE2_MODEL_ID`: The specific model ID for the LLM.
-   `METRICS_ENABLED`: Set to `true` to expose a `/metrics` endpoint for Prometheus.

## 3. JSON-RPC API Usage

All interactions are via JSON-RPC calls to the `/jsonrpc` endpoint.

### Method: `a2a.submit_task`

Submits a new request to generate a transport plan.

**Request:**

```json
{
  "jsonrpc": "2.0",
  "method": "a2a.submit_task",
  "params": {
    "user_requirement": {
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
    "task_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  },
  "id": 1
}
```

### Method: `a2a.get_task_status`

Checks the status of the transport plan generation task.

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

Retrieves the final transport plan.

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
      "destination": "台南",
      "requested_arrival_time": "15:30:00",
      "date": "2024-10-25",
      "plans": [
        {
          "type": "台灣高鐵",
          "train_number": "0837",
          "departure_time": "13:55",
          "arrival_time": "15:31",
          "note": "建議班次"
        },
        // ... other plans
      ]
    }
  },
  "id": 3
}
```

## 4. Local Testing Guide

To test this agent directly (after deploying it to Kubernetes and using `kubectl port-forward`), you can use `curl`.

1.  **Submit the task:**

    ```bash
    curl -X POST http://1227.0.0.1:50002/jsonrpc \
      -H "Content-Type: application/json" \
      -d '{
            "jsonrpc": "2.0",
            "method": "a2a.submit_task",
            "params": {
              "user_requirement": { "destination": "台南", "travel_date": "2024-10-25", "desired_arrival_time": "15:30" }
            },
            "id": 1
          }'
    ```

    (Save the `task_id` from the response)

2.  **Check the status (wait a few seconds):**

    ```bash
    curl -X POST http://127.0.0.1:50002/jsonrpc \
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
    curl -X POST http://127.0.0.1:50002/jsonrpc \
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
