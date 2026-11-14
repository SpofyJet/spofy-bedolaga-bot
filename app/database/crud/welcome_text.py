import html

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WelcomeText


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
