"""Какой панельный аккаунт уходит вместе с удалённой подпиской.

Адресация аккаунта в двух режимах устроена по-разному, и удаление подписки —
единственное место, где ошибка адресации не откатывается: либо у человека
остаётся живой VPN после того, как админ снял доступ, либо наоборот умирает
доступ по соседней, ещё действующей подписке.

* мультитариф — аккаунт у каждой подписки свой (``subscriptions.remnawave_id``);
* однотарифный — аккаунт общий на пользователя (``users.remnawave_id``), а
  колонка подписки заполнена максимум у одной строки: индекс
  ``uq_subscriptions_remnawave_id`` частично уникален, поэтому второй строке
  id не пишется (см. subscription_service), а синхронизация кабинета по
  email/OAuth создаёт строку с ``remnawave_id=None`` намеренно.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.database.models import (
    DiscountOffer,
    PlategaSubscription,
    SentNotification,
    Subscription,
    SubscriptionEvent,
    SubscriptionServer,
    SubscriptionStatus,
    SubscriptionTemporaryAccess,
    TrafficPurchase,
    User,
    UserStatus,
)
from app.services import subscription_deletion_service as deletion
from tests.fixtures.sqlite_memory import memory_session


# db.delete() подтягивает все связи подписки — без их таблиц падает на SELECT.
TABLES = (
    User.__table__,
    Subscription.__table__,
    DiscountOffer.__table__,
    SubscriptionTemporaryAccess.__table__,
    TrafficPurchase.__table__,
    PlategaSubscription.__table__,
    SentNotification.__table__,
    SubscriptionEvent.__table__,
    SubscriptionServer.__table__,
)

PANEL_ID = 4242


def _user(*, remnawave_id: int | None) -> User:
    return User(
        id=10,
        telegram_id=10,
        username='client',
        status=UserStatus.ACTIVE.value,
        remnawave_id=remnawave_id,
    )


def _sub(sub_id: int, *, status: str, remnawave_id: int | None = None) -> Subscription:
    now = datetime.now(UTC)
    return Subscription(
        id=sub_id,
        user_id=10,
        status=status,
        is_trial=False,
        remnawave_id=remnawave_id,
        # колонка nullable=False + unique, дефолт '' — двум строкам нужны разные
        remnawave_short_id=f'short{sub_id}',
        start_date=now - timedelta(days=30),
        end_date=now + timedelta(days=30),
    )


@pytest.mark.asyncio
async def test_single_tariff_falls_back_to_the_user_account(monkeypatch):
    """Однотарифный: колонка подписки пуста, но аккаунт есть — и его надо снять.

    Без этого админ жмёт «удалить», строка исчезает, а VPN у человека
    продолжает работать до конца оплаченного периода.
    """

    async with memory_session(monkeypatch, TABLES) as db:
        db.add(_user(remnawave_id=PANEL_ID))
        target = _sub(1, status=SubscriptionStatus.ACTIVE.value, remnawave_id=None)
        db.add(target)
        await db.commit()

        panel_user_id, deletable = await deletion._resolve_panel_target(db, target)

    assert panel_user_id == PANEL_ID
    # Аккаунт общий на пользователя — отключаем, но не сносим.
    assert deletable is False


@pytest.mark.asyncio
async def test_single_tariff_spares_account_of_a_live_sibling(monkeypatch):
    """Однотарифный: живая соседка сидит на том же аккаунте — не трогаем его.

    Иначе уборка отработавшей строки убивает действующий доступ.
    """

    async with memory_session(monkeypatch, TABLES) as db:
        db.add(_user(remnawave_id=PANEL_ID))
        target = _sub(1, status=SubscriptionStatus.EXPIRED.value, remnawave_id=PANEL_ID)
        db.add(target)
        db.add(_sub(2, status=SubscriptionStatus.ACTIVE.value, remnawave_id=None))
        await db.commit()

        assert await deletion._resolve_panel_target(db, target) == (None, False)


@pytest.mark.asyncio
async def test_single_tariff_ignores_dead_sibling(monkeypatch):
    """Мёртвая соседка ничего не держит — аккаунт всё равно отключаем."""

    async with memory_session(monkeypatch, TABLES) as db:
        db.add(_user(remnawave_id=PANEL_ID))
        target = _sub(1, status=SubscriptionStatus.ACTIVE.value, remnawave_id=None)
        db.add(target)
        db.add(_sub(2, status=SubscriptionStatus.EXPIRED.value, remnawave_id=PANEL_ID))
        await db.commit()

        assert await deletion._resolve_panel_target(db, target) == (PANEL_ID, False)


@pytest.mark.asyncio
async def test_single_tariff_uses_subscription_id_when_user_has_none(monkeypatch):
    """Историческая строка: id остался только на подписке — работаем по нему."""

    async with memory_session(monkeypatch, TABLES) as db:
        db.add(_user(remnawave_id=None))
        target = _sub(1, status=SubscriptionStatus.EXPIRED.value, remnawave_id=PANEL_ID)
        db.add(target)
        await db.commit()

        assert await deletion._resolve_panel_target(db, target) == (PANEL_ID, True)


class _PanelSpy:
    """Счётчик того, что реально ушло в панель."""

    def __init__(self) -> None:
        self.deleted: list[int] = []
        self.disabled: list[int] = []
        self.marked: list[int] = []
        self.decremented: list[int] = []
        self.order: list[str] = []

    def install(self, monkeypatch) -> None:
        from app.services.remnawave_webhook_service import RemnaWaveWebhookService
        from app.services.subscription_service import SubscriptionService

        async def fake_delete(_self, panel_user_id):
            self.deleted.append(panel_user_id)
            self.order.append('panel_delete')
            return True

        async def fake_disable(_self, panel_user_id, db=None):
            self.disabled.append(panel_user_id)
            self.order.append('panel_disable')
            return True

        monkeypatch.setattr(SubscriptionService, 'delete_remnawave_user', fake_delete)
        monkeypatch.setattr(SubscriptionService, 'disable_remnawave_user', fake_disable)
        monkeypatch.setattr(
            RemnaWaveWebhookService,
            'mark_intentional_panel_deletion',
            staticmethod(lambda panel_user_ids: self.marked.extend(panel_user_ids)),
        )

        def _record(label):
            async def recorder(*args, **kwargs):
                self.order.append(label)

            return recorder

        async def fake_decrement(_db, subscription):
            self.decremented.append(subscription.id)
            self.order.append('decrement')

        monkeypatch.setattr(
            'app.services.payment.platega.cancel_platega_recurring_for_subscription_safe', _record('platega')
        )
        monkeypatch.setattr(deletion, 'decrement_subscription_server_counts', fake_decrement)


@pytest.mark.asyncio
async def test_single_tariff_deletion_disables_shared_account(monkeypatch):
    """Однотарифный, соседок нет: доступ снят, аккаунт остался живым для новой покупки."""
    spy = _PanelSpy()
    spy.install(monkeypatch)

    async with memory_session(monkeypatch, TABLES) as db:
        db.add(_user(remnawave_id=PANEL_ID))
        target = _sub(1, status=SubscriptionStatus.ACTIVE.value, remnawave_id=None)
        db.add(target)
        await db.commit()

        await deletion.delete_subscription_record(db, target, deleted_by='admin:1')

        remaining = await db.scalar(select(Subscription.id).where(Subscription.id == 1))

    assert spy.disabled == [PANEL_ID]
    assert spy.deleted == []
    assert spy.marked == []
    assert remaining is None
    # Счётчики серверов не должны остаться завышенными после удаления строки
    assert spy.decremented == [1]


@pytest.mark.asyncio
async def test_single_tariff_deletion_leaves_live_sibling_alone(monkeypatch):
    """Уборка отработавшей строки не должна трогать аккаунт живой соседки."""
    spy = _PanelSpy()
    spy.install(monkeypatch)

    async with memory_session(monkeypatch, TABLES) as db:
        db.add(_user(remnawave_id=PANEL_ID))
        target = _sub(1, status=SubscriptionStatus.EXPIRED.value, remnawave_id=PANEL_ID)
        db.add(target)
        db.add(_sub(2, status=SubscriptionStatus.ACTIVE.value, remnawave_id=None))
        await db.commit()

        await deletion.delete_subscription_record(db, target, deleted_by='admin:1')

    assert spy.deleted == []
    assert spy.disabled == []
