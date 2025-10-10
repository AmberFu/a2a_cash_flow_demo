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

# --- 2. Root Agent 處理 ---
AGENT_NAME="a2a_demo_root_agent"
ECR_IMAGE="${ECR_BASE}/${AGENT_NAME}"
echo "--- Building $AGENT_NAME ---"
docker build -f services/root-agent/Dockerfile -t ${AGENT_NAME}:${VERSION_TAG} services/root-agent --network sagemaker
docker tag ${AGENT_NAME}:${VERSION_TAG} ${ECR_IMAGE}:${VERSION_TAG}
docker push ${ECR_IMAGE}:${VERSION_TAG}
echo "=== Push $AGENT_NAME to ECR Succeeded! Tag: ${VERSION_TAG} ==="


# # --- 3. Remote Agent 1 處理 ---
# AGENT_NAME="a2a_demo_remote_agent1"
# ECR_IMAGE="${ECR_BASE}/${AGENT_NAME}"
# echo "--- Building $AGENT_NAME ---"
# docker build -f services/remote-agent-1/Dockerfile -t ${AGENT_NAME}:${VERSION_TAG} services/remote-agent-1 --network sagemaker
# docker tag ${AGENT_NAME}:${VERSION_TAG} ${ECR_IMAGE}:${VERSION_TAG}
# docker push ${ECR_IMAGE}:${VERSION_TAG}
# echo "=== Push $AGENT_NAME to ECR Succeeded! Tag: ${VERSION_TAG} ==="


# # --- 4. Remote Agent 2 處理 ---
# AGENT_NAME="a2a_demo_remote_agent2"
# ECR_IMAGE="${ECR_BASE}/${AGENT_NAME}"
# echo "--- Building $AGENT_NAME ---"
# docker build -f services/remote-agent-2/Dockerfile -t ${AGENT_NAME}:${VERSION_TAG} services/remote-agent-2 --network sagemaker
# docker tag ${AGENT_NAME}:${VERSION_TAG} ${ECR_IMAGE}:${VERSION_TAG}
# docker push ${ECR_IMAGE}:${VERSION_TAG}
# echo "=== Push $AGENT_NAME to ECR Succeeded! Tag: ${VERSION_TAG} ==="


# --- CD 部分：更新 Kubernetes YAML 與部署 ---
## 說明：此階段連接到 EKS 叢集，更新 Deployment YAML 檔案中的映像標籤，並應用部署。

echo "--- 5. Configure Kubeconfig ---"
aws eks update-kubeconfig --region $AWS_REGION --name $EKS_CLUSTER_NAME
echo "=== Kubeconfig Updated! ==="

# # --- 6. 自動更新 Deployment YAML 映像標籤 ---
# # 使用 sed 替換 Deployment 檔案中的映像標籤，確保使用剛剛推送的 $VERSION_TAG
# # 假設您的 YAML 檔案中的映像標籤目前是 :latest 或 :placeholder
# # 範例：更新 Root Agent 部署
# ROOT_YAML="kubernetes/deployment-root.yaml"
# ROOT_ECR_FULL="${ECR_BASE}/a2a_demo_root_agent"
# echo "Updating $ROOT_YAML with image tag: ${ROOT_ECR_FULL}:${VERSION_TAG}"
# # 這裡假設您在 YAML 檔案中是以特定的行或字串標識映像。
# # 更安全的做法是使用 kustomize 或 helm，但這裡用 sed 實現簡單替換。
# # 假設您 YAML 中是這樣： image: 182399696164.dkr.ecr.ap-southeast-1.amazonaws.com/image/a2a_demo_root_agent:latest
# sed -i "s|a2a_demo_root_agent:latest|a2a_demo_root_agent:${VERSION_TAG}|g" $ROOT_YAML
# kubectl apply -f $ROOT_YAML
# kubectl apply -f kubernetes/service-root.yaml
# kubectl rollout restart deployment root-agent -n $K8S_NAMESPACE

# --- 6. 自動更新 Deployment YAML 映像標籤 (修正 sed 替換邏輯) ---

# 模式說明：
# 1. 我們匹配完整的 ECR 路徑，例如：182399696164.dkr.ecr.ap-southeast-1.amazonaws.com/image/a2a_demo_root_agent
# 2. 我們使用通配符 '.*' 來匹配路徑後面的任何舊標籤 (例如 :latest, :202401010000)
# 3. 將整個匹配到的字串替換為新的 ECR 路徑 + 新的 $VERSION_TAG

# Root Agent 部署
ROOT_YAML="kubernetes/deployment-root.yaml"
ROOT_ECR_PATH="${ECR_BASE}/a2a_demo_root_agent"
echo "Updating $ROOT_YAML with image tag: ${ROOT_ECR_PATH}:${VERSION_TAG}"

# sed 替換邏輯：匹配完整的 ECR 映像路徑和任何舊標籤，並替換為新的 $VERSION_TAG
# 關鍵：這裡我們假設映像路徑是完整的 ECR URL + 映像名稱
# e.g., s|.../a2a_demo_root_agent:.*|.../a2a_demo_root_agent:${VERSION_TAG}|g
sed -i "s|${ROOT_ECR_PATH}:.*|${ROOT_ECR_PATH}:${VERSION_TAG}|g" $ROOT_YAML
kubectl apply -f $ROOT_YAML
kubectl apply -f kubernetes/service-root.yaml
kubectl rollout restart deployment root-agent -n $K8S_NAMESPACE

# # Remote Agent 1 部署
# REMOTE1_YAML="kubernetes/deployment-remote1.yaml"
# REMOTE1_ECR_PATH="${ECR_BASE}/a2a_demo_remote_agent1"
# echo "Updating $REMOTE1_YAML with image tag: ${REMOTE1_ECR_PATH}:${VERSION_TAG}"

# sed -i "s|${REMOTE1_ECR_PATH}:.*|${REMOTE1_ECR_PATH}:${VERSION_TAG}|g" $REMOTE1_YAML
# kubectl apply -f $REMOTE1_YAML
# kubectl apply -f kubernetes/service-remote1.yaml
# kubectl rollout restart deployment remote-agent-1 -n $K8S_NAMESPACE


# # Remote Agent 2 部署
# REMOTE2_YAML="kubernetes/deployment-remote2.yaml"
# REMOTE2_ECR_PATH="${ECR_BASE}/a2a_demo_remote_agent2"
# echo "Updating $REMOTE2_YAML with image tag: ${REMOTE2_ECR_PATH}:${VERSION_TAG}"

# sed -i "s|${REMOTE2_ECR_PATH}:.*|${REMOTE2_ECR_PATH}:${VERSION_TAG}|g" $REMOTE2_YAML
# kubectl apply -f $REMOTE2_YAML
# kubectl apply -f kubernetes/service-remote2.yaml
# kubectl rollout restart deployment remote-agent-2 -n $K8S_NAMESPACE

echo "\n====== CD Deployment Succeeded! ======\n"



# --- 7. 部署後檢查與日誌輸出 ---
echo "Wait for rollout completion (max 120 sec)..."
kubectl rollout status deployment/root-agent -n $K8S_NAMESPACE --timeout=120s
# kubectl rollout status deployment/remote-agent-1 -n $K8S_NAMESPACE --timeout=120s
# kubectl rollout status deployment/remote-agent-2 -n $K8S_NAMESPACE --timeout=120s


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

# # Remote Agent 1 - POD name
# REMOTE_AG1_POD=$(kubectl get pods -n a2a-demo -l app=remote-agent-1 -o jsonpath='{.items[0].metadata.name}')
# echo "\$REMOTE_AG1_POD: $REMOTE_AG1_POD"
# kubectl logs $REMOTE_AG1_POD -n a2a-demo --tail=100
# echo "------"

# # Remote Agent 1 - POD name
# REMOTE_AG2_POD=$(kubectl get pods -n a2a-demo -l app=remote-agent-2 -o jsonpath='{.items[0].metadata.name}')
# echo "\$REMOTE_AG1_POD: $REMOTE_AG2_POD"
# kubectl logs $REMOTE_AG2_POD -n a2a-demo --tail=100
# echo "------"