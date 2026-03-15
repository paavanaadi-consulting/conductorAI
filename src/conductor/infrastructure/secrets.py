"""
conductor.infrastructure.secrets - Secrets Management
=======================================================

Provides a pluggable secrets retrieval interface. The default
EnvSecretsProvider reads secrets from environment variables with
a configurable prefix. Stub providers for HashiCorp Vault and
AWS Secrets Manager are included for future implementation.

Architecture:
    SecretsProvider (ABC)
        ├── EnvSecretsProvider      ← Default (reads env vars)
        ├── VaultSecretsProvider    ← Stub (needs hvac package)
        └── AWSSecretsProvider     ← Stub (needs boto3 package)

Usage:
    >>> provider = EnvSecretsProvider(prefix="CONDUCTOR_SECRET_")
    >>> api_key = await provider.get_secret("llm_api_key")
    >>> # Reads CONDUCTOR_SECRET_LLM_API_KEY from environment
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

import structlog

logger = structlog.get_logger()


class SecretsProvider(ABC):
    """Abstract interface for secrets retrieval.

    All secrets providers implement this interface. Users can swap
    implementations without changing application code.
    """

    @abstractmethod
    async def get_secret(self, key: str) -> Optional[str]:
        """Retrieve a secret by key.

        Args:
            key: Secret identifier (e.g., "redis_password").

        Returns:
            The secret value, or None if not found.
        """
        ...

    @abstractmethod
    async def set_secret(self, key: str, value: str) -> None:
        """Store a secret (for providers that support writes).

        Args:
            key: Secret identifier.
            value: Secret value to store.

        Raises:
            NotImplementedError: If the provider is read-only.
        """
        ...

    @abstractmethod
    async def list_keys(self) -> list[str]:
        """List available secret keys.

        Returns:
            List of secret key names (without prefix).
        """
        ...


class EnvSecretsProvider(SecretsProvider):
    """Reads secrets from environment variables.

    Maps secret keys to env vars with a configurable prefix.
    Default prefix: CONDUCTOR_SECRET_

    Example:
        get_secret("redis_password") reads CONDUCTOR_SECRET_REDIS_PASSWORD

    This provider is read-only — set_secret raises NotImplementedError
    since environment variables cannot be reliably set at runtime for
    other processes.
    """

    def __init__(self, prefix: str = "CONDUCTOR_SECRET_") -> None:
        self._prefix = prefix
        self._logger = logger.bind(component="env_secrets_provider")

    async def get_secret(self, key: str) -> Optional[str]:
        """Read a secret from environment variables.

        Args:
            key: Secret name (converted to uppercase, prefixed).

        Returns:
            The env var value, or None if not set.
        """
        env_key = f"{self._prefix}{key.upper()}"
        value = os.environ.get(env_key)
        if value is not None:
            self._logger.debug("secret_retrieved", key=key)
        return value

    async def set_secret(self, key: str, value: str) -> None:
        """Not supported for environment variables.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "EnvSecretsProvider is read-only. "
            "Set environment variables before starting the application."
        )

    async def list_keys(self) -> list[str]:
        """List all env vars matching the prefix.

        Returns:
            List of key names with prefix stripped and lowercased.
        """
        keys = []
        for env_key in os.environ:
            if env_key.startswith(self._prefix):
                name = env_key[len(self._prefix) :].lower()
                keys.append(name)
        return sorted(keys)


class VaultSecretsProvider(SecretsProvider):
    """HashiCorp Vault secrets provider (stub).

    Requires the `hvac` package: pip install hvac

    Args:
        vault_addr: Vault server URL (e.g., "https://vault.example.com:8200").
        vault_token: Authentication token.
        mount_point: KV secrets engine mount point (default: "secret").
        path_prefix: Path prefix within the mount (default: "conductorai").
    """

    def __init__(
        self,
        vault_addr: str,
        vault_token: str,
        mount_point: str = "secret",
        path_prefix: str = "conductorai",
    ) -> None:
        self._vault_addr = vault_addr
        self._vault_token = vault_token
        self._mount_point = mount_point
        self._path_prefix = path_prefix

    async def get_secret(self, key: str) -> Optional[str]:
        raise NotImplementedError(
            "VaultSecretsProvider requires the 'hvac' package. "
            "Install with: pip install hvac"
        )

    async def set_secret(self, key: str, value: str) -> None:
        raise NotImplementedError(
            "VaultSecretsProvider requires the 'hvac' package. "
            "Install with: pip install hvac"
        )

    async def list_keys(self) -> list[str]:
        raise NotImplementedError(
            "VaultSecretsProvider requires the 'hvac' package. "
            "Install with: pip install hvac"
        )


class AWSSecretsProvider(SecretsProvider):
    """AWS Secrets Manager provider (stub).

    Requires the `boto3` package: pip install boto3

    Args:
        region_name: AWS region (e.g., "us-east-1").
        secret_prefix: Prefix for secret names in AWS (default: "conductorai/").
    """

    def __init__(
        self,
        region_name: str = "us-east-1",
        secret_prefix: str = "conductorai/",
    ) -> None:
        self._region_name = region_name
        self._secret_prefix = secret_prefix

    async def get_secret(self, key: str) -> Optional[str]:
        raise NotImplementedError(
            "AWSSecretsProvider requires the 'boto3' package. "
            "Install with: pip install boto3"
        )

    async def set_secret(self, key: str, value: str) -> None:
        raise NotImplementedError(
            "AWSSecretsProvider requires the 'boto3' package. "
            "Install with: pip install boto3"
        )

    async def list_keys(self) -> list[str]:
        raise NotImplementedError(
            "AWSSecretsProvider requires the 'boto3' package. "
            "Install with: pip install boto3"
        )
