"""Рассылка предложения: пропуск «уже получал» не считается ошибкой; уведомление о пополнении переживает сбой сессии."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.exc import MissingGreenlet

from app.handlers.admin import promo_offers
from app.services.admin_notification_service import AdminNotificationService


async def test_skipped_users_are_counted_separately(monkeypatch):
    template = SimpleNamespace(id=4, offer_type='tariff_discount')
    users = [SimpleNamespace(id=n, telegram_id=n, language='ru') for n in range(1, 7)]
    outcomes = {1: True, 2: True, 3: None, 4: None, 5: None, 6: False}  # получили, пропущены, не доставлено

    async def fake_prepaid(bot, db, tpl, user, language, minutes=None):
        return outcomes[user.id]

    class Session:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(promo_offers, '_send_prepaid_tariff_offer', fake_prepaid)
    monkeypatch.setattr('app.database.database.AsyncSessionLocal', lambda: Session())
    sent, failed, already = await promo_offers._send_offer_to_users(
        MagicMock(),
        template,
        SimpleNamespace(language='ru'),
        MagicMock(),
        users,
        squad_name=None,
        effect_type='percent_discount',
    )
    assert (sent, failed, already) == (2, 1, 3)  # пропуски не попадают в «ошибки»


async def test_topup_notification_survives_broken_session(monkeypatch):
    service = AdminNotificationService(MagicMock())
    monkeypatch.setattr(service, '_is_enabled', lambda: True)
    monkeypatch.setattr(service, '_record_subscription_event', AsyncMock(side_effect=RuntimeError('db broken')))
    monkeypatch.setattr(
        service, '_build_balance_topup_message', MagicMock(side_effect=MissingGreenlet('greenlet_spawn'))
    )
    monkeypatch.setattr(service, '_reload_topup_notification_entities', AsyncMock(side_effect=MissingGreenlet('x')))
    monkeypatch.setattr(service, '_build_topup_message_in_fresh_session', AsyncMock(return_value='текст пополнения'))
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(service, '_send_message', send)

    # Новый апстримовый флоу: после сбоя записи события данные перезагружаются
    # через CRUD из той же сессии — подменяем их, «сессия» тут MagicMock.
    import app.services.admin_notification_service as ans_module

    db = MagicMock()
    db.rollback = AsyncMock()
    user = SimpleNamespace(id=7, balance_kopeks=10000)
    transaction = SimpleNamespace(id=9, amount_kopeks=10000, completed_at=None, created_at=None)
    monkeypatch.setattr(ans_module, 'get_user_by_id', AsyncMock(return_value=user))
    monkeypatch.setattr(ans_module, 'get_transaction_by_id', AsyncMock(return_value=transaction))
    monkeypatch.setattr(service, '_get_user_promo_group', AsyncMock(return_value=None))

    result = await service._send_balance_topup_notification(
        user,
        transaction,
        0,
        topup_status='ok',
        referrer_info='',
        subscription=None,
        promo_group=None,
        db=db,
    )

    assert result is True
    send.assert_awaited_once()
    assert send.await_args.args[0] == 'текст пополнения'
    service._build_topup_message_in_fresh_session.assert_awaited_once()
    assert service._build_topup_message_in_fresh_session.await_args.args[:2] == (7, 9)  # id взяты заранее


async def test_subscription_event_is_retried_in_a_fresh_session(monkeypatch):
    from app.services import admin_notification_service as module

    calls = []

    async def fake_create(db, **kwargs):
        calls.append((db, kwargs))
        if db is broken_db:
            raise MissingGreenlet('greenlet_spawn')

    class FreshSession:
        async def __aenter__(self):
            return fresh_db

        async def __aexit__(self, *args):
            return False

    broken_db = MagicMock(name='broken')
    broken_db.rollback = AsyncMock()
    fresh_db = MagicMock(name='fresh')
    monkeypatch.setattr(module, 'create_subscription_event', fake_create)
    monkeypatch.setattr('app.database.database.AsyncSessionLocal', lambda: FreshSession())

    service = AdminNotificationService(MagicMock())
    await service._record_subscription_event(
        broken_db,
        event_type='balance_topup',
        user=SimpleNamespace(id=7),
        subscription=None,
        transaction=SimpleNamespace(id=9),
        amount_kopeks=10000,
    )

    assert [call[0] for call in calls] == [broken_db, fresh_db]  # второй раз — в чистой сессии
    assert calls[1][1]['user_id'] == 7 and calls[1][1]['transaction_id'] == 9


async def test_tariff_offer_is_sent_every_time_without_protections(monkeypatch):
    """Админ отправляет сколько угодно раз: прежнее предложение и чужая скидка не мешают."""
    from datetime import UTC, datetime, timedelta

    from app.config import Settings

    monkeypatch.setattr(promo_offers.settings, 'PROMO_OFFER_TARIFF_ID', 4, raising=False)
    monkeypatch.setattr(Settings, 'is_notifications_enabled', lambda self: True)
    monkeypatch.setattr('app.utils.notification_prefs.is_promo_offers_enabled', lambda user: True)
    offer = SimpleNamespace(id=1, notification_type='promo_template_4', extra_data={'offer_type': 'tariff_discount'})
    monkeypatch.setattr(promo_offers, 'upsert_discount_offer', AsyncMock(return_value=offer))
    monkeypatch.setattr('app.database.crud.discount_offer.mark_offer_claimed', AsyncMock())

    other_discount_until = datetime.now(UTC) + timedelta(hours=5)
    stored = SimpleNamespace(
        id=7,
        telegram_id=77,
        language='ru',
        promo_offer_discount_percent=15,  # чужая действующая скидка
        promo_offer_discount_source='promo_template_3',
        promo_offer_discount_expires_at=other_discount_until,
    )
    db = MagicMock()
    db.get = AsyncMock(return_value=stored)
    db.commit = AsyncMock()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    template = SimpleNamespace(
        id=4,
        name='ULTIMA',
        offer_type='tariff_discount',
        discount_percent=37,
        active_discount_hours=1,
        valid_hours=1,
        message_text='текст',
        button_text='Купить',
        test_duration_hours=None,
    )

    for _ in range(3):  # три рассылки подряд тому же человеку
        assert await promo_offers._send_prepaid_tariff_offer(bot, db, template, stored, 'ru') is True

    assert bot.send_message.await_count == 3
    assert stored.promo_offer_discount_percent == 37 and stored.promo_offer_discount_source.startswith('tariff:4|')


async def test_xrocket_trade_api_is_skipped_after_it_died(monkeypatch):
    """Мёртвый Trade API xRocket не опрашиваем на каждом платеже: после первого не-JSON ответа 6 часов пропуск."""
    import time

    from app.external.xrocket import XRocketService

    calls = []

    class FakeResponse:
        status = 404

        async def text(self):
            return '<html>404 Not Found</html>'

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class FakeSession:
        def get(self, url, **kwargs):
            calls.append(url)
            return FakeResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr('app.external.xrocket.aiohttp.ClientSession', lambda *a, **k: FakeSession())
    monkeypatch.setattr(XRocketService, '_trade_dead_until', 0.0)
    service = XRocketService.__new__(XRocketService)

    assert await service._get_rate_xrocket_trade('USDT', 'RUB') is None
    assert await service._get_rate_xrocket_trade('USDT', 'RUB') is None
    assert len(calls) == 1  # второй раз в сеть не ходили
    assert XRocketService._trade_dead_until > time.monotonic()
    monkeypatch.setattr(XRocketService, '_trade_dead_until', 0.0)
