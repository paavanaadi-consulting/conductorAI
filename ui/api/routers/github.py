"""
ConductorAI UI — GitHub Router
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request

from ui.api.database import get_db
from ui.api.models.schemas import (
    PRReviewRequest,
    PRReviewResponse,
    PRSummary,
    RepoSummary,
)
from ui.api.services import review_service

router = APIRouter()


@router.get("/repos", response_model=list[RepoSummary])
async def list_repos(
    request: Request,
    installation_id: int = Query(...),
):
    github_svc = request.app.state.github
    if not github_svc.configured:
        raise HTTPException(status_code=503, detail="GitHub App not configured")

    repos = await github_svc.list_repos(installation_id)
    return [
        RepoSummary(
            id=r["id"],
            full_name=r["full_name"],
            name=r["name"],
            description=r.get("description"),
            html_url=r["html_url"],
            default_branch=r.get("default_branch", "main"),
            open_issues_count=r.get("open_issues_count", 0),
        )
        for r in repos
    ]


@router.get("/repos/{owner}/{repo}/prs", response_model=list[PRSummary])
async def list_prs(
    owner: str,
    repo: str,
    request: Request,
    installation_id: int = Query(...),
    state: str = Query("open"),
):
    github_svc = request.app.state.github
    if not github_svc.configured:
        raise HTTPException(status_code=503, detail="GitHub App not configured")

    prs = await github_svc.list_pull_requests(installation_id, owner, repo, state=state)
    return [
        PRSummary(
            number=pr["number"],
            title=pr["title"],
            state=pr["state"],
            user_login=pr["user"]["login"],
            user_avatar_url=pr["user"].get("avatar_url", ""),
            created_at=pr["created_at"],
            updated_at=pr["updated_at"],
            html_url=pr["html_url"],
            additions=pr.get("additions", 0),
            deletions=pr.get("deletions", 0),
            changed_files=pr.get("changed_files", 0),
        )
        for pr in prs
    ]


@router.post(
    "/repos/{owner}/{repo}/prs/{pr_number}/review",
    response_model=PRReviewResponse,
)
async def review_pr(
    owner: str,
    repo: str,
    pr_number: int,
    req: PRReviewRequest,
    request: Request,
    project_id: str = Query(...),
):
    conductor_svc = request.app.state.conductor
    github_svc = request.app.state.github

    if not github_svc.configured:
        raise HTTPException(status_code=503, detail="GitHub App not configured")

    result = await review_service.review_pr(
        conductor=conductor_svc,
        github=github_svc,
        installation_id=req.installation_id,
        owner=owner,
        repo=repo,
        pr_number=pr_number,
        project_id=project_id,
        submit_to_github=req.submit_to_github,
    )

    return PRReviewResponse(
        id=result["id"],
        pr_number=result["pr_number"],
        pr_title=result.get("pr_title"),
        complexity_score=result["complexity_score"],
        quality_score=result["quality_score"],
        review_summary=result["review_summary"],
        findings=result.get("findings", []),
        recommendations=result.get("recommendations", []),
        reviewed_at=result.get("reviewed_at", ""),
    )


@router.get(
    "/repos/{owner}/{repo}/prs/{pr_number}/review",
    response_model=list[PRReviewResponse],
)
async def get_pr_reviews(
    owner: str,
    repo: str,
    pr_number: int,
    request: Request,
    project_id: str = Query(...),
):
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM pr_reviews WHERE project_id = ? AND pr_number = ? ORDER BY reviewed_at DESC",
        (project_id, pr_number),
    )
    rows = await cursor.fetchall()
    return [
        PRReviewResponse(
            id=r["id"],
            pr_number=r["pr_number"],
            pr_title=r["pr_title"],
            complexity_score=r["complexity_score"],
            quality_score=r["quality_score"],
            review_summary=r["review_summary"],
            findings=json.loads(r["findings"] or "[]"),
            recommendations=json.loads(r["recommendations"] or "[]"),
            reviewed_at=r["reviewed_at"],
        )
        for r in rows
    ]
