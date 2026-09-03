# AWS deployment boundary

This Terraform is a reviewable starting point for Seoul-region deployment:

- Application Load Balancer with TLS and WebSocket pass-through
- Two ECS Fargate tasks in private subnets
- PostgreSQL 16 on encrypted RDS
- TLS/encrypted ElastiCache Redis for ephemeral transcripts
- CloudWatch logs and separate ALB/API/data security groups

It intentionally requires an existing VPC, subnets, certificate, and immutable container image. It has **not** been applied to a real AWS account. Before production use, move credentials to Secrets Manager, enable RDS deletion protection and Multi-AZ, add Redis authentication/failover, configure WAF, autoscaling, VPC endpoints, KMS key policies, backups, alarms, and a formal medical-data security review.

`AUTO_CREATE_SCHEMA=false` is set for ECS. Run `alembic upgrade head` as a one-off migration task before rolling out the service.
