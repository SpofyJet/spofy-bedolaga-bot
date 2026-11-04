"""Оплата Stars прошла, а применить её нельзя — деньги уходят на баланс, а не теряются.

Звёзды Telegram сам не возвращает и successful_payment не повторяет, поэтому
раньше «Звезды будут возвращены» / «Telegram повторит» означало потерю денег.
Зачисление — DEPOSIT с external_id = telegram_payment_charge_id, повтор того же
платежа второй раз не зачисляет.
"""

from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.config import settings
from app.database.models import Base, Transaction, TransactionType, User
from tests.fixtures.sqlite_memory import memory_session


TABLES = list(Base.metadata.sorted_tables)
CHARGE = 'stars-charge-1'


def _settings_patches(stack: ExitStack, *, rate: float = 1.5, notifications: bool = True) -> AsyncMock:
    stack.enter_context(patch.object(type(settings), 'get_stars_rate', lambda self: rate))
    stack.enter_context(patch.object(type(settings), 'is_notifications_enabled', lambda self: notifications))
    alert = AsyncMock()
    stack.enter_context(patch('app.services.payment_problem_alert.alert_payment_not_applied', alert))
    return alert


async def _user(db) -> User:
    db.add(User(id=1, telegram_id=1001, first_name='U', language='ru', balance_kopeks=0))
    await db.commit()
    from app.database.crud.user import get_user_by_id

    return await get_user_by_id(db, 1)


async def _transactions(db) -> list[Transaction]:
    db.expire_all()
    return list((await db.scalars(select(Transaction))).all())


def _message():
    return SimpleNamespace(answer=AsyncMock(), bot=None)


def _callbacks(markup) -> set[str]:
    return {button.callback_data for row in markup.inline_keyboard for button in row}


@pytest.mark.asyncio
async def test_credit_is_deposit_keyed_by_charge_id_and_idempotent(monkeypatch):
    from app.services.payment.stars import credit_unapplied_stars_payment

    with ExitStack() as stack:
        alert = _settings_patches(stack)
        async with memory_session(monkeypatch, TABLES) as db:
            user = await _user(db)
            first = await credit_unapplied_stars_payment(
                db, user=user, stars_amount=100, telegram_payment_charge_id=CHARGE, problem='тест'
            )
            second = await credit_unapplied_stars_payment(
                db, user=user, stars_amount=100, telegram_payment_charge_id=CHARGE, problem='тест'
            )
            rows = await _transactions(db)
            balance = (await db.get(User, 1)).balance_kopeks

    assert first == second == 15000  # 100 ⭐ × 1.5 ₽ — как обычное пополнение Stars
    assert balance == 15000, 'повтор того же платежа второй раз не зачисляет'
    assert len(rows) == 1
    assert rows[0].type == TransactionType.DEPOSIT.value
    assert rows[0].payment_method == 'telegram_stars'
    assert rows[0].external_id == CHARGE
    alert.assert_awaited_once()
    assert alert.await_args.kwargs['reference'] == CHARGE
    assert alert.await_args.kwargs['amount_kopeks'] == 15000


@pytest.mark.asyncio
async def test_credit_failure_alerts_admins_and_returns_none(monkeypatch):
    from app.services.payment.stars import credit_unapplied_stars_payment

    with ExitStack() as stack:
        alert = _settings_patches(stack)
        stack.enter_context(patch('app.database.crud.user.add_user_balance', AsyncMock(return_value=False)))
        async with memory_session(monkeypatch, TABLES) as db:
            user = await _user(db)
            result = await credit_unapplied_stars_payment(
                db, user=user, stars_amount=100, telegram_payment_charge_id=CHARGE, problem='тест'
            )

    assert result is None
    alert.assert_awaited_once()
    assert 'не удалось' in alert.await_args.kwargs['problem']


@pytest.mark.asyncio
async def test_wheel_disabled_credits_balance_and_says_so_honestly(monkeypatch):
    from app.handlers.stars_payments import _handle_wheel_spin_payment

    message = _message()
    with ExitStack() as stack:
        alert = _settings_patches(stack)
        config_loader = AsyncMock(return_value=SimpleNamespace(is_enabled=False))
        stack.enter_context(patch('app.database.crud.wheel.get_or_create_wheel_config', config_loader))
        async with memory_session(monkeypatch, TABLES) as db:
            user = await _user(db)
            kwargs = dict(message=message, db=db, user=user, stars_amount=100, payload='wheel_spin_1', texts=None)
            await _handle_wheel_spin_payment(**kwargs, charge_id=CHARGE)
            # Повторная доставка того же successful_payment.
            assert await _handle_wheel_spin_payment(**kwargs, charge_id=CHARGE) is True
            rows = await _transactions(db)
            balance = (await db.get(User, 1)).balance_kopeks

    assert balance == 15000
    assert [(r.type, r.external_id) for r in rows] == [(TransactionType.DEPOSIT.value, CHARGE)]
    assert config_loader.await_count == 1, 'повтор отсечён до проверки колеса'
    alert.assert_awaited_once()
    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert 'Колесо удачи сейчас недоступно' in text
    assert 'зачислена на баланс' in text
    assert '150' in text
    assert 'будут возвращены' not in text
    assert _callbacks(message.answer.await_args.kwargs['reply_markup']) == {'menu_balance', 'menu_support'}


@pytest.mark.asyncio
async def test_wheel_daily_limit_credit_is_deposit_not_refund(monkeypatch):
    from app.handlers.stars_payments import _handle_wheel_spin_payment

    message = _message()
    with ExitStack() as stack:
        _settings_patches(stack)
        stack.enter_context(patch.object(type(settings), 'is_multi_tariff_enabled', lambda self: False))
        stack.enter_context(
            patch(
                'app.database.crud.wheel.get_or_create_wheel_config',
                AsyncMock(return_value=SimpleNamespace(is_enabled=True, id=1, daily_spin_limit=1)),
            )
        )
        stack.enter_context(
            patch('app.database.crud.wheel.get_wheel_prizes', AsyncMock(return_value=[SimpleNamespace()]))
        )
        stack.enter_context(patch('app.database.crud.wheel.get_user_spins_today', AsyncMock(return_value=1)))
        stack.enter_context(
            patch(
                'app.database.crud.subscription.get_subscription_by_user_id',
                AsyncMock(return_value=SimpleNamespace(is_active=True)),
            )
        )
        async with memory_session(monkeypatch, TABLES) as db:
            user = await _user(db)
            await _handle_wheel_spin_payment(
                message=message,
                db=db,
                user=user,
                stars_amount=100,
                payload='wheel_spin_1',
                texts=None,
                charge_id=CHARGE,
            )
            rows = await _transactions(db)

    assert [(r.type, r.external_id) for r in rows] == [(TransactionType.DEPOSIT.value, CHARGE)]
    assert 'лимит спинов' in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_simple_subscription_not_activated_goes_to_balance(monkeypatch):
    """Раньше: откат «Telegram повторит» — он не повторяет, звёзды терялись."""
    from app.services.payment_service import PaymentService

    with ExitStack() as stack:
        alert = _settings_patches(stack)
        async with memory_session(monkeypatch, TABLES) as db:
            await _user(db)
            service = PaymentService(None)
            # Подписки #77 нет — выдать нечего.
            result = await service.process_stars_payment(
                db=db, user_id=1, stars_amount=100, payload='simple_sub_1_77_30', telegram_payment_charge_id=CHARGE
            )
            rows = await _transactions(db)
            balance = (await db.get(User, 1)).balance_kopeks

    assert result is True
    assert balance == 15000
    assert [(r.type, r.external_id) for r in rows] == [(TransactionType.DEPOSIT.value, CHARGE)]
    alert.assert_awaited_once()


def _successful_payment_message(payload: str):
    return SimpleNamespace(
        successful_payment=SimpleNamespace(
            total_amount=100, invoice_payload=payload, telegram_payment_charge_id=CHARGE
        ),
        from_user=SimpleNamespace(id=1001),
        chat=SimpleNamespace(id=1001),
        bot=SimpleNamespace(),
        answer=AsyncMock(),
    )


async def _run_handler(message, transaction, *, notifications: bool = True):
    from app.handlers import stars_payments

    user = SimpleNamespace(id=1, telegram_id=1001, language='ru')
    payment_service = SimpleNamespace(process_stars_payment=AsyncMock(return_value=True))
    state = SimpleNamespace(get_data=AsyncMock(return_value={}), update_data=AsyncMock())
    with ExitStack() as stack:
        _settings_patches(stack, notifications=notifications)
        stack.enter_context(patch.object(stars_payments, 'get_user_by_telegram_id', AsyncMock(return_value=user)))
        stack.enter_context(patch.object(stars_payments, 'PaymentService', lambda bot: payment_service))
        stack.enter_context(
            patch(
                'app.database.crud.transaction.get_transaction_by_external_id',
                AsyncMock(return_value=transaction),
            )
        )
        await stars_payments.handle_successful_payment(message, AsyncMock(), state)


@pytest.mark.asyncio
async def test_handler_tells_user_subscription_payment_went_to_balance():
    message = _successful_payment_message('simple_sub_1_77_30')
    await _run_handler(message, SimpleNamespace(type=TransactionType.DEPOSIT.value, amount_kopeks=15000))

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert 'Не удалось активировать подписку' in text
    assert 'зачислена на баланс' in text
    assert _callbacks(message.answer.await_args.kwargs['reply_markup']) == {'menu_balance', 'menu_support'}


@pytest.mark.asyncio
async def test_handler_does_not_claim_balance_topup_for_activated_subscription():
    message = _successful_payment_message('simple_sub_1_77_30')
    await _run_handler(message, SimpleNamespace(type=TransactionType.SUBSCRIPTION_PAYMENT.value, amount_kopeks=-15000))

    # «Подписка активирована» шлёт сервис; «Баланс пополнен» здесь было бы неправдой.
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_paid_trial_without_pending_subscription_goes_to_balance(monkeypatch):
    from app.handlers.stars_payments import _handle_trial_payment

    message = _message()
    with ExitStack() as stack:
        alert = _settings_patches(stack)
        async with memory_session(monkeypatch, TABLES) as db:
            user = await _user(db)
            kwargs = dict(message=message, db=db, user=user, stars_amount=100, payload='trial_77', texts=None)
            assert await _handle_trial_payment(**kwargs, charge_id=CHARGE) is False
            assert await _handle_trial_payment(**kwargs, charge_id=CHARGE) is True  # повтор
            rows = await _transactions(db)
            balance = (await db.get(User, 1)).balance_kopeks

    assert balance == 15000
    # Ни «оплаты пробной подписки» без подписки, ни второго зачисления.
    assert [(r.type, r.external_id) for r in rows] == [(TransactionType.DEPOSIT.value, CHARGE)]
    alert.assert_awaited_once()
    message.answer.assert_awaited_once()
    assert 'зачислена на баланс' in message.answer.await_args.args[0]
