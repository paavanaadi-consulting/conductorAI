# =============================================================================
# ConductorAI - Outputs
# =============================================================================
# Values exported after apply for use by CI/CD pipelines, kubectl config,
# and application configuration.
# =============================================================================

# -----------------------------------------------------------------------------
# EKS
# -----------------------------------------------------------------------------

output "eks_cluster_endpoint" {
  description = "Endpoint URL for the EKS cluster API server."
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_name" {
  description = "Name of the EKS cluster."
  value       = module.eks.cluster_name
}

# -----------------------------------------------------------------------------
# ElastiCache Redis
# -----------------------------------------------------------------------------

output "redis_primary_endpoint" {
  description = "Primary endpoint for the Redis replication group (configuration endpoint for cluster mode)."
  value       = aws_elasticache_replication_group.redis.configuration_endpoint_address
}

output "redis_port" {
  description = "Port number for the Redis cluster."
  value       = aws_elasticache_replication_group.redis.port
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------

output "vpc_id" {
  description = "ID of the VPC."
  value       = module.vpc.vpc_id
}

# -----------------------------------------------------------------------------
# Additional Outputs (useful for downstream configuration)
# -----------------------------------------------------------------------------

output "eks_cluster_certificate_authority" {
  description = "Base64-encoded certificate authority data for the EKS cluster."
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "conductorai_irsa_role_arn" {
  description = "IAM role ARN for the ConductorAI Kubernetes service account (IRSA)."
  value       = module.conductorai_irsa.iam_role_arn
}

output "private_subnet_ids" {
  description = "IDs of the private subnets where workloads run."
  value       = module.vpc.private_subnets
}
