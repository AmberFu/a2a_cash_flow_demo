# cd a2a_cash_flow_demo/
# echo "PWD: $PWD"

## CI
# 登錄 ECR 與推送映像
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin 182399696164.dkr.ecr.ap-southeast-1.amazonaws.com
echo "=== Login ECR Succeeded! ==="

# Root Agent Images
ROOT_ECR='182399696164.dkr.ecr.ap-southeast-1.amazonaws.com/image/a2a_demo_root_agent'
echo "docker build -f services/root-agent/Dockerfile -t image/a2a_demo_root_agent:latest services/root-agent --network sagemaker"
docker build -f services/root-agent/Dockerfile -t image/a2a_demo_root_agent:latest services/root-agent --network sagemaker
echo "=== Build Root Agent Docker Succeeded! ==="


echo "docker tag image/a2a_demo_root_agent:latest $ROOT_ECR:latest"
docker tag image/a2a_demo_root_agent:latest $ROOT_ECR:latest
echo "=== Tag Root Agent Docker Succeeded! ==="

echo "docker push $ROOT_ECR:latest"
docker push $ROOT_ECR:latest
echo "=== Push Root Agent to ECR Succeeded! ==="

# Remote Agent 1 Images
REMOTE_AGENT1='182399696164.dkr.ecr.ap-southeast-1.amazonaws.com/image/a2a_demo_remote_agent1'
echo "docker build -f services/remote-agent-1/Dockerfile -t image/a2a_demo_remote_agent1:latest . --network sagemaker"
docker build -f services/remote-agent-1/Dockerfile -t image/a2a_demo_remote_agent1:latest services/remote-agent-1 --network sagemaker
echo "=== Build Remote Agent 1 Docker Succeeded! ==="

echo "docker tag image/a2a_demo_remote_agent1:latest $REMOTE_AGENT1:latest"
docker tag image/a2a_demo_remote_agent1:latest $REMOTE_AGENT1:latest
echo "=== Tag Remote Agent 1 Docker Succeeded! ==="

echo "docker push $REMOTE_AGENT1:latest"
docker push $REMOTE_AGENT1:latest
echo "=== Push Root Agent to ECR Succeeded! ==="


# Remote Agent 2 Images
REMOTE_AGENT2='182399696164.dkr.ecr.ap-southeast-1.amazonaws.com/image/a2a_demo_remote_agent2'
echo "docker build -f services/remote-agent-2/Dockerfile -t a2a_demo_remote_agent2:latest . --network sagemaker"
docker build -f services/remote-agent-2/Dockerfile -t a2a_demo_remote_agent2:latest services/remote-agent-2 --network sagemaker
echo "=== Build Remote Agent 2 Docker Succeeded! ==="

echo "docker tag a2a_demo_remote_agent2:latest $REMOTE_AGENT2:latest"
docker tag a2a_demo_remote_agent2:latest $REMOTE_AGENT2:latest
echo "=== Tag Remote Agent 2 Docker Succeeded! ==="

echo "docker push $REMOTE_AGENT2:latest"
docker push $REMOTE_AGENT2:latest
echo "=== Push Root Agent to ECR Succeeded! ==="



## CD
aws eks update-kubeconfig --region ap-southeast-1 --name ds-eks-cluster

kubectl apply -f kubernetes/deployment-root.yaml
kubectl apply -f kubernetes/service-root.yaml
kubectl rollout restart deployment root-agent -n a2a-demo


kubectl apply -f kubernetes/deployment-remote1.yaml
kubectl apply -f kubernetes/service-remote1.yaml
kubectl rollout restart deployment remote-agent-1 -n a2a-demo


kubectl apply -f kubernetes/deployment-remote2.yaml
kubectl apply -f kubernetes/service-remote2.yaml
kubectl rollout restart deployment remote-agent-2 -n a2a-demo



echo "\n======\n"
echo "Wait a while... sleep 30 sec"
sleep 30

# 確認 POD 狀態
kubectl get pods -n a2a-demo

# 確認 Service 狀態
kubectl get svc -n a2a-demo




## 看佈署上去的 POD 的 LOG
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

# Remote Agent 1 - POD name
REMOTE_AG2_POD=$(kubectl get pods -n a2a-demo -l app=remote-agent-2 -o jsonpath='{.items[0].metadata.name}')
echo "\$REMOTE_AG1_POD: $REMOTE_AG2_POD"
kubectl logs $REMOTE_AG2_POD -n a2a-demo --tail=100
echo "------"



# ## 測試 A2A 溝通 (最關鍵)
# ## 進入 Root Agent Pod:
# ROOT_POD=$(kubectl get pods -n a2a-demo -l app=root-agent -o jsonpath='{.items[0].metadata.name}')
# kubectl exec -it $ROOT_POD -n a2a-demo -- /bin/bash

# ## 在 Pod 內部測試連線
# # 測試連線 remote-agent-1
# curl http://remote-agent-1-service:50001
# # 預期輸出：{"status": "OK", "agent": "Remote Agent 1", "port": 50001}

# # 測試連線 remote-agent-2
# curl http://remote-agent-2-service:50002
# # 預期輸出：{"status": "OK", "agent": "Remote Agent 2", "port": 50002}





### example:
# kubectl apply -f app-search-k8s.yaml

# # 只需要執行一次(已完成)
# # helm install dmg-srv-cub-spending-insights dmg-srv-cub-spending-insights/ -n midcpdmg01

# # 更新 IMAGE 後 重新佈署
# helm upgrade dmg-srv-cub-spending-insights dmg-srv-cub-spending-insights/ -n midcpdmg01

# # 更新 cofig 後 強制重新佈署
# kubectl rollout restart deployment dmg-srv-cub-spending-insights -n midcpdmg01

# sleep 30

# # 看佈署上去的 POD 的 LOG
# export POD_NAME=$(kubectl get pods -n midcpdmg01 -l app=dmg-srv-cub-spending-insights -o jsonpath="{.items[0].metadata.name}")
# echo "POD_NAME: $POD_NAME"
# kubectl logs $POD_NAME -n midcpdmg01 --tail 100


