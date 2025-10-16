# terraform/variables.tf

# --- AWS Provider 變數 ---
variable "region" {
  description = "AWS region for all resources."
  type        = string
  default     = "ap-southeast-1"
}

# ----------------------------------------
# DynamoDB Tables
# ----------------------------------------
variable "a2a_tasks_table_name" {
  description = "DynamoDB table for a2a task status (LangGraph checkpoint)"
  type        = string
}

variable "a2a_audit_table_name" {
  description = "DynamoDB table for a2a task audit usage (read only)"
  type        = string
}

# ----------------------------------------
# SQS Queues
# ----------------------------------------
variable "remote_a_queue_name" {
  description = "SQS Queue for Remote Agent A"
  type        = string
}

variable "remote_b_queue_name" {
  description = "SQS Queue for Remote Agent B"
  type        = string
}

variable "callback_queue_name" {
  description = "SQS Queue for callbacks from Remote Agents"
  type        = string
}

variable "hitl_queue_name" {
  description = "SQS Queue for Human-in-the-Loop requests"
  type        = string
}

# ----------------------------------------
# EventBridge
# ----------------------------------------
variable "a2a_bus_name" {
  description = "Name of custom EventBridge Bus"
  type        = string
}

variable "dispatch_remote_a_rule_name" {
  description = "Name of EventBridge Rule for dispatching to Remote Agent A"
  type        = string
}

variable "dispatch_remote_b_rule_name" {
  description = "Name of EventBridge Rule for dispatching to Remote Agent B"
  type        = string
}

variable "eventbridge_to_sqs_role_name" {
  description = "IAM Role for EventBridge to send messages to SQS"
  type        = string
}

variable "eventbridge_sqs_send_policy_attachment_name" {
  description = "IAM Policy name for EventBridge to SQS permissions"
  type        = string
}

# ----------------------------------------
# EKS Cluster (CRITICAL for IRSA)
# ----------------------------------------
variable "eks_cluster_name" {
  description = "Name of the EKS cluster where the Agents will be deployed. This is required for IRSA (IAM Roles for Service Accounts)."
  type        = string
}

# ----------------------------------------
# Kubernetes Namespace
# ----------------------------------------
variable "k8s_namespace" {
  description = "Kubernetes namespace where all Agent service accounts will be created."
  type        = string
  default     = "default"
}

# ----------------------------------------
# Root Agent - Service Account & IAM Role
# ----------------------------------------
variable "root_agent_sa_name" {
  description = "Kubernetes Service Account name for the Root Agent."
  type        = string
  default     = "ds-a2a-root-agent-sa"
}

variable "root_agent_sa_role_name" {
  description = "IAM Role name for the Root Agent Service Account (IRSA). This role grants permissions to access DynamoDB, EventBridge, and SQS (callback/hitl queues)."
  type        = string
}

# ----------------------------------------
# Remote Agent A - Service Account & IAM Role
# ----------------------------------------
variable "remote_agent_a_sa_name" {
  description = "Kubernetes Service Account name for Remote Agent A."
  type        = string
  default     = "ds-a2a-remote-agent-a-sa"
}

variable "remote_agent_a_sa_role_name" {
  description = "IAM Role name for Remote Agent A Service Account (IRSA). This role grants permissions to read from remote-a SQS queue and send to callback/hitl queues."
  type        = string
}

# ----------------------------------------
# Remote Agent B - Service Account & IAM Role
# ----------------------------------------
variable "remote_agent_b_sa_name" {
  description = "Kubernetes Service Account name for Remote Agent B."
  type        = string
  default     = "ds-a2a-remote-agent-b-sa"
}

variable "remote_agent_b_sa_role_name" {
  description = "IAM Role name for Remote Agent B Service Account (IRSA). This role grants permissions to read from remote-b SQS queue and send to callback/hitl queues."
  type        = string
}

# ----------------------------------------
# VPC and Security Groups
# ----------------------------------------
variable "vpc_id" {
  description = "The VPC ID where the EKS cluster and Redis reside."
  type        = string
}

variable "eks_worker_node_sg_id" {
  description = "The Security Group ID used by EKS Worker Nodes (where Agent Pods run). This is CRITICAL for Redis connectivity."
  type        = string
}

# ----------------------------------------
# Redis (Existing d-redis-sg)
# ----------------------------------------
variable "redis_endpoint" {
  description = "The Primary Endpoint address of the existing d-redis-sg cluster."
  type        = string
}

variable "redis_port" {
  description = "The port of the existing d-redis-sg cluster."
  type        = number
  default     = 6379
}

variable "redis_target_sg_id" {
  description = "One of the Security Group IDs attached to the d-redis-sg cluster that we will modify to allow EKS traffic."
  type        = string
}