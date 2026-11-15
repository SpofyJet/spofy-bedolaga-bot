from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PrivacyPolicy


logger = structlog.get_logger(__name__)


async def get_privacy_policy(db: AsyncSession, language: str) -> PrivacyPolicy | None:
    result = await db.execute(select(PrivacyPolicy).where(PrivacyPolicy.language == language))
    return result.scalar_one_or_none()


async def upsert_privacy_policy(
    db: AsyncSession,
    language: str,
    content: str,
    *,
    enable_if_new: bool = True,
    is_enabled: bool | None = None,
) -> PrivacyPolicy:
    policy = await get_privacy_policy(db, language)

    if policy:
        policy.content = content or ''
        if is_enabled is not None:
            policy.is_enabled = bool(is_enabled)
        policy.updated_at = datetime.now(UTC)
    else:
        policy = PrivacyPolicy(
            language=language,
            content=content or '',
            is_enabled=bool(enable_if_new) if is_enabled is None else bool(is_enabled),
        )
        db.add(policy)

    await db.commit()
    await db.refresh(policy)

    logger.info('✅ Политика конфиденциальности обновлена', language=language, policy_id=policy.id)

    return policy
