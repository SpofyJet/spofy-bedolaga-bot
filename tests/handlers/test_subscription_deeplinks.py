"""Диплинк ``/start renew`` и ``renew_<источник>``: кнопка под постом в канале одна на всех.

Раньше ``renew_ch1212`` бот не знал и принимал за реферальный код («Вы уже зарегистрированы
в системе. Реферальная ссылка не может быть применена»), а ``renew`` без подписки открывал
обычное меню. Теперь каждый получает экран по своей подписке, а источник пишется в событие.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select

from app.config import settings
from app.database.models import Subscription, SubscriptionEvent, SubscriptionStatus, Tariff, User, UserStatus
from app.handlers import subscription_deeplinks as deeplinks
from app.localization.texts import get_texts
from app.utils.lifetime import LIFETIME_END
from tests.fixtures.sqlite_memory import memory_session
from tests.handlers.test_gift_deeplink_activation import _TABLES, _make_message


NOW = datetime.now(UTC)
TABLES = [*_TABLES, SubscriptionEvent.__table__]


@pytest.fixture(autouse=True)
def _bot_menu_mode(monkeypatch):
    monkeypatch.setattr(settings, 'MAIN_MENU_MODE', 'default')
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', False)


def _user(**kw):
    return SimpleNamespace(**{'id': 10, 'telegram_id': 555, 'language': 'ru', 'status': 'active', **kw})


def _sub(**kw):
    base = dict(id=101, user_id=10, is_trial=False, tariff_id=2, end_date=NOW + timedelta(days=5))
    return SimpleNamespace(**{**base, **kw})


def _db():
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _message():
    message = MagicMock()
    message.answer = AsyncMock()
    return message


async def _open(monkeypatch, subscription, *, action='renew', source='', db=None):
    monkeypatch.setattr(deeplinks, 'get_subscription_by_user_id', AsyncMock(return_value=subscription))
    message, db = _message(), db or _db()
    handled = await deeplinks.open_subscription_deeplink(message, _user(), db, action, source=source)
    return handled, message, db


def _callbacks(message) -> list[str]:
    markup = message.answer.await_args.kwargs['reply_markup']
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _event(db) -> SubscriptionEvent:
    (event,) = [call.args[0] for call in db.add.call_args_list]
    return event


# ── разбор параметра ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ('parameter', 'action'),
    [
        ('renew', 'renew'),
        ('renew_ch1212', 'renew'),
        ('renew_', 'renew'),
        ('traffic', 'traffic'),
        ('traffic_ch1', None),
        ('renewal', None),
        ('RENEW', None),
        ('ref7Kx2pQ', None),
        ('1311', None),
        ('', None),
        (None, None),
    ],
)
def test_action_is_recognised_only_for_renew_and_traffic(parameter, action):
    assert deeplinks.subscription_deeplink_action(parameter) == action


@pytest.mark.parametrize(
    ('parameter', 'source'),
    [
        ('renew_ch1212', 'ch1212'),
        ('renew', ''),
        ('renew_', ''),
        ('traffic', ''),
        (None, ''),
        ('renew_post-12_a', 'post-12_a'),
        ('renew_<b>x</b>', 'bxb'),
        ('renew_' + 'a' * 60, 'a' * 32),
    ],
)
def test_source_is_the_tail_after_the_first_underscore(parameter, source):
    assert deeplinks.subscription_deeplink_source(parameter) == source


# ── ответ по подписке ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_paid_subscription_gets_the_renewal_button_and_the_source_is_recorded(monkeypatch):
    handled, message, db = await _open(monkeypatch, _sub(), source='ch1212')

    assert handled is True
    assert message.answer.await_args.args[0] == get_texts('ru').get('DEEPLINK_RENEW_TEXT')
    assert _callbacks(message) == ['subscription_extend']
    event = _event(db)
    assert (event.event_type, event.message, event.user_id, event.subscription_id) == (
        'renew_link_open',
        'renew:ch1212',
        10,
        101,
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_paid_subscription_still_goes_to_renewal(monkeypatch):
    _, message, db = await _open(monkeypatch, _sub(end_date=NOW - timedelta(days=90)))

    assert _callbacks(message) == ['subscription_extend']
    assert _event(db).message == 'renew:'


@pytest.mark.asyncio
@pytest.mark.parametrize('subscription', [None, _sub(is_trial=True, tariff_id=None)])
async def test_no_subscription_or_plain_trial_goes_straight_to_tariff_choice(monkeypatch, subscription):
    handled, message, db = await _open(monkeypatch, subscription, source='ch1212')

    assert handled is True
    assert message.answer.await_args.args[0] == get_texts('ru').get('DEEPLINK_BUY_TEXT')
    assert _callbacks(message) == ['menu_buy']
    button = message.answer.await_args.kwargs['reply_markup'].inline_keyboard[0][0]
    assert button.style == 'success'
    assert _event(db).message == 'buy:ch1212'


@pytest.mark.asyncio
async def test_trial_with_a_tariff_keeps_the_renewal_screen(monkeypatch):
    _, message, db = await _open(monkeypatch, _sub(is_trial=True, tariff_id=3))

    assert _callbacks(message) == ['subscription_extend']
    assert _event(db).message == 'trial:'


@pytest.mark.asyncio
async def test_lifetime_subscription_is_told_there_is_nothing_to_renew(monkeypatch):
    handled, message, db = await _open(monkeypatch, _sub(tariff_id=4, end_date=LIFETIME_END), source='ch1212')

    assert handled is True
    assert message.answer.await_args.args[0] == get_texts('ru').get('SUBSCRIPTION_LIFETIME_NO_RENEW')
    assert message.answer.await_args.kwargs['reply_markup'] is None
    assert _event(db).message == 'lifetime:ch1212'


@pytest.mark.asyncio
async def test_english_user_gets_english_tariff_choice(monkeypatch):
    monkeypatch.setattr(deeplinks, 'get_subscription_by_user_id', AsyncMock(return_value=None))
    message = _message()

    await deeplinks.open_subscription_deeplink(message, _user(language='en'), _db(), 'renew')

    assert message.answer.await_args.args[0] == get_texts('en').get('DEEPLINK_BUY_TEXT')
    assert 'Choose a plan' in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_failed_event_write_does_not_break_the_answer(monkeypatch):
    db = _db()
    db.commit = AsyncMock(side_effect=RuntimeError('db is down'))

    handled, message, db = await _open(monkeypatch, _sub(), source='ch1212', db=db)

    assert handled is True
    message.answer.assert_awaited_once()
    db.rollback.assert_awaited_once()


# ── traffic без изменений ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_traffic_keeps_its_button_and_writes_no_event(monkeypatch):
    handled, message, db = await _open(monkeypatch, _sub(), action='traffic')

    assert handled is True
    assert _callbacks(message) == ['buy_traffic']
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_traffic_without_subscription_falls_through_to_plain_start(monkeypatch):
    handled, message, db = await _open(monkeypatch, None, action='traffic')

    assert handled is False
    message.answer.assert_not_awaited()
    db.add.assert_not_called()


# ── через /start с настоящей базой ──────────────────────────────────────────


def _state(user_id: int) -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=user_id, user_id=user_id))


async def _add_user(db, **kw) -> User:
    user = User(telegram_id=22222, username='rec', balance_kopeks=0, language='ru', **kw)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _events(db) -> list[tuple[str, str]]:
    rows = await db.execute(select(SubscriptionEvent.event_type, SubscriptionEvent.message))
    return [tuple(row) for row in rows.all()]


@pytest.mark.asyncio
async def test_start_with_channel_link_opens_tariff_choice_instead_of_referral_refusal(monkeypatch):
    from app.handlers import start

    async with memory_session(monkeypatch, TABLES) as db:
        user = await _add_user(db)
        message = _make_message('/start renew_ch1212', user.telegram_id, 'rec')

        await start.cmd_start(message, _state(user.telegram_id), db, db_user=user)

        message.answer.assert_awaited_once()
        assert message.answer.await_args.args[0] == get_texts('ru').get('DEEPLINK_BUY_TEXT')
        assert _callbacks(message) == ['menu_buy']
        assert await _events(db) == [('renew_link_open', 'buy:ch1212')]


@pytest.mark.asyncio
async def test_start_with_channel_link_opens_renewal_for_a_paid_subscription(monkeypatch):
    from app.handlers import start

    async with memory_session(monkeypatch, TABLES) as db:
        user = await _add_user(db)
        tariff = Tariff(
            name='Стандартный', is_active=True, device_limit=3, traffic_limit_gb=0, period_prices={'30': 15900}
        )
        db.add(tariff)
        await db.flush()
        db.add(
            Subscription(
                user_id=user.id,
                tariff_id=tariff.id,
                status=SubscriptionStatus.ACTIVE.value,
                is_trial=False,
                start_date=NOW - timedelta(days=20),
                end_date=NOW + timedelta(days=10),
                traffic_limit_gb=0,
                device_limit=3,
            )
        )
        await db.commit()
        message = _make_message('/start renew_ch1212', user.telegram_id, 'rec')

        await start.cmd_start(message, _state(user.telegram_id), db, db_user=user)

        message.answer.assert_awaited_once()
        assert message.answer.await_args.args[0] == get_texts('ru').get('DEEPLINK_RENEW_TEXT')
        assert _callbacks(message) == ['subscription_extend']
        assert await _events(db) == [('renew_link_open', 'renew:ch1212')]


class _StopAfterDeeplink(Exception):
    """Дальше идёт обычный /start — его здесь не проверяем."""


@pytest.mark.asyncio
async def test_start_with_channel_link_for_deleted_account_is_a_plain_start(monkeypatch):
    """Удалённому — обычный /start; метка не должна уйти дальше как реферальный код."""
    from app.handlers import start

    seen: list[str | None] = []

    def next_step(start_parameter):
        seen.append(start_parameter)
        raise _StopAfterDeeplink

    async with memory_session(monkeypatch, TABLES) as db:
        user = await _add_user(db, status=UserStatus.DELETED.value)
        opened = AsyncMock(return_value=True)
        monkeypatch.setattr(start, 'open_subscription_deeplink', opened)
        monkeypatch.setattr(start, 'is_ultima_deeplink', next_step)
        message = _make_message('/start renew_ch1212', user.telegram_id, 'rec')

        with pytest.raises(_StopAfterDeeplink):
            await start.cmd_start(message, _state(user.telegram_id), db, db_user=None)

        opened.assert_not_awaited()
        assert seen == [None]
        assert await _events(db) == []
