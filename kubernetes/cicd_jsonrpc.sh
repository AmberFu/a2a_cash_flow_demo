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

echo "[2/5] 套用 JSON-RPC 專用 Service / Ingress"
kubectl apply -f kubernetes/service-jsonrpc.yaml
kubectl apply -f kubernetes/ingress-jsonrpc.yaml

echo "[3/5] 透過 port-forward 驗證叢集內 HTTP 流量"
kubectl port-forward -n "$K8S_NAMESPACE" "svc/${JSONRPC_SERVICE_NAME}" "${LOCAL_PORT}:50000" >/tmp/jsonrpc_port_forward.log 2>&1 &
PF_PID=$!
trap 'kill $PF_PID 2>/dev/null || true' EXIT
sleep 5

echo "  - 呼叫 a2a.describe_agent"
python services/jsonrpc_gateway/client.py \
  --endpoint "http://127.0.0.1:${LOCAL_PORT}${JSONRPC_PATH}" \
  --method a2a.describe_agent

echo "  - 呼叫 a2a.submit_task"
python services/jsonrpc_gateway/client.py \
  --endpoint "http://127.0.0.1:${LOCAL_PORT}${JSONRPC_PATH}" \
  --method a2a.submit_task \
  --params '{"payload": {"loan_case_id": "jsonrpc-trial"}}'

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
