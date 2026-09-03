variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-2"
}

variable "name" {
  description = "Resource name prefix"
  type        = string
  default     = "careflow"
}

variable "vpc_id" {
  description = "Existing VPC ID"
  type        = string
}

variable "public_subnet_ids" {
  description = "At least two public subnets for the ALB"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "At least two private subnets for ECS, RDS, and ElastiCache"
  type        = list(string)
}

variable "container_image" {
  description = "Immutable ECR image URI including digest or tag"
  type        = string
}

variable "certificate_arn" {
  description = "ACM certificate ARN for the HTTPS listener"
  type        = string
}

variable "database_password" {
  description = "Prototype database password; use Secrets Manager injection in production"
  type        = string
  sensitive   = true
}

