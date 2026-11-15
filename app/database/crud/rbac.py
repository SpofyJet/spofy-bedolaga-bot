from datetime import UTC, datetime

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import AdminAuditLog, AdminRole, UserRole


logger = structlog.get_logger(__name__)

# Superadmin level constant — single source of truth, imported by bootstrap and support_ws
SUPERADMIN_LEVEL = 999


class UserRoleCRUD:
    """CRUD operations for user_roles table + permission aggregation."""

    @staticmethod
    async def get_user_permissions(
        db: AsyncSession,
        user_id: int,
    ) -> tuple[list[str], list[str], int]:
        """Aggregate permissions from all active, non-expired roles.

        Returns:
            (sorted_permissions, role_names, max_level)
        """
        now = datetime.now(UTC)
        result = await db.execute(
            select(UserRole)
            .options(selectinload(UserRole.role))
            .where(
                UserRole.user_id == user_id,
                UserRole.is_active.is_(True),
            )
        )
        user_roles = result.scalars().all()

        permissions: set[str] = set()
        role_names: list[str] = []
        max_level: int = 0

        for ur in user_roles:
            # Skip expired assignments
            if ur.expires_at is not None and ur.expires_at <= now:
                continue
            role = ur.role
            if role is None or not role.is_active:
                continue
            permissions.update(role.permissions or [])
            role_names.append(role.name)
            max_level = max(max_level, role.level)

        return sorted(permissions), role_names, max_level

    @staticmethod
    async def get_superadmin_count(db: AsyncSession) -> int:
        """Count users with an active, non-expired role at superadmin level (999)."""
        now = datetime.now(UTC)
        result = await db.execute(
            select(func.count(func.distinct(UserRole.user_id)))
            .join(AdminRole, UserRole.role_id == AdminRole.id)
            .where(
                UserRole.is_active.is_(True),
                AdminRole.is_active.is_(True),
                AdminRole.level == SUPERADMIN_LEVEL,
                or_(UserRole.expires_at.is_(None), UserRole.expires_at > now),
            )
        )
        return result.scalar() or 0


class AuditLogCRUD:
    """Writes to admin_audit_log table."""

    @staticmethod
    async def create(
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
    ) -> AdminAuditLog:
        entry = AdminAuditLog(
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
        db.add(entry)
        await db.flush()
        await db.refresh(entry)
        logger.debug(
            'Audit log created',
            audit_id=entry.id,
            user_id=user_id,
            action=action,
            status=status,
        )
        return entry
