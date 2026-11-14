from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ServiceRule
from app.localization.texts import refresh_rules_cache


logger = structlog.get_logger(__name__)


async def get_rules_by_language(db: AsyncSession, language: str = 'ru') -> ServiceRule | None:
    result = await db.execute(
        select(ServiceRule)
        .where(ServiceRule.language == language, ServiceRule.is_active == True)
        .order_by(ServiceRule.order, ServiceRule.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_or_update_rules(
    db: AsyncSession, content: str, language: str = 'ru', title: str = 'Правила сервиса'
) -> ServiceRule:
    existing_rules_result = await db.execute(
        select(ServiceRule).where(ServiceRule.language == language, ServiceRule.is_active == True)
    )
    existing_rules = existing_rules_result.scalars().all()

    for rule in existing_rules:
        rule.is_active = False
        rule.updated_at = datetime.now(UTC)

    new_rules = ServiceRule(title=title, content=content, language=language, is_active=True, order=0)

    db.add(new_rules)
    await db.commit()
    await db.refresh(new_rules)
    await refresh_rules_cache(language)

    logger.info('✅ Правила обновлены', language=language, new_rules_id=new_rules.id)
    return new_rules


async def clear_all_rules(db: AsyncSession, language: str = 'ru') -> bool:
    try:
        result = await db.execute(
            update(ServiceRule)
            .where(ServiceRule.language == language, ServiceRule.is_active == True)
            .values(is_active=False, updated_at=datetime.now(UTC))
        )

        await db.commit()
        await refresh_rules_cache(language)

        rows_affected = result.rowcount
        logger.info(
            '✅ Очищены правила для языка . Деактивировано записей', language=language, rows_affected=rows_affected
        )

        return rows_affected > 0

    except Exception as e:
        logger.error('❌ Ошибка при очистке правил для языка', language=language, error=e)
        await db.rollback()
        raise


async def get_current_rules_content(db: AsyncSession, language: str = 'ru') -> str:
    rules = await get_rules_by_language(db, language)

    if rules:
        return rules.content
    return """
🔒 <b>Правила использования сервиса</b>

1. Сервис предоставляется "как есть" без каких-либо гарантий.

2. Запрещается использование сервиса для незаконных действий.

3. Администрация оставляет за собой право заблокировать доступ пользователя при нарушении правил.

4. Возврат средств осуществляется в соответствии с политикой возврата.

5. Пользователь несет полную ответственность за безопасность своего аккаунта.

6. При возникновении вопросов обращайтесь в техническую поддержку.

Используя сервис, вы соглашаетесь с данными правилами.
"""
