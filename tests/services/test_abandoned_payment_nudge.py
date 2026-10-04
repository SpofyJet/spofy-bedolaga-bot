"""Напоминание о брошенной оплате: через 10 минут, один раз, без лишних людей."""

import contextlib
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import (
    Base,
    HeleketPayment,
    PlategaPayment,
    SubscriptionEvent,
    Transaction,
    TransactionType,
    User,
    WataPayment,
    XRocketPayment,
)
from app.services import activation_funnel_service as funnel


NOW = datetime.now(UTC)


def _ensure_real_aiosqlite(monkeypatch):
    stub = sys.modules.get('aiosqlite')
    if stub is not None and not hasattr(stub, 'connect'):
        monkeypatch.delitem(sys.modules, 'aiosqlite', raising=False)


@contextlib.asynccontextmanager
async def _session(monkeypatch):
    _ensure_real_aiosqlite(monkeypatch)
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    tables = [
        m.__table__
        for m in (User, PlategaPayment, WataPayment, XRocketPayment, HeleketPayment, Transaction, SubscriptionEvent)
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


def _user(uid=1, **kw):
    return User(id=uid, telegram_id=1000 + uid, username=f'u{uid}', status='active', language='ru', **kw)


def _platega(uid, minutes_ago, *, amount=31500, status='CANCELED', is_paid=False):
    return PlategaPayment(
        user_id=uid,
        amount_kopeks=amount,
        status=status,
        is_paid=is_paid,
        correlation_id=f'c{uid}{minutes_ago}',
        payment_method_code=2,
        created_at=NOW - timedelta(minutes=minutes_ago),
        updated_at=NOW - timedelta(minutes=minutes_ago),
    )


def _service(monkeypatch):
    sent = AsyncMock(return_value=object())
    monkeypatch.setattr(funnel, '_funnel_enabled', lambda: True)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='СБП', callback_data='topup_amount|platega|31500')],
            [InlineKeyboardButton(text='навигация', callback_data='balance_topup')],
        ]
    )
    monkeypatch.setattr('app.keyboards.inline.get_payment_methods_keyboard', lambda amount, lang: keyboard)
    return funnel.ActivationFunnelService(bot=MagicMock(), send_func=sent), sent


async def test_sends_after_ten_minutes_with_amount_and_methods(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add_all([_user(), _platega(1, 15)])
        await db.commit()
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_payments(db) == 1

    text = sent.await_args.args[1]
    assert '315 ₽' in text and 'Оплата не завершена' in text
    rows = sent.await_args.kwargs['reply_markup'].inline_keyboard
    assert rows[0][0].callback_data.startswith('topup_amount|')  # способ на ту же сумму
    assert rows[-1][0].callback_data == 'balance_topup'  # «Другая сумма»


async def test_too_fresh_payment_is_left_alone(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add_all([_user(), _platega(1, 3)])  # 3 минуты: человек ещё сам платит
        await db.commit()
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_payments(db) == 0
    sent.assert_not_awaited()


async def test_not_repeated_within_a_day(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add_all([_user(), _platega(1, 15)])
        await db.commit()
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_payments(db) == 1
        assert await service.process_abandoned_payments(db) == 0
    assert sent.await_count == 1


async def test_skips_user_who_paid_afterwards(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add_all([_user(), _platega(1, 20)])
        db.add(
            Transaction(
                user_id=1,
                type=TransactionType.DEPOSIT.value,
                amount_kopeks=31500,
                description='Пополнение',
                is_completed=True,
                created_at=NOW - timedelta(minutes=12),
            )
        )
        await db.commit()
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_payments(db) == 0
    sent.assert_not_awaited()


async def test_paid_payment_is_not_abandoned(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add_all([_user(), _platega(1, 20, status='CONFIRMED', is_paid=True)])
        await db.commit()
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_payments(db) == 0
    sent.assert_not_awaited()


async def test_discount_is_really_locked_for_twenty_minutes(monkeypatch):
    async with _session(monkeypatch) as db:
        user = _user(promo_offer_discount_percent=37, promo_offer_discount_expires_at=NOW + timedelta(minutes=4))
        db.add_all([user, _platega(1, 15)])
        await db.commit()
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_payments(db) == 1
        left = (
            user.promo_offer_discount_expires_at - datetime.now(UTC).replace(tzinfo=None)
            if user.promo_offer_discount_expires_at.tzinfo is None
            else user.promo_offer_discount_expires_at - datetime.now(UTC)
        )

    assert timedelta(minutes=18) < left <= timedelta(minutes=20)  # продлена, а не 4 минуты
    assert 'закреплена' in sent.await_args.args[1] and '37%' in sent.await_args.args[1]


async def test_no_discount_line_without_discount(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add_all([_user(), _platega(1, 15)])
        await db.commit()
        service, sent = _service(monkeypatch)

        await service.process_abandoned_payments(db)
    assert 'закреплена' not in sent.await_args.args[1]
