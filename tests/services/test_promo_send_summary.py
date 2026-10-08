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

    db = MagicMock()
    db.rollback = AsyncMock()
    user = SimpleNamespace(id=7, balance_kopeks=10000)
    transaction = SimpleNamespace(id=9, amount_kopeks=10000, completed_at=None, created_at=None)

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
