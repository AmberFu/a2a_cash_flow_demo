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
