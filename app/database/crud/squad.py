import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Squad


logger = structlog.get_logger(__name__)


async def create_squad(
    db: AsyncSession, uuid: str, name: str, country_code: str = None, price_kopeks: int = 0, description: str = None
) -> Squad:
    squad = Squad(uuid=uuid, name=name, country_code=country_code, price_kopeks=price_kopeks, description=description)

    db.add(squad)
    await db.commit()
    await db.refresh(squad)

    logger.info('✅ Создан сквад', name=name)
    return squad


async def update_squad(db: AsyncSession, squad: Squad, **kwargs) -> Squad:
    for field, value in kwargs.items():
        if hasattr(squad, field):
            setattr(squad, field, value)

    await db.commit()
    await db.refresh(squad)

    return squad
