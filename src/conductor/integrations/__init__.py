"""
conductor.integrations - External Service Integration Layer
============================================================

This package provides adapters for external services that ConductorAI
agents depend on. Each integration is abstracted behind an interface
so implementations can be swapped (e.g., OpenAI → Anthropic, or real → mock).

Sub-packages:
    llm/   - Large Language Model providers (OpenAI, Anthropic, Mock)

Future (Days 8-9):
    notifications/ - Slack, email, webhook notifications
    cicd/          - GitHub Actions, Jenkins, GitLab CI
    cloud/         - AWS, GCP, Azure cloud providers
"""

__all__: list[str] = []
