"""Банк отклонил оплату: человеку одно сообщение «Оплата не прошла, деньги не списаны».

Platega присылает CANCELED и на отказ, и на счёт, который истёк неоткрытым (через 30 минут);
причины в ответе нет. Отказ приходит, пока счёт ещё жив: за 30 дней 140 таких счетов у 108 человек,
из них 85 счетов (68 человек) — созданы в боте, без нового счёта и без оплаты следом.

Здесь всё настоящее (вебхук PaymentService, SQLite), подменены только бот и настройки Platega.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.config import settings
from app.database.models import (
    CryptoBotPayment,
    Pay2328Payment,
    PlategaPayment,
    SubscriptionEvent,
    Transaction,
    TransactionType,
    User,
    WataPayment,
    XRocketPayment,
)
from app.services import activation_funnel_service as funnel
from app.services.payment_service import PaymentService
from tests.fixtures.sqlite_memory import memory_session


USER_ID = 1
TELEGRAM_ID = 555000111
PAYMENT_ID = 10
AMOUNT = 17900
TABLES = [
    model.__table__
    for model in (
        User,
        PlategaPayment,
        Transaction,
        SubscriptionEvent,
        # Общее напоминание о брошенной оплате смотрит счета всех способов.
        WataPayment,
        XRocketPayment,
        CryptoBotPayment,
        Pay2328Payment,
    )
]


@pytest.fixture(autouse=True)
def _platega_on(monkeypatch):
    monkeypatch.setattr(settings, 'ENABLE_NOTIFICATIONS', True)
    monkeypatch.setattr(type(settings), 'is_platega_enabled', lambda self: True)
    monkeypatch.setattr(type(settings), 'get_platega_active_methods', lambda self: [2, 12])


def _service() -> tuple[PaymentService, AsyncMock]:
    service = PaymentService.__new__(PaymentService)
    service.bot = SimpleNamespace(send_message=AsyncMock())
    service.platega_service = None
    return service, service.bot.send_message


async def _seed(
    db,
    *,
    created_minutes_ago: int = 3,
    expires_in_minutes: int = 27,
    from_bot: bool = True,
    status: str = 'PENDING',
    method_code: int = 2,
) -> None:
    now = datetime.now(UTC)
    metadata = {'language': 'ru', 'selected_method': method_code}
    if from_bot:
        metadata['invoice_message'] = {'chat_id': TELEGRAM_ID, 'message_id': 77}
    db.add_all(
        [
            User(id=USER_ID, telegram_id=TELEGRAM_ID, username='u', status='active', language='ru'),
            PlategaPayment(
                id=PAYMENT_ID,
                user_id=USER_ID,
                platega_transaction_id='tx-1',
                correlation_id='c1',
                amount_kopeks=AMOUNT,
                currency='RUB',
                payment_method_code=method_code,
                status=status,
                is_paid=False,
                metadata_json=metadata,
                created_at=now - timedelta(minutes=created_minutes_ago),
                updated_at=now - timedelta(minutes=created_minutes_ago),
                expires_at=now + timedelta(minutes=expires_in_minutes),
            ),
        ]
    )
    await db.commit()


async def _webhook(service: PaymentService, db, status: str = 'CANCELED') -> bool:
    return await service.process_platega_webhook(
        db, {'id': 'tx-1', 'status': status, 'amount': AMOUNT / 100, 'currency': 'RUB', 'payload': 'platega:c1'}
    )


async def _notice(db) -> str | None:
    payment = await db.get(PlategaPayment, PAYMENT_ID)
    return (payment.metadata_json or {}).get('decline_notice')


def _callbacks(sent: AsyncMock) -> list[str]:
    return [row[0].callback_data for row in sent.await_args.kwargs['reply_markup'].inline_keyboard]


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['CANCELED', 'FAILED'])
async def test_declined_payment_gets_one_message_with_retry_and_other_method(monkeypatch, status):
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db)
        service, sent = _service()

        assert await _webhook(service, db, status) is True

        payment = await db.get(PlategaPayment, PAYMENT_ID)
        assert payment.status == status
        assert await _notice(db) == 'sent'

    sent.assert_awaited_once()
    assert sent.await_args.args[0] == TELEGRAM_ID
    assert 'Оплата не прошла, деньги не списаны.' in sent.await_args.args[1]
    assert _callbacks(sent) == [f'topup_amount|platega_m2|{AMOUNT}', 'balance_topup'], 'та же сумма тем же способом'


@pytest.mark.asyncio
async def test_webhook_retries_do_not_repeat_the_message(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db)
        service, sent = _service()

        for _ in range(3):
            assert await _webhook(service, db) is True

    sent.assert_awaited_once()


@pytest.mark.asyncio
async def test_status_button_pressed_before_the_webhook_does_not_lose_the_message(monkeypatch):
    """«Проверить статус» уже записал CANCELED — вебхук всё равно пишет, один раз."""
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db, status='CANCELED')
        service, sent = _service()

        await _webhook(service, db)
        await _webhook(service, db)

    sent.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_button_is_dropped_when_the_method_is_switched_off(monkeypatch):
    monkeypatch.setattr(type(settings), 'get_platega_active_methods', lambda self: [12])
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db)
        service, sent = _service()

        await _webhook(service, db)

    assert _callbacks(sent) == ['balance_topup']


@pytest.mark.asyncio
async def test_general_reminder_does_not_follow_the_decline_message(monkeypatch):
    """Через 10 минут воронка шлёт «Оплата не завершена» — тому, кому уже написали об отказе, не шлёт."""
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db, created_minutes_ago=12, expires_in_minutes=18)
        service, sent = _service()
        await _webhook(service, db)

        nudge = AsyncMock(return_value=object())
        monkeypatch.setattr(funnel, '_funnel_enabled', lambda: True)
        reminders = await funnel.ActivationFunnelService(bot=MagicMock(), send_func=nudge).process_abandoned_payments(
            db
        )

        events = (await db.execute(select(SubscriptionEvent.event_type, SubscriptionEvent.message))).all()

    sent.assert_awaited_once()
    assert reminders == 0
    nudge.assert_not_awaited()
    assert events == [('funnel_abandoned_topup', 'payment declined notice')]


# ── Когда молчим ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('status', 'expires_in_minutes', 'reason'),
    [
        ('CANCELED', -1, 'expired'),  # счёт дожил до конца срока: отказ от истечения не отличить
        ('CANCELED', -40, 'expired'),
        ('EXPIRED', 27, 'expired'),
    ],
)
async def test_expired_invoice_stays_silent(monkeypatch, status, expires_in_minutes, reason):
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db, created_minutes_ago=31, expires_in_minutes=expires_in_minutes)
        service, sent = _service()

        assert await _webhook(service, db, status) is True
        assert await _notice(db) == reason

    sent.assert_not_awaited()


@pytest.mark.asyncio
async def test_invoice_created_outside_the_bot_stays_silent(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db, from_bot=False)
        service, sent = _service()

        await _webhook(service, db)
        assert await _notice(db) == 'not_from_bot'

    sent.assert_not_awaited()


@pytest.mark.asyncio
async def test_person_who_already_made_a_new_invoice_is_not_disturbed(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db)
        db.add(
            PlategaPayment(
                id=PAYMENT_ID + 1,
                user_id=USER_ID,
                correlation_id='c2',
                amount_kopeks=AMOUNT,
                currency='RUB',
                payment_method_code=2,
                status='PENDING',
                is_paid=False,
            )
        )
        await db.commit()
        service, sent = _service()

        await _webhook(service, db)
        assert await _notice(db) == 'newer_invoice'

    sent.assert_not_awaited()


@pytest.mark.asyncio
async def test_person_who_paid_meanwhile_is_not_told_the_payment_failed(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db)
        db.add(
            Transaction(
                user_id=USER_ID,
                type=TransactionType.DEPOSIT.value,
                amount_kopeks=AMOUNT,
                description='Пополнение',
                is_completed=True,
                # Platega ставит created_at транзакции по созданию счёта — смотрим на время зачисления.
                created_at=datetime.now(UTC) - timedelta(minutes=20),
                completed_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )
        await db.commit()
        service, sent = _service()

        await _webhook(service, db)
        assert await _notice(db) == 'already_paid'

    sent.assert_not_awaited()


@pytest.mark.asyncio
async def test_undelivered_message_is_marked_and_does_not_break_the_webhook(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        await _seed(db)
        service, sent = _service()
        sent.side_effect = RuntimeError('bot was blocked by the user')

        assert await _webhook(service, db) is True
        assert await _webhook(service, db) is True
        assert await _notice(db) == 'undelivered'
        events = (await db.execute(select(SubscriptionEvent))).all()

    sent.assert_awaited_once()
    assert events == [], 'не доставили — общее напоминание остаётся'
