"""
conductor.core.config - Configuration Management
==================================================

This module provides the configuration system for ConductorAI. Configuration
can be loaded from multiple sources with the following priority (highest first):

    1. Explicit constructor arguments
    2. Environment variables (prefixed with CONDUCTOR_)
    3. YAML configuration file (conductor.yaml)
    4. Default values defined in the models below

Architecture Context:
    Configuration flows DOWN through the system. The top-level ConductorConfig
    is created once and passed to all components during initialization:

        ConductorConfig
            ├── RedisConfig      → MessageBus, StateManager
            ├── LLMConfig        → LLM Providers → Agents
            └── (other settings) → WorkflowEngine, PolicyEngine, etc.

Key Design Decisions:
    - Uses Pydantic BaseSettings for automatic env var loading
    - All config values have sensible defaults (zero-config startup)
    - Nested configs (RedisConfig, LLMConfig) keep concerns separated
    - YAML support for complex deployments (conductor.yaml)
    - Immutable after creation (frozen=False but convention is set-once)

Usage:
    # Load from environment variables:
    config = ConductorConfig()

    # Load from YAML file:
    config = load_config("conductor.yaml")

    # Explicit overrides:
    config = ConductorConfig(log_level="DEBUG", environment="dev")

Environment Variables:
    CONDUCTOR_LOG_LEVEL=DEBUG
    CONDUCTOR_ENVIRONMENT=prod
    CONDUCTOR_REDIS_URL=redis://prod-host:6379
    CONDUCTOR_LLM_PROVIDER=openai
    CONDUCTOR_LLM_MODEL=gpt-4
    CONDUCTOR_LLM_API_KEY=sk-...
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# =============================================================================
# Redis Configuration
# =============================================================================
# Controls how ConductorAI connects to Redis, which serves as both:
#   1. Message Bus backend (pub/sub for agent communication)
#   2. State persistence backend (workflow and agent state storage)
#
# In development/testing, you can use InMemory implementations instead of
# Redis — these config values are only used when Redis backends are selected.
# =============================================================================
class RedisConfig(BaseModel):
    """Configuration for Redis connection.

    Redis serves dual purpose in ConductorAI:
        - Message Bus: pub/sub channels for agent-to-agent communication
        - State Store: persistent storage for workflow and agent states

    Attributes:
        url: Redis connection URL. Format: redis://[password@]host:port/db
        max_connections: Maximum connections in the connection pool. Higher
            values support more concurrent operations but use more memory.
        key_prefix: Namespace prefix for all Redis keys. Prevents collisions
            when sharing a Redis instance with other applications.
        socket_timeout: Timeout in seconds for Redis socket operations.
            Prevents hanging connections on network issues.
    """

    url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL (redis://host:port/db)",
    )
    max_connections: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of connections in the Redis pool",
    )
    key_prefix: str = Field(
        default="conductor:",
        description="Prefix for all Redis keys (namespace isolation)",
    )
    socket_timeout: float = Field(
        default=5.0,
        gt=0,
        description="Socket timeout in seconds for Redis operations",
    )


# =============================================================================
# LLM Configuration
# =============================================================================
# Controls which Large Language Model provider and model the AI agents use.
# ConductorAI supports multiple providers through an abstraction layer
# (see integrations/llm/). This config tells agents which one to use.
# =============================================================================
class LLMConfig(BaseModel):
    """Configuration for Large Language Model provider.

    The LLM is the "brain" of each AI agent. When a CodingAgent needs to
    generate code, or a ReviewAgent needs to analyze code quality, they
    call the LLM through the provider specified here.

    Supported Providers:
        - "openai":    OpenAI API (GPT-4, GPT-3.5-turbo, etc.)
        - "anthropic": Anthropic API (Claude models)
        - "mock":      Mock provider for testing (returns configurable responses)

    Attributes:
        provider: Which LLM service to use. The provider string maps to a
            concrete LLMProvider implementation in integrations/llm/.
        model: The specific model to use within the provider.
        api_key: API authentication key. Can also be set via CONDUCTOR_LLM_API_KEY.
            Stored as Optional because mock provider doesn't need one.
        temperature: Controls randomness in LLM output (0.0 = deterministic,
            1.0 = maximum creativity). Lower values for code generation.
        max_tokens: Maximum number of tokens the LLM can generate per request.
            Higher values allow longer responses but cost more.
        api_base_url: Custom API endpoint URL (for proxies or self-hosted models).
    """

    provider: str = Field(
        default="mock",
        description="LLM provider name: 'openai', 'anthropic', or 'mock'",
    )
    model: str = Field(
        default="gpt-4",
        description="Model identifier within the provider",
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key for authentication (None for mock provider)",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="LLM temperature: 0.0=deterministic, 1.0=creative",
    )
    max_tokens: int = Field(
        default=4096,
        ge=1,
        le=128000,
        description="Maximum tokens per LLM response",
    )
    api_base_url: Optional[str] = Field(
        default=None,
        description="Custom API base URL (for proxies or self-hosted models)",
    )


# =============================================================================
# Main Configuration
# =============================================================================
# This is the top-level configuration that encompasses all settings.
# It uses pydantic-settings for automatic environment variable loading.
#
# Environment Variable Mapping:
#   CONDUCTOR_LOG_LEVEL       → config.log_level
#   CONDUCTOR_ENVIRONMENT     → config.environment
#   CONDUCTOR_REDIS__URL      → config.redis.url  (nested with double underscore)
#   CONDUCTOR_LLM__PROVIDER   → config.llm.provider
# =============================================================================
class ConductorConfig(BaseSettings):
    """Top-level configuration for the ConductorAI framework.

    This is the single configuration object that gets passed to all components
    during initialization. It aggregates all sub-configurations and provides
    sensible defaults for zero-config startup.

    The configuration cascade (highest priority first):
        1. Constructor arguments: ConductorConfig(log_level="DEBUG")
        2. Environment variables: CONDUCTOR_LOG_LEVEL=DEBUG
        3. YAML file: load_config("conductor.yaml")
        4. Default values defined below

    Attributes:
        environment: Deployment environment. Affects logging verbosity,
            error detail level, and default behaviors.
        log_level: Python logging level. Structured logs use structlog.
        max_agent_retries: How many times to retry a failed agent task
            before giving up and escalating to the error handler.
        workflow_timeout_seconds: Maximum time (in seconds) a workflow can
            run before being forcefully cancelled. Prevents runaway workflows.
        enable_persistence: Whether to persist state to Redis. When False,
            uses in-memory storage (useful for testing and development).
        redis: Redis connection configuration (see RedisConfig).
        llm: LLM provider configuration (see LLMConfig).

    Example:
        >>> config = ConductorConfig(
        ...     environment="dev",
        ...     log_level="DEBUG",
        ...     llm=LLMConfig(provider="mock"),
        ... )
    """

    # -------------------------------------------------------------------------
    # General Settings
    # -------------------------------------------------------------------------
    environment: Literal["dev", "staging", "prod"] = Field(
        default="dev",
        description="Deployment environment (affects defaults and verbosity)",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )
    max_agent_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for failed agent tasks",
    )
    workflow_timeout_seconds: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Maximum workflow execution time in seconds",
    )
    enable_persistence: bool = Field(
        default=False,
        description="Use Redis for persistence (False = in-memory for dev/test)",
    )

    # -------------------------------------------------------------------------
    # Nested Configurations
    # -------------------------------------------------------------------------
    redis: RedisConfig = Field(
        default_factory=RedisConfig,
        description="Redis connection configuration",
    )
    llm: LLMConfig = Field(
        default_factory=LLMConfig,
        description="LLM provider configuration",
    )

    # -------------------------------------------------------------------------
    # Pydantic Settings Configuration
    # -------------------------------------------------------------------------
    # model_config tells pydantic-settings how to load from environment:
    #   - env_prefix: All env vars start with "CONDUCTOR_"
    #   - env_nested_delimiter: Use "__" for nested configs
    #     (e.g., CONDUCTOR_REDIS__URL maps to config.redis.url)
    #   - case_sensitive: Env vars are case-insensitive
    # -------------------------------------------------------------------------
    model_config = {
        "env_prefix": "CONDUCTOR_",
        "env_nested_delimiter": "__",
        "case_sensitive": False,
    }


# =============================================================================
# Configuration Loader
# =============================================================================
# Utility function to load configuration from a YAML file. This is the
# recommended way to configure ConductorAI in production deployments.
# =============================================================================
def load_config(path: Optional[str] = None) -> ConductorConfig:
    """Load ConductorAI configuration from a YAML file and/or environment variables.

    The loading process:
        1. If a path is provided, read and parse the YAML file
        2. Merge YAML values with environment variables (env vars win)
        3. Apply default values for anything not specified
        4. Validate all values through Pydantic

    Args:
        path: Path to a YAML configuration file. If None, looks for
            'conductor.yaml' in the current directory. If that doesn't
            exist either, uses pure defaults + environment variables.

    Returns:
        A fully validated ConductorConfig instance.

    Raises:
        ConfigurationError: If the YAML file exists but is invalid.
        FileNotFoundError: If an explicit path is provided but doesn't exist.

    Example:
        >>> config = load_config("conductor.yaml")
        >>> config = load_config()  # auto-detect or use defaults
    """
    # Determine the configuration file path
    if path is None:
        # Look for conductor.yaml in the current working directory
        default_path = Path("conductor.yaml")
        if default_path.exists():
            path = str(default_path)

    # If we have a YAML file, parse it
    yaml_data: dict[str, Any] = {}
    if path is not None:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {path}. "
                f"Create one from conductor.yaml.example or use environment variables."
            )

        with open(config_path) as f:
            raw_data = yaml.safe_load(f)
            if isinstance(raw_data, dict):
                yaml_data = raw_data

    # Create config: YAML values are passed as constructor args,
    # environment variables are loaded automatically by BaseSettings
    return ConductorConfig(**yaml_data)


# =============================================================================
# Convenience: Get config from environment
# =============================================================================
def get_default_config() -> ConductorConfig:
    """Create a ConductorConfig with all defaults.

    This is a convenience function for quick startup, testing, and examples.
    All values come from defaults and environment variables.

    Returns:
        A ConductorConfig with default values (overridden by any set env vars).
    """
    return ConductorConfig()
