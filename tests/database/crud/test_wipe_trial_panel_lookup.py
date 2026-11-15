"""`wipe_trial_subscriptions`: удаление панельного аккаунта при сбросе триала.

Самая разрушительная операция во всей миграции — она вызывает `delete_user`
в панели и потом сносит строку в БД. После 0104 у каждой доапгрейдной строки
`remnawave_id IS NULL`, поэтому ветка «нет id» перестала однозначно означать
«в панели удалять нечего»: у строки может быть живой аккаунт, найденный по
`remnawave_short_uuid`. Ошибка здесь либо оставляет ACTIVE-аккаунт-сироту
(занимает лицензию, связи с ботом нет), либо удаляет ЧУЖОЙ аккаунт.

Мутационная проверка показала, что раньше все эти сценарии проходили при
зелёном прогоне, поэтому они пиннятся отдельно.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.services.subscription_service as subscription_service_mod
from app.config import settings
from app.database.crud.subscription import wipe_trial_subscriptions


@pytest.fixture
def api():
    client = AsyncMock()
    client.delete_user.return_value = True
    return client


@pytest.fixture
def patched_service(monkeypatch, api):
    """Подменяем SubscriptionService целиком: нужен только его API-клиент."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_client():
        yield api

    class _Service:
        is_configured = True
        configuration_error = None

        def get_api_client(self):
            return fake_client()

    # `wipe_trial_subscriptions` импортирует зависимости внутри функции, поэтому
    # подменять их надо в модулях-источниках.
    monkeypatch.setattr(subscription_service_mod, 'SubscriptionService', _Service)
    return api


def _sub(sub_id=42, *, panel_id=None, short_uuid=None, user_panel_id=None):
    return SimpleNamespace(
        id=sub_id,
        remnawave_id=panel_id,
        remnawave_short_uuid=short_uuid,
        remnawave_uuid=None,
        user=SimpleNamespace(id=1, remnawave_id=user_panel_id),
        user_id=1,
    )


@pytest.fixture
def db():
    session = AsyncMock()
    session.execute.return_value = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# REMNAWAVE_USER_DELETE_MODE. Отчёт из «Багов»: при сбросе триала аккаунт
# удалялся из панели, хотя в .env стоял disable. Режим читался только при
# полном удалении пользователя; сброс триала всегда звал delete_user.
# ---------------------------------------------------------------------------


def _executed_updates(db) -> list:
    from sqlalchemy.sql.dml import Update

    return [call.args[0] for call in db.execute.await_args_list if isinstance(call.args[0], Update)]


@pytest.mark.asyncio
async def test_disable_mode_keeps_single_tariff_user_identity(monkeypatch, patched_service, db):
    """Аккаунт остаётся (отключённым) — users.remnawave_id обязан остаться с ним:
    следующий триал или покупка включат тот же аккаунт заново."""
    monkeypatch.setattr(settings, 'REMNAWAVE_USER_DELETE_MODE', 'disable')

    wiped = await wipe_trial_subscriptions(db, [_sub(42, user_panel_id=555)])

    assert wiped == 1
    patched_service.disable_user.assert_awaited_once_with(555)
    patched_service.delete_user.assert_not_awaited()
    assert _executed_updates(db) == []


@pytest.mark.asyncio
async def test_delete_mode_still_clears_single_tariff_user_identity(monkeypatch, patched_service, db):
    """Регресс-стража: в режиме delete аккаунта больше нет — ссылку на него стираем."""
    monkeypatch.setattr(settings, 'REMNAWAVE_USER_DELETE_MODE', 'delete')

    wiped = await wipe_trial_subscriptions(db, [_sub(42, user_panel_id=555)])

    assert wiped == 1
    patched_service.delete_user.assert_awaited_once_with(555)
    assert len(_executed_updates(db)) == 1


# ---------------------------------------------------------------------------
# Мультитариф: первый аккаунт записан и человеку (users.remnawave_id). Сброс
# триала удалял аккаунт в панели, но ссылку у человека стирал только в
# однотарифном режиме — следующая покупка наследовала мёртвый id
# (should_create_panel_account) и сыпала «User not found». Тот же класс, что
# «удалил подписку → купил заново» (8e37e780), только через сброс триала.
# ---------------------------------------------------------------------------


async def _seed_multi(db, *, user_panel_id: int, subs: list[tuple[int, bool]]):
    """subs: (remnawave_id, is_trial). Возвращает (user, [subscriptions])."""
    from datetime import UTC, datetime, timedelta

    from app.database.models import Subscription, SubscriptionStatus, User

    user = User(telegram_id=700, username='multi', language='ru', remnawave_id=user_panel_id)
    db.add(user)
    await db.flush()
    rows = []
    for index, (panel_id, is_trial) in enumerate(subs):
        row = Subscription(
            user_id=user.id,
            status=SubscriptionStatus.EXPIRED.value if is_trial else SubscriptionStatus.ACTIVE.value,
            is_trial=is_trial,
            end_date=datetime.now(UTC) + (timedelta(days=-1) if is_trial else timedelta(days=30)),
            remnawave_id=panel_id,
            remnawave_short_id=f'short{index}',
        )
        db.add(row)
        rows.append(row)
    await db.commit()
    return user, rows


async def _user_panel_id(db, user_id: int):
    from sqlalchemy import select

    from app.database.models import User

    return (await db.execute(select(User.remnawave_id).where(User.id == user_id))).scalar_one()
