from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError
from sqlalchemy import select

from app.database.crud.discount_offer import deactivate_expired_offers
from app.database.models import Base, DiscountOffer, PromoOfferLog, Subscription, Transaction, User
from app.services import gift_days_offer as gd
from app.services.admin_notification_service import AdminNotificationService
from app.services.subscription_service import SubscriptionService
from tests.fixtures.postgres_db import postgres_session


pytestmark = pytest.mark.postgres


class Bot:
    def __init__(self, error=None):
        self.sent = []
        self.error = error

    async def send_message(self, chat_id, text, reply_markup=None):
        if self.error:
            raise self.error
        self.sent.append((chat_id, text))


def _sessions(db):
    @asynccontextmanager
    async def same():
        yield db

    return same


@pytest.fixture
def panel(monkeypatch):
    state = {'ok': True, 'calls': 0}

    async def update(self, db, subscription, **kwargs):
        state['calls'] += 1
        return object() if state['ok'] else None

    monkeypatch.setattr(SubscriptionService, 'update_remnawave_user', update)
    return state


async def _setup(db, now, *, trial=False, telegram_id=101, end_days=90, status='active'):
    db.add(User(id=1, telegram_id=telegram_id, language='ru'))
    db.add(
        Subscription(
            id=10,
            user_id=1,
            status=status,
            is_trial=trial,
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=end_days),
            device_limit=3,
        )
    )
    await db.commit()
    assert await gd.grant(db, [1, 1], expires_at=now + timedelta(days=7)) == 1
    offer = (await db.execute(select(DiscountOffer))).scalar_one()
    offer.created_at = now - timedelta(hours=2)
    await db.commit()
    return offer


def _pay(db, now, description, *, ago=timedelta(minutes=5), amount=-40900):
    db.add(
        Transaction(
            user_id=1,
            type='subscription_payment',
            amount_kopeks=amount,
            description=description,
            is_completed=True,
            created_at=now - ago,
        )
    )


async def _end(db):
    db.expire_all()
    return (await db.get(Subscription, 10)).end_date


async def test_three_months_purchase_gets_three_months_once(postgres_database, panel):
    now = datetime.now(UTC)
    service = gd.GiftDaysService()
    bot = Bot()
    service.set_bot(bot)
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        offer = await _setup(db, now)
        assert (await gd.active_gift(db, 1)).bonus_days == 90
        before = await _end(db)
        _pay(db, now, 'Покупка тарифа ⭐️ Стандартный на 30 дней', ago=timedelta(minutes=50), amount=-17900)
        _pay(db, now, 'Покупка тарифа ⭐️ Стандартный на 90 дней')
        await db.commit()

        stats = await service.run_once(now, _sessions(db))
        assert stats['granted'] == 1 and stats['panel'] == 1 and stats['notified'] == 1
        assert await _end(db) - before == timedelta(days=90)
        await db.refresh(offer)
        assert offer.claimed_at is not None and not offer.is_active
        assert (
            offer.extra_data['period_days'] == 90 and offer.extra_data['panel_synced'] and offer.extra_data['notified']
        )
        assert (await db.execute(select(PromoOfferLog))).scalar_one().action == 'claimed'
        assert bot.sent[0][0] == 101 and '+3 месяца' in bot.sent[0][1]
        assert await gd.active_gift(db, 1) is None

        _pay(db, now, 'Продление тарифа ⭐️ Стандартный на 365 дней', ago=timedelta(minutes=1))
        await db.commit()
        assert not any((await service.run_once(now, _sessions(db))).values())
        assert await _end(db) - before == timedelta(days=90)
        assert len(bot.sent) == 1


@pytest.mark.parametrize(
    ('description', 'ago', 'amount'),
    [
        ('Покупка тарифа ⭐️ Стандартный на 60 дней', timedelta(minutes=5), -31900),
        ('Покупка тарифа 👑 ULTIMA навсегда', timedelta(minutes=5), -579000),
        ('Покупка тарифа 👑 ULTIMA на 36500 дней', timedelta(minutes=5), -579000),
        ('Покупка тарифа ⭐️ Стандартный на 90 дней', timedelta(hours=3), -40900),
        ('Покупка тарифа ⭐️ Стандартный на 90 дней', timedelta(seconds=10), -40900),
        ('Смена тарифа администратором на 90 дней', timedelta(minutes=5), 0),
        ('Покупка 1 доп. устройств', timedelta(minutes=5), -5900),
    ],
)
async def test_no_gift_for_short_lifetime_early_unsettled_or_free(postgres_database, panel, description, ago, amount):
    now = datetime.now(UTC)
    service = gd.GiftDaysService()
    service.set_bot(Bot())
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        offer = await _setup(db, now)
        before = await _end(db)
        _pay(db, now, description, ago=ago, amount=amount)
        await db.commit()
        assert not any((await service.run_once(now, _sessions(db))).values())
        assert await _end(db) == before
        await db.refresh(offer)
        assert offer.claimed_at is None


async def test_purchase_after_offer_expired_gets_nothing(postgres_database, panel):
    now = datetime.now(UTC)
    service = gd.GiftDaysService()
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        offer = await _setup(db, now)
        offer.expires_at = now - timedelta(hours=1)
        await db.commit()
        _pay(db, now, 'Покупка тарифа ⭐️ Стандартный на 90 дней', ago=timedelta(minutes=5))
        await db.commit()
        assert not any((await service.run_once(now, _sessions(db))).values())


async def test_purchase_just_before_expiry_counts_after_cleanup(postgres_database, panel):
    now = datetime.now(UTC)
    service = gd.GiftDaysService()
    service.set_bot(Bot())
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        offer = await _setup(db, now)
        offer.expires_at = now - timedelta(minutes=1)
        await db.commit()
        _pay(db, now, 'Покупка тарифа ⭐️ Стандартный на 90 дней', ago=timedelta(minutes=5))
        await db.commit()
        assert await deactivate_expired_offers(db) == 1
        assert (await service.run_once(now, _sessions(db)))['granted'] == 1


async def test_admin_deactivated_offer_is_not_granted(postgres_database, panel):
    now = datetime.now(UTC)
    service = gd.GiftDaysService()
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        offer = await _setup(db, now)
        offer.is_active = False
        await db.commit()
        _pay(db, now, 'Покупка тарифа ⭐️ Стандартный на 90 дней')
        await db.commit()
        assert not any((await service.run_once(now, _sessions(db))).values())


async def test_waits_while_subscription_is_still_trial(postgres_database, panel):
    now = datetime.now(UTC)
    service = gd.GiftDaysService()
    service.set_bot(Bot())
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        offer = await _setup(db, now, trial=True, end_days=-1, status='expired')
        _pay(db, now, 'Покупка тарифа ⭐️ Стандартный на 90 дней')
        await db.commit()
        assert (await service.run_once(now, _sessions(db)))['waiting'] == 1
        await db.refresh(offer)
        assert offer.claimed_at is None
        sub = await db.get(Subscription, 10)
        sub.is_trial, sub.status, sub.end_date = False, 'active', now + timedelta(days=90)
        await db.commit()
        assert (await service.run_once(now, _sessions(db)))['granted'] == 1
        assert await _end(db) == now + timedelta(days=180)


async def test_panel_failure_is_retried_and_message_waits_for_panel(postgres_database, panel):
    now = datetime.now(UTC)
    service = gd.GiftDaysService()
    bot = Bot()
    service.set_bot(bot)
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        offer = await _setup(db, now)
        _pay(db, now, 'Покупка тарифа ⭐️ Стандартный на 90 дней')
        await db.commit()
        panel['ok'] = False
        stats = await service.run_once(now, _sessions(db))
        assert stats['granted'] == 1 and stats['panel'] == 0 and not bot.sent
        panel['ok'] = True
        stats = await service.run_once(now, _sessions(db))
        assert stats == {'granted': 0, 'waiting': 0, 'failed': 0, 'panel': 1, 'notified': 1}
        await db.refresh(offer)
        assert offer.extra_data['panel_synced'] and offer.extra_data['notified']
        calls = panel['calls']
        assert not any((await service.run_once(now, _sessions(db))).values())
        assert panel['calls'] == calls


async def test_blocked_user_is_not_retried_but_network_error_is(postgres_database, panel):
    now = datetime.now(UTC)
    service = gd.GiftDaysService()
    bot = Bot(TelegramNetworkError(method=MagicMock(), message='timeout'))
    service.set_bot(bot)
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        offer = await _setup(db, now)
        _pay(db, now, 'Покупка тарифа ⭐️ Стандартный на 90 дней')
        await db.commit()
        assert (await service.run_once(now, _sessions(db)))['notified'] == 0
        await db.refresh(offer)
        assert not offer.extra_data['notified']
        bot.error = TelegramForbiddenError(method=MagicMock(), message='Forbidden: bot was blocked by the user')
        await service.run_once(now, _sessions(db))
        await db.refresh(offer)
        assert offer.extra_data['notified']


async def test_cabinet_user_without_telegram_gets_gift_silently(postgres_database, panel):
    now = datetime.now(UTC)
    service = gd.GiftDaysService()
    service.set_bot(Bot())
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        offer = await _setup(db, now, telegram_id=None)
        _pay(db, now, 'Покупка тарифа ⭐️ Стандартный на 180 дней', amount=-78900)
        await db.commit()
        assert (await service.run_once(now, _sessions(db)))['granted'] == 1
        await db.refresh(offer)
        assert offer.extra_data['notified'] and offer.extra_data['period_days'] == 180


async def test_grant_refuses_past_deadline(postgres_database):
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        with pytest.raises(ValueError):
            await gd.grant(db, [1], expires_at=datetime.now(UTC) - timedelta(minutes=1))


async def test_purchases_topic_gets_each_gift_once(postgres_database, panel, monkeypatch):
    now = datetime.now(UTC)
    calls = []
    state = {'ok': False}

    async def send(self, db, user, subscription, **kwargs):
        calls.append(kwargs)
        return state['ok']

    monkeypatch.setattr(AdminNotificationService, 'is_enabled', property(lambda self: True))
    monkeypatch.setattr(AdminNotificationService, 'send_gift_days_notification', send)
    service = gd.GiftDaysService()
    bot = Bot()
    service.set_bot(bot)
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        offer = await _setup(db, now)
        _pay(db, now, 'Покупка тарифа ⭐️ Стандартный на 180 дней', amount=-78900)
        await db.commit()
        await service.run_once(now, _sessions(db))
        await db.refresh(offer)
        assert len(calls) == 1 and not offer.extra_data['admin_notified'] and len(bot.sent) == 1
        assert calls[0]['period_days'] == 180 and calls[0]['bonus_days'] == 90
        state['ok'] = True
        await service.run_once(now, _sessions(db))
        await db.refresh(offer)
        assert len(calls) == 2 and offer.extra_data['admin_notified'] and len(bot.sent) == 1
        await service.run_once(now, _sessions(db))
        assert len(calls) == 2


async def test_purchases_topic_message_text(postgres_database, monkeypatch):
    now = datetime.now(UTC)
    sent = {}

    async def capture(self, text, reply_markup=None, *, category=None, thread_id=None):
        sent['text'], sent['category'] = text, category
        return True

    monkeypatch.setattr(AdminNotificationService, '_send_message', capture)
    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        await _setup(db, now)
        user, sub = await db.get(User, 1), await db.get(Subscription, 10)
        ok = await AdminNotificationService(Bot()).send_gift_days_notification(
            db, user, sub, period_days=90, bonus_days=90, old_end=now, transaction_id=7
        )
    assert ok and sent['category'].value == 'purchases'
    assert 'ПОДАРОК ПО АКЦИИ' in sent['text'] and 'Оплачено 90 дн. + <b>90 дн. в подарок</b>' in sent['text']
    assert '#7' in sent['text']
