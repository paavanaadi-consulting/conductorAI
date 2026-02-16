"""
Tests for conductor.core.config
=================================

These tests verify that the configuration system works correctly:
    - Default values are sensible and complete
    - Environment variables override defaults
    - YAML files are parsed correctly
    - Validation catches invalid values
    - Nested configs (Redis, LLM) work properly

All tests are unit tests — they don't need Redis or any external service.
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from conductor.core.config import (
    ConductorConfig,
    LLMConfig,
    RedisConfig,
    get_default_config,
    load_config,
)


# =============================================================================
# Test: Default Configuration
# =============================================================================
# Verify that creating a ConductorConfig with no arguments produces a
# valid configuration with sensible defaults. This is critical because
# users should be able to start with zero configuration.
# =============================================================================
class TestDefaultConfig:
    """Tests for default configuration values."""

    def test_default_config_creates_successfully(self) -> None:
        """ConductorConfig() should work with no arguments (zero-config startup)."""
        config = ConductorConfig()
        assert config is not None

    def test_default_environment_is_dev(self) -> None:
        """Default environment should be 'dev' for safe local development."""
        config = ConductorConfig()
        assert config.environment == "dev"

    def test_default_log_level_is_info(self) -> None:
        """Default log level should be INFO (not too noisy, not too quiet)."""
        config = ConductorConfig()
        assert config.log_level == "INFO"

    def test_default_max_retries(self) -> None:
        """Default retry count should be 3 (enough for transient failures)."""
        config = ConductorConfig()
        assert config.max_agent_retries == 3

    def test_default_workflow_timeout(self) -> None:
        """Default workflow timeout should be 300 seconds (5 minutes)."""
        config = ConductorConfig()
        assert config.workflow_timeout_seconds == 300

    def test_default_persistence_is_disabled(self) -> None:
        """Persistence should default to False (in-memory for easy dev startup)."""
        config = ConductorConfig()
        assert config.enable_persistence is False

    def test_default_redis_config(self) -> None:
        """Redis config should have sensible defaults even if not used."""
        config = ConductorConfig()
        assert config.redis.url == "redis://localhost:6379/0"
        assert config.redis.max_connections == 10
        assert config.redis.key_prefix == "conductor:"

    def test_default_llm_config(self) -> None:
        """LLM config should default to mock provider for safe testing."""
        config = ConductorConfig()
        assert config.llm.provider == "mock"
        assert config.llm.model == "gpt-4"
        assert config.llm.api_key is None
        assert config.llm.temperature == 0.7

    def test_get_default_config_convenience(self) -> None:
        """get_default_config() should return a valid ConductorConfig."""
        config = get_default_config()
        assert isinstance(config, ConductorConfig)
        assert config.environment == "dev"


# =============================================================================
# Test: Configuration Overrides
# =============================================================================
# Verify that explicit values override defaults.
# =============================================================================
class TestConfigOverrides:
    """Tests for explicit configuration value overrides."""

    def test_override_environment(self) -> None:
        """Explicit environment value should override default."""
        config = ConductorConfig(environment="prod")
        assert config.environment == "prod"

    def test_override_log_level(self) -> None:
        """Explicit log_level should override default."""
        config = ConductorConfig(log_level="DEBUG")
        assert config.log_level == "DEBUG"

    def test_override_nested_redis(self) -> None:
        """Nested RedisConfig should accept overrides."""
        config = ConductorConfig(
            redis=RedisConfig(url="redis://custom-host:6380/1", max_connections=20)
        )
        assert config.redis.url == "redis://custom-host:6380/1"
        assert config.redis.max_connections == 20

    def test_override_nested_llm(self) -> None:
        """Nested LLMConfig should accept overrides."""
        config = ConductorConfig(
            llm=LLMConfig(provider="openai", api_key="sk-test-key", temperature=0.3)
        )
        assert config.llm.provider == "openai"
        assert config.llm.api_key == "sk-test-key"
        assert config.llm.temperature == 0.3


# =============================================================================
# Test: Configuration Validation
# =============================================================================
# Verify that Pydantic validation catches invalid values.
# =============================================================================
class TestConfigValidation:
    """Tests for configuration validation constraints."""

    def test_invalid_environment_rejected(self) -> None:
        """Environment must be one of: dev, staging, prod."""
        with pytest.raises(Exception):
            ConductorConfig(environment="invalid")

    def test_negative_retries_rejected(self) -> None:
        """max_agent_retries must be >= 0."""
        with pytest.raises(Exception):
            ConductorConfig(max_agent_retries=-1)

    def test_excessive_retries_rejected(self) -> None:
        """max_agent_retries must be <= 10."""
        with pytest.raises(Exception):
            ConductorConfig(max_agent_retries=11)

    def test_redis_max_connections_bounds(self) -> None:
        """Redis max_connections must be between 1 and 100."""
        with pytest.raises(Exception):
            RedisConfig(max_connections=0)

    def test_llm_temperature_bounds(self) -> None:
        """LLM temperature must be between 0.0 and 2.0."""
        with pytest.raises(Exception):
            LLMConfig(temperature=3.0)


# =============================================================================
# Test: Environment Variable Loading
# =============================================================================
# Verify that environment variables with the CONDUCTOR_ prefix override
# default values. Uses monkeypatch to safely set env vars in tests.
# =============================================================================
class TestEnvVarLoading:
    """Tests for environment variable configuration loading."""

    def test_env_var_overrides_log_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CONDUCTOR_LOG_LEVEL env var should override default."""
        monkeypatch.setenv("CONDUCTOR_LOG_LEVEL", "DEBUG")
        config = ConductorConfig()
        assert config.log_level == "DEBUG"

    def test_env_var_overrides_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CONDUCTOR_ENVIRONMENT env var should override default."""
        monkeypatch.setenv("CONDUCTOR_ENVIRONMENT", "prod")
        config = ConductorConfig()
        assert config.environment == "prod"


# =============================================================================
# Test: YAML Configuration Loading
# =============================================================================
# Verify that load_config() correctly reads YAML files and merges with
# defaults and environment variables.
# =============================================================================
class TestYamlLoading:
    """Tests for YAML configuration file loading."""

    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        """load_config() should parse a valid YAML file."""
        yaml_content = {
            "environment": "staging",
            "log_level": "WARNING",
            "llm": {"provider": "openai", "model": "gpt-3.5-turbo"},
        }
        config_file = tmp_path / "conductor.yaml"
        config_file.write_text(yaml.dump(yaml_content))

        config = load_config(str(config_file))
        assert config.environment == "staging"
        assert config.log_level == "WARNING"
        assert config.llm.provider == "openai"

    def test_load_nonexistent_file_raises(self) -> None:
        """load_config() with explicit missing path should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/conductor.yaml")

    def test_load_empty_yaml_uses_defaults(self, tmp_path: Path) -> None:
        """An empty YAML file should result in all defaults."""
        config_file = tmp_path / "conductor.yaml"
        config_file.write_text("")

        config = load_config(str(config_file))
        assert config.environment == "dev"
        assert config.log_level == "INFO"

    def test_load_config_no_path_uses_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """load_config() with no path and no conductor.yaml should use defaults."""
        # Change to a temp dir where no conductor.yaml exists
        monkeypatch.chdir(tempfile.mkdtemp())
        config = load_config()
        assert isinstance(config, ConductorConfig)


# =============================================================================
# Test: Nested Configuration Models
# =============================================================================
# Verify that RedisConfig and LLMConfig work correctly as standalone models.
# =============================================================================
class TestNestedConfigs:
    """Tests for RedisConfig and LLMConfig as standalone models."""

    def test_redis_config_defaults(self) -> None:
        """RedisConfig should have sensible defaults."""
        config = RedisConfig()
        assert config.url == "redis://localhost:6379/0"
        assert config.max_connections == 10
        assert config.key_prefix == "conductor:"
        assert config.socket_timeout == 5.0

    def test_llm_config_defaults(self) -> None:
        """LLMConfig should have sensible defaults."""
        config = LLMConfig()
        assert config.provider == "mock"
        assert config.model == "gpt-4"
        assert config.api_key is None
        assert config.temperature == 0.7
        assert config.max_tokens == 4096
        assert config.api_base_url is None

    def test_llm_config_serialization(self) -> None:
        """LLMConfig should serialize to/from dict cleanly."""
        config = LLMConfig(provider="openai", api_key="sk-test")
        data = config.model_dump()
        restored = LLMConfig(**data)
        assert restored.provider == "openai"
        assert restored.api_key == "sk-test"
