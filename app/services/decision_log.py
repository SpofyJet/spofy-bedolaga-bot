"""Журнал решений: что бот сделал с людьми и почему. Читается SQL-запросом к таблице decision_log, а не поиском по логам.

Логи контейнера пропадают при пересоздании, а файловые ротируются за часы (шум рассылок раздувал их до сотен
мегабайт). Решения, о которых потом спрашивают («за что сняли триал?», «почему не выдали награду?»), лежат в базе.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.database.database import AsyncSessionLocal
from app.database.models import DecisionLog


logger = structlog.get_logger(__name__)

KIND_ABUSE_TRIAL_REMOVED = 'abuse_trial_removed'
KIND_REWARD_BLOCKED = 'friend_reward_blocked'
KIND_REWARD_GRANTED = 'friend_reward_granted'
KIND_MASS_SEND_STARTED = 'mass_send_started'
KIND_MASS_SEND_FINISHED = 'mass_send_finished'
KIND_MASS_SEND_RESUMED = 'mass_send_resumed'
KIND_BROADCAST_RESUMED = 'broadcast_resumed'


async def record_decision(
    kind: str,
    summary: str,
    *,
    user_id: int | None = None,
    panel_user_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Записать решение. Никогда не бросает: журнал не должен ломать то, что он журналирует."""
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                DecisionLog(
                    kind=kind,
                    user_id=user_id,
                    panel_user_id=panel_user_id,
                    summary=summary[:2000],
                    details=details,
                )
            )
            await db.commit()
    except Exception as error:
        logger.warning('Журнал решений: запись не удалась', kind=kind, error=str(error))
