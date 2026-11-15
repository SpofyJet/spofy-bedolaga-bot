"""
Регрессия: create_trial_subscription должна быть идемпотентной.

Проблема: при двойном клике или гонке параллельных запросов оба потока проходили
проверку is_trial_already_used() и оба доходили до INSERT. Второй INSERT нарушал
частичный уникальный индекс ``uq_subscriptions_user_tariff_active`` (user_id,
tariff_id WHERE status IN ('active','trial','limited')) и падал с IntegrityError.

Фикс — два слоя защиты в create_trial_subscription:

1. Идемпотентность: если при проверке existing живая подписка уже найдена
   (active/trial/limited, не PENDING), возвращаем её без INSERT.
2. Защита от гонки (TOCTOU): если между проверкой и commit конкурентный запрос
   успел вставить запись — перехватываем IntegrityError, делаем rollback и
   возвращаем подписку, созданную параллельным потоком.

GitHub issue: https://github.com/BEDOLAGA-DEV/remnawave-bedolaga-telegram-bot/issues/2995
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.database.crud import subscription as sub_crud
from app.database.models import SubscriptionStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _integrity_error() -> IntegrityError:
    """IntegrityError с orig.constraint_name — имитирует asyncpg UniqueViolationError.

    Использует sub_crud.UQ_TRIAL_CONSTRAINT как единственный источник истины,
    чтобы не дублировать строку и не расходиться при переименовании.
    """
    orig = MagicMock()
    orig.constraint_name = sub_crud.UQ_TRIAL_CONSTRAINT
    return IntegrityError('duplicate key', {}, orig)


def _sub(**kw) -> MagicMock:
    """Создаёт мок-подписку с заданными атрибутами."""
    s = MagicMock()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _db() -> AsyncMock:
    """Мок AsyncSession с нужными методами."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.expunge = MagicMock()  # синхронный метод SQLAlchemy
    return db


# ---------------------------------------------------------------------------
# 1. Идемпотентность: возврат активной подписки без повторного INSERT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_subscription_does_not_block_new_trial_single_tariff(monkeypatch):
    """В single-tariff режиме EXPIRED-подписка не блокирует создание нового триала
    (регрессия: if existing: без проверки статуса возвращал устаревшую запись)."""

    expired = _sub(
        id=99,
        user_id=5,
        tariff_id=None,
        status=SubscriptionStatus.EXPIRED.value,
        is_trial=True,
    )
    monkeypatch.setattr(sub_crud, 'get_subscription_by_user_id', AsyncMock(return_value=expired))
    monkeypatch.setattr(sub_crud, 'generate_unique_short_id', AsyncMock(return_value='exp-new'))

    db = _db()
    result = await sub_crud.create_trial_subscription(
        db,
        user_id=5,
        connected_squads=['squad-x'],
    )

    # Новая подписка создана, EXPIRED не вернулась
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    added_obj = db.add.call_args[0][0]
    assert result is added_obj


# ---------------------------------------------------------------------------
# 2. PENDING-триал: переиспользуется (старый путь не сломан)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 3. Защита от гонки: перехват IntegrityError в multi-tariff-режиме
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 4. Защита от гонки: non-multi-tariff-режим
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integrity_error_on_commit_returns_concurrent_subscription_single_tariff(monkeypatch):
    """Та же защита от гонки в режиме без multi-tariff: используем
    get_subscription_by_user_id вместо get_subscription_by_user_and_tariff."""
    monkeypatch.setattr(sub_crud, 'generate_unique_short_id', AsyncMock(return_value='single-id'))

    concurrent = _sub(id=40, user_id=5, tariff_id=None, status=SubscriptionStatus.ACTIVE.value, is_trial=True)

    # Первый вызов (при проверке existing) → None, второй (после rollback) → concurrent
    get_sub_mock = AsyncMock(side_effect=[None, concurrent])
    monkeypatch.setattr(sub_crud, 'get_subscription_by_user_id', get_sub_mock)

    db = _db()
    db.commit.side_effect = _integrity_error()

    result = await sub_crud.create_trial_subscription(
        db,
        user_id=5,
        connected_squads=['squad-x'],
        tariff_id=None,
    )

    assert result is concurrent
    db.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# 5. Счастливый путь: создание новой подписки (нет existing, нет гонки)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 6. Подписка другого тарифа не считается конфликтом
# ---------------------------------------------------------------------------
