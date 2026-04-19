"""
ConductorAI UI — API Configuration
"""

from __future__ import annotations

import yaml
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

    # ConductorAI Configuration
    """conductor_config_path: str = str(
        Path(__file__).resolve().parent.parent.parent / "conductor.yaml"
    )

    config = yaml.safe_load(open(conductor_config_path))
    """

    # GitHub App
    github_app_id: int = 0
    github_app_private_key_path: str = ""
    github_app_webhook_secret: str = ""
    github_token: str = "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"

    # ConductorAI LLM
    conductor_llm_provider: str = "anthropic"
    conductor_llm_model: str = "claude-sonnet-4-20250514"
    conductor_llm_api_key: str = "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"
    #conductor_llm_provider: str = config["llm"]["provider"]
    #conductor_llm_model: str = config["llm"]["model"]
    #conductor_llm_api_key: str = config["llm"]["api_key"]


    # Frontend
    frontend_url: str = "http://localhost:3000"

    model_config = {"env_prefix": "CONDUCTOR_UI_"}


@lru_cache
def get_settings() -> APISettings:
    return APISettings()
