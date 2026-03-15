"""
ConductorAI UI — Projects Router
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Request

from ui.api.database import get_db
from ui.api.models.schemas import (
    ProjectCreateRequest,
    ProjectResponse,
    ProjectSummary,
    ProjectUpdateRequest,
    RunProjectRequest,
    WorkflowRunResponse,
)
from ui.api.services.workflow_builder import build_workflow_definition

logger = structlog.get_logger()
router = APIRouter()


def _row_to_project(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "github_repo": row["github_repo"],
        "github_app_installation_id": row["github_app_installation_id"],
        "requirements_yaml": row["requirements_yaml"],
        "infra_yaml": row["infra_yaml"],
        "last_pipeline_yaml": row["last_pipeline_yaml"],
        "selected_components": json.loads(row["selected_components"] or "[]"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(req: ProjectCreateRequest, request: Request):
    db = await get_db()

    # Check for existing project with same github_repo
    cursor = await db.execute(
        "SELECT * FROM projects WHERE github_repo = ?", (req.github_repo,)
    )
    existing = await cursor.fetchone()
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Project with this GitHub repo already exists",
                "existing_project": _row_to_project(existing),
            },
        )

    project_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO projects
           (id, name, github_repo, github_app_installation_id,
            requirements_yaml, infra_yaml, selected_components, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id,
            req.name,
            req.github_repo,
            req.github_app_installation_id,
            req.requirements_yaml,
            req.infra_yaml,
            json.dumps(req.selected_components),
            now,
            now,
        ),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = await cursor.fetchone()
    return ProjectResponse(**_row_to_project(row))


@router.get("/", response_model=list[ProjectSummary])
async def list_projects(
    request: Request,
    github_repo: Optional[str] = None,
):
    db = await get_db()
    if github_repo:
        cursor = await db.execute(
            "SELECT * FROM projects WHERE github_repo = ?", (github_repo,)
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        )
    rows = await cursor.fetchall()
    return [
        ProjectSummary(
            id=r["id"],
            name=r["name"],
            github_repo=r["github_repo"],
            selected_components=json.loads(r["selected_components"] or "[]"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, request: Request):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse(**_row_to_project(row))


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, req: ProjectUpdateRequest, request: Request):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    updates = []
    params = []
    if req.name is not None:
        updates.append("name = ?")
        params.append(req.name)
    if req.github_app_installation_id is not None:
        updates.append("github_app_installation_id = ?")
        params.append(req.github_app_installation_id)
    if req.requirements_yaml is not None:
        updates.append("requirements_yaml = ?")
        params.append(req.requirements_yaml)
    if req.infra_yaml is not None:
        updates.append("infra_yaml = ?")
        params.append(req.infra_yaml)
    if req.selected_components is not None:
        updates.append("selected_components = ?")
        params.append(json.dumps(req.selected_components))

    if updates:
        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(project_id)
        await db.execute(
            f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", params
        )
        await db.commit()

    cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = await cursor.fetchone()
    return ProjectResponse(**_row_to_project(row))


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, request: Request):
    db = await get_db()
    await db.execute("DELETE FROM workflow_runs WHERE project_id = ?", (project_id,))
    await db.execute("DELETE FROM pr_reviews WHERE project_id = ?", (project_id,))
    await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    await db.commit()


@router.post("/{project_id}/run", response_model=WorkflowRunResponse)
async def run_project(project_id: str, req: RunProjectRequest, request: Request):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    project = _row_to_project(row)
    conductor_svc = request.app.state.conductor

    # Generate pipeline YAML if not cached
    pipeline_yaml = project.get("last_pipeline_yaml") or ""
    if not pipeline_yaml and project.get("requirements_yaml") and project.get("infra_yaml"):
        try:
            result = await conductor_svc.generate_pipeline(
                project["requirements_yaml"],
                project["infra_yaml"],
                pipeline_type=req.pipeline_type,
            )
            pipeline_yaml = result.get("pipeline_yaml", "")
            await db.execute(
                "UPDATE projects SET last_pipeline_yaml = ?, updated_at = ? WHERE id = ?",
                (pipeline_yaml, datetime.now(timezone.utc).isoformat(), project_id),
            )
            await db.commit()
        except Exception as exc:
            logger.error("pipeline_generation_failed", error=str(exc))

    # Create workflow run record
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO workflow_runs
           (id, project_id, status, selected_components, pipeline_yaml, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (run_id, project_id, "pending", json.dumps(req.selected_components), pipeline_yaml, now),
    )
    await db.commit()

    # Build and run workflow in background
    definition = build_workflow_definition(
        project_id=project_id,
        project_name=project["name"],
        github_repo=project["github_repo"],
        requirements_yaml=project.get("requirements_yaml") or "",
        infra_yaml=project.get("infra_yaml") or "",
        pipeline_yaml=pipeline_yaml,
        selected_components=req.selected_components,
    )

    async def _run_workflow():
        try:
            await db.execute(
                "UPDATE workflow_runs SET status = ?, workflow_id = ? WHERE id = ?",
                ("in_progress", definition.workflow_id, run_id),
            )
            await db.commit()

            state = await conductor_svc.run_workflow(definition)

            status = "completed" if state.status.value == "completed" else "failed"
            await db.execute(
                "UPDATE workflow_runs SET status = ?, completed_at = ?, result_summary = ? WHERE id = ?",
                (status, datetime.now(timezone.utc).isoformat(), json.dumps({"status": status}), run_id),
            )
            await db.commit()
        except Exception as exc:
            logger.error("workflow_run_failed", run_id=run_id, error=str(exc))
            await db.execute(
                "UPDATE workflow_runs SET status = ?, error_log = ?, completed_at = ? WHERE id = ?",
                ("failed", json.dumps({"error": str(exc)}), datetime.now(timezone.utc).isoformat(), run_id),
            )
            await db.commit()

    asyncio.create_task(_run_workflow())

    return WorkflowRunResponse(
        id=run_id,
        project_id=project_id,
        status="pending",
        workflow_id=definition.workflow_id,
        selected_components=req.selected_components,
        pipeline_yaml=pipeline_yaml,
        created_at=now,
    )
