# 指定 AWS provider，讓 Terraform 知道要操作 AWS 資源
provider "aws" {
  region = var.region
}

# 取得 EKS 叢集連線資訊
data "aws_eks_cluster" "this" {
  name = var.eks_cluster_name      # 例如 "ds-eks-cluster"
}

# 取得可用的 Bearer Token（由 AWS CLI 產生）
data "aws_eks_cluster_auth" "this" {
  name = var.eks_cluster_name
}

# 正確設定 Kubernetes Provider
provider "kubernetes" {
  host                   = data.aws_eks_cluster.this.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.this.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.this.token
}


# ----------------------------------------
# 區塊 1: DynamoDB (狀態與資料)
# ----------------------------------------
### checkpoint - langgraph_checkpoint_dynamodb 的 DynamoDBSaver 寫死 PK & SK 
# ds_demo_a2a_tasks - 用來記錄 agent 執行狀態
# ds_demo_a2a_tasks - LangGraph checkpoint table (PK/SK)
resource "aws_dynamodb_table" "a2a_tasks_table" {
  name         = var.a2a_tasks_table_name
  billing_mode = "PAY_PER_REQUEST"

  # <<< 這裡改成 PK/SK >>>
  hash_key  = "PK"
  range_key = "SK"

  # --- 必須宣告所有被 key/GSI 使用的屬性 ---
  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  # GSI 用到的屬性
  attribute {
    name = "checkpoint_ns"
    type = "S"
  }

  attribute {
    name = "checkpoint_id"
    type = "S"
  }

  # 保留你原本的 GSI（查 checkpoint_ns + checkpoint_id）
  global_secondary_index {
    name            = "checkpoint_ns-checkpoint_id-index"
    hash_key        = "checkpoint_ns"
    range_key       = "checkpoint_id"
    projection_type = "ALL"
  }

  tags = {
    Name        = var.a2a_tasks_table_name
    Environment = "demo"
    Purpose     = "langgraph-checkpoint"
  }
}

# 宣告 ds_demo_a2a_audit - 用來記錄審計日誌
resource "aws_dynamodb_table" "a2a_audit_table" {
  name         = var.a2a_audit_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "task_id"
  range_key    = "ts"

  attribute {
    name = "task_id"
    type = "S"
  }
  attribute {
    name = "ts"
    type = "N"
  }

  tags = {
    Name        = var.a2a_audit_table_name
    Environment = "demo"
    Purpose     = "audit-log"
  }
}

# 輸出 DynamoDB 表格的 ARN
output "a2a_tasks_table_arn" {
  value = aws_dynamodb_table.a2a_tasks_table.arn
}

output "a2a_audit_table_arn" {
  value = aws_dynamodb_table.a2a_audit_table.arn
}

# ----------------------------------------
# 區塊 2: SQS Queues & EventBridge (訊息傳遞)
# ----------------------------------------

# SQS.remote-a: 派工給 Remote Agent A (Weather Agent) 的佇列
resource "aws_sqs_queue" "remote_a_queue" {
  name                       = var.remote_a_queue_name
  visibility_timeout_seconds = 300
  message_retention_seconds  = 1209600 # 14 days

  tags = {
    Name        = var.remote_a_queue_name
    Environment = "demo"
  }
}

# SQS.remote-b: 派工給 Remote Agent B (Train Agent) 的佇列
resource "aws_sqs_queue" "remote_b_queue" {
  name                       = var.remote_b_queue_name
  visibility_timeout_seconds = 300
  message_retention_seconds  = 1209600

  tags = {
    Name        = var.remote_b_queue_name
    Environment = "demo"
  }
}

# SQS.summary: 派工給 Summary Agent 的佇列
resource "aws_sqs_queue" "summary_queue" {
  name                       = local.summary_queue_name
  visibility_timeout_seconds = 300
  message_retention_seconds  = 1209600

  tags = {
    Name        = local.summary_queue_name
    Environment = "demo"
  }
}

# SQS.callback: Remote Agent 完成工作後回報給 Root Agent 的佇列
resource "aws_sqs_queue" "callback_queue" {
  name                      = var.callback_queue_name
  message_retention_seconds = 1209600

  tags = {
    Name        = var.callback_queue_name
    Environment = "demo"
  }
}

# SQS.hitl: Remote Agent 需要人工作業時回報給 Root Agent 的佇列
resource "aws_sqs_queue" "hitl_queue" {
  name                      = var.hitl_queue_name
  message_retention_seconds = 1209600

  tags = {
    Name        = var.hitl_queue_name
    Environment = "demo"
  }
}

# ----------------------------------------
# SQS Queue Policies (允許 EventBridge 發送訊息)
# ----------------------------------------

resource "aws_sqs_queue_policy" "remote_a_queue_policy" {
  queue_url = aws_sqs_queue.remote_a_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowEventBridgeToSendMessage"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.remote_a_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_cloudwatch_event_rule.dispatch_remote_a_rule.arn
          }
        }
      }
    ]
  })
}

resource "aws_sqs_queue_policy" "remote_b_queue_policy" {
  queue_url = aws_sqs_queue.remote_b_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowEventBridgeToSendMessage"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.remote_b_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_cloudwatch_event_rule.dispatch_remote_b_rule.arn
          }
        }
      }
    ]
  })
}

resource "aws_sqs_queue_policy" "summary_queue_policy" {
  queue_url = aws_sqs_queue.summary_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowEventBridgeToSendMessage"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.summary_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_cloudwatch_event_rule.dispatch_summary_rule.arn
          }
        }
      }
    ]
  })
}

# ----------------------------------------
# IAM Role for EventBridge to SQS
# ----------------------------------------

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

resource "aws_iam_role" "eventbridge_to_sqs_role" {
  name               = var.eventbridge_to_sqs_role_name
  assume_role_policy = data.aws_iam_policy_document.eventbridge_assume_role.json

  tags = {
    Name        = var.eventbridge_to_sqs_role_name
    Environment = "demo"
  }
}

data "aws_iam_policy_document" "eventbridge_sqs_send_policy" {
  statement {
    effect = "Allow"
    actions = [
      "sqs:SendMessage"
    ]
    resources = [
      aws_sqs_queue.remote_a_queue.arn,
      aws_sqs_queue.remote_b_queue.arn,
      aws_sqs_queue.summary_queue.arn,
    ]
  }
}

resource "aws_iam_role_policy" "eventbridge_sqs_send_policy_attachment" {
  name   = var.eventbridge_sqs_send_policy_attachment_name
  role   = aws_iam_role.eventbridge_to_sqs_role.name
  policy = data.aws_iam_policy_document.eventbridge_sqs_send_policy.json
}

# ----------------------------------------
# EventBridge Bus and Rules
# ----------------------------------------

resource "aws_cloudwatch_event_bus" "a2a_bus" {
  name = var.a2a_bus_name

  tags = {
    Name        = var.a2a_bus_name
    Environment = "demo"
  }
}

resource "aws_cloudwatch_event_rule" "dispatch_remote_a_rule" {
  name           = var.dispatch_remote_a_rule_name
  event_bus_name = aws_cloudwatch_event_bus.a2a_bus.name
  description    = "Route Task.GetWeather events to SQS.remote-a"

  event_pattern = jsonencode({
    source        = ["a2a.root-agent"]
    "detail-type" = ["Task.GetWeather"]
  })

  tags = {
    Name        = var.dispatch_remote_a_rule_name
    Environment = "demo"
  }
}

resource "aws_cloudwatch_event_target" "remote_a_target" {
  rule           = aws_cloudwatch_event_rule.dispatch_remote_a_rule.name
  arn            = aws_sqs_queue.remote_a_queue.arn
  event_bus_name = aws_cloudwatch_event_bus.a2a_bus.name
}

resource "aws_cloudwatch_event_rule" "dispatch_remote_b_rule" {
  name           = var.dispatch_remote_b_rule_name
  event_bus_name = aws_cloudwatch_event_bus.a2a_bus.name
  description    = "Route Task.GetTrainSchedule events to SQS.remote-b"

  event_pattern = jsonencode({
    source        = ["a2a.root-agent"]
    "detail-type" = ["Task.GetTrainSchedule"]
  })

  tags = {
    Name        = var.dispatch_remote_b_rule_name
    Environment = "demo"
  }
}

resource "aws_cloudwatch_event_target" "remote_b_target" {
  rule           = aws_cloudwatch_event_rule.dispatch_remote_b_rule.name
  arn            = aws_sqs_queue.remote_b_queue.arn
  event_bus_name = aws_cloudwatch_event_bus.a2a_bus.name
}

resource "aws_cloudwatch_event_rule" "dispatch_summary_rule" {
  name           = local.dispatch_summary_rule_name
  event_bus_name = aws_cloudwatch_event_bus.a2a_bus.name
  description    = "Route Task.Summarize events to SQS.summary"

  event_pattern = jsonencode({
    source        = ["a2a.root-agent"]
    "detail-type" = ["Task.Summarize"]
  })

  tags = {
    Name        = local.dispatch_summary_rule_name
    Environment = "demo"
  }
}

resource "aws_cloudwatch_event_target" "summary_target" {
  rule           = aws_cloudwatch_event_rule.dispatch_summary_rule.name
  arn            = aws_sqs_queue.summary_queue.arn
  event_bus_name = aws_cloudwatch_event_bus.a2a_bus.name
}

# ----------------------------------------
# 區塊 3: EKS Service Account IAM Roles (IRSA)
# ----------------------------------------

# 取得當前 AWS Account ID 和 OIDC Provider
data "aws_caller_identity" "current" {}

data "aws_eks_cluster" "cluster" {
  name = var.eks_cluster_name
}

# 從 EKS Cluster 取得 OIDC Provider URL (去掉 https://)
locals {
  oidc_provider_url          = replace(data.aws_eks_cluster.cluster.identity[0].oidc[0].issuer, "https://", "")
  summary_agent_sa_name      = "${var.remote_agent_b_sa_name}-summary"
  summary_agent_role_name    = "${var.remote_agent_b_sa_role_name}-summary"
  summary_queue_name         = "${var.remote_b_queue_name}-summary"
  dispatch_summary_rule_name = "${var.dispatch_remote_b_rule_name}-summary"
}

# ========================================
# 3.1 Root Agent Service Account IAM Role
# ========================================
resource "kubernetes_service_account" "root_sa" {
  metadata {
    name      = var.root_agent_sa_name
    namespace = var.k8s_namespace
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.root_agent_sa_role.arn
    }
  }
}

resource "kubernetes_service_account" "remote_a_sa" {
  metadata {
    name      = var.remote_agent_a_sa_name
    namespace = var.k8s_namespace
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.remote_agent_a_sa_role.arn
    }
  }
}

resource "kubernetes_service_account" "remote_b_sa" {
  metadata {
    name      = var.remote_agent_b_sa_name
    namespace = var.k8s_namespace
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.remote_agent_b_sa_role.arn
    }
  }
}

resource "kubernetes_service_account" "summary_sa" {
  metadata {
    name      = local.summary_agent_sa_name
    namespace = var.k8s_namespace
    annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.summary_agent_sa_role.arn
    }
  }
}

data "aws_iam_policy_document" "root_agent_sa_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Federated"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${local.oidc_provider_url}"]
    }
    actions = ["sts:AssumeRoleWithWebIdentity"]
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:${var.k8s_namespace}:${var.root_agent_sa_name}"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "root_agent_sa_role" {
  name               = var.root_agent_sa_role_name
  assume_role_policy = data.aws_iam_policy_document.root_agent_sa_assume_role.json

  tags = {
    Name        = var.root_agent_sa_role_name
    Environment = "demo"
    Purpose     = "eks-service-account-irsa"
    Agent       = "root-agent"
  }
}

data "aws_iam_policy_document" "root_agent_permissions" {
  # DynamoDB 權限
  statement {
    sid    = "DynamoDBAccess"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:DescribeTable",
      "dynamodb:BatchGetItem",
      "dynamodb:BatchWriteItem"
    ]
    resources = [
      aws_dynamodb_table.a2a_tasks_table.arn,
      "${aws_dynamodb_table.a2a_tasks_table.arn}/index/*",
      aws_dynamodb_table.a2a_audit_table.arn
    ]
  }

  # EventBridge 權限 (發送任務到 Remote Agents)
  statement {
    sid    = "EventBridgeAccess"
    effect = "Allow"
    actions = [
      "events:PutEvents"
    ]
    resources = [
      aws_cloudwatch_event_bus.a2a_bus.arn
    ]
  }

  # SQS 權限 (接收 callback 和 HITL 訊息)
  statement {
    sid    = "SQSReceiveAccess"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ChangeMessageVisibility"
    ]
    resources = [
      aws_sqs_queue.callback_queue.arn,
      aws_sqs_queue.hitl_queue.arn
    ]
  }
}

resource "aws_iam_role_policy" "root_agent_permissions" {
  name   = "${var.root_agent_sa_role_name}-permissions"
  role   = aws_iam_role.root_agent_sa_role.name
  policy = data.aws_iam_policy_document.root_agent_permissions.json
}

# ========================================
# 3.2 Remote Agent A Service Account IAM Role
# ========================================

data "aws_iam_policy_document" "remote_agent_a_sa_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Federated"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${local.oidc_provider_url}"]
    }
    actions = ["sts:AssumeRoleWithWebIdentity"]
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:${var.k8s_namespace}:${var.remote_agent_a_sa_name}"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "remote_agent_a_sa_role" {
  name               = var.remote_agent_a_sa_role_name
  assume_role_policy = data.aws_iam_policy_document.remote_agent_a_sa_assume_role.json

  tags = {
    Name        = var.remote_agent_a_sa_role_name
    Environment = "demo"
    Purpose     = "eks-service-account-irsa"
    Agent       = "remote-agent-a"
  }
}

data "aws_iam_policy_document" "remote_agent_a_permissions" {
  # SQS 權限 (接收任務)
  statement {
    sid    = "SQSReceiveFromRemoteA"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ChangeMessageVisibility"
    ]
    resources = [
      aws_sqs_queue.remote_a_queue.arn
    ]
  }

  # SQS 權限 (發送結果)
  statement {
    sid    = "SQSSendToCallback"
    effect = "Allow"
    actions = [
      "sqs:SendMessage",
      "sqs:GetQueueUrl"
    ]
    resources = [
      aws_sqs_queue.callback_queue.arn,
      aws_sqs_queue.hitl_queue.arn
    ]
  }

  # DynamoDB 權限 (可選: 寫審計日誌)
  statement {
    sid    = "DynamoDBAuditAccess"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem"
    ]
    resources = [
      aws_dynamodb_table.a2a_audit_table.arn
    ]
  }
}

resource "aws_iam_role_policy" "remote_agent_a_permissions" {
  name   = "${var.remote_agent_a_sa_role_name}-permissions"
  role   = aws_iam_role.remote_agent_a_sa_role.name
  policy = data.aws_iam_policy_document.remote_agent_a_permissions.json
}

# ========================================
# 3.3 Remote Agent B Service Account IAM Role
# ========================================

data "aws_iam_policy_document" "remote_agent_b_sa_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Federated"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${local.oidc_provider_url}"]
    }
    actions = ["sts:AssumeRoleWithWebIdentity"]
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:${var.k8s_namespace}:${var.remote_agent_b_sa_name}"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "remote_agent_b_sa_role" {
  name               = var.remote_agent_b_sa_role_name
  assume_role_policy = data.aws_iam_policy_document.remote_agent_b_sa_assume_role.json

  tags = {
    Name        = var.remote_agent_b_sa_role_name
    Environment = "demo"
    Purpose     = "eks-service-account-irsa"
    Agent       = "remote-agent-b"
  }
}

data "aws_iam_policy_document" "summary_agent_sa_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Federated"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${local.oidc_provider_url}"]
    }
    actions = ["sts:AssumeRoleWithWebIdentity"]
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:${var.k8s_namespace}:${local.summary_agent_sa_name}"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "summary_agent_sa_role" {
  name               = local.summary_agent_role_name
  assume_role_policy = data.aws_iam_policy_document.summary_agent_sa_assume_role.json

  tags = {
    Name        = local.summary_agent_role_name
    Environment = "demo"
    Purpose     = "eks-service-account-irsa"
    Agent       = "summary-agent"
  }
}

data "aws_iam_policy_document" "remote_agent_b_permissions" {
  # SQS 權限 (接收任務)
  statement {
    sid    = "SQSReceiveFromRemoteB"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ChangeMessageVisibility"
    ]
    resources = [
      aws_sqs_queue.remote_b_queue.arn
    ]
  }

  # SQS 權限 (發送結果)
  statement {
    sid    = "SQSSendToCallback"
    effect = "Allow"
    actions = [
      "sqs:SendMessage",
      "sqs:GetQueueUrl"
    ]
    resources = [
      aws_sqs_queue.callback_queue.arn,
      aws_sqs_queue.hitl_queue.arn
    ]
  }

  # DynamoDB 權限 (可選: 寫審計日誌)
  statement {
    sid    = "DynamoDBAuditAccess"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem"
    ]
    resources = [
      aws_dynamodb_table.a2a_audit_table.arn
    ]
  }
}

resource "aws_iam_role_policy" "remote_agent_b_permissions" {
  name   = "${var.remote_agent_b_sa_role_name}-permissions"
  role   = aws_iam_role.remote_agent_b_sa_role.name
  policy = data.aws_iam_policy_document.remote_agent_b_permissions.json
}

data "aws_iam_policy_document" "summary_agent_permissions" {
  # SQS 權限 (接收任務)
  statement {
    sid    = "SQSReceiveFromSummary"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ChangeMessageVisibility"
    ]
    resources = [
      aws_sqs_queue.summary_queue.arn
    ]
  }

  # SQS 權限 (發送結果)
  statement {
    sid    = "SQSSendToCallback"
    effect = "Allow"
    actions = [
      "sqs:SendMessage",
      "sqs:GetQueueUrl"
    ]
    resources = [
      aws_sqs_queue.callback_queue.arn,
      aws_sqs_queue.hitl_queue.arn
    ]
  }

  # DynamoDB 權限 (可選: 寫審計日誌)
  statement {
    sid    = "DynamoDBAuditAccess"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem"
    ]
    resources = [
      aws_dynamodb_table.a2a_audit_table.arn
    ]
  }
}

resource "aws_iam_role_policy" "summary_agent_permissions" {
  name   = "${local.summary_agent_role_name}-permissions"
  role   = aws_iam_role.summary_agent_sa_role.name
  policy = data.aws_iam_policy_document.summary_agent_permissions.json
}

# ----------------------------------------
# 區塊 4: Redis 連線配置 (僅網路規則)
# ----------------------------------------

resource "aws_security_group_rule" "allow_eks_to_redis" {
  type                     = "ingress"
  from_port                = var.redis_port
  to_port                  = var.redis_port
  protocol                 = "tcp"
  source_security_group_id = var.eks_worker_node_sg_id
  security_group_id        = var.redis_target_sg_id
  description              = "Allow traffic from A2A EKS Pods to d-redis-sg (TCP 6379)"
}

# ----------------------------------------
# Outputs
# ----------------------------------------

output "remote_a_queue_url" {
  value = aws_sqs_queue.remote_a_queue.id
}

output "remote_b_queue_url" {
  value = aws_sqs_queue.remote_b_queue.id
}

output "summary_queue_url" {
  value = aws_sqs_queue.summary_queue.id
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

output "root_agent_sa_role_arn" {
  description = "IAM Role ARN for Root Agent Service Account (IRSA)"
  value       = aws_iam_role.root_agent_sa_role.arn
}

output "remote_agent_a_sa_role_arn" {
  description = "IAM Role ARN for Remote Agent A Service Account (IRSA)"
  value       = aws_iam_role.remote_agent_a_sa_role.arn
}

output "remote_agent_b_sa_role_arn" {
  description = "IAM Role ARN for Remote Agent B Service Account (IRSA)"
  value       = aws_iam_role.remote_agent_b_sa_role.arn
}

output "summary_agent_sa_role_arn" {
  description = "IAM Role ARN for Summary Agent Service Account (IRSA)"
  value       = aws_iam_role.summary_agent_sa_role.arn
}

output "redis_host" {
  description = "The endpoint of the existing Redis cluster for LangGraph short-term memory."
  value       = var.redis_endpoint
}

output "redis_port" {
  description = "The port of the existing Redis cluster."
  value       = var.redis_port
}