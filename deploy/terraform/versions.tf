# =============================================================================
# ConductorAI - Terraform Version Constraints
# =============================================================================
# Defines the minimum Terraform version and required provider versions.
# Pin providers to minor versions (~>) for stability with patch updates.
# =============================================================================

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }

  # ---------------------------------------------------
  # Remote State Configuration (uncomment for team use)
  # ---------------------------------------------------
  # backend "s3" {
  #   bucket         = "conductorai-terraform-state"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-west-2"
  #   dynamodb_table = "conductorai-terraform-locks"
  #   encrypt        = true
  # }
}
