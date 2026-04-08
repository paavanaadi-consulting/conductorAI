"""
conductor.core.rbac - Role-Based Access Control
=================================================

Provides a minimal RBAC system for ConductorAI. Users integrate
this by calling check_permission() before executing protected
operations in their application layer.

Architecture:
    RBACManager is a plain in-memory permission checker with no I/O.
    It lives in core/ because it deals only in data models and enums.

    ┌─────────────────────────────────┐
    │ User's Application              │
    │   rbac.require_permission(      │
    │     user_id, Permission.RUN)    │
    │   await conductor.run_workflow()│
    └─────────────────────────────────┘

Usage:
    >>> rbac = RBACManager()
    >>> rbac.assign_role("user-123", Role.OPERATOR)
    >>> rbac.check_permission("user-123", Permission.WORKFLOW_RUN)
    True
    >>> rbac.check_permission("user-123", Permission.CONFIG_MODIFY)
    False
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from src.conductor.core.exceptions import ConductorError


class PermissionDeniedError(ConductorError):
    """Raised when a user lacks permission for a requested action.

    Attributes:
        user_id: The user who attempted the action.
        permission: The permission that was denied.
    """

    def __init__(
        self,
        message: str,
        user_id: str,
        permission: str,
        error_code: str = "PERMISSION_DENIED",
        details: Optional[dict] = None,
    ) -> None:
        enriched = details or {}
        enriched["user_id"] = user_id
        enriched["permission"] = permission
        super().__init__(message=message, error_code=error_code, details=enriched)
        self.user_id = user_id
        self.permission = permission


class Role(str, Enum):
    """User roles for access control."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Permission(str, Enum):
    """Granular permissions for ConductorAI operations."""

    # Workflow permissions
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_RUN = "workflow:run"
    WORKFLOW_CANCEL = "workflow:cancel"
    WORKFLOW_VIEW = "workflow:view"

    # Agent permissions
    AGENT_REGISTER = "agent:register"
    AGENT_UNREGISTER = "agent:unregister"
    AGENT_VIEW = "agent:view"

    # Configuration permissions
    CONFIG_MODIFY = "config:modify"
    CONFIG_VIEW = "config:view"

    # Artifact permissions
    ARTIFACT_VIEW = "artifact:view"
    ARTIFACT_DELETE = "artifact:delete"


# Default role → permission mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: set(Permission),
    Role.OPERATOR: {
        Permission.WORKFLOW_CREATE,
        Permission.WORKFLOW_RUN,
        Permission.WORKFLOW_CANCEL,
        Permission.WORKFLOW_VIEW,
        Permission.AGENT_REGISTER,
        Permission.AGENT_UNREGISTER,
        Permission.AGENT_VIEW,
        Permission.CONFIG_VIEW,
        Permission.ARTIFACT_VIEW,
    },
    Role.VIEWER: {
        Permission.WORKFLOW_VIEW,
        Permission.AGENT_VIEW,
        Permission.CONFIG_VIEW,
        Permission.ARTIFACT_VIEW,
    },
}


class RBACManager:
    """In-memory role-based access control manager.

    Manages user → role assignments and checks permissions against
    the role-permission mapping. Users integrate this into their
    application layer before calling ConductorAI operations.

    Args:
        role_permissions: Custom role → permission mapping. If None,
            uses the default ROLE_PERMISSIONS.

    Example:
        >>> rbac = RBACManager()
        >>> rbac.assign_role("alice", Role.ADMIN)
        >>> rbac.assign_role("bob", Role.VIEWER)
        >>> rbac.check_permission("alice", Permission.CONFIG_MODIFY)
        True
        >>> rbac.require_permission("bob", Permission.CONFIG_MODIFY)
        PermissionDeniedError: ...
    """

    def __init__(
        self,
        role_permissions: Optional[dict[Role, set[Permission]]] = None,
    ) -> None:
        self._role_permissions = role_permissions or ROLE_PERMISSIONS
        self._user_roles: dict[str, Role] = {}

    def assign_role(self, user_id: str, role: Role) -> None:
        """Assign a role to a user.

        Args:
            user_id: Unique user identifier.
            role: Role to assign.
        """
        self._user_roles[user_id] = role

    def revoke_role(self, user_id: str) -> None:
        """Remove a user's role assignment.

        Args:
            user_id: User to revoke role from.
        """
        self._user_roles.pop(user_id, None)

    def get_role(self, user_id: str) -> Optional[Role]:
        """Get a user's assigned role.

        Args:
            user_id: User to look up.

        Returns:
            The user's role, or None if no role assigned.
        """
        return self._user_roles.get(user_id)

    def get_permissions(self, user_id: str) -> set[Permission]:
        """Get all permissions for a user based on their role.

        Args:
            user_id: User to look up.

        Returns:
            Set of permissions, or empty set if no role assigned.
        """
        role = self._user_roles.get(user_id)
        if role is None:
            return set()
        return self._role_permissions.get(role, set())

    def check_permission(self, user_id: str, permission: Permission) -> bool:
        """Check if a user has a specific permission.

        Args:
            user_id: User to check.
            permission: Permission to verify.

        Returns:
            True if the user has the permission, False otherwise.
        """
        return permission in self.get_permissions(user_id)

    def require_permission(self, user_id: str, permission: Permission) -> None:
        """Assert that a user has a permission, raising on denial.

        Args:
            user_id: User to check.
            permission: Required permission.

        Raises:
            PermissionDeniedError: If the user lacks the permission.
        """
        if not self.check_permission(user_id, permission):
            role = self._user_roles.get(user_id)
            role_name = role.value if role else "none"
            raise PermissionDeniedError(
                message=(
                    f"User '{user_id}' (role: {role_name}) "
                    f"lacks permission '{permission.value}'"
                ),
                user_id=user_id,
                permission=permission.value,
                details={"role": role_name},
            )
