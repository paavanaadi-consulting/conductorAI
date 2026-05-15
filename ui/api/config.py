"""
ConductorAI UI — API Configuration
"""

from __future__ import annotations

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
    github_token: str = "xxx"
    #githut_token=""

    # ConductorAI LLM
    conductor_llm_provider: str = "anthropic"
    conductor_llm_model: str = "xxx"
    conductor_llm_api_key: str = "xxx"
    # conductor_llm_api_key: str = ""
    #conductor_llm_provider: str = config["llm"]["provider"]
    #conductor_llm_model: str = config["llm"]["model"]
    #conductor_llm_api_key: str = config["llm"]["api_key"]

    # Email Service Configuration
    email_smtp_server: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_sender_email: str = "xxx"  # Fallback value, override with env var
    email_sender_password: str = "xxx"  # Fallback value, override with env var
    email_sender_name: str = "ConductorAI"
    email_use_tls: bool = True

    # Frontend
    frontend_url: str = "http://localhost:3000"

    model_config = {"env_prefix": "CONDUCTOR_UI_"}


@lru_cache
def get_settings() -> APISettings:
    return APISettings()
