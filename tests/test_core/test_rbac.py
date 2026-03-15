"""
Tests for conductor.core.rbac
==============================
"""

from __future__ import annotations

import pytest

from conductor.core.rbac import (
    Permission,
    PermissionDeniedError,
    RBACManager,
    Role,
    ROLE_PERMISSIONS,
)


class TestRole:
    """Tests for Role enum."""

    def test_role_values(self):
        assert Role.ADMIN == "admin"
        assert Role.OPERATOR == "operator"
        assert Role.VIEWER == "viewer"


class TestPermission:
    """Tests for Permission enum."""

    def test_permission_format(self):
        assert Permission.WORKFLOW_CREATE == "workflow:create"
        assert Permission.CONFIG_MODIFY == "config:modify"
        assert Permission.ARTIFACT_DELETE == "artifact:delete"


class TestRolePermissions:
    """Tests for default role-permission mapping."""

    def test_admin_has_all_permissions(self):
        assert ROLE_PERMISSIONS[Role.ADMIN] == set(Permission)

    def test_viewer_cannot_modify(self):
        viewer_perms = ROLE_PERMISSIONS[Role.VIEWER]
        assert Permission.CONFIG_MODIFY not in viewer_perms
        assert Permission.WORKFLOW_RUN not in viewer_perms
        assert Permission.ARTIFACT_DELETE not in viewer_perms

    def test_viewer_can_view(self):
        viewer_perms = ROLE_PERMISSIONS[Role.VIEWER]
        assert Permission.WORKFLOW_VIEW in viewer_perms
        assert Permission.AGENT_VIEW in viewer_perms
        assert Permission.CONFIG_VIEW in viewer_perms

    def test_operator_can_run_but_not_modify_config(self):
        op_perms = ROLE_PERMISSIONS[Role.OPERATOR]
        assert Permission.WORKFLOW_RUN in op_perms
        assert Permission.AGENT_REGISTER in op_perms
        assert Permission.CONFIG_MODIFY not in op_perms
        assert Permission.ARTIFACT_DELETE not in op_perms


class TestRBACManager:
    """Tests for RBACManager."""

    def test_assign_and_get_role(self):
        rbac = RBACManager()
        rbac.assign_role("alice", Role.ADMIN)
        assert rbac.get_role("alice") == Role.ADMIN

    def test_get_role_unassigned(self):
        rbac = RBACManager()
        assert rbac.get_role("unknown") is None

    def test_revoke_role(self):
        rbac = RBACManager()
        rbac.assign_role("alice", Role.ADMIN)
        rbac.revoke_role("alice")
        assert rbac.get_role("alice") is None

    def test_revoke_nonexistent_user_no_error(self):
        rbac = RBACManager()
        rbac.revoke_role("nonexistent")  # Should not raise

    def test_check_permission_admin(self):
        rbac = RBACManager()
        rbac.assign_role("alice", Role.ADMIN)
        assert rbac.check_permission("alice", Permission.CONFIG_MODIFY) is True
        assert rbac.check_permission("alice", Permission.ARTIFACT_DELETE) is True

    def test_check_permission_viewer(self):
        rbac = RBACManager()
        rbac.assign_role("bob", Role.VIEWER)
        assert rbac.check_permission("bob", Permission.WORKFLOW_VIEW) is True
        assert rbac.check_permission("bob", Permission.WORKFLOW_RUN) is False

    def test_check_permission_unassigned(self):
        rbac = RBACManager()
        assert rbac.check_permission("nobody", Permission.WORKFLOW_VIEW) is False

    def test_get_permissions(self):
        rbac = RBACManager()
        rbac.assign_role("alice", Role.OPERATOR)
        perms = rbac.get_permissions("alice")
        assert Permission.WORKFLOW_RUN in perms
        assert Permission.CONFIG_MODIFY not in perms

    def test_get_permissions_unassigned(self):
        rbac = RBACManager()
        assert rbac.get_permissions("nobody") == set()

    def test_require_permission_passes(self):
        rbac = RBACManager()
        rbac.assign_role("alice", Role.ADMIN)
        rbac.require_permission("alice", Permission.CONFIG_MODIFY)  # Should not raise

    def test_require_permission_raises(self):
        rbac = RBACManager()
        rbac.assign_role("bob", Role.VIEWER)
        with pytest.raises(PermissionDeniedError, match="lacks permission"):
            rbac.require_permission("bob", Permission.CONFIG_MODIFY)

    def test_require_permission_error_details(self):
        rbac = RBACManager()
        rbac.assign_role("bob", Role.VIEWER)
        with pytest.raises(PermissionDeniedError) as exc_info:
            rbac.require_permission("bob", Permission.WORKFLOW_RUN)
        err = exc_info.value
        assert err.user_id == "bob"
        assert err.permission == "workflow:run"
        assert err.error_code == "PERMISSION_DENIED"

    def test_custom_role_permissions(self):
        custom = {
            Role.ADMIN: {Permission.WORKFLOW_VIEW},
            Role.OPERATOR: set(),
            Role.VIEWER: set(),
        }
        rbac = RBACManager(role_permissions=custom)
        rbac.assign_role("alice", Role.ADMIN)
        assert rbac.check_permission("alice", Permission.WORKFLOW_VIEW) is True
        assert rbac.check_permission("alice", Permission.CONFIG_MODIFY) is False

    def test_reassign_role(self):
        rbac = RBACManager()
        rbac.assign_role("alice", Role.VIEWER)
        assert rbac.check_permission("alice", Permission.WORKFLOW_RUN) is False
        rbac.assign_role("alice", Role.OPERATOR)
        assert rbac.check_permission("alice", Permission.WORKFLOW_RUN) is True
