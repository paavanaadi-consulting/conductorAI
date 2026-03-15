"""
ConductorAI UI — Templates Router

Serves YAML templates from the templates/ directory.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ui.api.config import get_settings
from ui.api.models.schemas import TemplateContent, TemplateInfo

router = APIRouter()

VALID_CATEGORIES = {"requirements", "infrastructure"}


def _templates_path() -> Path:
    return Path(get_settings().templates_dir)


@router.get("/requirements", response_model=list[TemplateInfo])
async def list_requirements_templates():
    base = _templates_path() / "requirements"
    if not base.exists():
        return []
    return [
        TemplateInfo(filename=f.name, category="requirements")
        for f in sorted(base.glob("*.yaml")) + sorted(base.glob("*.yml"))
    ]


@router.get("/infrastructure", response_model=list[TemplateInfo])
async def list_infrastructure_templates():
    base = _templates_path() / "infrastructure"
    if not base.exists():
        return []
    return [
        TemplateInfo(filename=f.name, category="infrastructure")
        for f in sorted(base.glob("*.yaml")) + sorted(base.glob("*.yml"))
    ]


@router.get("/{category}/{filename}", response_model=TemplateContent)
async def get_template(category: str, filename: str):
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")

    # Sanitize filename to prevent directory traversal
    safe_name = Path(filename).name
    filepath = _templates_path() / category / safe_name
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Template not found")

    return TemplateContent(
        filename=safe_name,
        category=category,
        content=filepath.read_text(),
    )
