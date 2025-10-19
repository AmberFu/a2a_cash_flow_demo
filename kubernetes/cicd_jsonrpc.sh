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

echo "  - 呼叫 a2a.describe_agent"
python services/jsonrpc_gateway/client.py \
  --endpoint "http://127.0.0.1:${LOCAL_PORT}${DEPLOY_JSONRPC_PATH}" \
  --method a2a.describe_agent

echo "  - 呼叫 a2a.submit_task"
python services/jsonrpc_gateway/client.py \
  --endpoint "http://127.0.0.1:${LOCAL_PORT}${DEPLOY_JSONRPC_PATH}" \
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
