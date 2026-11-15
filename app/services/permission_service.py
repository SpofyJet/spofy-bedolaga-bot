"""Permission Engine — RBAC evaluation for admin cabinet.

Role-based permission checks with fnmatch wildcards.
"""

from __future__ import annotations

from fnmatch import fnmatch
from typing import TYPE_CHECKING

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud.rbac import SUPERADMIN_LEVEL, AuditLogCRUD, UserRoleCRUD


if TYPE_CHECKING:
    from app.database.models import User


logger = structlog.get_logger(__name__)


def _is_legacy_admin(user: User) -> bool:
    """Check if user is a legacy config-based admin (ADMIN_IDS / ADMIN_EMAILS).

    Routed through is_user_admin_by_env so the ADMIN_EMAILS match honours the
    trusted email_verification_source guard. settings.is_admin() trusts
    email_verified alone, but untrusted sources (VK/Yandex OAuth) set
    email_verified=True without proof of ownership and must not escalate.
    """
    from app.services.rbac_bootstrap_service import is_user_admin_by_env

    return is_user_admin_by_env(user).is_admin


# ---------------------------------------------------------------------------
# Permission Registry — section -> available actions
# ---------------------------------------------------------------------------

PERMISSION_REGISTRY: dict[str, list[str]] = {
    'users': [
        'read',
        'edit',
        'block',
        'delete',
        'sync',
        'promo_group',
        'balance',
        'subscription',
        'send_offer',
        'send_message',
        'referral',
    ],
    'tickets': ['read', 'reply', 'close', 'settings'],
    'stats': ['read', 'export'],
    'sales_stats': ['read', 'export'],
    'broadcasts': ['read', 'create', 'edit', 'delete', 'send'],
    'tariffs': ['read', 'create', 'edit', 'delete'],
    'promocodes': ['read', 'create', 'edit', 'delete', 'stats'],
    'promo_groups': ['read', 'create', 'edit', 'delete'],
    'promo_offers': ['read', 'create', 'edit', 'send'],
    'campaigns': ['read', 'create', 'edit', 'delete', 'stats'],
    'partners': ['read', 'edit', 'approve', 'revoke', 'settings'],
    'withdrawals': ['read', 'approve', 'reject'],
    'payments': ['read', 'edit', 'export'],
    'payment_methods': ['read', 'edit'],
    'servers': ['read', 'edit'],
    'remnawave': ['read', 'sync', 'manage'],
    'traffic': ['read', 'export'],
    'settings': ['read', 'edit'],
    'system_errors': ['read', 'manage'],
    'channels': ['read', 'edit'],
    'wheel': ['read', 'edit'],
    'apps': ['read', 'edit'],
    'email_templates': ['read', 'edit'],
    'pinned_messages': ['read', 'create', 'edit', 'delete'],
    'user_reminders': ['read', 'create', 'edit', 'delete'],
    'updates': ['read', 'manage'],
    'info_pages': ['read', 'create', 'edit', 'delete'],
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_all_permissions() -> list[str]:
    """Return flat list of all permissions: ``['users:read', 'users:edit', ...]``."""
    return [f'{section}:{action}' for section, actions in PERMISSION_REGISTRY.items() for action in actions]


def permission_matches(user_perm: str, required_perm: str) -> bool:
    """Check if *user_perm* grants access for *required_perm*.

    Wildcard rules (fnmatch):
    - ``*:*``        matches everything
    - ``users:*``    matches ``users:read``, ``users:edit``, ...
    - ``users:read`` matches only ``users:read``
    """
    return fnmatch(required_perm, user_perm)


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class PermissionService:
    """Stateless RBAC permission engine."""

    @staticmethod
    async def check_permission(
        db: AsyncSession,
        user: User,
        required_permission: str,
    ) -> tuple[bool, str]:
        """Evaluate whether *user* may perform *required_permission*.

        Returns ``(allowed, reason)`` tuple.

        Algorithm:
        1. Legacy config-based admins (ADMIN_IDS / ADMIN_EMAILS) get full access.
        2. Aggregate user permissions via ``UserRoleCRUD.get_user_permissions``.
        3. Grant when any RBAC permission matches the required one (fnmatch).
        """
        # Step 0 -- legacy config-based admins get full access
        if _is_legacy_admin(user):
            return True, 'Granted by legacy admin config'

        # Step 1 -- aggregate RBAC permissions
        permissions, _role_names, _max_level = await UserRoleCRUD.get_user_permissions(db, user.id)

        if not permissions:
            logger.debug(
                'Permission denied: no active roles',
                user_id=user.id,
                required=required_permission,
            )
            return False, 'No active roles assigned'

        # Step 2 -- RBAC wildcard matching
        if not any(permission_matches(perm, required_permission) for perm in permissions):
            logger.debug(
                'Permission denied: RBAC mismatch',
                user_id=user.id,
                required=required_permission,
                permissions=permissions,
            )
            return False, 'Permission not granted by any role'

        return True, 'Granted by RBAC'

    @staticmethod
    async def get_user_permissions(db: AsyncSession, user_id: int, user: User | None = None) -> dict:
        """Return aggregated permission info for a user.

        Returns::

            {
                'permissions': ['users:read', ...],
                'roles': ['editor', 'moderator'],
                'role_level': 50,
            }
        """
        permissions, role_names, max_level = await UserRoleCRUD.get_user_permissions(db, user_id)

        # Legacy config-based admins get full superadmin permissions
        # Level is SUPERADMIN_LEVEL + 1 so they can manage all roles including level-999
        if user is not None and not permissions and _is_legacy_admin(user):
            permissions = ['*:*']
            role_names = ['superadmin']
            max_level = SUPERADMIN_LEVEL + 1

        return {
            'permissions': permissions,
            'roles': role_names,
            'role_level': max_level,
        }

    @staticmethod
    async def log_action(
        db: AsyncSession,
        *,
        user_id: int,
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        status: str = 'success',
        request_method: str | None = None,
        request_path: str | None = None,
    ) -> None:
        """Persist an admin audit log entry via ``AuditLogCRUD``."""
        await AuditLogCRUD.create(
            db,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            request_method=request_method,
            request_path=request_path,
        )
