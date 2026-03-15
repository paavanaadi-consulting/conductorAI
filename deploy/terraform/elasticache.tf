# =============================================================================
# ConductorAI - ElastiCache Redis Configuration
# =============================================================================
# Redis is the backbone of ConductorAI's message bus (pub/sub) and state
# persistence layer. This configuration deploys a Redis replication group
# with cluster mode, automatic failover, and encryption.
# =============================================================================

# -----------------------------------------------------------------------------
# Subnet Group - place Redis in private subnets
# -----------------------------------------------------------------------------

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${local.cluster_name}-redis-subnet"
  subnet_ids = module.vpc.private_subnets

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-redis-subnet"
  })
}

# -----------------------------------------------------------------------------
# Security Group - restrict access to EKS nodes on port 6379
# -----------------------------------------------------------------------------

resource "aws_security_group" "redis" {
  name_prefix = "${local.cluster_name}-redis-"
  description = "Security group for ConductorAI Redis cluster"
  vpc_id      = module.vpc.vpc_id

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-redis-sg"
  })

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group_rule" "redis_ingress_eks" {
  description              = "Allow Redis access from EKS worker nodes"
  type                     = "ingress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  source_security_group_id = module.eks.node_security_group_id
  security_group_id        = aws_security_group.redis.id
}

resource "aws_security_group_rule" "redis_egress" {
  description       = "Allow all outbound traffic"
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.redis.id
}

# -----------------------------------------------------------------------------
# Redis Replication Group
# -----------------------------------------------------------------------------

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${local.cluster_name}-redis"
  description          = "ConductorAI Redis cluster for message bus and state persistence"

  # Engine configuration
  engine               = "redis"
  engine_version       = "7.0"
  node_type            = var.redis_node_type
  parameter_group_name = aws_elasticache_parameter_group.redis.name

  # Cluster mode enabled with a single shard and replicas
  num_node_groups         = 1
  replicas_per_node_group = var.redis_num_cache_nodes - 1

  # High availability
  automatic_failover_enabled = true
  multi_az_enabled           = true

  # Networking
  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.redis.id]
  port               = 6379

  # Encryption
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  # Maintenance
  maintenance_window       = "sun:05:00-sun:06:00"
  snapshot_retention_limit = 7
  snapshot_window          = "03:00-04:00"
  auto_minor_version_upgrade = true

  # Apply changes during maintenance window to avoid disruption
  apply_immediately = false

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-redis"
  })
}

# -----------------------------------------------------------------------------
# Parameter Group - enable cluster mode
# -----------------------------------------------------------------------------

resource "aws_elasticache_parameter_group" "redis" {
  name   = "${local.cluster_name}-redis-params"
  family = "redis7"

  description = "ConductorAI Redis parameter group with cluster mode enabled"

  parameter {
    name  = "cluster-enabled"
    value = "yes"
  }

  # Pub/Sub related tuning for ConductorAI message bus
  parameter {
    name  = "notify-keyspace-events"
    value = "Ex"
  }

  tags = local.common_tags
}
