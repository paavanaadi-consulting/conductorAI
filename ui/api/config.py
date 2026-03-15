"""
ConductorAI UI — API Configuration
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class APISettings(BaseSettings):
    # Database
    database_path: str = str(
        Path(__file__).resolve().parent / "conductor_ui.db"
    )

    # File uploads
    upload_dir: str = str(Path(__file__).resolve().parent / "uploads")

    # Templates (relative to repo root)
    templates_dir: str = str(
        Path(__file__).resolve().parent.parent.parent / "templates"
    )

    # GitHub App
    github_app_id: int = 0
    github_app_private_key_path: str = ""
    github_app_webhook_secret: str = ""

    # ConductorAI LLM
    conductor_llm_provider: str = "mock"
    conductor_llm_model: str = "gpt-4"
    conductor_llm_api_key: str = ""

    # Frontend
    frontend_url: str = "http://localhost:3000"

    model_config = {"env_prefix": "CONDUCTOR_UI_"}


@lru_cache
def get_settings() -> APISettings:
    return APISettings()
