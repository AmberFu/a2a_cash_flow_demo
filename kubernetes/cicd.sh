#!/bin/bash
set -e # 任何指令失敗時，立即退出腳本

# --- 變數設定 (請根據您的環境確認) ---
AWS_REGION="ap-southeast-1"
AWS_ACCOUNT_ID="182399696164"
EKS_CLUSTER_NAME="ds-eks-cluster"
K8S_NAMESPACE="a2a-demo"
# 使用時間戳作為唯一的版本標籤 (tag)
VERSION_TAG=$(date +%Y%m%d%H%M%S) 
# ECR Repository Base URL
ECR_BASE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/image"

echo "================================================="
echo "  A2A Agent CI/CD Pipeline Started"
echo "================================================="
echo "  VERSION_TAG: $VERSION_TAG"
echo "  ECR_BASE: $ECR_BASE"
echo "================================================="

# --- CI 部分：建置、標籤與推送映像 ---
## 說明：此階段負責將您的程式碼打包成 Docker 映像，並推送到 ECR (Elastic Container Registry)。

echo "--- 1. ECR Login ---"
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
echo "=== Login ECR Succeeded! ==="

# --- 2. Root Agent 處理 - create ECR image ---
AGENT_NAME="a2a_demo_root_agent"
ECR_IMAGE="${ECR_BASE}/${AGENT_NAME}"
echo "--- Building $AGENT_NAME ---"
docker build -f services/root-agent/Dockerfile -t ${AGENT_NAME}:${VERSION_TAG} services/root-agent --network sagemaker
docker tag ${AGENT_NAME}:${VERSION_TAG} ${ECR_IMAGE}:${VERSION_TAG}
docker push ${ECR_IMAGE}:${VERSION_TAG}
echo "=== Push $AGENT_NAME to ECR Succeeded! Tag: ${VERSION_TAG} ==="


# --- 3. Remote Agent 1 處理 - create ECR image ---
AGENT_NAME="a2a_demo_remote_agent1"
ECR_IMAGE="${ECR_BASE}/${AGENT_NAME}"
echo "--- Building $AGENT_NAME ---"
docker build -f services/remote-agent-1/Dockerfile -t ${AGENT_NAME}:${VERSION_TAG} services/remote-agent-1 --network sagemaker
docker tag ${AGENT_NAME}:${VERSION_TAG} ${ECR_IMAGE}:${VERSION_TAG}
docker push ${ECR_IMAGE}:${VERSION_TAG}
echo "=== Push $AGENT_NAME to ECR Succeeded! Tag: ${VERSION_TAG} ==="


# --- 4. Remote Agent 2 處理 - create ECR image ---
# AGENT_NAME="a2a_demo_remote_agent2"
# ECR_IMAGE="${ECR_BASE}/${AGENT_NAME}"
# echo "--- Building $AGENT_NAME ---"
# docker build -f services/remote-agent-2/Dockerfile -t ${AGENT_NAME}:${VERSION_TAG} services/remote-agent-2 --network sagemaker
# docker tag ${AGENT_NAME}:${VERSION_TAG} ${ECR_IMAGE}:${VERSION_TAG}
# docker push ${ECR_IMAGE}:${VERSION_TAG}
# echo "=== Push $AGENT_NAME to ECR Succeeded! Tag: ${VERSION_TAG} ==="


# --- 5. Summary Agent 處理 - create ECR image ---
# AGENT_NAME="a2a_demo_summary_agent"
# ECR_IMAGE="${ECR_BASE}/${AGENT_NAME}"
# echo "--- Building $AGENT_NAME ---"
# docker build -f services/summary-agent/Dockerfile -t ${AGENT_NAME}:${VERSION_TAG} services/summary-agent --network sagemaker
# docker tag ${AGENT_NAME}:${VERSION_TAG} ${ECR_IMAGE}:${VERSION_TAG}
# docker push ${ECR_IMAGE}:${VERSION_TAG}
# echo "=== Push $AGENT_NAME to ECR Succeeded! Tag: ${VERSION_TAG} ==="


# --- CD 部分：更新 Kubernetes YAML 與部署 ---
## 說明：此階段連接到 EKS 叢集，更新 Deployment YAML 檔案中的映像標籤，並應用部署。

echo "--- 6. Configure Kubeconfig ---"
aws eks update-kubeconfig --region $AWS_REGION --name $EKS_CLUSTER_NAME
echo "=== Kubeconfig Updated! ==="

# --- 6. 自動更新 Deployment 映像標籤並部署 (使用 kubectl set image) ---

# 設置變數
AGENT_NAME="a2a_demo_root_agent"
ROOT_ECR_PATH="${ECR_BASE}/${AGENT_NAME}"
FULL_IMAGE_TAG="${ROOT_ECR_PATH}:${VERSION_TAG}"

echo "--- 7. 部署 Root Agent (更新映像標籤) ---"
echo "  - 使用映像: ${FULL_IMAGE_TAG}"

# 確認 configmap 有更新
kubectl apply -f kubernetes/configmap-agent-models.yaml

# 使用 kubectl set image 更新 Deployment，這會觸發滾動更新
kubectl set image deployment/root-agent \
  "root-agent-container=${FULL_IMAGE_TAG}" \
  -n $K8S_NAMESPACE

# 套用 Service YAML (確保 Service 存在且指向正確的 Pods)
kubectl apply -f kubernetes/service-root.yaml

echo "=== Root Agent Deployment Update Triggered! ==="

# Remote Agent 1 部署
REMOTE1_AGENT_NAME="a2a_demo_remote_agent1"
REMOTE1_ECR_PATH="${ECR_BASE}/${REMOTE1_AGENT_NAME}"
REMOTE1_FULL_IMAGE_TAG="${REMOTE1_ECR_PATH}:${VERSION_TAG}"

echo "--- 8. 部署 Remote Agent 1 (更新映像標籤) ---"
echo "  - 使用映像: ${REMOTE1_FULL_IMAGE_TAG}"

kubectl set image deployment/remote-agent-1 \
  "remote-agent-1-container=${REMOTE1_FULL_IMAGE_TAG}" \
  -n $K8S_NAMESPACE

kubectl apply -f kubernetes/service-remote1.yaml

echo "=== Remote Agent 1 Deployment Update Triggered! ==="

# Remote Agent 2 部署
REMOTE2_AGENT_NAME="a2a_demo_remote_agent2"
REMOTE2_ECR_PATH="${ECR_BASE}/${REMOTE2_AGENT_NAME}"
REMOTE2_FULL_IMAGE_TAG="${REMOTE2_ECR_PATH}:${VERSION_TAG}"

echo "--- 9. 部署 Remote Agent 2 (更新映像標籤) ---"
echo "  - 使用映像: ${REMOTE2_FULL_IMAGE_TAG}"

kubectl set image deployment/remote-agent-2 \
  "remote-agent-2-container=${REMOTE2_FULL_IMAGE_TAG}" \
  -n $K8S_NAMESPACE

kubectl apply -f kubernetes/service-remote2.yaml

echo "=== Remote Agent 2 Deployment Update Triggered! ==="

# Summary Agent 部署
SUMMARY_AGENT_NAME="a2a_demo_summary_agent"
SUMMARY_ECR_PATH="${ECR_BASE}/${SUMMARY_AGENT_NAME}"
SUMMARY_FULL_IMAGE_TAG="${SUMMARY_ECR_PATH}:${VERSION_TAG}"

echo "--- 10. 部署 Summary Agent (更新映像標籤) ---"
echo "  - 使用映像: ${SUMMARY_FULL_IMAGE_TAG}"

kubectl set image deployment/summary-agent \
  "summary-agent-container=${SUMMARY_FULL_IMAGE_TAG}" \
  -n $K8S_NAMESPACE

kubectl apply -f kubernetes/service-summary.yaml

echo "=== Summary Agent Deployment Update Triggered! ==="

echo "\n====== CD Deployment Succeeded! ======\n"



# --- 7. 部署後檢查與日誌輸出 ---
echo "Wait for rollout completion (max 300 sec)..."
kubectl rollout status deployment/root-agent -n $K8S_NAMESPACE --timeout=300s
# kubectl rollout status deployment/remote-agent-1 -n $K8S_NAMESPACE --timeout=300s
# kubectl rollout status deployment/remote-agent-2 -n $K8S_NAMESPACE --timeout=300s


sleep 120
echo "\n--- POD and Service Status ---"
kubectl get pods -n $K8S_NAMESPACE
kubectl get svc -n $K8S_NAMESPACE

# 日誌查看區塊
# Root Agent - POD name
ROOT_POD=$(kubectl get pods -n a2a-demo -l app=root-agent -o jsonpath='{.items[0].metadata.name}')
echo "\$ROOT_POD: $ROOT_POD"
kubectl logs $ROOT_POD -n a2a-demo --tail=100
echo "------"

# Remote Agent 1 - POD name
REMOTE_AG1_POD=$(kubectl get pods -n a2a-demo -l app=remote-agent-1 -o jsonpath='{.items[0].metadata.name}')
echo "\$REMOTE_AG1_POD: $REMOTE_AG1_POD"
kubectl logs $REMOTE_AG1_POD -n a2a-demo --tail=100
echo "------"

# Remote Agent 2 - POD name
REMOTE_AG2_POD=$(kubectl get pods -n a2a-demo -l app=remote-agent-2 -o jsonpath='{.items[0].metadata.name}')
echo "\$REMOTE_AG2_POD: $REMOTE_AG2_POD"
kubectl logs $REMOTE_AG2_POD -n a2a-demo --tail=100
echo "------"

# Summary Agent - POD name
SUMMARY_POD=$(kubectl get pods -n a2a-demo -l app=summary-agent -o jsonpath='{.items[0].metadata.name}')
echo "\$SUMMARY_POD: $SUMMARY_POD"
kubectl logs $SUMMARY_POD -n a2a-demo --tail=100
echo "------"



######## 測試時：
# 確保您的 kubectl 已配置並指向 EKS 叢集
# kubectl port-forward svc/root-agent-service 50000:50000 --namespace a2a-demo
# Remote Agent 1 服務（啟用）
kubectl port-forward svc/remote-agent-1-service 50001:50001 --namespace a2a-demo
# Remote Agent 2 服務（可視需求啟用）
# kubectl port-forward svc/remote-agent-2-service 50002:50002 --namespace a2a-demo
# Summary Agent 服務（可視需求啟用）
# kubectl port-forward svc/summary-agent-service 50003:50003 --namespace a2a-demo
# 執行後，這些指令會持續運行在前景

# 測試 POST /tasks
# # POST /tasks (Start Workflow)
# TASK_ID=$(curl -s -X POST http://127.0.0.1:50000/tasks \
#   -H 'Content-Type: application/json' \
#   -d '{
#     "loan_case_id": "LCASE-20251014-001"
#   }' | jq -r .task_id)
# echo "Started Task ID: $TASK_ID"




# ## 在 EKS Pod 內直接驗證 IRSA 是否成功
# ROOT_POD=$(kubectl get pods -n a2a-demo -l app=root-agent -o jsonpath='{.items[0].metadata.name}')
# kubectl exec -it $ROOT_POD -n a2a-demo -- bash

# # 這條命令會嘗試使用 IRSA 提供的臨時憑證去獲取調用者的身份
# > aws sts get-caller-identity
# > 應該看到類似 arn:aws:iam::<account_id>:role/eks-a2a-root-agent-sa-role 的 ARN

# # 確認您的 EKS 集群已啟用 OIDC Provider
# EKS_CLUSTER_NAME="ds-eks-cluster"
# aws eks describe-cluster --name $EKS_CLUSTER_NAME --query "cluster.identity.oidc.issuer" --output text
# """
# sagemaker-user@default:~$ EKS_CLUSTER_NAME="ds-eks-cluster"
# aws eks describe-cluster --name $EKS_CLUSTER_NAME --query "cluster.identity.oidc.issuer" --output text
# https://oidc.eks.ap-southeast-1.amazonaws.com/id/1DDF0561C57CB2ABDFE048B7FEB180FA
# """

## 確認部署錯誤或問題：尤其是當 POD 起不起來時
# kubectl -n a2a-demo get events --sort-by=.lastTimestamp

## 確認狀態？！
# kubectl -n a2a-demo get rs -l app=root-agent -o wide

# ## 怎麼查 Node 的 security group?
# EKS_CLUSTER_NAME="ds-eks-cluster"
# NODE_GROUP="ds-node-group"
# aws eks describe-nodegroup \
#   --cluster-name $EKS_CLUSTER_NAME \
#   --nodegroup-name $NODE_GROUP \
#   --query "nodegroup.resources" \
#   --output json
# """
# {
#     "autoScalingGroups": [
#         {
#             "name": "eks-ds-node-group-96cab485-d9d4-71f4-7527-9f08bf578fc3"
#         }
#     ]
# }
# """
# # 1) 先拿到 ASG 名稱（你已經有了）
# ASG_NAME="eks-ds-node-group-96cab485-d9d4-71f4-7527-9f08bf578fc3"

# # 2) 取出這個 ASG 目前的 EC2 instance IDs
# INSTANCE_IDS=$(aws autoscaling describe-auto-scaling-groups \
#   --auto-scaling-group-names "$ASG_NAME" \
#   --query "AutoScalingGroups[0].Instances[*].InstanceId" \
#   --output text)

# # 3) 直接查每台 EC2 綁定的 SG
# aws ec2 describe-instances \
#   --instance-ids $INSTANCE_IDS \
#   --query "Reservations[].Instances[].SecurityGroups[].GroupId" \
#   --output text