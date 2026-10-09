"""Напоминание о брошенной оплате: через 10 минут, один раз, без лишних людей."""

import contextlib
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import (
    Base,
    CryptoBotPayment,
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
        for m in (
            User,
            CryptoBotPayment,
            PlategaPayment,
            WataPayment,
            XRocketPayment,
            HeleketPayment,
            Transaction,
            SubscriptionEvent,
        )
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
    assert 'Не получилось оплатить? Попробуйте другой способ.' in text
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


async def test_cryptobot_invoice_is_covered(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add_all(
            [
                _user(),
                CryptoBotPayment(
                    user_id=1,
                    invoice_id='inv1',
                    amount='37.73',
                    asset='USDT',
                    status='active',
                    payload='balance_1_315000',
                    created_at=NOW - timedelta(minutes=15),
                ),
            ]
        )
        await db.commit()
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_payments(db) == 1
    assert '3150 ₽' in sent.await_args.args[1]


# ───────────── брошенная покупка подписки (корзина) ─────────────


def _cart_service(monkeypatch, carts, extended=None):
    from app.services import user_cart_service as cart_module

    async def listing():
        return carts

    async def extend(user_id, seconds):
        if extended is not None:
            extended.append((user_id, seconds))
        return True

    monkeypatch.setattr(cart_module.user_cart_service, 'list_global_carts', listing)
    monkeypatch.setattr(cart_module.user_cart_service, 'extend_cart_ttl', extend)


def _cart(**kw):
    base = {
        'cart_mode': 'tariff_purchase',
        'tariff_id': 4,
        'total_price': 500000,
        'description': 'Покупка тарифа ULTIMA на 2222 дней',
    }
    return {**base, **kw}


async def test_abandoned_cart_gets_one_message_and_is_extended(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add(_user(balance_kopeks=100000))
        await db.commit()
        extended = []
        _cart_service(monkeypatch, [(1, _cart(), 1000)], extended)  # корзине 16 минут
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_carts(db) == 1
        assert await service.process_abandoned_carts(db) == 0  # второй раз не пишем
    text = sent.await_args.args[1]
    assert 'остановились на покупке' in text and '5000 ₽' in text and 'ULTIMA' in text
    assert extended == [(1, 20 * 60)]  # корзину реально продлили на 20 минут
    callbacks = [b.callback_data for row in sent.await_args.kwargs['reply_markup'].inline_keyboard for b in row]
    assert callbacks[-1] == 'return_to_saved_cart'
    assert callbacks[0].startswith('topup_amount|')  # недостающее можно оплатить сразу


async def test_fresh_cart_is_left_alone(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add(_user())
        await db.commit()
        _cart_service(monkeypatch, [(1, _cart(), 300)])  # 5 минут
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_carts(db) == 0
    sent.assert_not_awaited()


async def test_cart_without_missing_balance_has_only_resume_button(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add(_user(balance_kopeks=900000))  # денег хватает
        await db.commit()
        _cart_service(monkeypatch, [(1, _cart(), 1000)])
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_carts(db) == 1
    rows = sent.await_args.kwargs['reply_markup'].inline_keyboard
    assert [b.callback_data for row in rows for b in row] == ['return_to_saved_cart']


async def test_spofy_subpage_cart_is_not_nudged(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add(_user())
        await db.commit()
        _cart_service(monkeypatch, [(1, _cart(source='spofy_subpage'), 1000)])
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_carts(db) == 0
    sent.assert_not_awaited()


# ───────────── приглашение друга после оплаты ─────────────


async def test_referral_prompt_after_purchase_once(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add(_user())
        db.add(
            Transaction(
                user_id=1,
                type=TransactionType.SUBSCRIPTION_PAYMENT.value,
                amount_kopeks=-31500,
                description='Покупка',
                is_completed=True,
                created_at=NOW - timedelta(minutes=5),
            )
        )
        await db.commit()
        service, sent = _service(monkeypatch)

        assert await service.process_referral_prompt(db) == 1
        assert await service.process_referral_prompt(db) == 0  # раз в 30 дней
    text = sent.await_args.args[1]
    assert '+2 дн.' in text and 'Без ограничений' in text


async def test_referral_prompt_waits_three_minutes(monkeypatch):
    async with _session(monkeypatch) as db:
        db.add(_user())
        db.add(
            Transaction(
                user_id=1,
                type=TransactionType.SUBSCRIPTION_PAYMENT.value,
                amount_kopeks=-31500,
                description='Покупка',
                is_completed=True,
                created_at=NOW - timedelta(minutes=1),
            )
        )
        await db.commit()
        service, sent = _service(monkeypatch)

        assert await service.process_referral_prompt(db) == 0
    sent.assert_not_awaited()


async def test_reminder_is_not_sent_long_after_the_payment(monkeypatch):
    # Напоминание — про платёж, оставшийся неоплаченным 10 минут; через 45 минут уже поздно.
    async with _session(monkeypatch) as db:
        db.add_all([_user(), _platega(1, 45)])
        await db.commit()
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_payments(db) == 0
    sent.assert_not_awaited()


# ───────────── письма для аккаунтов без Telegram ─────────────


def _email_user(uid=5):
    return User(
        id=uid,
        telegram_id=None,
        username=f'e{uid}',
        email=f'user{uid}@example.com',
        email_verified=True,
        status='active',
        language='ru',
    )


async def test_email_only_user_gets_a_payment_email_not_a_telegram_message(monkeypatch):
    sent_emails = []

    async def fake_email(**kwargs):
        sent_emails.append(kwargs)
        return True

    monkeypatch.setattr('app.services.payment_reminder_email.send_payment_reminder_email', fake_email)
    async with _session(monkeypatch) as db:
        db.add_all([_email_user(), _platega(5, 15)])
        await db.commit()
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_payments(db) == 1
        assert await service.process_abandoned_payments(db) == 0  # один раз в сутки и по почте
    sent.assert_not_awaited()  # Telegram у человека нет
    assert sent_emails[0]['kind'] == 'payment' and sent_emails[0]['amount_kopeks'] == 31500
    assert sent_emails[0]['email'] == 'user5@example.com'


async def test_email_only_user_with_unverified_email_gets_nothing(monkeypatch):
    sent_emails = []

    async def fake_email(**kwargs):
        sent_emails.append(kwargs)
        return True

    monkeypatch.setattr('app.services.payment_reminder_email.send_payment_reminder_email', fake_email)
    async with _session(monkeypatch) as db:
        user = _email_user()
        user.email_verified = False
        db.add_all([user, _platega(5, 15)])
        await db.commit()
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_payments(db) == 0
    assert sent_emails == []


async def test_email_only_user_gets_a_cart_email(monkeypatch):
    sent_emails = []

    async def fake_email(**kwargs):
        sent_emails.append(kwargs)
        return True

    monkeypatch.setattr('app.services.payment_reminder_email.send_payment_reminder_email', fake_email)
    async with _session(monkeypatch) as db:
        db.add(_email_user())
        await db.commit()
        extended = []
        _cart_service(monkeypatch, [(5, _cart(), 1000)], extended)
        service, sent = _service(monkeypatch)

        assert await service.process_abandoned_carts(db) == 1
    sent.assert_not_awaited()
    assert sent_emails[0]['kind'] == 'cart' and sent_emails[0]['amount_kopeks'] == 500000
    assert extended == [(5, 20 * 60)]  # корзину продлили и для почтового напоминания


def test_reminder_email_text_has_the_phrase():
    from app.services.payment_reminder_email import render_reminder

    subject, body, button, _ = render_reminder('payment', 'ru', amount_kopeks=31500)
    assert subject == 'Оплата не завершена'
    assert '315 ₽' in body and 'Не получилось оплатить? Попробуйте другой способ.' in body
    assert button == 'Продолжить оплату'
