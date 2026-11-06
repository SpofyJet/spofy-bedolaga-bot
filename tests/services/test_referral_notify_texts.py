"""Уведомления пригласившему: сумма первой, что с ней делать и кнопки по одной в строке.

Раньше сообщения были без кнопок: человек видел начисление, но ни посмотреть
друзей, ни позвать следующего одним нажатием не мог. База настоящая.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.database.models import Base, ReferralEarning, Subscription, User
from app.handlers import referral as referral_handlers
from app.localization.texts import get_texts
from app.services import referral_service as service
from tests.fixtures.sqlite_memory import memory_session


REFERRER_ID = 10
FRIEND_ID = 11


def _user(user_id: int, *, balance: int = 0, referred_by: int | None = None) -> User:
    return User(
        id=user_id,
        telegram_id=500_000 + user_id,
        first_name='Иван' if user_id == FRIEND_ID else 'Партнёр',
        status='active',
        language='ru',
        balance_kopeks=balance,
        referred_by_id=referred_by,
        created_at=datetime.now(UTC),
    )


def _subscription(*, tariff_id: int | None, is_trial: bool = False, end: datetime | None = None) -> Subscription:
    now = datetime.now(UTC)
    return Subscription(
        id=1,
        user_id=REFERRER_ID,
        tariff_id=tariff_id,
        status='active',
        is_trial=is_trial,
        start_date=now - timedelta(days=1),
        end_date=end or now + timedelta(days=20),
        traffic_limit_gb=100,
        traffic_used_gb=0.0,
        device_limit=3,
    )


async def _seed(db, *rows) -> None:
    db.add_all(rows)
    await db.commit()


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(settings, 'REFERRAL_INVITER_BONUS_KOPEKS', 0)
    monkeypatch.setattr(settings, 'REFERRAL_WITHDRAWAL_ENABLED', True)
    monkeypatch.setattr(settings, 'REFERRAL_WITHDRAWAL_MIN_AMOUNT_KOPEKS', 250_000)
    monkeypatch.setattr(settings, 'TRIAL_DURATION_DAYS', 2)


@pytest.mark.asyncio
async def test_commission_leads_with_amount_and_says_what_it_buys(monkeypatch):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        referrer = _user(REFERRER_ID, balance=14_000)
        friend = _user(FRIEND_ID, referred_by=REFERRER_ID)
        await _seed(
            db,
            referrer,
            friend,
            ReferralEarning(user_id=REFERRER_ID, referral_id=FRIEND_ID, amount_kopeks=124_000, reason='x'),
        )

        text = await service._commission_text(
            db, referrer, friend, amount_kopeks=5_900, topup_kopeks=19_900, percent=30
        )

    assert text.index('+59') < text.index('Иван')
    assert 'ваши 30% уже начислены' in text
    assert 'Всего заработано: 1' in text and '240' in text
    assert 'Этим можно оплатить подписку или вывести от 2' in text and '500 ₽.' in text


def test_spend_line_without_withdrawal(monkeypatch):
    monkeypatch.setattr(settings, 'REFERRAL_WITHDRAWAL_ENABLED', False)

    assert service._spend_line(get_texts('ru')) == 'Этим можно оплатить подписку.'


@pytest.mark.asyncio
async def test_first_topup_promises_next_percent(monkeypatch):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        referrer = _user(REFERRER_ID, balance=5_000)
        friend = _user(FRIEND_ID, referred_by=REFERRER_ID)
        await _seed(db, referrer, friend)

        text = await service._first_topup_text(
            db, referrer, friend, amount_kopeks=5_000, topup_kopeks=16_700, percent=30
        )

    assert 'первое пополнение' in text
    assert 'Теперь 30% с каждого его пополнения — ваши.' in text


@pytest.mark.asyncio
async def test_new_friend_quest_line_only_for_inviter_who_gets_the_days(monkeypatch):
    async with memory_session(monkeypatch, list(Base.metadata.sorted_tables)) as db:
        referrer = _user(REFERRER_ID)
        friend = _user(FRIEND_ID, referred_by=REFERRER_ID)
        await _seed(db, referrer, friend)
        without_subscription = await service._new_friend_text(db, referrer, friend, percent=30)

        await _seed(db, _subscription(tariff_id=None))
        with_subscription = await service._new_friend_text(db, referrer, friend, percent=30)

    assert 'пробный период' not in without_subscription
    assert 'вы оба получите по +2 дн.' in with_subscription
    assert 'С каждого пополнения друга вам 30% на баланс.' in with_subscription
    assert 'Всего друзей: 1.' in with_subscription


@pytest.mark.asyncio
async def test_money_message_survives_a_failed_summary():
    db = SimpleNamespace(scalar=AsyncMock(side_effect=RuntimeError('db')))
    referrer = SimpleNamespace(id=1, language='ru', balance_kopeks=0)
    friend = SimpleNamespace(full_name='Иван')

    text = await service._commission_text(db, referrer, friend, amount_kopeks=100, topup_kopeks=300, percent=30)

    assert 'Иван' in text
    assert 'Всего заработано' not in text


def test_buttons_are_one_per_row_with_invite_first():
    rows = service._inviter_keyboard('ru').inline_keyboard

    assert [len(row) for row in rows] == [1, 1]
    assert rows[0][0].callback_data == service.REFERRAL_NOTIFY_INVITE_CALLBACK
    assert rows[1][0].callback_data == service.REFERRAL_NOTIFY_FRIENDS_CALLBACK


def test_notification_buttons_reach_the_real_screens():
    dispatcher = MagicMock()

    referral_handlers.register_handlers(dispatcher)

    routes = {call.args[0]: call.args[1] for call in dispatcher.callback_query.register.call_args_list}
    invite = routes[referral_handlers.create_invite_message]
    friends = routes[referral_handlers.show_detailed_referral_list]
    assert invite.resolve(SimpleNamespace(data=service.REFERRAL_NOTIFY_INVITE_CALLBACK))
    assert invite.resolve(SimpleNamespace(data='referral_create_invite'))
    assert friends.resolve(SimpleNamespace(data=service.REFERRAL_NOTIFY_FRIENDS_CALLBACK))
    assert friends.resolve(SimpleNamespace(data='referral_list'))


@pytest.mark.asyncio
async def test_telegram_gets_the_keyboard(monkeypatch):
    monkeypatch.setattr(type(settings), 'is_notifications_enabled', lambda self: True)
    monkeypatch.setattr(type(settings), 'is_referral_notifications_enabled', lambda self: True)
    bot = MagicMock(send_message=AsyncMock())
    keyboard = service._inviter_keyboard('ru')

    await service.send_referral_notification(bot, 123, 'текст', reply_markup=keyboard)

    assert bot.send_message.await_args.kwargs['reply_markup'] is keyboard
