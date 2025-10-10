# 指定 AWS provider，讓 Terraform 知道要操作 AWS 資源
provider "aws" {
  region = var.region
}

# ----------------------------------------
# 區塊 1: DynamoDB (狀態與資料)
# ----------------------------------------

# ds_demo_a2a_tasks - 用來記錄 agent 執行狀態
resource "aws_dynamodb_table" "a2a_tasks_table" {
  name           = var.a2a_tasks_table_name # 表格名稱
  billing_mode   = "PAY_PER_REQUEST"   # 使用 On-Demand 容量模式，適合 demo 用
  hash_key       = "task_id"         # 主鍵 (Primary Key)

  attribute {
    name = "task_id"
    type = "S" # String
  }
}

# 宣告 ds_demo_a2a_audit - 用來記錄審計日誌
resource "aws_dynamodb_table" "a2a_audit_table" {
  name           = var.a2a_audit_table_name
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "task_id"
  range_key      = "ts"             # 排序鍵 (Sort Key)

  attribute {
    name = "task_id"
    type = "S"
  }
  attribute {
    name = "ts"
    type = "N" # Number
  }
}

# 輸出 DynamoDB 表格的 ARN，方便後續在程式碼中使用
output "a2a_tasks_table_arn" {
  value = aws_dynamodb_table.a2a_tasks_table.arn
}

output "a2a_audit_table_arn" {
  value = aws_dynamodb_table.a2a_audit_table.arn
}

# ----------------------------------------
# 區塊 2: SQS Queues & EventBridge (訊息傳遞)
# ----------------------------------------

# SQS.remote-a: 派工給 Remote Agent A 的佇列
resource "aws_sqs_queue" "remote_a_queue" {
  name                      = var.remote_a_queue_name
  visibility_timeout_seconds = 300 # EKS Pod 拉取後處理時間，可調整
}

# SQS.remote-b: 派工給 Remote Agent B 的佇列
resource "aws_sqs_queue" "remote_b_queue" {
  name                      = var.remote_b_queue_name
  visibility_timeout_seconds = 300 # EKS Pod 拉取後處理時間，可調整
}

# SQS.callback: Remote Agent 完成工作後回報給 Root Agent 的佇列
resource "aws_sqs_queue" "callback_queue" {
  name = var.callback_queue_name
}

# SQS.hitl: Remote Agent 需要人工作業時回報給 Root Agent 的佇列
resource "aws_sqs_queue" "hitl_queue" {
  name = var.hitl_queue_name
}

# --- IAM Role and Policy for EventBridge to SQS ---
# IAM Role and Policy for EventBridge to SQS

# 1. 建立 IAM 信任策略 (Trust Policy)，允許 EventBridge 服務扮演此角色
data "aws_iam_policy_document" "eventbridge_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

# 2. 建立 EventBridge 扮演的角色
resource "aws_iam_role" "eventbridge_to_sqs_role" {
  name               = var.eventbridge_to_sqs_role_name
  assume_role_policy = data.aws_iam_policy_document.eventbridge_assume_role.json
}

# 3. 建立 EventBridge 傳送 SQS 訊息的權限策略
data "aws_iam_policy_document" "eventbridge_sqs_send_policy" {
  statement {
    effect = "Allow"
    actions = ["sqs:SendMessage"]
    resources = [
      aws_sqs_queue.remote_a_queue.arn,
      aws_sqs_queue.remote_b_queue.arn,
    ]
  }
}

# 4. 將權限策略附加到 EventBridge 角色上
resource "aws_iam_role_policy" "eventbridge_sqs_send_policy_attachment" {
  name   = var.eventbridge_sqs_send_policy_attachment_name
  role   = aws_iam_role.eventbridge_to_sqs_role.name
  policy = data.aws_iam_policy_document.eventbridge_sqs_send_policy.json
}

# --- EventBridge Bus and Rules ---

# 1. 建立自訂 EventBus (A2A.Dispatch 的事件來源)
resource "aws_cloudwatch_event_bus" "a2a_bus" {
  name = var.a2a_bus_name
}

# 2. 建立 EventBridge 規則: A2A.Dispatch.RemoteA
resource "aws_cloudwatch_event_rule" "dispatch_remote_a_rule" {
  name          = var.dispatch_remote_a_rule_name
  event_bus_name = aws_cloudwatch_event_bus.a2a_bus.name
  description   = "Route A2A.Dispatch.RemoteA events to SQS.remote-a"

  # 匹配 Root Agent 發出的特定事件
  event_pattern = jsonencode({
    source      = ["a2a.cash.flow.root"],
    "detail-type" = ["A2A.Dispatch.RemoteA"]
  })
}

# 3. 規則目標: 將事件導向 SQS.remote-a
resource "aws_cloudwatch_event_target" "remote_a_target" {
  rule      = aws_cloudwatch_event_rule.dispatch_remote_a_rule.name
  arn       = aws_sqs_queue.remote_a_queue.arn
  event_bus_name = aws_cloudwatch_event_bus.a2a_bus.name
  # 指定 EventBridge 用哪個 IAM 角色發送訊息
  role_arn  = aws_iam_role.eventbridge_to_sqs_role.arn 

  # 可選: 傳送固定內容 (Input) 或轉換事件內容 (InputTransformer)
  # 這裡使用原事件內容 (InputPath = "$")，如果需要自訂 SQS 訊息內容，請改用 InputTransformer
  input_path = "$" 
}

# 4. 建立 EventBridge 規則: A2A.Dispatch.RemoteB
resource "aws_cloudwatch_event_rule" "dispatch_remote_b_rule" {
  name          = var.dispatch_remote_b_rule_name
  event_bus_name = aws_cloudwatch_event_bus.a2a_bus.name
  description   = "Route A2A.Dispatch.RemoteB events to SQS.remote-b"
  
  # 匹配 Root Agent 發出的特定事件
  event_pattern = jsonencode({
    source      = ["a2a.cash.flow.root"],
    "detail-type" = ["A2A.Dispatch.RemoteB"]
  })
}

# 5. 規則目標: 將事件導向 SQS.remote-b
resource "aws_cloudwatch_event_target" "remote_b_target" {
  rule      = aws_cloudwatch_event_rule.dispatch_remote_b_rule.name
  arn       = aws_sqs_queue.remote_b_queue.arn
  event_bus_name = aws_cloudwatch_event_bus.a2a_bus.name
  role_arn  = aws_iam_role.eventbridge_to_sqs_role.arn
  input_path = "$"
}

# --- Outputs for EventBridge/SQS ---

output "remote_a_queue_url" {
  value = aws_sqs_queue.remote_a_queue.id
}

output "remote_b_queue_url" {
  value = aws_sqs_queue.remote_b_queue.id
}

output "callback_queue_url" {
  value = aws_sqs_queue.callback_queue.id
}

output "hitl_queue_url" {
  value = aws_sqs_queue.hitl_queue.id
}

output "a2a_event_bus_name" {
    value = aws_cloudwatch_event_bus.a2a_bus.name
}

output "eventbridge_to_sqs_role_arn" {
    value = aws_iam_role.eventbridge_to_sqs_role.arn
}


# ----------------------------------------
# 區塊 3: Redis 連線配置 (僅網路規則)
# ----------------------------------------

# 由於無法建立新的 Redis Cluster，我們僅配置網路規則來允許 EKS 存取現有的 d-redis-sg。
# 我們假設 var.redis_target_sg_id 已經存在於 AWS 中。

# 建立 Ingress 規則到 d-redis-sg 叢集使用的其中一個 SG
resource "aws_security_group_rule" "allow_eks_to_redis" {
  type                     = "ingress"
  from_port                = var.redis_port
  to_port                  = var.redis_port
  protocol                 = "tcp"
  # 允許來自 EKS Worker Node SG 的流量
  source_security_group_id = var.eks_worker_node_sg_id 
  # 目標 Security Group ID (d-redis-sg 正在使用的其中一個 SG)
  security_group_id        = var.redis_target_sg_id 
  description              = "Allow traffic from A2A EKS Pods to d-redis-sg (TCP 6379)"
}

output "redis_host" {
    description = "The endpoint of the existing Redis cluster for LangGraph short-term memory."
    value       = var.redis_endpoint
}

output "redis_port" {
    description = "The port of the existing Redis cluster."
    value       = var.redis_port
}
