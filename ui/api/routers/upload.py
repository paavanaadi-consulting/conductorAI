"""
ConductorAI UI — File Upload Router
"""

from __future__ import annotations

import yaml
from fastapi import APIRouter, UploadFile, File

from ui.api.models.schemas import UploadResponse

router = APIRouter()


@router.post("/", response_model=UploadResponse)
async def upload_yaml(file: UploadFile = File(...)):
    """Upload a YAML file, validate it, and return the content."""
    content = (await file.read()).decode("utf-8")

    # Validate YAML syntax
    try:
        yaml.safe_load(content)
        return UploadResponse(
            filename=file.filename or "unknown.yaml",
            content=content,
            valid=True,
        )
    except yaml.YAMLError as exc:
        return UploadResponse(
            filename=file.filename or "unknown.yaml",
            content=content,
            valid=False,
            error=str(exc),
        )
