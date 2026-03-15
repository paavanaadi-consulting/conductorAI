"""
ConductorAI UI — Workflows Router
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from ui.api.database import get_db
from ui.api.models.schemas import WorkflowRunResponse

router = APIRouter()


@router.get("/{run_id}", response_model=WorkflowRunResponse)
async def get_workflow_run(run_id: str, request: Request):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return WorkflowRunResponse(
        id=row["id"],
        project_id=row["project_id"],
        status=row["status"],
        workflow_id=row["workflow_id"],
        selected_components=json.loads(row["selected_components"] or "[]"),
        pipeline_yaml=row["pipeline_yaml"],
        result_summary=row["result_summary"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


@router.get("/project/{project_id}", response_model=list[WorkflowRunResponse])
async def list_project_runs(project_id: str, request: Request):
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM workflow_runs WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )
    rows = await cursor.fetchall()
    return [
        WorkflowRunResponse(
            id=r["id"],
            project_id=r["project_id"],
            status=r["status"],
            workflow_id=r["workflow_id"],
            selected_components=json.loads(r["selected_components"] or "[]"),
            pipeline_yaml=r["pipeline_yaml"],
            result_summary=r["result_summary"],
            created_at=r["created_at"],
            completed_at=r["completed_at"],
        )
        for r in rows
    ]
