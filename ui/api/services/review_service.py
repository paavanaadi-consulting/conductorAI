"""
ConductorAI UI — PR Review Service

Combines GitHub diff fetching with ConductorAI ReviewAgent for
AI-powered code review with complexity and quality scoring.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog

from ui.api.database import get_db
from ui.api.services.conductor_service import ConductorService
from ui.api.services.github_service import GitHubService

logger = structlog.get_logger()

MAX_DIFF_CHARS = 30_000  # Truncate large diffs to fit LLM context


async def review_pr(
    conductor: ConductorService,
    github: GitHubService,
    installation_id: int,
    owner: str,
    repo: str,
    pr_number: int,
    project_id: str,
    submit_to_github: bool = False,
) -> dict[str, Any]:
    """Run AI-powered review on a pull request."""

    # 1. Fetch PR diff
    diff = await github.get_pr_diff(installation_id, owner, repo, pr_number)

    # 2. Fetch PR metadata for title
    prs = await github.list_pull_requests(installation_id, owner, repo, state="all")
    pr_title = ""
    for pr in prs:
        if pr["number"] == pr_number:
            pr_title = pr.get("title", "")
            break

    # 3. Truncate if too large
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n... [truncated for review] ..."

    # 4. Send to ReviewAgent
    review_result = await conductor.review_code(
        code=diff,
        language="diff",
        context=f"Pull Request #{pr_number}: {pr_title} in {owner}/{repo}",
    )

    # 5. Extract scores (default to 5.0 if not found)
    complexity_score = float(review_result.get("score", 5.0))
    quality_score = float(review_result.get("score", 5.0))
    findings = review_result.get("findings", [])
    recommendations = review_result.get("recommendations", [])
    review_summary = review_result.get("review", "No review generated.")

    # 6. Save to database
    review_id = uuid.uuid4().hex
    db = await get_db()
    await db.execute(
        """INSERT INTO pr_reviews
           (id, project_id, pr_number, pr_title, complexity_score, quality_score,
            review_summary, review_comments, findings, recommendations)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            review_id,
            project_id,
            pr_number,
            pr_title,
            complexity_score,
            quality_score,
            review_summary,
            json.dumps([]),
            json.dumps(findings),
            json.dumps(recommendations),
        ),
    )
    await db.commit()

    # 7. Optionally submit to GitHub
    if submit_to_github and github.configured:
        body = f"## AI Code Review\n\n"
        body += f"**Complexity Score**: {complexity_score}/10\n"
        body += f"**Quality Score**: {quality_score}/10\n\n"
        body += f"### Summary\n{review_summary}\n\n"
        if findings:
            body += "### Findings\n" + "\n".join(f"- {f}" for f in findings) + "\n\n"
        if recommendations:
            body += "### Recommendations\n" + "\n".join(f"- {r}" for r in recommendations)

        await github.submit_review(
            installation_id, owner, repo, pr_number, body, event="COMMENT"
        )

    return {
        "id": review_id,
        "pr_number": pr_number,
        "pr_title": pr_title,
        "complexity_score": complexity_score,
        "quality_score": quality_score,
        "review_summary": review_summary,
        "findings": findings,
        "recommendations": recommendations,
    }
