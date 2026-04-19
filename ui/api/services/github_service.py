"""
ConductorAI UI — GitHub App Integration Service
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any, Optional

import httpx
import jwt
import structlog

from ui.api.config import APISettings

logger = structlog.get_logger()

GITHUB_API = "https://api.github.com"


class GitHubService:
    """Handles GitHub App authentication and API calls."""

    def __init__(self, settings: APISettings=None) -> None:
        self._app_id = settings.github_app_id
        self._webhook_secret = settings.github_app_webhook_secret
        self._private_key: Optional[str] = None
        self._token = settings.github_token

        key_path = settings.github_app_private_key_path
        if key_path and Path(key_path).exists():
            self._private_key = Path(key_path).read_text()

    @property
    def configured(self) -> bool:
        return bool(self._app_id and self._private_key)

    """def _generate_jwt(self) -> str:
        if not self._private_key:
            raise RuntimeError("GitHub App private key not configured")
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + (10 * 60), "iss": self._app_id}
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    async def get_installation_token(self, installation_id: int) -> str:
        jwt_token = self._generate_jwt()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            return resp.json()["token"]
    """

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    async def list_repos(self) -> list[dict[str, Any]]:
        #token = await self.get_installation_token(installation_id)
        async with httpx.AsyncClient() as client:
            repos = []
            page = 1
            while True:
                resp = await client.get(
                    f"{GITHUB_API}/installation/repositories",
                    params={"per_page": 100, "page": page},
                    headers=self._headers(self._token),
                )
                resp.raise_for_status()
                data = resp.json()
                repos.extend(data.get("repositories", []))
                if len(repos) >= data.get("total_count", 0):
                    break
                page += 1
            return repos

    async def list_pull_requests(
        self,
        token: str,
        owner: str,
        repo: str,
        state: str = "open",
    ) -> list[dict[str, Any]]:
        #token = await self.get_installation_token(installation_id)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
                params={"state": state, "per_page": 50},
                headers=self._headers(token),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_pr_diff(
        self, token: str, owner: str, repo: str, pr_number: int
    ) -> str:
        #token = await self.get_installation_token(installation_id)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}",
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.diff",
                },
            )
            resp.raise_for_status()
            return resp.text

    async def get_pr_files(
        self, token: str, owner: str, repo: str, pr_number: int
    ) -> list[dict[str, Any]]:
        #token = await self.get_installation_token(installation_id)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files",
                headers=self._headers(token),
            )
            resp.raise_for_status()
            return resp.json()

    async def submit_review(
        self,
        token: str,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",
    ) -> dict[str, Any]:
        # token = await self.get_installation_token(installation_id)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                json={"body": body, "event": event},
                headers=self._headers(token),
            )
            resp.raise_for_status()
            return resp.json()

    async def create_repository(self, name: str, private: bool = False) -> dict[str, Any]:
        # token = await self.get_installation_token(installation_id)
        logger.info("Creating Repository")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GITHUB_API}/user/repos",
                json={"name": name, "private": private},
                headers=self._headers(self._token),
            )
            logger.info(resp.json())
            resp.raise_for_status()
            logger.info("Repository created successfully")
            return resp.json()

    async def create_branch(
        self,
        token: str,
        owner: str,
        repo: str,
        branch_name: str,
        from_sha: str,
    ) -> dict[str, Any]:
        # token = await self.get_installation_token(token)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GITHUB_API}/repos/{owner}/{repo}/git/refs",
                json={"ref": f"refs/heads/{branch_name}", "sha": from_sha},
                headers=self._headers(token),
            )
            resp.raise_for_status()
            return resp.json()

    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: Optional[str] = None,
    ) -> dict[str, Any]:
        # token = await self.get_installation_token(installation_id)
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                json=payload,
                headers=self._headers(self._token),
            )
            resp.raise_for_status()
            return resp.json()

    async def create_pull_request(
        self,
        token: str,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base_branch: str = "main",
    ) -> dict[str, Any]:
        #token = await self.get_installation_token(installation_id)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
                json={"title": title, "body": body, "head": head, "base": base_branch},
                headers=self._headers(token),
            )
            resp.raise_for_status()
            return resp.json()
