import html
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, WelcomeText


logger = structlog.get_logger(__name__)


async def get_active_welcome_text(db: AsyncSession) -> str | None:
    result = await db.execute(
        select(WelcomeText)
        .where(WelcomeText.is_active == True)
        .where(WelcomeText.is_enabled == True)
        .order_by(WelcomeText.updated_at.desc())
    )
    welcome_text = result.scalar_one_or_none()

    if welcome_text:
        return welcome_text.text_content

    return None


async def get_welcome_text_by_id(db: AsyncSession, welcome_text_id: int) -> WelcomeText | None:
    result = await db.execute(select(WelcomeText).where(WelcomeText.id == welcome_text_id))
    return result.scalar_one_or_none()


async def list_welcome_texts(
    db: AsyncSession,
    *,
    include_inactive: bool = True,
    limit: int = 50,
    offset: int = 0,
):
    query = select(WelcomeText).order_by(WelcomeText.updated_at.desc())
    if not include_inactive:
        query = query.where(WelcomeText.is_active == True)

    result = await db.execute(query.limit(limit).offset(offset))
    return result.scalars().all()


async def count_welcome_texts(db: AsyncSession, *, include_inactive: bool = True) -> int:
    query = select(func.count(WelcomeText.id))
    if not include_inactive:
        query = query.where(WelcomeText.is_active == True)

    result = await db.execute(query)
    return result.scalar()


async def create_welcome_text(
    db: AsyncSession,
    *,
    text_content: str,
    created_by: int | None = None,
    is_enabled: bool = True,
    is_active: bool = True,
) -> WelcomeText:
    resolved_creator = created_by

    if created_by is not None:
        result = await db.execute(select(User.id).where(User.id == created_by))
        resolved_creator = result.scalar_one_or_none()

    if is_active:
        await db.execute(update(WelcomeText).values(is_active=False))

    welcome_text = WelcomeText(
        text_content=text_content,
        is_active=is_active,
        is_enabled=is_enabled,
        created_by=resolved_creator,
    )

    db.add(welcome_text)
    await db.commit()
    await db.refresh(welcome_text)

    logger.info(
        '✅ Создан приветственный текст',
        welcome_text_id=welcome_text.id,
        is_active=welcome_text.is_active,
        is_enabled=welcome_text.is_enabled,
    )
    return welcome_text


async def update_welcome_text(
    db: AsyncSession,
    welcome_text: WelcomeText,
    *,
    text_content: str | None = None,
    is_enabled: bool | None = None,
    is_active: bool | None = None,
) -> WelcomeText:
    if is_active:
        await db.execute(update(WelcomeText).where(WelcomeText.id != welcome_text.id).values(is_active=False))

    if text_content is not None:
        welcome_text.text_content = text_content

    if is_enabled is not None:
        welcome_text.is_enabled = is_enabled

    if is_active is not None:
        welcome_text.is_active = is_active

    welcome_text.updated_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(welcome_text)

    logger.info(
        '📝 Обновлен приветственный текст',
        welcome_text_id=welcome_text.id,
        is_active=welcome_text.is_active,
        is_enabled=welcome_text.is_enabled,
    )
    return welcome_text


async def delete_welcome_text(db: AsyncSession, welcome_text: WelcomeText) -> None:
    await db.delete(welcome_text)
    await db.commit()
    logger.info('🗑️ Удален приветственный текст ID', welcome_text_id=welcome_text.id)


def replace_placeholders(text: str, user) -> str:
    first_name = getattr(user, 'first_name', None)
    username = getattr(user, 'username', None)

    first_name = first_name.strip() if first_name else None
    username = username.strip() if username else None

    user_name = html.escape(first_name or username or 'друг')
    display_first_name = html.escape(first_name or 'друг')
    display_username = f'@{html.escape(username)}' if username else html.escape(first_name or 'друг')
    clean_username = html.escape(username or first_name or 'друг')

    replacements = {
        '{user_name}': user_name,
        '{first_name}': display_first_name,
        '{username}': display_username,
        '{username_clean}': clean_username,
        'Egor': user_name,
    }

    result = text
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    return result


async def get_welcome_text_for_user(db: AsyncSession, user) -> str:
    welcome_text = await get_active_welcome_text(db)

    if not welcome_text:
        return None

    if isinstance(user, str):

        class SimpleUser:
            def __init__(self, name):
                self.first_name = name
                self.username = None

        user = SimpleUser(user)

    return replace_placeholders(welcome_text, user)
