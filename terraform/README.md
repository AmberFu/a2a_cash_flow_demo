# Terraform 使用方法

## Pre-request - 安裝 Terraform

安裝 terraform @AWS SegeMaker Studio

```
#安裝
wget -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(grep -oP '(?<=UBUNTU_CODENAME=).*' /etc/os-release || lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform

#確認
sagemaker-user@default:~$ terraform -v
Terraform v1.13.3
on linux_amd64
```


## 開發 main.tf

- main.tf 是主程式
- variables.tf 是定義變數型別跟預設值的檔案
- terraform.tfvars 提供 variables.tf 內變實際值 （不上傳）
- terraform.tfvars.example 請使用此變數值範本替換您的實際內容

### `terraform init`

> 初始化 Terraform 工作目錄，準備運行環境

```
sagemaker-user@default:~/a2a_cash_flow_demo/terraform$ terraform init
Initializing the backend...
Initializing provider plugins...
- Reusing previous version of hashicorp/kubernetes from the dependency lock file
- Reusing previous version of hashicorp/aws from the dependency lock file
- Using previously-installed hashicorp/kubernetes v2.38.0
- Using previously-installed hashicorp/aws v6.14.1

Terraform has been successfully initialized!

You may now begin working with Terraform. Try running "terraform plan" to see
any changes that are required for your infrastructure. All Terraform commands
should now work.

If you ever set or change modules or backend configuration for Terraform,
rerun this command to reinitialize your working directory. If you forget, other
commands will detect it and remind you to do so if necessary.
```

### `terraform plan -out='ds_a2a_plan'`

> 產生一個預覽執行計畫，它會比對你撰寫的設定檔與現有的基礎架構，並顯示 Terraform 即將執行的變更，
> 例如要新增、修改或刪除哪些資源，但不會實際執行任何變更。

```
sagemaker-user@default:~/a2a_cash_flow_demo/terraform$ terraform plan -out='ds_a2a_plan'
...
Changes to Outputs:
  ~ a2a_tasks_table_arn         = "arn:aws:dynamodb:ap-southeast-1:***************:table/DDB_TB_1" -> (known after apply)

─────────────────────────────────────────────────────────────────────────────────────────

Saved the plan to: ds_a2a_plan

To perform exactly these actions, run the following command to apply:
    terraform apply "ds_a2a_plan"
```

### `terraform apply "ds_a2a_plan"`

> 實際執行 Terraform 配置文件中定義的變更，它會建立、更新或刪除基礎設施資源，以使實際狀態與代碼定義相匹配。

```
sagemaker-user@default:~/a2a_cash_flow_demo/terraform$ terraform apply "ds_a2a_plan"
aws_dynamodb_table.a2a_tasks_table: Destroying... [id=DDB_TB_1]
aws_dynamodb_table.a2a_audit_table: Modifying... [id=DDB_TB_2]
aws_dynamodb_table.a2a_audit_table: Modifications complete after 3s [id=DDB_TB_2]
data.aws_iam_policy_document.remote_agent_b_permissions: Reading...
data.aws_iam_policy_document.remote_agent_a_permissions: Reading...
data.aws_iam_policy_document.remote_agent_b_permissions: Read complete after 0s [id=**********]
data.aws_iam_policy_document.remote_agent_a_permissions: Read complete after 0s [id=**********]
aws_dynamodb_table.a2a_tasks_table: Destruction complete after 4s
aws_dynamodb_table.a2a_tasks_table: Creating...
aws_dynamodb_table.a2a_tasks_table: Still creating... [00m10s elapsed]
aws_dynamodb_table.a2a_tasks_table: Still creating... [00m20s elapsed]
aws_dynamodb_table.a2a_tasks_table: Creation complete after 23s [id=DDB_TB_1]
data.aws_iam_policy_document.root_agent_permissions: Reading...
data.aws_iam_policy_document.root_agent_permissions: Read complete after 0s [id=**********]

Apply complete! Resources: 1 added, 1 changed, 1 destroyed.

Outputs:

a2a_audit_table_arn = "arn:aws:dynamodb:ap-southeast-1:***************:table/DDB_TB_2"
a2a_event_bus_name = "a2a-cash-flow-demo-bus"
a2a_tasks_table_arn = "arn:aws:dynamodb:ap-southeast-1:***************:table/DDB_TB_1"
callback_queue_url = "https://sqs.ap-southeast-1.amazonaws.com/***************/a2a-callback-root"
eventbridge_to_sqs_role_arn = "arn:aws:iam::***************:role/a2a-eventbridge-to-sqs-role"
hitl_queue_url = "https://sqs.ap-southeast-1.amazonaws.com/***************/a2a-hitl-root"
redis_host = "d-redis-sg-iqd4qt.serverless.apse1.cache.amazonaws.com"
redis_port = 6379
remote_a_queue_url = "https://sqs.ap-southeast-1.amazonaws.com/***************/a2a-dispatch-remote-a"
remote_agent_a_sa_role_arn = "arn:aws:iam::***************:role/ds-a2a-remote-agent-a-sa-role"
remote_agent_b_sa_role_arn = "arn:aws:iam::***************:role/ds-a2a-remote-agent-b-sa-role"
remote_b_queue_url = "https://sqs.ap-southeast-1.amazonaws.com/***************/a2a-dispatch-remote-b"
root_agent_sa_role_arn = "arn:aws:iam::***************:role/ds-a2a-root-agent-sa-role"
```

## JSON-RPC over HTTPS 與 AWS 元件整合指引

### EKS + ALB (ELBv2) + ACM 憑證
* **Kubernetes Service**：`kubernetes/service-jsonrpc.yaml` 會針對 Root Agent 建立額外的 ClusterIP，讓 ALB Ingress Controller 能把 HTTPS 流量導向現有的 50000 埠（Pod 內部仍維持 HTTP）。
* **Kubernetes Ingress**：`kubernetes/ingress-jsonrpc.yaml` 透過 `alb.ingress.kubernetes.io/*` 註解要求 ALB 建立 HTTPS Listener；`certificate-arn` 指向 ACM 憑證即可完成 TLS 終止。ALB 與 EKS 的關係僅止於 Ingress Controller 代為建立 AWS Load Balancer 與 Target Group，內部 Pod 不需要額外修改。 
* **Terraform 控制點**：
  - ACM 憑證可以在 `terraform/main.tf` 內以 `aws_acm_certificate` 與 `aws_acm_certificate_validation` 管理，再將 ARN 透過 `locals` 或 `kubernetes_ingress` 資源帶入。
  - 若採用 AWS Load Balancer Controller，Terraform 可以用 `kubernetes_manifest` 或 `helm_release` 安裝 Controller，並透過 `kubernetes_ingress` 將 `ingress-jsonrpc.yaml` 的設定模組化。

### EKS + API Gateway
* 若希望由 **API Gateway** 提供自訂網域、WAF 或節流等能力，可將 JSON-RPC Ingress 的 `certificate-arn` 移除，將 ALB 當成 Private NLB/ALB，再透過 API Gateway HTTP API 的 **VPC Link** 對接。TLS 終止由 API Gateway 的自訂網域或預設網域負責，EKS 僅需暴露 HTTP。
* Terraform 可使用 `aws_apigatewayv2_api`、`aws_apigatewayv2_vpc_link`、`aws_apigatewayv2_integration` 等資源，把 API Gateway 指向 Kubernetes Ingress 所建立的 ALB DNS；之後再透過 `aws_apigatewayv2_stage` 與 `aws_apigatewayv2_domain_name` 完成部署。

### EKS + 傳統 ELB (Classic / NLB)
* 若只需要 L4 負載平衡，也可以將 Service type 改為 `LoadBalancer` 並設定 `service.beta.kubernetes.io/aws-load-balancer-type: nlb-ip`。TLS 可在 NLB 上使用 **TLS Listener + Target Group**，或直接在 Pod 內使用 `server.py` 的 TLS 選項，這樣流量會以端到端 HTTPS 傳遞。
* Terraform 可透過 `kubernetes_service` 直接宣告這個 Service；若要手動建立 NLB，則改用 `aws_lb`、`aws_lb_target_group`、`aws_lb_listener` 等資源，然後搭配 `kubernetes_endpoints` 綁定後端 Pod IP。

> ✅ 無論採用哪種組合，Terraform 都能成為單一事實來源：只要在狀態檔裡註冊 ACM 憑證、Load Balancer、API Gateway 等資源，再由 Kubernetes Provider 套用 YAML，即可保留既有變數不變、同時開啟 JSON-RPC over HTTPS 的選項。
