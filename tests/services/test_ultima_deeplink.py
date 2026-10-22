"""Ссылка из канала /start ultima: личное предложение, свой час, понятные повторные нажатия."""

import contextlib
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.database.models import Base, PromoOfferTemplate, Subscription, SubscriptionEvent
from app.handlers import ultima_deeplink as link
from app.handlers.admin import promo_offers


def test_link_parsing():
    assert link.is_ultima_deeplink('ultima') and link.is_ultima_deeplink('ultima_ch1')
    assert (
        not link.is_ultima_deeplink('ultimate')
        and not link.is_ultima_deeplink(None)
        and not link.is_ultima_deeplink('renew')
    )
    assert link.link_source('ultima_ch1') == 'ch1' and link.link_source('ultima') == ''


@contextlib.asynccontextmanager
async def _session(monkeypatch):
    stub = sys.modules.get('aiosqlite')
    if stub is not None and not hasattr(stub, 'connect'):
        monkeypatch.delitem(sys.modules, 'aiosqlite', raising=False)
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c, tables=[PromoOfferTemplate.__table__, SubscriptionEvent.__table__, Subscription.__table__]
            )
        )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            session.add(
                PromoOfferTemplate(
                    id=4,
                    name='ULTIMA',
                    offer_type='tariff_discount',
                    message_text='Предложение ULTIMA',
                    button_text='Купить за 3 150 ₽',
                    valid_hours=1,
                    discount_percent=37,
                    active_discount_hours=1,
                    is_active=True,
                )
            )
            await session.commit()
            yield session
    finally:
        await engine.dispose()


def _user(**kw):
    base = dict(
        id=7,
        telegram_id=77,
        language='ru',
        promo_offer_discount_percent=0,
        promo_offer_discount_source=None,
        promo_offer_discount_expires_at=None,
    )
    return SimpleNamespace(**{**base, **kw})


def _message():
    message = MagicMock()
    message.answer = AsyncMock()
    message.bot = MagicMock()
    return message


async def _events(db):
    return [row[0] for row in (await db.execute(select(SubscriptionEvent.message))).all()]


async def test_first_open_activates_and_records_the_source(monkeypatch):
    monkeypatch.setattr(settings, 'PROMO_OFFER_TARIFF_ID', 4, raising=False)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(promo_offers, '_send_prepaid_tariff_offer', send)
    async with _session(monkeypatch) as db:
        assert await link.open_ultima_offer(_message(), _user(), db, source='ch1') is True
        assert await _events(db) == ['activated:ch1']
    assert send.await_args.kwargs['ignore_preferences'] is True  # человек сам нажал ссылку


async def test_second_open_while_active_shows_remaining_without_extending(monkeypatch):
    monkeypatch.setattr(settings, 'PROMO_OFFER_TARIFF_ID', 4, raising=False)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(promo_offers, '_send_prepaid_tariff_offer', send)
    user = _user(
        promo_offer_discount_percent=37,
        promo_offer_discount_source='tariff:4|promo_template_4',
        promo_offer_discount_expires_at=datetime.now(UTC) + timedelta(minutes=40),
    )
    message = _message()
    async with _session(monkeypatch) as db:
        assert await link.open_ultima_offer(message, user, db, source='ch2') is True
        assert await _events(db) == ['active:ch2']
    send.assert_not_awaited()  # скидку не выдавали заново
    text = message.answer.await_args.args[0]
    assert 'осталось 39' in text and 'Предложение ULTIMA' in text


async def test_reopen_after_expiry_inside_cooldown_gets_no_new_discount(monkeypatch):
    monkeypatch.setattr(settings, 'PROMO_OFFER_TARIFF_ID', 4, raising=False)
    monkeypatch.setattr(settings, 'PROMO_LINK_COOLDOWN_HOURS', 12, raising=False)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(promo_offers, '_send_prepaid_tariff_offer', send)
    message = _message()
    async with _session(monkeypatch) as db:
        await link.open_ultima_offer(_message(), _user(), db, source='ch1')  # первое открытие
        assert await link.open_ultima_offer(message, _user(), db, source='ch1') is True  # скидка уже не действует
        assert await _events(db) == ['activated:ch1', 'cooldown:ch1']
    assert send.await_count == 1
    assert 'уже открывали' in message.answer.await_args.args[0]


async def test_cooldown_zero_allows_unlimited_reopening(monkeypatch):
    monkeypatch.setattr(settings, 'PROMO_OFFER_TARIFF_ID', 4, raising=False)
    monkeypatch.setattr(settings, 'PROMO_LINK_COOLDOWN_HOURS', 0, raising=False)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(promo_offers, '_send_prepaid_tariff_offer', send)
    async with _session(monkeypatch) as db:
        await link.open_ultima_offer(_message(), _user(), db, source='x')
        await link.open_ultima_offer(_message(), _user(), db, source='x')
    assert send.await_count == 2


async def test_without_a_template_the_link_falls_back_to_normal_start(monkeypatch):
    async with _session(monkeypatch) as db:
        await db.execute(PromoOfferTemplate.__table__.delete())
        await db.commit()
        assert await link.open_ultima_offer(_message(), _user(), db, source='') is False


async def test_already_owned_tariff_skips_the_offer(monkeypatch):
    """ULTIMA уже куплен — скидка на его покупку бесполезна, идём в обычный /start."""
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(promo_offers, '_send_prepaid_tariff_offer', send)
    async with _session(monkeypatch) as db:
        db.add(
            Subscription(
                id=1,
                user_id=7,
                tariff_id=4,
                status='active',
                is_trial=False,
                end_date=datetime.now(UTC) + timedelta(days=30),
            )
        )
        await db.commit()
        assert await link.open_ultima_offer(_message(), _user(), db, source='ch1') is False
        assert await _events(db) == ['already_owned:ch1']
    send.assert_not_awaited()


@pytest.fixture(autouse=True)
def _tariff_id(monkeypatch):
    monkeypatch.setattr(settings, 'PROMO_OFFER_TARIFF_ID', 4, raising=False)
