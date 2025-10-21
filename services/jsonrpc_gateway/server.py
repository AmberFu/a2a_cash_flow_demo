"""簡化版 JSON-RPC 2.0 over HTTPS 伺服器範例。

此範例示範：
1. 以標準庫 `http.server` 實作 JSON-RPC 2.0。
2. 透過 `AGENT_CARD` 與 `TASK_STATUS` 回傳 A2A Protocol 常見欄位。
3. 若環境變數提供 `JSONRPC_TLS_CERT` 與 `JSONRPC_TLS_KEY`，將自動啟用 TLS。

實務部署時建議：
* 在容器啟動腳本中掛載 ACM/自簽憑證，或改由 ALB/NLB/API Gateway 終止 TLS。
* 搭配 `kubernetes/service-jsonrpc.yaml` 讓叢集內其他 Pod（或透過 `kubectl port-forward` 的測試流程）將流量導入 Root Agent。
"""
from __future__ import annotations

import json
import os
import ssl
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict

# Agent Card 範例：描述遠端 Agent 的功能、輸入輸出與聯絡資訊。
AGENT_CARD: Dict[str, Any] = {
    "agent_id": "root-agent-jsonrpc",
    "name": "Root Agent (JSON-RPC 入口)",
    "capabilities": [
        "task.dispatch.weather",  # 呼叫 Weather Agent
        "task.dispatch.train",    # 呼叫 Train Agent
        "task.summarize"          # 呼叫 Summary Agent
    ],
    "protocol": {
        "type": "json-rpc",
        "version": "2.0",
        "transport": "https"
    },
    "maintainer": {
        "team": "A2A Demo",
        "email": "a2a@example.com"
    }
}

# 任務狀態範例，實際情境應存放在資料庫或快取。
TASK_STATUS: Dict[str, Any] = {
    "weather-task": {"status": "completed", "result": {"city": "Kaohsiung", "forecast": "Sunny"}},
    "train-task": {"status": "in_progress", "eta": "2024-05-01T00:00:00Z"}
}


class JSONRPCHandler(BaseHTTPRequestHandler):
    server_version = "A2AJSONRPC/0.1"

    def _read_json(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:  # noqa: TRY003 - 只針對 JSON 解析
            raise ValueError("invalid json body") from exc

    def _write_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_POST(self) -> None:  # noqa: N802 - http.server 既有命名
        try:
            request = self._read_json()
        except ValueError:
            self._write_json(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": "Parse error"},
                    "id": None,
                },
                status=400,
            )
            return

        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params", {})

        if method == "a2a.describe_agent":
            result = AGENT_CARD
        elif method == "a2a.get_task_status":
            task_id = params.get("task_id")
            if not task_id:
                self._write_json(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32602, "message": "task_id is required"},
                        "id": request_id,
                    },
                    status=400,
                )
                return
            result = TASK_STATUS.get(task_id, {"status": "not_found"})
        elif method == "a2a.submit_task":
            payload = params.get("payload", {})
            result = {
                "accepted": True,
                "task_id": payload.get("task_id", "demo-task"),
                "message": "Task received by JSON-RPC gateway"
            }
        else:
            self._write_json(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method {method} not found"},
                    "id": request_id,
                },
                status=404,
            )
            return

        self._write_json({"jsonrpc": "2.0", "result": result, "id": request_id})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - 保留原始名稱
        if os.getenv("JSONRPC_QUIET", "false").lower() == "true":
            return
        super().log_message(format, *args)


def run_server(host: str = "0.0.0.0", port: int = 50010) -> None:
    """啟動 JSON-RPC 伺服器，並視需要套用 TLS。"""
    httpd = HTTPServer((host, port), JSONRPCHandler)

    cert_path = os.getenv("JSONRPC_TLS_CERT")
    key_path = os.getenv("JSONRPC_TLS_KEY")
    if cert_path and key_path:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        print(f"[JSON-RPC] HTTPS 伺服器啟動於 https://{host}:{port}")
    else:
        print(f"[JSON-RPC] HTTP 伺服器啟動於 http://{host}:{port}")

    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
