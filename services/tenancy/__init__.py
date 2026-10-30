"""Multi-tenant identity, workspace and role primitives."""

from .schema import ROLES, ensure_schema
from .service import (
    ACTIONS,
    ROLE_PERMISSIONS,
    TenancyError,
    add_member,
    authenticate,
    authorize,
    bootstrap_default_workspace,
    create_user,
    create_workspace,
    get_membership,
    get_user,
    get_user_by_username,
    list_members,
    list_workspaces,
)

__all__ = [
    "ACTIONS",
    "ROLES",
    "ROLE_PERMISSIONS",
    "TenancyError",
    "add_member",
    "authenticate",
    "authorize",
    "bootstrap_default_workspace",
    "create_user",
    "create_workspace",
    "ensure_schema",
    "get_membership",
    "get_user",
    "get_user_by_username",
    "list_members",
    "list_workspaces",
]
