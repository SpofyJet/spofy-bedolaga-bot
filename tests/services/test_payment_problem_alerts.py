"""Алерты админам в точках «деньги пришли, но не применены».

Логгеры платежей намеренно не уходят в Telegram-лог, поэтому эти места раньше
видели только в логах контейнера.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.database.models import Base, GuestPurchase, GuestPurchaseStatus, User, XRocketPayment
from app.services import payment_problem_alert as alerts
from tests.fixtures.sqlite_memory import memory_session


TABLES = list(Base.metadata.sorted_tables)


def test_alert_text_escapes_and_lists_details():
    text = alerts.build_payment_problem_text(
        provider='xRocket',
        problem='Сумма <не> определена',
        user_id=5,
        amount_kopeks=12345,
        reference='inv<1>',
        details={'Оплачено': '5 USDT', 'Пусто': None},
    )
    assert '&lt;не&gt;' in text
    assert '<code>inv&lt;1&gt;</code>' in text
    assert 'Пользователь: 5' in text
    assert 'Сумма: 123.45 ₽' in text
    assert 'Оплачено: 5 USDT' in text
    assert 'Пусто' not in text


@pytest.mark.asyncio
async def test_alert_goes_to_errors_topic_with_given_bot():
    from app.services.admin_notification_service import AdminNotificationService, NotificationCategory

    with patch.object(AdminNotificationService, 'send_admin_notification', AsyncMock(return_value=True)) as send:
        await alerts.alert_payment_not_applied(object(), provider='Platega', problem='p', user_id=1)
    send.assert_awaited_once()
    assert send.await_args.kwargs['category'] == NotificationCategory.ERRORS


@pytest.mark.asyncio
async def test_alert_without_bot_and_notifications_off_is_quiet():
    with (
        patch.object(type(settings), 'ADMIN_NOTIFICATIONS_ENABLED', False, create=True),
        patch('app.bot_factory.create_bot') as create_bot,
    ):
        await alerts.alert_payment_not_applied(None, provider='Platega', problem='p')
    create_bot.assert_not_called()


@pytest.mark.asyncio
async def test_alert_never_raises():
    from app.services.admin_notification_service import AdminNotificationService

    with patch.object(AdminNotificationService, 'send_admin_notification', AsyncMock(side_effect=RuntimeError('x'))):
        await alerts.alert_payment_not_applied(object(), provider='Platega', problem='p')


@pytest.mark.asyncio
async def test_guest_purchase_amount_mismatch_alerts_once(monkeypatch):
    from app.services.payment.common import try_fulfill_guest_purchase

    async with memory_session(monkeypatch, TABLES) as db:
        db.add(
            GuestPurchase(
                token='tok-1',
                contact_type='email',
                contact_value='a@b.c',
                period_days=30,
                amount_kopeks=29900,
                status=GuestPurchaseStatus.PENDING.value,
            )
        )
        await db.commit()

        meta = {'purpose': 'guest_purchase', 'purchase_token': 'tok-1'}
        with patch('app.services.payment_problem_alert.alert_payment_not_applied', AsyncMock()) as alert:
            for _ in range(2):  # ретрай того же вебхука
                assert (
                    await try_fulfill_guest_purchase(
                        db,
                        metadata=meta,
                        payment_amount_kopeks=100,
                        provider_payment_id='pay-1',
                        provider_name='platega',
                    )
                    is True
                )

        alert.assert_awaited_once()
        kwargs = alert.await_args.kwargs
        assert kwargs['amount_kopeks'] == 100
        assert kwargs['reference'] == 'pay-1'
        assert kwargs['details']['Ожидалось'] == '299.00 ₽'


@pytest.mark.asyncio
async def test_xrocket_paid_invoice_without_amount_alerts_once(monkeypatch):
    from app.services.payment.xrocket import XRocketPaymentMixin

    class Svc(XRocketPaymentMixin):
        bot = None

    async with memory_session(monkeypatch, TABLES) as db:
        db.add(User(id=1, telegram_id=1001, first_name='U', language='ru', balance_kopeks=0))
        db.add(
            XRocketPayment(
                id=1,
                user_id=1,
                invoice_id='inv-9',
                amount='5',
                asset='USDT',
                amount_kopeks=0,
                status='active',
                payload='garbage',
                created_at=datetime.now(UTC),
            )
        )
        await db.commit()

        webhook = {'type': 'invoicePay', 'data': {'id': 'inv-9', 'status': 'paid'}}
        with patch('app.services.payment.xrocket.alert_payment_not_applied', AsyncMock()) as alert:
            assert await Svc().process_xrocket_webhook(db, webhook) is False
            await db.commit()  # как get_db() после обработчика вебхука
            assert await Svc().process_xrocket_webhook(db, webhook) is True  # ретрай: «уже обработан»

        alert.assert_awaited_once()
        assert alert.await_args.kwargs['provider'] == 'xRocket'
        assert alert.await_args.kwargs['reference'] == 'inv-9'
        user = await db.get(User, 1)
        await db.refresh(user)
        assert user.balance_kopeks == 0


@pytest.mark.asyncio
async def test_platega_paid_payment_for_missing_user_alerts():
    from app.services.payment.platega import PlategaPaymentMixin

    class Svc(PlategaPaymentMixin):
        bot = None

    payment = SimpleNamespace(
        transaction_id=None,
        metadata_json={},
        amount_kopeks=50000,
        correlation_id='corr-1',
        user_id=99,
        payment_method_code=2,
        platega_transaction_id='tx-1',
    )
    fake_module = SimpleNamespace(get_user_by_id=AsyncMock(return_value=None))
    with (
        patch('app.services.payment.platega.import_module', lambda name: fake_module),
        patch('app.services.payment.common.try_fulfill_guest_purchase', AsyncMock(return_value=None)),
        patch('app.services.payment.platega.alert_payment_not_applied', AsyncMock()) as alert,
    ):
        assert await Svc()._finalize_platega_payment(object(), payment, {'status': 'CONFIRMED'}) is payment

    alert.assert_awaited_once()
    assert alert.await_args.kwargs['user_id'] == 99
    assert alert.await_args.kwargs['amount_kopeks'] == 50000
