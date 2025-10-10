# terraform/variables.tf

# --- AWS Provider 變數 ---
variable "region" {
  description = "AWS region for all resources."
  type        = string
  default     = "ap-southeast-1" # 您的預設區域
}

# --- DynamoDB 變數 ---
variable "a2a_tasks_table_name" {
  description = "DynamoDB table for a2a task status"
  type        = string
}

variable "a2a_audit_table_name" {
  description = "DynamoDB table for a2a task audit usage (read only)"
  type        = string
}

# --- SQS Queues & EventBridge 變數 ---
variable "remote_a_queue_name" {
  description = "SQS Queues for Remote A agent"
  type        = string
}

variable "remote_b_queue_name" {
  description = "SQS Queues for Remote A agent"
  type        = string
}

variable "callback_queue_name" {
  description = "SQS Queues for Remote A agent"
  type        = string
}

variable "hitl_queue_name" {
  description = "SQS Queues for Remote A agent"
  type        = string
}

# --- IAM Role and Policy for EventBridge to SQS 變數 ---
variable "eventbridge_to_sqs_role_name" {
  description = "IAM Role for EventBridge to SQS"
  type        = string
}

variable "eventbridge_sqs_send_policy_attachment_name" {
  description = "IAM Policy for EventBridge to SQS"
  type        = string
}

# --- EventBridge Bus and Rules 變數 ---
variable "a2a_bus_name" {
  description = "Name of EventBridge Bus"
  type        = string
}

variable "dispatch_remote_a_rule_name" {
  description = "Name of EventBridge Rules for agent A"
  type        = string
}

variable "dispatch_remote_b_rule_name" {
  description = "Name of EventBridge Rules for agent B"
  type        = string
}

# --- VPC/EKS 網路變數 (部署 EKS 叢集後需要填入) ---
variable "vpc_id" {
  description = "The VPC ID where the EKS cluster and Redis reside."
  type        = string
}

variable "eks_worker_node_sg_id" {
  description = "The Security Group ID used by EKS Worker Nodes (where Agent Pods run). This is CRITICAL for Redis connectivity."
  type        = string
}

# --- 現有 Redis 資訊變數 (d-redis-sg) ---
variable "redis_endpoint" {
  description = "The Primary Endpoint address of the existing d-redis-sg cluster."
  type        = string
  default     = "d-redis-sg-iqd4qt.serverless.apse1.cache.amazonaws.com"
}

variable "redis_port" {
  description = "The port of the existing d-redis-sg cluster."
  type        = number
  default     = 6379
}

variable "redis_target_sg_id" {
  description = "One of the Security Group IDs attached to the d-redis-sg cluster that we will modify to allow EKS traffic."
  type        = string
  default     = "sg-0c52cb92e89306efe" # 使用您提供的其中一個 ID
}