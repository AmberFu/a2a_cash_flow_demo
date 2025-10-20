# JSON-RPC Gateway 範例

此資料夾示範如何為 Root Agent 建立 JSON-RPC 2.0 over HTTPS 的入口，並提供：

1. `server.py`：簡化版伺服器，可直接部署為 Pod 或 sidecar，或複製其中的 JSON-RPC handler 到 `services/root-agent`。
2. `client.py`：測試用 CLI，支援 TLS/自簽憑證與 `a2a.*` 方法，方便整合 CI/CD。
3. Agent Card / 任務狀態等範例欄位，示範如何與既有 A2A Protocol 對齊。

```
Client (JSON-RPC CLI) ---> HTTPS ----> server.py (或 Root Agent JSON-RPC endpoint)
         ^                                                |
         |                                                v
         +-------- a2a.* method response --------- graph_app / EventBridge / SQS
```

## 快速測試

```bash
# 啟動伺服器（HTTP）
python services/jsonrpc_gateway/server.py

# 另一個終端呼叫 describe_agent
python services/jsonrpc_gateway/client.py \
  --endpoint http://127.0.0.1:50000/jsonrpc \
  --method a2a.describe_agent
```

若需要端到端 HTTPS，可先準備憑證：

```bash
openssl req -x509 -nodes -days 1 -newkey rsa:2048 \
  -keyout /tmp/jsonrpc.key -out /tmp/jsonrpc.crt \
  -subj "/CN=jsonrpc.example.com"

JSONRPC_TLS_CERT=/tmp/jsonrpc.crt JSONRPC_TLS_KEY=/tmp/jsonrpc.key \
python services/jsonrpc_gateway/server.py

python services/jsonrpc_gateway/client.py \
  --endpoint https://127.0.0.1:50000/jsonrpc \
  --method a2a.describe_agent \
  --insecure
```

其中 `jsonrpc.crt` 與 `jsonrpc.key` 分別是伺服器端 TLS 憑證與私鑰：

* **本機/測試**：可使用上述指令建立自簽憑證，並以 `JSONRPC_TLS_CERT`、`JSONRPC_TLS_KEY` 環境變數指向檔案。
* **EKS/正式環境**：建議改由 AWS ACM 建立公有或私有憑證，並透過 Ingress(ALB) 或 API Gateway 終止 TLS，不直接把私鑰放進 Pod。

## 與 Kubernetes / Terraform 的對應

* `kubernetes/service-jsonrpc.yaml`：建立 ClusterIP Service，將 `app: root-agent` Pod 換成穩定的 DNS（`root-agent-jsonrpc.a2a-demo.svc.cluster.local`），供叢集內其他 Pod 或測試 port-forward 直接呼叫 `/jsonrpc`。
* `terraform/README.md`：說明如何在 Terraform 控制 ACM、ALB、API Gateway、Route53 等元件，仍維持單一事實來源。

您可以依據實際情況將 `server.py` 直接包入 Root Agent 映像，或把既有 Root Agent 改成支援 JSON-RPC 的 HTTP 介面（本專案已示範如何在 FastAPI 中新增 `/jsonrpc` 路徑）。若保留 EventBridge + SQS，則同時具備同步（JSON-RPC）與非同步（EventBridge/SQS）兩種路徑。

## 可用的 Python / LangGraph JSON-RPC 套件

* **`fastapi-jsonrpc`**：提供 decorator 與 schema validation，可直接掛在 FastAPI 之上處理 JSON-RPC 2.0。適合希望重用 FastAPI 生態系的場景。
* **`json-rpc` / `jsonrpcserver`**：獨立於 Web framework，能與 ASGI/WSGI 整合，適合想自行控制路由與傳輸層的部署。
* **LangGraph/LangChain** 目前沒有內建 JSON-RPC adapter，但可藉由上述套件包裝自訂 endpoint，再呼叫 `graph_app.invoke` 與 `graph_app.get_state`。本專案的 `/jsonrpc` 實作即示範如何串接。
