"""Докупка из сохранённой корзины, когда панель Remnawave не отвечает, — на PostgreSQL.

Корзина докупки (трафик или устройства) исполняется по кнопке «Оплатить» после
пополнения и тихо — сразу после зачисления денег. Списание коммитилось отдельно
от выдачи, а при сбое панели её сервис делает ``db.rollback()`` и возвращает
``None``: после него чтение ``user.remnawave_id`` падало с MissingGreenlet. Деньги
и лимит к этому моменту уже в базе, но:

- корзина не удалялась — следующее нажатие или следующее пополнение покупали ещё раз;
- оплаченный лимит не ставился в очередь повторов и в панели оставался старым;
- человек видел «Не удалось завершить покупку».

Отдельно: если выдача трафика падала в базе, «компенсирующий возврат» шёл по
протухшему объекту и тоже падал — деньги списаны, трафика нет, возврата нет.

Здесь настоящая покупка и база; не отвечает только панель (502, как 02.11.2026).
"""

from __future__ import annotations

import contextlib

import pytest

from app.config import settings
from app.database.models import Base, Subscription, User
from app.external.remnawave_api import RemnaWaveAPIError
from app.services import subscription_auto_purchase_service as auto_service
from app.services.remnawave_retry_queue import remnawave_retry_queue
from app.services.subscription_service import SubscriptionService
from tests.fixtures.postgres_db import postgres_session
from tests.services import test_addon_cart_real_purchase as scenarios


pytestmark = pytest.mark.postgres

TABLES = list(Base.metadata.sorted_tables)
PANEL_ID = 9001

cart_service = scenarios.cart_service


@pytest.fixture(autouse=True)
def _classic_mode_real_panel(monkeypatch):
    """Как в сценариях докупки, но сервис панели настоящий — недоступна сама панель."""
    monkeypatch.setattr(settings, 'PRICE_PER_DEVICE', scenarios.DEVICE_PRICE)
    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', 0)
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_ENABLED', False)
    monkeypatch.setattr(
        type(settings),
        'get_traffic_topup_price',
        lambda self, gb: scenarios.TRAFFIC_PRICE if gb == 100 else 0,
    )
    monkeypatch.setattr(type(settings), 'is_auto_purchase_after_topup_enabled', lambda self: True)
    monkeypatch.setattr(type(settings), 'is_notifications_enabled', lambda self: True)
    monkeypatch.setattr(auto_service, 'AdminNotificationService', scenarios._AdminNotifyStub)


@pytest.fixture
def panel_down(monkeypatch) -> list[str]:
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


async def _seed_on_panel(db) -> User:
    user, subscription = await scenarios._seed(db)
    user.remnawave_id = PANEL_ID
    subscription.remnawave_id = PANEL_ID
    await db.commit()
    return await db.get(User, scenarios.USER_ID)


async def test_button_devices_while_panel_is_down_charge_once_and_retry(
    postgres_database, cart_service, panel_down, retry_queue
):
    bot = scenarios._bot()
    async with postgres_session(postgres_database, TABLES) as db:
        user = await _seed_on_panel(db)
        cart = scenarios._devices_cart()
        await cart_service.save_user_cart(scenarios.USER_ID, cart)

        succeeded = await auto_service.resume_addon_cart(db, user, cart, bot=bot)
        after = await scenarios._state(db)

    charged = scenarios.BALANCE - after.balance
    assert panel_down, 'до панели дошли — и она не ответила'
    assert succeeded is True, 'после списания нельзя отвечать «Не удалось завершить покупку»'
    assert charged > 0 and [abs(p.amount_kopeks) for p in after.payments] == [charged]
    assert after.devices == 3
    assert await cart_service.get_user_cart(scenarios.USER_ID) is None, 'иначе следующее нажатие купит ещё раз'
    assert [item['subscription_id'] for item in retry_queue] == [scenarios.SUB_ID], 'оплаченный лимит дойдёт до панели'
    assert 'Устройства добавлены' in bot.send_message.call_args.kwargs['text']


async def test_topup_traffic_while_panel_is_down_charge_once_and_retry(
    postgres_database, cart_service, panel_down, retry_queue
):
    async with postgres_session(postgres_database, TABLES) as db:
        user = await _seed_on_panel(db)
        await cart_service.save_user_cart(scenarios.USER_ID, scenarios._traffic_cart())

        succeeded = await auto_service.auto_purchase_saved_cart_after_topup(db, user, bot=None)
        after = await scenarios._state(db)

    charged = scenarios.BALANCE - after.balance
    assert panel_down
    assert succeeded is True
    assert charged > 0 and [abs(p.amount_kopeks) for p in after.payments] == [charged]
    assert after.traffic == 200 and [p.traffic_gb for p in after.purchases] == [100]
    assert await cart_service.get_user_cart(scenarios.USER_ID) is None, 'иначе следующее пополнение купит ещё раз'
    assert await cart_service.has_topup_intent(scenarios.USER_ID) is False
    assert [item['subscription_id'] for item in retry_queue] == [scenarios.SUB_ID]


async def test_traffic_grant_failure_leaves_money_untouched(postgres_database, cart_service, monkeypatch):
    """Выдача трафика упала в базе — списания нет (раньше: списано, трафика нет, возврат упал)."""
    from app.database.crud import subscription as subscription_crud

    async def broken_grant(db, subscription, gb):
        subscription.traffic_limit_gb = (subscription.traffic_limit_gb or 0) + gb
        await db.flush()
        raise RuntimeError('deadlock detected')

    monkeypatch.setattr(subscription_crud, 'add_subscription_traffic', broken_grant)

    async with postgres_session(postgres_database, TABLES) as db:
        user = await _seed_on_panel(db)
        cart = scenarios._traffic_cart()
        await cart_service.save_user_cart(scenarios.USER_ID, cart)

        succeeded = await auto_service.resume_addon_cart(db, user, cart, bot=scenarios._bot())
        after = await scenarios._state(db)
        sub = await db.get(Subscription, scenarios.SUB_ID)

    assert succeeded is False
    assert (after.balance, after.payments, after.traffic) == (scenarios.BALANCE, [], 100), 'ни списания, ни трафика'
    assert sub.purchased_traffic_gb in (0, None)
    assert await cart_service.get_user_cart(scenarios.USER_ID) is not None, 'корзина ждёт повторной попытки'
