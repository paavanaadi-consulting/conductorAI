# =============================================================================
# ConductorAI - IAM Configuration (IRSA)
# =============================================================================
# IAM Role for Service Accounts (IRSA) allows ConductorAI pods to securely
# access AWS Secrets Manager without embedding credentials. The role is bound
# to a specific Kubernetes service account via OIDC federation.
# =============================================================================

# -----------------------------------------------------------------------------
# IRSA Module - ConductorAI Secrets Manager Access
# -----------------------------------------------------------------------------

module "conductorai_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "${local.cluster_name}-conductorai-secrets"

  # Attach custom policy for Secrets Manager access
  role_policy_arns = {
    secrets_manager = aws_iam_policy.conductorai_secrets.arn
  }

  # Bind to the ConductorAI service account in the conductorai namespace
  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["conductorai:conductorai"]
    }
  }

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# IAM Policy - Secrets Manager Read Access
# -----------------------------------------------------------------------------

resource "aws_iam_policy" "conductorai_secrets" {
  name        = "${local.cluster_name}-secrets-manager-access"
  description = "Allows ConductorAI pods to read secrets from AWS Secrets Manager"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecretsManagerRead"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
          "secretsmanager:ListSecretVersionIds",
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}/${var.environment}/*"
      },
      {
        Sid    = "SecretsManagerList"
        Effect = "Allow"
        Action = [
          "secretsmanager:ListSecrets",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "secretsmanager:ResourceTag/Project" = var.project_name
          }
        }
      },
    ]
  })

  tags = local.common_tags
}
