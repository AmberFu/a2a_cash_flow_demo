#!/bin/bash
set -euo pipefail

# 參數可透過環境變數覆寫，預設與現有 cicd.sh 對齊
AWS_REGION=${AWS_REGION:-ap-southeast-1}
EKS_CLUSTER_NAME=${EKS_CLUSTER_NAME:-ds-eks-cluster}
K8S_NAMESPACE=${K8S_NAMESPACE:-a2a-demo}
JSONRPC_SERVICE_NAME=${JSONRPC_SERVICE_NAME:-root-agent-jsonrpc}
JSONRPC_PATH=${JSONRPC_PATH:-/jsonrpc}
LOCAL_PORT=${LOCAL_PORT:-50500}
JSONRPC_PUBLIC_ENDPOINT=${JSONRPC_PUBLIC_ENDPOINT:-}

banner() {
  echo "================================================="
  echo "$1"
  echo "================================================="
}

banner "JSON-RPC 2.0 over HTTPS 測試流程"

echo "[1/5] 更新 kubeconfig ($EKS_CLUSTER_NAME)"
aws eks update-kubeconfig --region "$AWS_REGION" --name "$EKS_CLUSTER_NAME"

echo "[2/5] 套用 JSON-RPC 專用 Service"
kubectl apply -f kubernetes/service-jsonrpc.yaml

# 讀取 Deployment 中 JSON-RPC 相關設定，若未設定則採用預設值
CONTAINER_NAME=${CONTAINER_NAME:-root-agent-container}
DEPLOY_JSONRPC_PATH=$(kubectl get deploy -n "$K8S_NAMESPACE" root-agent -o \
  jsonpath='{range .spec.template.spec.containers[?(@.name=="'"$CONTAINER_NAME"'")].env[?(@.name=="JSONRPC_BASE_PATH")]}{.value}{end}' 2>/dev/null || true)
DEPLOY_JSONRPC_PORT=$(kubectl get deploy -n "$K8S_NAMESPACE" root-agent -o \
  jsonpath='{range .spec.template.spec.containers[?(@.name=="'"$CONTAINER_NAME"'")].env[?(@.name=="JSONRPC_PORT")]}{.value}{end}' 2>/dev/null || true)
DEPLOY_JSONRPC_ENABLED=$(kubectl get deploy -n "$K8S_NAMESPACE" root-agent -o \
  jsonpath='{range .spec.template.spec.containers[?(@.name=="'"$CONTAINER_NAME"'")].env[?(@.name=="JSONRPC_ENABLED")]}{.value}{end}' 2>/dev/null || true)

if [[ -z "$DEPLOY_JSONRPC_PATH" ]]; then
  DEPLOY_JSONRPC_PATH="$JSONRPC_PATH"
fi
if [[ -z "$DEPLOY_JSONRPC_PORT" ]]; then
  DEPLOY_JSONRPC_PORT="50000"
fi

if [[ -n "$DEPLOY_JSONRPC_ENABLED" && "$DEPLOY_JSONRPC_ENABLED" != "true" && "$DEPLOY_JSONRPC_ENABLED" != "True" ]]; then
  echo "⚠️  偵測到 Deployment 中 JSONRPC_ENABLED=$DEPLOY_JSONRPC_ENABLED，請確認已於 Kubernetes Deployment 內開啟 JSON-RPC 功能。"
fi

# 重新正規化 JSON-RPC Path，確保至少包含前導斜線並避免重複斜線導致 404。
JSONRPC_SANITIZED_PATH=$(INPUT_PATH="$DEPLOY_JSONRPC_PATH" python - <<'PY'
import os

path = os.environ.get("INPUT_PATH", "").strip()
if not path:
    path = "/jsonrpc"
if not path.startswith("/"):
    path = "/" + path
canonical = path.rstrip("/") or "/"
paths = [canonical]
if canonical != "/":
    paths.append(canonical + "/")
print("|".join(paths))
PY
)

IFS='|' read -r -a JSONRPC_PATH_CANDIDATES <<<"$JSONRPC_SANITIZED_PATH"
# 追加預設 /jsonrpc 以避免部署尚未更新環境變數時測試失敗
if [[ " ${JSONRPC_PATH_CANDIDATES[*]} " != *" /jsonrpc "* ]]; then
  JSONRPC_PATH_CANDIDATES+=("/jsonrpc")
fi

echo "[3/5] 透過 port-forward 驗證叢集內 HTTP 流量"
kubectl rollout status -n "$K8S_NAMESPACE" deploy/root-agent --timeout=60s
kubectl port-forward -n "$K8S_NAMESPACE" "svc/${JSONRPC_SERVICE_NAME}" "${LOCAL_PORT}:${DEPLOY_JSONRPC_PORT}" >/tmp/jsonrpc_port_forward.log 2>&1 &
PF_PID=$!
trap 'kill $PF_PID 2>/dev/null || true' EXIT

# 等待 port-forward 建立連線
for _ in {1..10}; do
  if grep -q "Forwarding from" /tmp/jsonrpc_port_forward.log; then
    break
  fi
  if ! kill -0 $PF_PID 2>/dev/null; then
    echo "❌ port-forward 已終止，log 如下："
    cat /tmp/jsonrpc_port_forward.log
    exit 1
  fi
  sleep 1
done

if ! grep -q "Forwarding from" /tmp/jsonrpc_port_forward.log; then
  echo "❌ 無法建立 port-forward，log 如下："
  cat /tmp/jsonrpc_port_forward.log
  exit 1
fi

call_jsonrpc_client() {
  local endpoint="$1"
  local method="$2"
  local params="${3:-}"

  if [[ -n "$params" ]]; then
    python services/jsonrpc_gateway/client.py \
      --endpoint "$endpoint" \
      --method "$method" \
      --params "$params"
  else
    python services/jsonrpc_gateway/client.py \
      --endpoint "$endpoint" \
      --method "$method"
  fi
}

SUCCESS_PATH=""
for candidate_path in "${JSONRPC_PATH_CANDIDATES[@]}"; do
  endpoint="http://127.0.0.1:${LOCAL_PORT}${candidate_path}"
  echo "  - 嘗試呼叫 a2a.describe_agent (endpoint: $endpoint)"
  if call_jsonrpc_client "$endpoint" a2a.describe_agent; then
    SUCCESS_PATH="$candidate_path"
    break
  fi
  echo "    ⚠️  端點 $endpoint 呼叫失敗，嘗試下一個候選路徑"
done

if [[ -z "$SUCCESS_PATH" ]]; then
  echo "❌ 無法透過任何候選 JSON-RPC Path 呼叫 a2a.describe_agent，請確認 Root Agent 映像或環境變數是否已更新。"
  echo "   候選路徑: ${JSONRPC_PATH_CANDIDATES[*]}"
  echo "   Port-forward log:"
  cat /tmp/jsonrpc_port_forward.log
  exit 1
fi

echo "  - 呼叫 a2a.submit_task (endpoint: http://127.0.0.1:${LOCAL_PORT}${SUCCESS_PATH})"
call_jsonrpc_client "http://127.0.0.1:${LOCAL_PORT}${SUCCESS_PATH}" a2a.submit_task '{"payload": {"loan_case_id": "jsonrpc-trial"}}'

echo "[4/5] （選擇性）測試公開 HTTPS 入口"
if [[ -n "$JSONRPC_PUBLIC_ENDPOINT" ]]; then
  python services/jsonrpc_gateway/client.py \
    --endpoint "$JSONRPC_PUBLIC_ENDPOINT" \
    --method a2a.describe_agent \
    --insecure
else
  echo "⚠️  未設定 JSONRPC_PUBLIC_ENDPOINT，略過公開 HTTPS 測試"
fi

echo "[5/5] 清理 port-forward"
kill $PF_PID 2>/dev/null || true
trap - EXIT

echo "完成 JSON-RPC 測試"
