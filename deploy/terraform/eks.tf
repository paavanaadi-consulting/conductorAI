# =============================================================================
# ConductorAI - EKS Cluster Configuration
# =============================================================================
# Provisions an EKS cluster with a managed node group for running ConductorAI
# workloads. IRSA (IAM Roles for Service Accounts) is enabled so pods can
# assume fine-grained IAM roles via Kubernetes service accounts.
# =============================================================================

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = local.cluster_name
  cluster_version = var.eks_cluster_version

  # ---------------------------------------------------------------------------
  # Networking
  # ---------------------------------------------------------------------------
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Allow public access to the API server for administration.
  # Restrict via cluster_endpoint_public_access_cidrs in production.
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  # ---------------------------------------------------------------------------
  # IRSA - IAM Roles for Service Accounts
  # ---------------------------------------------------------------------------
  enable_irsa = true

  # ---------------------------------------------------------------------------
  # Cluster Add-ons
  # ---------------------------------------------------------------------------
  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
  }

  # ---------------------------------------------------------------------------
  # Managed Node Group
  # ---------------------------------------------------------------------------
  eks_managed_node_groups = {
    conductorai_workers = {
      name = "${local.cluster_name}-workers"

      instance_types = var.eks_node_instance_types
      capacity_type  = "ON_DEMAND"

      min_size     = var.eks_min_nodes
      max_size     = var.eks_max_nodes
      desired_size = var.eks_min_nodes

      # Labels for pod scheduling
      labels = {
        role        = "worker"
        application = "conductorai"
      }

      tags = merge(local.common_tags, {
        "k8s.io/cluster-autoscaler/enabled"             = "true"
        "k8s.io/cluster-autoscaler/${local.cluster_name}" = "owned"
      })
    }
  }

  tags = local.common_tags
}
