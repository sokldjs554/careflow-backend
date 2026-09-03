locals {
  tags = {
    Project   = var.name
    ManagedBy = "terraform"
  }
}

resource "aws_security_group" "alb" {
  name_prefix = "${var.name}-alb-"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_security_group" "api" {
  name_prefix = "${var.name}-api-"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

resource "aws_security_group" "data" {
  name_prefix = "${var.name}-data-"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }

  tags = local.tags
}

resource "aws_db_subnet_group" "main" {
  name       = var.name
  subnet_ids = var.private_subnet_ids
  tags       = local.tags
}

resource "aws_db_instance" "postgres" {
  identifier              = "${var.name}-postgres"
  engine                  = "postgres"
  engine_version          = "16"
  instance_class          = "db.t4g.micro"
  allocated_storage       = 20
  storage_encrypted       = true
  db_name                 = "careflow"
  username                = "careflow"
  password                = var.database_password
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.data.id]
  backup_retention_period = 7
  multi_az                = false
  publicly_accessible     = false
  skip_final_snapshot     = true
  deletion_protection     = false
  tags                    = local.tags
}

resource "aws_elasticache_subnet_group" "main" {
  name       = var.name
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${var.name}-redis"
  description                = "CareFlow ephemeral transcript store"
  engine                     = "redis"
  node_type                  = "cache.t4g.micro"
  port                       = 6379
  num_cache_clusters         = 1
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [aws_security_group.data.id]
  tags                       = local.tags
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.name}"
  retention_in_days = 30
  tags              = local.tags
}

resource "aws_iam_role" "execution" {
  name = "${var.name}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
  tags = local.tags
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_ecs_cluster" "main" {
  name = var.name
  tags = local.tags
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = var.container_image
    essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = [
      { name = "ENVIRONMENT", value = "aws" },
      { name = "AUTO_CREATE_SCHEMA", value = "false" },
      { name = "DATABASE_URL", value = "postgresql+asyncpg://careflow:${urlencode(var.database_password)}@${aws_db_instance.postgres.address}:5432/careflow" },
      { name = "REDIS_URL", value = "rediss://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0" }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "api"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "python -c 'import urllib.request; urllib.request.urlopen(\"http://localhost:8000/health/live\")'"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 20
    }
  }])
  tags = local.tags
}

resource "aws_lb" "api" {
  name               = "${var.name}-api"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids
  tags               = local.tags
}

resource "aws_lb_target_group" "api" {
  name        = "${var.name}-api"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    path    = "/health/ready"
    matcher = "200"
  }
  tags = local.tags
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.api.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_ecs_service" "api" {
  name            = "${var.name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.https]
  tags       = local.tags
}
