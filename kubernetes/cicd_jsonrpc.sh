#!/bin/bash
set -euo pipefail

AWS_REGION=${AWS_REGION:-ap-southeast-1}
EKS_CLUSTER_NAME=${EKS_CLUSTER_NAME:-ds-eks-cluster}
K8S_NAMESPACE=${K8S_NAMESPACE:-a2a-demo}
JSONRPC_SERVICE_MANIFEST=${JSONRPC_SERVICE_MANIFEST:-kubernetes/service-jsonrpc.yaml}
JSONRPC_SERVICE_NAME=${JSONRPC_SERVICE_NAME:-root-agent-jsonrpc}
JSONRPC_TARGET_PORT=${JSONRPC_TARGET_PORT:-50010}
LOCAL_PORT=${LOCAL_PORT:-50500}
JSONRPC_PATH=${JSONRPC_PATH:-/jsonrpc}
JSONRPC_SUBMIT_PARAMS=${JSONRPC_SUBMIT_PARAMS:-'{"payload": {"loan_case_id": "jsonrpc-demo"}}'}

banner() {
  echo "================================================="
  echo "$1"
  echo "================================================="
}

cleanup() {
  if [[ -n "${PF_PID:-}" ]]; then
    kill "$PF_PID" 2>/dev/null || true
  fi
}

banner "JSON-RPC 2.0 over HTTP 測試流程"

echo "[1/5] 更新 kubeconfig ($EKS_CLUSTER_NAME)"
aws eks update-kubeconfig --region "$AWS_REGION" --name "$EKS_CLUSTER_NAME"

if ! kubectl get deploy -n "$K8S_NAMESPACE" root-agent >/dev/null 2>&1; then
  echo "❌ 尚未找到 root-agent Deployment，請先執行 kubernetes/cicd.sh 部署完整環境。"
  exit 1
fi

echo "[2/5] 套用 JSON-RPC 專用 Service"
kubectl apply -f "$JSONRPC_SERVICE_MANIFEST"

ENDPOINT="http://127.0.0.1:${LOCAL_PORT}${JSONRPC_PATH}"

echo "[3/5] 確認 Root Agent JSON-RPC Pod 就緒"
kubectl rollout status -n "$K8S_NAMESPACE" deploy/root-agent --timeout=120s

echo "[4/5] 透過 port-forward 驗證叢集內 HTTP 流量"
set +e
kubectl port-forward -n "$K8S_NAMESPACE" "svc/${JSONRPC_SERVICE_NAME}" \
  "${LOCAL_PORT}:${JSONRPC_TARGET_PORT}" >/tmp/jsonrpc_port_forward.log 2>&1 &
PF_PID=$!
trap cleanup EXIT
sleep 5
if ! kill -0 "$PF_PID" 2>/dev/null; then
  echo "❌ 無法建立 port-forward，log 如下："
  cat /tmp/jsonrpc_port_forward.log
  exit 1
fi
set -e

echo "  - 呼叫 a2a.describe_agent (${ENDPOINT})"
python services/jsonrpc_gateway/client.py \
  --endpoint "$ENDPOINT" \
  --method a2a.describe_agent

echo "  - 呼叫 a2a.submit_task (${ENDPOINT})"
python services/jsonrpc_gateway/client.py \
  --endpoint "$ENDPOINT" \
  --method a2a.submit_task \
  --params "$JSONRPC_SUBMIT_PARAMS"

cleanup
trap - EXIT

echo "[5/5] 完成 JSON-RPC 測試"
