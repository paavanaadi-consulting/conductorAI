# =============================================================================
# ConductorAI - VPC Configuration
# =============================================================================
# Creates a production-grade VPC with public and private subnets across 3 AZs.
# - Public subnets:  NAT gateways, load balancers
# - Private subnets: EKS nodes, ElastiCache, application workloads
# =============================================================================

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${local.cluster_name}-vpc"
  cidr = var.vpc_cidr

  azs             = local.azs
  public_subnets  = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 8, i)]
  private_subnets = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 10)]

  # ---------------------------------------------------------------------------
  # NAT Gateway - single NAT for cost efficiency; use one_nat_gateway_per_az
  # in production for higher availability.
  # ---------------------------------------------------------------------------
  enable_nat_gateway   = true
  single_nat_gateway   = false
  one_nat_gateway_per_az = true

  # ---------------------------------------------------------------------------
  # DNS - required for EKS and service discovery
  # ---------------------------------------------------------------------------
  enable_dns_hostnames = true
  enable_dns_support   = true

  # ---------------------------------------------------------------------------
  # Subnet Tags - required for EKS to discover subnets for load balancers
  # and internal networking.
  # ---------------------------------------------------------------------------
  public_subnet_tags = {
    "kubernetes.io/role/elb"                    = 1
    "kubernetes.io/cluster/${local.cluster_name}" = "owned"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"             = 1
    "kubernetes.io/cluster/${local.cluster_name}" = "shared"
  }

  tags = local.common_tags
}
