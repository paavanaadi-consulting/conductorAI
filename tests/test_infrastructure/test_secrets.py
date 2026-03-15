"""
Tests for conductor.infrastructure.secrets
============================================
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from conductor.infrastructure.secrets import (
    AWSSecretsProvider,
    EnvSecretsProvider,
    VaultSecretsProvider,
)


class TestEnvSecretsProvider:
    """Tests for environment variable secrets provider."""

    async def test_get_secret_found(self):
        with patch.dict(os.environ, {"CONDUCTOR_SECRET_API_KEY": "sk-test-123"}):
            provider = EnvSecretsProvider()
            value = await provider.get_secret("api_key")
            assert value == "sk-test-123"

    async def test_get_secret_not_found(self):
        provider = EnvSecretsProvider()
        value = await provider.get_secret("nonexistent_key")
        assert value is None

    async def test_get_secret_case_insensitive_key(self):
        with patch.dict(os.environ, {"CONDUCTOR_SECRET_REDIS_PASSWORD": "pass123"}):
            provider = EnvSecretsProvider()
            value = await provider.get_secret("redis_password")
            assert value == "pass123"

    async def test_custom_prefix(self):
        with patch.dict(os.environ, {"MYAPP_DB_HOST": "localhost"}):
            provider = EnvSecretsProvider(prefix="MYAPP_")
            value = await provider.get_secret("db_host")
            assert value == "localhost"

    async def test_set_secret_raises(self):
        provider = EnvSecretsProvider()
        with pytest.raises(NotImplementedError, match="read-only"):
            await provider.set_secret("key", "value")

    async def test_list_keys(self):
        env_vars = {
            "CONDUCTOR_SECRET_API_KEY": "sk-123",
            "CONDUCTOR_SECRET_DB_PASSWORD": "pass",
            "OTHER_VAR": "ignored",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            provider = EnvSecretsProvider()
            keys = await provider.list_keys()
            assert "api_key" in keys
            assert "db_password" in keys
            assert "other_var" not in keys

    async def test_list_keys_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = EnvSecretsProvider()
            keys = await provider.list_keys()
            assert keys == []


class TestVaultSecretsProvider:
    """Tests for Vault secrets provider stub."""

    async def test_get_secret_raises(self):
        provider = VaultSecretsProvider(
            vault_addr="https://vault.example.com:8200",
            vault_token="test-token",
        )
        with pytest.raises(NotImplementedError, match="hvac"):
            await provider.get_secret("key")

    async def test_set_secret_raises(self):
        provider = VaultSecretsProvider(
            vault_addr="https://vault.example.com:8200",
            vault_token="test-token",
        )
        with pytest.raises(NotImplementedError, match="hvac"):
            await provider.set_secret("key", "value")

    async def test_list_keys_raises(self):
        provider = VaultSecretsProvider(
            vault_addr="https://vault.example.com:8200",
            vault_token="test-token",
        )
        with pytest.raises(NotImplementedError, match="hvac"):
            await provider.list_keys()


class TestAWSSecretsProvider:
    """Tests for AWS Secrets Manager provider stub."""

    async def test_get_secret_raises(self):
        provider = AWSSecretsProvider(region_name="us-east-1")
        with pytest.raises(NotImplementedError, match="boto3"):
            await provider.get_secret("key")

    async def test_set_secret_raises(self):
        provider = AWSSecretsProvider(region_name="us-east-1")
        with pytest.raises(NotImplementedError, match="boto3"):
            await provider.set_secret("key", "value")
