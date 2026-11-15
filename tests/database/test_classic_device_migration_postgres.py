"""Classic subscriptions must retain and pay for carried devices on tariff purchase."""

import inspect
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from app.cabinet.routes.subscription_modules import purchase as cabinet
from app.config import settings
from app.database.crud.user import get_user_by_id
from app.database.models import Base, Subscription, Tariff, Transaction, User
from app.external.remnawave_api import RemnaWaveAPI
from app.handlers.subscription import tariff_purchase as telegram
from app.services import subscription_auto_purchase_service as auto
from app.services.subscription_service import SubscriptionService
from tests.fixtures.postgres_db import postgres_session


pytestmark = pytest.mark.postgres


class Panel(RemnaWaveAPI):
    def __init__(self, now):
        super().__init__(base_url='https://panel.example', api_key='test')
        self.patches = []
        self.account = dict(
            id=9001,
            shortUuid='test-classic',
            username='test-classic',
            expireAt=(now + timedelta(days=10)).isoformat(),
            status='ACTIVE',
            createdAt=now.isoformat(),
            updatedAt=now.isoformat(),
            telegramId=101,
            subscriptionUrl='https://vpn.example/sub/test',
            hwidDeviceLimit=3,
        )

    async def get_user_by_id(self, user_id):
        assert user_id == 9001
        return self._parse_user(self.account)

    async def enrich_user_with_happ_link(self, user):
        return user

    async def _make_request(self, method, path, data=None, **kwargs):
        if (method, path) == ('GET', '/api/hwid/devices/9001'):
            return {'response': {'total': 0, 'devices': []}}
        if (method, path) == ('PATCH', '/api/users'):
            assert data['id'] == 9001
            self.patches.append(data.copy())
            self.account.update(data)
            return {'response': self.account}
        assert (method, path) == ('POST', '/api/users/9001/actions/reset-traffic')
        return {'response': self.account}


@pytest.mark.parametrize('flow', ['cabinet', 'telegram', 'auto'])
async def test_selected_classic_devices_are_priced_and_preserved(
    postgres_database,
    monkeypatch,
    flow,
    days=30,
    base=1,
    old=3,
    tariff_max=None,
    global_max=10,
    expected=3,
    daily=False,
    repeat=False,
    trial=False,
    custom_traffic=None,
    custom_enabled=False,
):
    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', global_max)
    monkeypatch.setattr(settings, 'RESET_DEVICES_ON_RENEWAL', False)
    monkeypatch.setattr(settings, 'ADMIN_NOTIFICATIONS_ENABLED', False)
    monkeypatch.setattr(auto, '_delete_cart_for_subscription', AsyncMock())
    monkeypatch.setattr(telegram.user_cart_service, 'delete_user_cart', AsyncMock())
    monkeypatch.setattr(telegram.user_cart_service, 'delete_subscription_cart', AsyncMock())
    monkeypatch.setattr('app.services.subscription_renewal_service.with_admin_notification_service', AsyncMock())
    trial_notice = AsyncMock()
    if trial and flow == 'telegram_cart_period':

        async def notify(callback):
            await callback(SimpleNamespace(send_subscription_purchase_notification=trial_notice))

        monkeypatch.setattr('app.services.subscription_renewal_service.with_admin_notification_service', notify)

    monkeypatch.setattr(telegram.AdminNotificationService, 'send_subscription_purchase_notification', AsyncMock())
    now = datetime.now(UTC)
    panel = Panel(now)

    @asynccontextmanager
    async def client(self):
        yield panel

    monkeypatch.setattr(SubscriptionService, 'get_api_client', client)
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        db.add_all(
            [
                User(
                    id=1,
                    telegram_id=101,
                    language='ru',
                    status='active',
                    balance_kopeks=10000,
                    remnawave_id=9001,
                ),
                User(id=2, telegram_id=202),
            ]
        )
        tariff = Tariff(
            id=1,
            name='Test',
            is_active=True,
            traffic_limit_gb=100,
            custom_traffic_enabled=custom_traffic is not None or custom_enabled,
            traffic_price_per_gb_kopeks=2,
            min_traffic_gb=10,
            max_traffic_gb=500,
            device_limit=base,
            max_device_limit=tariff_max,
            device_price_kopeks=100,
            period_prices={'30': 300, '45': 450},
            is_daily=daily,
            daily_price_kopeks=100,
            custom_days_enabled=True,
            price_per_day_kopeks=10,
            allowed_squads=['test-squad'],
        )
        db.add(tariff)
        for sub_id, owner, panel_id in [(10, 1, 9001), (20, 2, 9002)]:
            db.add(
                Subscription(
                    id=sub_id,
                    user_id=owner,
                    tariff_id=None,
                    remnawave_id=panel_id,
                    remnawave_short_id=f'test-{sub_id}',
                    subscription_url='https://vpn.example/sub/test',
                    is_trial=trial if sub_id == 10 else False,
                    status='active',
                    end_date=now + timedelta(days=10 if sub_id == 10 else 50),
                    device_limit=old if sub_id == 10 else 7,
                    traffic_used_gb=17,
                )
            )
        await db.commit()
        user = await get_user_by_id(db, 1)
        sub = await db.get(Subscription, 10)
        expected_extra = 0 if base == 0 else max(0, expected - base)
        expected_price = (100 if daily else days * 10) + (
            expected_extra * 100 if daily else expected_extra * 100 * days // 30
        )
        expected_price += (custom_traffic or 0) * 2
        saved_cart = None
        if flow in ('auto_cabinet_cart', 'telegram_cabinet_cart'):
            from fastapi import HTTPException

            saved = AsyncMock()
            monkeypatch.setattr(cabinet.user_cart_service, 'save_user_cart', saved)
            user.balance_kopeks = 1
            await db.commit()
            with pytest.raises(HTTPException) as error:
                await cabinet.purchase_tariff(
                    cabinet.TariffPurchaseRequest(
                        tariff_id=1, period_days=days, traffic_gb=custom_traffic, subscription_id=None
                    ),
                    user,
                    db,
                )
            assert error.value.status_code == 402
            saved_cart = saved.await_args.args[1]
            assert saved_cart['traffic_limit_gb'] == (custom_traffic if custom_traffic is not None else 100)
            user.balance_kopeks = 10000
            await db.commit()
        if flow == 'cabinet':
            preview = await cabinet._build_tariff_response(db, tariff, user=user, subscription=sub)
            assert preview['device_limit'] == expected
            assert preview['extra_devices_count'] == expected_extra
            if daily:
                assert preview['daily_price_kopeks'] == expected_price
            if days in [30, 45]:
                period = next(p for p in preview['periods'] if p['days'] == days)
                assert period['price_kopeks'] == expected_price - (custom_traffic or 0) * 2
            response = await cabinet.purchase_tariff(
                cabinet.TariffPurchaseRequest(
                    tariff_id=1, period_days=days, traffic_gb=custom_traffic, subscription_id=None
                ),
                user,
                db,
            )
            assert response['success']
        elif flow in ('auto', 'auto_cabinet_cart'):
            assert await auto._auto_purchase_tariff(
                db, user, saved_cart or {'tariff_id': 1, 'period_days': days, 'subscription_id': 10}
            )
        elif flow == 'auto_daily':
            assert await auto._auto_purchase_daily_tariff(db, user, {'tariff_id': 1, 'subscription_id': 10})
        else:
            state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=101, user_id=101))
            await state.update_data(target_subscription_id=10, active_subscription_id=10)
            callback = SimpleNamespace(
                data=f'tariff_confirm:1:{days}',
                answer=AsyncMock(),
                bot=SimpleNamespace(send_message=AsyncMock()),
                message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
            )
            if flow in ('telegram_cart_daily', 'telegram_cart_period', 'telegram_cabinet_cart'):
                await state.update_data(target_subscription_id=None, active_subscription_id=20)
                await telegram.return_to_saved_tariff_cart(
                    callback,
                    state,
                    user,
                    db,
                    saved_cart
                    or {
                        'cart_mode': 'daily_tariff_purchase' if daily else 'tariff_purchase',
                        'tariff_id': 1,
                        'period_days': days,
                        'subscription_id': 10,
                        'total_price': 100,
                        'daily_price_kopeks': 100,
                    },
                )
                preview = callback.message.edit_text.await_args.args[0]
                assert f'Устройств: {expected}' in preview
                assert telegram.format_price_kopeks(expected_price) in preview
                assert (await state.get_data())['target_subscription_id'] == 10
                callback.data = (
                    callback.message.edit_text.await_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data
                )
                handler = (
                    telegram.confirm_daily_tariff_purchase
                    if daily
                    else (
                        telegram.handle_custom_confirm
                        if callback.data.startswith('custom_confirm:')
                        else telegram.confirm_tariff_purchase
                    )
                )
                await inspect.unwrap(handler)(callback, user, db, state)
            elif flow == 'telegram_daily':
                await telegram._proceed_with_selected_tariff(callback, user, db, state, 1)
                preview = callback.message.edit_text.await_args.args[0]
                assert f'Устройств: {expected}' in preview
                assert telegram.format_price_kopeks(expected_price) in preview
                callback.data = 'daily_tariff_confirm:1'
                await inspect.unwrap(telegram.confirm_daily_tariff_purchase)(callback, user, db, state)
                if trial:
                    assert telegram.AdminNotificationService.send_subscription_purchase_notification.await_args.kwargs[
                        'was_trial_conversion'
                    ]
            elif flow == 'telegram_custom':
                await state.update_data(custom_days=days, custom_traffic_gb=100)
                preview = await telegram.format_custom_tariff_preview(
                    tariff,
                    days,
                    100,
                    user.balance_kopeks,
                    db_user=user,
                    db=db,
                    state=state,
                )
                assert f'Итого: {telegram.format_price_kopeks(expected_price)}' in preview
                assert f'Устройств: {telegram.Texts.format_device_limit(expected)}' in preview
                callback.data = 'custom_days:1:0'
                await inspect.unwrap(telegram.handle_custom_days_change)(callback, user, db, state)
                callback.data = next(
                    b.callback_data
                    for row in callback.message.edit_text.await_args.kwargs['reply_markup'].inline_keyboard
                    for b in row
                    if b.callback_data and b.callback_data.startswith('custom_confirm:')
                )
                await inspect.unwrap(telegram.handle_custom_confirm)(callback, user, db, state)
                # Экран «Оплата принята» показывает тариф, срок и списание; число
                # устройств проверяется ниже по базе и запросу в панель.
                success_text = callback.message.edit_text.await_args.args[0]
                assert f'Списано: {telegram.format_price_kopeks(expected_price)}' in success_text
            else:
                callback.data = f'tariff_period:1:{days}'
                await inspect.unwrap(telegram.select_tariff_period)(callback, user, db, state)
                preview_state = await state.get_data()
                assert preview_state['final_price'] == expected_price
                callback.data = (
                    callback.message.edit_text.await_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data
                )
                await inspect.unwrap(telegram.confirm_tariff_purchase)(callback, user, db, state)
        if repeat:
            if flow == 'auto_daily':
                assert not await auto._auto_purchase_daily_tariff(db, user, {'tariff_id': 1, 'subscription_id': 10})
            else:
                await inspect.unwrap(telegram.confirm_daily_tariff_purchase)(callback, user, db, state)
        if trial and flow == 'telegram_cart_period':
            call = trial_notice.await_args
            assert call.kwargs.get('was_trial_conversion', call.args[5] if len(call.args) > 5 else None) is True
        await db.refresh(sub)
        await db.refresh(user)
        assert sub.traffic_limit_gb == (custom_traffic if custom_traffic is not None else 100)
        assert sub.tariff_id == 1 and sub.device_limit == expected
        assert sub.remnawave_id == 9001 and sub.subscription_url == 'https://vpn.example/sub/test'
        assert user.balance_kopeks == 10000 - expected_price
        payments = (await db.scalars(select(Transaction))).all()
        assert len(payments) == 1 and payments[0].amount_kopeks == -expected_price
        assert len((await db.scalars(select(Subscription))).all()) == 2
        assert (await db.get(Subscription, 20)).device_limit == 7
        assert (await db.get(Subscription, 20)).end_date == now + timedelta(days=50)
        assert len(panel.patches) == 1 and panel.patches[0]['hwidDeviceLimit'] == expected
        assert (
            panel.patches[0]['trafficLimitBytes'] == (custom_traffic if custom_traffic is not None else 100) * 1024**3
        )


@pytest.mark.parametrize(
    ('base', 'old', 'tariff_max', 'global_max', 'expected'),
    [
        (5, 3, None, 10, 5),
        (1, 5, 3, 10, 3),
        (1, 5, None, 3, 3),
        (0, 3, None, 1, 0),
        (1, 10, 5, 10, 5),
        (2, 10, 5, 10, 5),
    ],
)
async def test_classic_migration_limits(postgres_database, monkeypatch, base, old, tariff_max, global_max, expected):
    await test_selected_classic_devices_are_priced_and_preserved(
        postgres_database,
        monkeypatch,
        'cabinet',
        True,
        base=base,
        old=old,
        tariff_max=tariff_max,
        global_max=global_max,
        expected=expected,
    )


@pytest.mark.parametrize(
    ('base', 'old', 'tariff_max', 'expected'),
    [(1, 3, None, 3), (1, 10, 5, 5), (2, 10, 5, 5), (0, 3, None, 0), (5, 3, None, 5)],
)
async def test_classic_custom_telegram_selected_purchase(
    postgres_database,
    monkeypatch,
    base,
    old,
    tariff_max,
    expected,
):
    await test_selected_classic_devices_are_priced_and_preserved(
        postgres_database,
        monkeypatch,
        'telegram_custom',
        days=75,
        base=base,
        old=old,
        tariff_max=tariff_max,
        expected=expected,
    )


async def test_cabinet_daily_classic_price_matches_charge(postgres_database, monkeypatch):
    await test_selected_classic_devices_are_priced_and_preserved(
        postgres_database, monkeypatch, 'cabinet', days=1, daily=True
    )


@pytest.mark.parametrize('flow', ['telegram_daily', 'auto_daily'])
@pytest.mark.parametrize(
    ('base', 'old', 'tariff_max', 'expected'),
    [(1, 3, None, 3), (1, 10, 5, 5), (2, 10, 5, 5), (0, 3, None, 0), (5, 3, None, 5)],
)
async def test_daily_selected_classic_devices(postgres_database, monkeypatch, flow, base, old, tariff_max, expected):
    await test_selected_classic_devices_are_priced_and_preserved(
        postgres_database,
        monkeypatch,
        flow,
        days=1,
        daily=True,
        base=base,
        old=old,
        tariff_max=tariff_max,
        expected=expected,
    )


@pytest.mark.parametrize('flow', ['telegram_daily', 'auto_daily'])
async def test_repeated_daily_purchase_does_not_charge_twice(postgres_database, monkeypatch, flow):
    await test_selected_classic_devices_are_priced_and_preserved(
        postgres_database,
        monkeypatch,
        flow,
        days=1,
        daily=True,
        repeat=True,
    )


async def test_daily_selected_trial_keeps_conversion_marker(postgres_database, monkeypatch):
    await test_selected_classic_devices_are_priced_and_preserved(
        postgres_database,
        monkeypatch,
        'telegram_daily',
        days=1,
        daily=True,
        trial=True,
        expected=1,
    )


@pytest.mark.parametrize(
    ('flow', 'days', 'daily'),
    [
        ('telegram_cart_daily', 1, True),
        ('telegram_cart_period', 30, False),
        ('telegram_cart_period', 75, False),
    ],
)
async def test_saved_cart_return_keeps_selected_classic_and_requotes(postgres_database, monkeypatch, flow, days, daily):
    await test_selected_classic_devices_are_priced_and_preserved(
        postgres_database,
        monkeypatch,
        flow,
        days=days,
        daily=daily,
    )


@pytest.mark.parametrize('flow', ['cabinet', 'auto_cabinet_cart', 'telegram_cabinet_cart'])
@pytest.mark.parametrize('days', [30, 75])
async def test_custom_traffic_survives_saved_checkout(postgres_database, monkeypatch, flow, days):
    await test_selected_classic_devices_are_priced_and_preserved(
        postgres_database,
        monkeypatch,
        flow,
        days=days,
        custom_traffic=250,
    )


@pytest.mark.parametrize('flow', ['auto_cabinet_cart', 'telegram_cabinet_cart'])
@pytest.mark.parametrize('custom_traffic', [None, 100])
async def test_cart_distinguishes_default_from_explicit_base_traffic(
    postgres_database, monkeypatch, flow, custom_traffic
):
    await test_selected_classic_devices_are_priced_and_preserved(
        postgres_database,
        monkeypatch,
        flow,
        days=75,
        custom_traffic=custom_traffic,
        custom_enabled=True,
    )


@pytest.mark.parametrize('days', [30, 75])
async def test_restored_trial_keeps_conversion_notice(postgres_database, monkeypatch, days):
    await test_selected_classic_devices_are_priced_and_preserved(
        postgres_database,
        monkeypatch,
        'telegram_cart_period',
        days=days,
        trial=True,
        expected=1,
    )
