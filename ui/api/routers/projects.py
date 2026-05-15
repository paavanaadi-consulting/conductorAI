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

from ui.api.config import APISettings
from ui.api.database import get_db
from ui.api.models.schemas import (
    ProjectCreateRequest,
    ProjectResponse,
    ProjectSummary,
    ProjectUpdateRequest,
    RunProjectRequest,
    WorkflowRunResponse,
)
from ui.api.services.github_service import GitHubService
from ui.api.services.email_service import EmailService, EmailConfig
from ui.api.services.workflow_builder import build_workflow_definition

logger = structlog.get_logger()
router = APIRouter()
api_settings = APISettings()
github_service = GitHubService(api_settings)

# Initialize email service with settings
email_config = EmailConfig(
    smtp_server=api_settings.email_smtp_server,
    smtp_port=api_settings.email_smtp_port,
    sender_email=api_settings.email_sender_email,
    sender_password=api_settings.email_sender_password,
    sender_name=api_settings.email_sender_name,
    use_tls=api_settings.email_use_tls,
)
email_service = EmailService(email_config)


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
        "project_manager_email": row["project_manager_email"],
        "architect_email": row["architect_email"],
        "github_owner": row["github_owner"],
        "is_approved": row["is_approved"]
    }


async def _send_review_emails(
    project_manager_email: str,
    architect_email: str,
    project_name: str,
    project_id: str,
    github_repo: str,
    frontend_url: str,
) -> None:
    """Send review request emails to project manager and architect.

    Args:
        project_manager_email: Email of project manager
        architect_email: Email of architect
        project_name: Name of the project
        project_id: ID of the project
        github_repo: GitHub repository
        frontend_url: Frontend URL for review links
    """
    try:
        tasks = []

        # Send email to project manager
        if project_manager_email:
            logger.info("sending_email_to_project_manager", email=project_manager_email)
            task = email_service.send_project_review_email(
                recipient_email=project_manager_email,
                recipient_name="Project Manager",
                project_name=project_name,
                project_id=project_id,
                github_repo=github_repo,
                review_type="both",
                frontend_url=frontend_url,
            )
            tasks.append(task)

        # Send email to architect
        if architect_email:
            logger.info("sending_email_to_architect", email=architect_email)
            task = email_service.send_project_review_email(
                recipient_email=architect_email,
                recipient_name="Architect",
                project_name=project_name,
                project_id=project_id,
                github_repo=github_repo,
                review_type="both",
                frontend_url=frontend_url,
            )
            tasks.append(task)

        # Send all emails concurrently
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        "email_send_exception",
                        index=i,
                        error=str(result),
                    )
                elif result:
                    logger.info("email_sent_successfully", index=i)
                else:
                    logger.warning("email_send_failed", index=i)
    except Exception as e:
        logger.error("send_review_emails_failed", error=str(e))


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
            requirements_yaml, infra_yaml, selected_components, created_at, updated_at, project_manager_email, 
            architect_email,github_owner, is_approved)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            req.project_manager_email,
            req.architect_email,
            req.github_owner,
            False,  # is_approved defaults to False on creation
        ),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = await cursor.fetchone()
    project = ProjectResponse(**_row_to_project(row))
    pipeline_content = await __generate_pipeline(project, req, request,db)
    logger.info("pipeline_generation_successful", project_id=project_id, pipeline_length=len(pipeline_content))
    read_me_content = await __generate_readme_file(project, request, db)
    logger.info("readme_generation_successful", project_id=project_id, readme_length=len(read_me_content))
    logger.info("Create Repository")
    # write code to create a repository
    await github_service.create_repository(req.name, False)
    await github_service.create_or_update_file(owner=req.github_owner,
                                               repo=req.name,
                                               path="pipeline.yaml",
                                               content=pipeline_content,
                                               message="Add generated pipeline.yaml",
                                               branch="main")

    await github_service.create_or_update_file(owner=req.github_owner,
                                               repo=req.name,
                                               path="README.md",
                                               content=read_me_content,
                                               message="Added README.md file",
                                               branch="main")

    # Send review request emails to project manager and architect
    logger.info("sending_review_request_emails", project_id=project_id)
    await _send_review_emails(
        project_manager_email=req.project_manager_email,
        architect_email=req.architect_email,
        project_name=req.name,
        project_id=project_id,
        github_repo=req.github_repo,
        frontend_url=api_settings.frontend_url,
    )

    return ProjectResponse(**_row_to_project(row))

async def __generate_readme_file(project: ProjectResponse, request: Request, db):
    conductor_svc = request.app.state.conductor
    logger.info("Generate readme file")
    readme_content = ""
    if project.requirements_yaml and project.infra_yaml:
        try:
            readme_content = await conductor_svc.generate_readme(
                project.requirements_yaml,
                project.infra_yaml
            )

            logger.info("readme_generation_successful", project_id=project.id)
        except Exception as exc:
            logger.error("readme_generation_failed", error=str(exc))
    return readme_content.get('readme_md')


async def __generate_pipeline(project: ProjectResponse, req: ProjectCreateRequest, request: Request, db):
    # Generate pipeline YAML if not cached
    project_id = project.id
    pipeline_yaml = project.last_pipeline_yaml is not None or ""
    conductor_svc = request.app.state.conductor
    if not pipeline_yaml and project.requirements_yaml and project.infra_yaml:
        try:
            result = await conductor_svc.generate_pipeline(
                project.requirements_yaml,
                project.infra_yaml,
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
    return pipeline_yaml


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

@router.put("/{project_id}/approve", response_model=ProjectResponse)
async def approve_project_review(project_id: str):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    if not row["is_approved"]:
        logger.info("approve_project_review", project_id=project_id)
        await db.execute(
            "UPDATE projects SET is_approved = ?, updated_at = ? WHERE id = ?",
            (True, datetime.now(timezone.utc).isoformat(), project_id),
        )
        await db.commit()
        logger.info("Project review approved successfully", project_id=project_id)
    else:
        logger.info("Project already reviewed and approved", project_id=project_id)
    cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = await cursor.fetchone()
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
    if req.is_approved is not None:
        updates.append("is_approved = ?")
        params.append(req.is_approved)
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
    logger.info("Run project triggered")
    db = await get_db()
    cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    project = _row_to_project(row)
    if not project.is_approved:
        raise HTTPException(status_code=404, detail="Project not approved")
    conductor_svc = request.app.state.conductor

    pipeline_yaml = project.get("last_pipeline_yaml")
    if not pipeline_yaml:
        raise HTTPException(status_code=404, detail="Pipeline YAML file not found or is empty")

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
        """Execute workflow in background with comprehensive logging."""
        try:
            logger.info(
                "workflow_background_task_started",
                run_id=run_id,
                project_id=project_id,
                workflow_id=definition.workflow_id,
            )
            
            # Step 1: Update status to in_progress
            logger.info("workflow_updating_status_to_in_progress", run_id=run_id)
            await db.execute(
                "UPDATE workflow_runs SET status = ?, workflow_id = ? WHERE id = ?",
                ("in_progress", definition.workflow_id, run_id),
            )
            await db.commit()
            logger.info("workflow_status_updated_to_in_progress", run_id=run_id)

            # Step 2: EXECUTE THE WORKFLOW (Line 179 area - THIS IS THE KEY CALL)
            logger.info(
                "workflow_calling_conductor_run_workflow",
                run_id=run_id,
                workflow_id=definition.workflow_id,
            )
            state = await conductor_svc.run_workflow(definition)
            logger.info(
                "workflow_conductor_call_completed",
                run_id=run_id,
                workflow_state=str(state),
                workflow_status=state.status.value if hasattr(state, 'status') else "unknown",
            )

            # Step 3: Update final status
            status = "completed" if state.status.value == "completed" else "failed"
            logger.info(
                "workflow_updating_final_status",
                run_id=run_id,
                final_status=status,
            )
            await db.execute(
                "UPDATE workflow_runs SET status = ?, completed_at = ?, result_summary = ? WHERE id = ?",
                (status, datetime.now(timezone.utc).isoformat(), json.dumps({"status": status}), run_id),
            )
            await db.commit()
            logger.info("workflow_completed_successfully", run_id=run_id, status=status)
            
        except Exception as exc:
            logger.error(
                "workflow_background_task_failed",
                run_id=run_id,
                project_id=project_id,
                error=str(exc),
                exc_info=True,
            )
            try:
                await db.execute(
                    "UPDATE workflow_runs SET status = ?, error_log = ?, completed_at = ? WHERE id = ?",
                    ("failed", json.dumps({"error": str(exc)}), datetime.now(timezone.utc).isoformat(), run_id),
                )
                await db.commit()
            except Exception as db_exc:
                logger.error("workflow_failed_to_update_db_with_error", error=str(db_exc))

    # Create task with error callback
    task = asyncio.create_task(_run_workflow())
    logger.info("workflow_background_task_created", run_id=run_id, task_name=task.get_name())
    
    # Add callback to handle task completion/exceptions
    def _handle_task_result(t: asyncio.Task):
        try:
            result = t.result()
            logger.info("workflow_background_task_completed_successfully", run_id=run_id)
        except asyncio.CancelledError:
            logger.warning("workflow_background_task_was_cancelled", run_id=run_id)
        except Exception as exc:
            logger.error(
                "workflow_background_task_exception_in_callback",
                run_id=run_id,
                error=str(exc),
                exc_info=True,
            )
    
    task.add_done_callback(_handle_task_result)
    
    # Store reference to task in app state to prevent garbage collection
    if not hasattr(request.app.state, 'background_tasks'):
        request.app.state.background_tasks = set()
    request.app.state.background_tasks.add(task)

    return WorkflowRunResponse(
        id=run_id,
        project_id=project_id,
        status="pending",
        workflow_id=definition.workflow_id,
        selected_components=req.selected_components,
        pipeline_yaml=pipeline_yaml,
        created_at=now,
    )

