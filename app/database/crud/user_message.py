import random

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import UserMessage
from app.utils.validators import sanitize_html


logger = structlog.get_logger(__name__)


async def get_active_user_messages(db: AsyncSession) -> list[UserMessage]:
    result = await db.execute(
        select(UserMessage)
        .where(UserMessage.is_active == True)
        .order_by(UserMessage.sort_order.asc(), UserMessage.created_at.desc())
    )
    return result.scalars().all()


async def get_random_active_message(db: AsyncSession) -> str | None:
    active_messages = await get_active_user_messages(db)

    if not active_messages:
        return None

    random_message = random.choice(active_messages)
    return sanitize_html(random_message.message_text)
