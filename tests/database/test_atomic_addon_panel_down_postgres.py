"""Докупка трафика и устройств, когда панель Remnawave не отвечает, — на PostgreSQL.

Сервис панели при её сбое делает ``db.rollback()`` и возвращает ``None``. Откат помечает
протухшими все объекты сессии, и первое же чтение поля после него падало с MissingGreenlet.
В докупках деньги к этому моменту уже были списаны отдельным коммитом, а дальше:

- бот, «Добавить трафик» и кабинет, «Докупка трафика»: запись о платеже создавалась ПОСЛЕ
  панели и не создавалась вовсе — баланс меньше суммы записей, человек видел «Ошибка»;
- бот, «Изменить устройства» и кабинет, «Купить устройства»: деньги и лимит в базе есть,
  но человек видел «Ошибка»/HTTP 500 и шёл платить ещё раз;
- во всех четырёх путях в очередь повторов панели ничего не ставилось: лимит в панели
  оставался старым, хотя оплачен.

Здесь настоящие обработчики и база, не отвечает только панель (502, как 02.11.2026).
"""

from __future__ import annotations

import contextlib
import inspect
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.config import settings
from app.database.models import Base, Subscription, Tariff, Transaction, TransactionType, User
from app.external.remnawave_api import RemnaWaveAPIError
from app.localization.texts import get_texts
from app.services.remnawave_retry_queue import remnawave_retry_queue
from app.services.subscription_service import SubscriptionService
from tests.fixtures.postgres_db import postgres_session


pytestmark = pytest.mark.postgres

TABLES = list(Base.metadata.sorted_tables)

USER_ID = 7
SUB_ID = 42
TARIFF_ID = 3
PANEL_ID = 9001
BALANCE = 100_000
TRAFFIC_GB = 50
TRAFFIC_PRICE = 15_000
DEVICE_PRICE = 5_000
DEVICE_LIMIT = 3


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_ENABLED', False)
    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', 10)
    monkeypatch.setattr('app.services.user_cart_service.user_cart_service.save_user_cart', AsyncMock())
    monkeypatch.setattr('app.services.user_cart_service.user_cart_service.delete_user_cart', AsyncMock())


@pytest.fixture
def panel_down(monkeypatch) -> list[str]:
    """Панель отвечает 502 на любой запрос."""
    requests: list[str] = []

    @contextlib.asynccontextmanager
    async def no_panel(self):
        requests.append('request')
        raise RemnaWaveAPIError('Bad Gateway', 502)
        yield  # pragma: no cover

    monkeypatch.setattr(SubscriptionService, 'get_api_client', no_panel)
    return requests


@pytest.fixture
def retry_queue(monkeypatch) -> list[dict]:
    queued: list[dict] = []
    monkeypatch.setattr(remnawave_retry_queue, 'enqueue', lambda **kwargs: queued.append(kwargs))
    return queued


async def _seed(db) -> datetime:
    now = datetime.now(UTC)
    db.add_all(
        [
            User(
                id=USER_ID,
                telegram_id=555000111,
                first_name='U',
                status='active',
                language='ru',
                balance_kopeks=BALANCE,
                remnawave_id=PANEL_ID,
            ),
            Tariff(
                id=TARIFF_ID,
                name='🏴‍☠️ С Обходами',
                is_active=True,
                traffic_limit_gb=100,
                device_limit=DEVICE_LIMIT,
                device_price_kopeks=DEVICE_PRICE,
                device_price_flat=True,
                traffic_topup_enabled=True,
                traffic_topup_packages={str(TRAFFIC_GB): TRAFFIC_PRICE},
                period_prices={'30': 27_000},
                allowed_squads=['squad'],
            ),
        ]
    )
    await db.commit()
    db.add(
        Subscription(
            id=SUB_ID,
            user_id=USER_ID,
            tariff_id=TARIFF_ID,
            status='active',
            is_trial=False,
            start_date=now - timedelta(days=10),
            end_date=now + timedelta(days=20),
            traffic_limit_gb=100,
            traffic_used_gb=0.0,
            device_limit=DEVICE_LIMIT,
            connected_squads=['squad'],
            subscription_url='https://sub.example/abc',
            remnawave_id=PANEL_ID,
            remnawave_short_id='short-42',
        )
    )
    await db.commit()
    return now


async def _state(db) -> tuple[int, list[int], Subscription]:
    db.expire_all()
    user = await db.get(User, USER_ID)
    sub = await db.get(Subscription, SUB_ID)
    payments = (
        await db.execute(
            select(Transaction.amount_kopeks).where(
                Transaction.user_id == USER_ID,
                Transaction.type == TransactionType.SUBSCRIPTION_PAYMENT.value,
                Transaction.is_completed.is_(True),
            )
        )
    ).scalars()
    return user.balance_kopeks, [abs(amount) for amount in payments], sub


def _callback(data: str) -> SimpleNamespace:
    return SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        bot=SimpleNamespace(),
        message=SimpleNamespace(edit_text=AsyncMock()),
        from_user=SimpleNamespace(id=555000111, username=None),
    )


def _shown(callback) -> str:
    call = callback.message.edit_text.await_args
    return call.args[0] if call else ''


# ── Трафик ──────────────────────────────────────────────────────────────────


async def test_bot_traffic_paid_while_panel_is_down_is_recorded_and_retried(postgres_database, panel_down, retry_queue):
    from app.handlers.subscription.traffic import add_traffic

    async with postgres_session(postgres_database, TABLES) as db:
        await _seed(db)
        callback = _callback(f'add_traffic_{TRAFFIC_GB}')

        await inspect.unwrap(add_traffic)(callback, await db.get(User, USER_ID), db, None)

        balance, payments, sub = await _state(db)

    assert panel_down, 'до панели дошли — и она не ответила'
    assert (balance, payments) == (BALANCE - TRAFFIC_PRICE, [TRAFFIC_PRICE]), 'списание записано в платежи'
    assert sub.traffic_limit_gb == 100 + TRAFFIC_GB and sub.purchased_traffic_gb == TRAFFIC_GB
    assert _shown(callback) != get_texts('ru').ERROR, 'после списания нельзя показывать «Ошибка»'
    assert 'Трафик успешно добавлен' in _shown(callback)
    assert [item['subscription_id'] for item in retry_queue] == [SUB_ID], 'оплаченный лимит дойдёт до панели'


async def test_cabinet_traffic_paid_while_panel_is_down_is_recorded_and_retried(
    postgres_database, panel_down, retry_queue
):
    from app.cabinet.routes.subscription_modules.traffic import purchase_traffic
    from app.cabinet.schemas.subscription import TrafficPurchaseRequest

    async with postgres_session(postgres_database, TABLES) as db:
        await _seed(db)

        response = await purchase_traffic(
            request=TrafficPurchaseRequest(gb=TRAFFIC_GB),
            user=await db.get(User, USER_ID),
            db=db,
            subscription_id=None,
        )

        balance, payments, sub = await _state(db)

    assert panel_down
    assert (balance, payments) == (BALANCE - TRAFFIC_PRICE, [TRAFFIC_PRICE]), 'списание записано в платежи'
    assert sub.traffic_limit_gb == 100 + TRAFFIC_GB
    assert response['success'] is True and response['new_traffic_limit_gb'] == 100 + TRAFFIC_GB
    assert [item['subscription_id'] for item in retry_queue] == [SUB_ID]


# ── Устройства ──────────────────────────────────────────────────────────────


async def test_bot_device_change_paid_while_panel_is_down_shows_success_and_retries(
    postgres_database, panel_down, retry_queue
):
    from app.handlers.subscription.devices import execute_change_devices

    async with postgres_session(postgres_database, TABLES) as db:
        await _seed(db)
        callback = _callback(f'confirm_change_devices_{DEVICE_LIMIT + 1}')

        await inspect.unwrap(execute_change_devices)(callback, await db.get(User, USER_ID), db, None)

        balance, payments, sub = await _state(db)

    assert panel_down
    assert (balance, payments) == (BALANCE - DEVICE_PRICE, [DEVICE_PRICE])
    assert sub.device_limit == DEVICE_LIMIT + 1
    assert _shown(callback) != get_texts('ru').ERROR, 'после списания нельзя показывать «Ошибка»'
    assert [item['subscription_id'] for item in retry_queue] == [SUB_ID], 'оплаченный лимит дойдёт до панели'


async def test_bot_add_devices_paid_while_panel_is_down_is_recorded_and_retried(
    postgres_database, panel_down, retry_queue
):
    from app.handlers.subscription.devices import confirm_add_devices

    async with postgres_session(postgres_database, TABLES) as db:
        await _seed(db)
        callback = _callback('add_devices_1')

        await inspect.unwrap(confirm_add_devices)(callback, await db.get(User, USER_ID), db, None)

        balance, payments, sub = await _state(db)

    assert panel_down
    assert (balance, payments) == (BALANCE - DEVICE_PRICE, [DEVICE_PRICE]), 'списание записано в платежи'
    assert sub.device_limit == DEVICE_LIMIT + 1
    assert _shown(callback) != get_texts('ru').ERROR
    assert [item['subscription_id'] for item in retry_queue] == [SUB_ID]


async def test_cabinet_devices_paid_while_panel_is_down_answers_success_and_retries(
    postgres_database, panel_down, retry_queue
):
    from app.cabinet.routes.subscription_modules.devices import purchase_devices
    from app.cabinet.schemas.subscription import DevicePurchaseRequest

    async with postgres_session(postgres_database, TABLES) as db:
        await _seed(db)

        response = await purchase_devices(
            request=DevicePurchaseRequest(devices=1),
            subscription_id=None,
            user=await db.get(User, USER_ID),
            db=db,
        )

        balance, payments, sub = await _state(db)

    assert panel_down
    assert (balance, payments) == (BALANCE - DEVICE_PRICE, [DEVICE_PRICE])
    assert sub.device_limit == DEVICE_LIMIT + 1
    assert response['success'] is True and response['new_device_limit'] == DEVICE_LIMIT + 1, 'не HTTP 500 после оплаты'
    assert [item['subscription_id'] for item in retry_queue] == [SUB_ID]
