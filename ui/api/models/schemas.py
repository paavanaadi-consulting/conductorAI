"""
ConductorAI UI — Pydantic Request / Response Schemas
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class ProjectCreateRequest(BaseModel):
    name: str
    github_repo: str  # org/repo
    github_app_installation_id: Optional[int] = None
    requirements_yaml: Optional[str] = None
    infra_yaml: Optional[str] = None
    selected_components: list[str] = Field(
        default=["code", "unit_test"],
        description="Subset of: code, unit_test, test_data, deployment, monitoring",
    )


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    github_app_installation_id: Optional[int] = None
    requirements_yaml: Optional[str] = None
    infra_yaml: Optional[str] = None
    selected_components: Optional[list[str]] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    github_repo: str
    github_app_installation_id: Optional[int] = None
    requirements_yaml: Optional[str] = None
    infra_yaml: Optional[str] = None
    last_pipeline_yaml: Optional[str] = None
    selected_components: list[str] = []
    created_at: str
    updated_at: str


class ProjectSummary(BaseModel):
    id: str
    name: str
    github_repo: str
    selected_components: list[str] = []
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Workflow Runs
# ---------------------------------------------------------------------------

class RunProjectRequest(BaseModel):
    selected_components: list[str] = Field(
        default=["code", "unit_test"],
        description="Components to generate: code, unit_test, test_data, deployment, monitoring",
    )
    pipeline_type: str = "auto"


class WorkflowRunResponse(BaseModel):
    id: str
    project_id: str
    status: str
    workflow_id: Optional[str] = None
    selected_components: list[str] = []
    pipeline_yaml: Optional[str] = None
    result_summary: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

class TemplateInfo(BaseModel):
    filename: str
    category: str  # "requirements" or "infrastructure"


class TemplateContent(BaseModel):
    filename: str
    category: str
    content: str


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

class RepoSummary(BaseModel):
    id: int
    full_name: str
    name: str
    description: Optional[str] = None
    html_url: str
    default_branch: str = "main"
    open_issues_count: int = 0


class PRSummary(BaseModel):
    number: int
    title: str
    state: str
    user_login: str
    user_avatar_url: str = ""
    created_at: str
    updated_at: str
    html_url: str
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0


class PRReviewRequest(BaseModel):
    installation_id: int
    submit_to_github: bool = False


class PRReviewResponse(BaseModel):
    id: str
    pr_number: int
    pr_title: Optional[str] = None
    complexity_score: float
    quality_score: float
    review_summary: str
    findings: list[str] = []
    recommendations: list[str] = []
    reviewed_at: str


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    filename: str
    content: str
    valid: bool
    error: Optional[str] = None
