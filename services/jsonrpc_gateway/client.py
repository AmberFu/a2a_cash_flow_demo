"""簡易 JSON-RPC 2.0 測試用戶端。

用法：
    python client.py --endpoint https://jsonrpc.example.com/jsonrpc --method a2a.describe_agent
"""
from __future__ import annotations

import argparse
import json
import ssl
import urllib.request
from typing import Any, Dict

DEFAULT_HEADERS = {"Content-Type": "application/json"}


def call_jsonrpc(endpoint: str, method: str, params: Dict[str, Any] | None = None,
                 *, request_id: str = "cli-1", ca_cert: str | None = None,
                 insecure: bool = False) -> Dict[str, Any]:
    """對指定 endpoint 發送 JSON-RPC 請求。"""
    payload = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}).encode("utf-8")

    context: ssl.SSLContext | None = None
    if endpoint.startswith("https://"):
        if insecure:
            context = ssl._create_unverified_context()
        else:
            context = ssl.create_default_context(cafile=ca_cert)

    request = urllib.request.Request(endpoint, data=payload, headers=DEFAULT_HEADERS, method="POST")
    with urllib.request.urlopen(request, context=context, timeout=10) as response:  # noqa: S310 - 採用 urllib 官方 API
        body = response.read().decode("utf-8")
        return json.loads(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="JSON-RPC 測試工具")
    parser.add_argument("--endpoint", required=True, help="JSON-RPC 入口，例如 https://jsonrpc.example.com/jsonrpc")
    parser.add_argument("--method", default="a2a.describe_agent", help="要呼叫的 JSON-RPC 方法")
    parser.add_argument("--params", default="{}", help="JSON 字串格式的 params，例如 '{\"task_id\": \"demo\"}'")
    parser.add_argument("--ca-cert", dest="ca_cert", help="自訂 CA 憑證路徑")
    parser.add_argument("--insecure", action="store_true", help="忽略 TLS 憑證驗證（測試用）")
    args = parser.parse_args(argv)

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as exc:  # noqa: TRY003 - CLI 只需提示輸入錯誤
        parser.error(f"params 不是合法的 JSON：{exc}")
        return 2

    response = call_jsonrpc(args.endpoint, args.method, params, ca_cert=args.ca_cert, insecure=args.insecure)
    print(json.dumps(response, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
