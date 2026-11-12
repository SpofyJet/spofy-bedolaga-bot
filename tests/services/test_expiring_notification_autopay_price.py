"""Напоминание об истечении при включённом автопродлении берёт цену, которую реально спишут.

Раньше цена бралась из тарифа за срок, без докупленных устройств. Человек с балансом
385 ₽ и семью устройствами (нужно 470 ₽) получал «ничего делать не нужно», а списание
в тот же проход не проходило.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.config import settings
from app.services.monitoring_service import MonitoringService


class _Texts:
    MENU_SUBSCRIPTION = 'Подписка'

    def t(self, key: str, default: str | None = None) -> str:
        return default if default is not None else key

    def format_price(self, kopeks: int) -> str:
        return f'{(kopeks or 0) // 100} ₽'


def _tariff() -> SimpleNamespace:
    return SimpleNamespace(
        name='С Обходами',
        period_prices={'30': 27000},
        get_shortest_period=lambda: 30,
        get_available_periods=lambda: [30],
    )


def _user(balance: int) -> SimpleNamespace:
    return SimpleNamespace(id=537, telegram_id=12345, language='ru', balance_kopeks=balance)


def _subscription() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        autopay_enabled=True,
        autopay_period_days=30,
        end_date=datetime.now(UTC) + timedelta(days=3),
        tariff=_tariff(),
    )


def _service(monkeypatch) -> tuple[MonitoringService, MagicMock]:
    monkeypatch.setattr(settings, 'ENABLE_LOGO_MODE', False)
    monkeypatch.setattr(settings, 'ENABLE_AUTOPAY', True)
    monkeypatch.setattr(type(settings), 'is_multi_tariff_enabled', lambda self: False)
    monkeypatch.setattr('app.services.monitoring_service.get_texts', lambda _lang: _Texts())
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return MonitoringService(bot=bot), bot


async def test_extra_devices_price_turns_promise_into_low_balance_warning(monkeypatch):
    svc, bot = _service(monkeypatch)

    # Баланс 385 ₽ покрывает цену срока из тарифа (270 ₽), но не реальную (470 ₽).
    ok = await svc._send_subscription_expiring_notification(_user(38500), _subscription(), days=3, renewal_price=47000)

    assert ok is True
    text = bot.send_message.await_args.kwargs['text']
    assert 'ничего делать не нужно' not in text.lower()
    assert '470 ₽' in text
    assert '385 ₽' in text


async def test_enough_balance_keeps_the_promise_with_real_cost(monkeypatch):
    svc, bot = _service(monkeypatch)

    ok = await svc._send_subscription_expiring_notification(_user(50000), _subscription(), days=3, renewal_price=47000)

    assert ok is True
    text = bot.send_message.await_args.kwargs['text']
    assert 'автоматически' in text
    assert '470 ₽' in text


async def test_without_real_price_falls_back_to_tariff_period_price(monkeypatch):
    svc, bot = _service(monkeypatch)

    ok = await svc._send_subscription_expiring_notification(_user(38500), _subscription(), days=3)

    assert ok is True
    text = bot.send_message.await_args.kwargs['text']
    assert 'автоматически' in text
    assert '270 ₽' in text


async def test_autopay_renewal_price_uses_the_charge_calculation(monkeypatch):
    svc, _ = _service(monkeypatch)
    calls: list[tuple] = []

    async def fake_price(db, subscription, period, user=None):
        calls.append((subscription.id, period, user.id))
        return SimpleNamespace(final_total=47000)

    monkeypatch.setattr('app.services.pricing_engine.pricing_engine.calculate_renewal_price', fake_price)

    assert await svc._autopay_renewal_price(MagicMock(), _user(0), _subscription()) == 47000
    assert calls == [(1, 30, 537)]


async def test_autopay_renewal_price_is_none_when_calculation_fails(monkeypatch):
    svc, _ = _service(monkeypatch)

    async def broken(*args, **kwargs):
        raise RuntimeError('no price')

    monkeypatch.setattr('app.services.pricing_engine.pricing_engine.calculate_renewal_price', broken)

    assert await svc._autopay_renewal_price(MagicMock(), _user(0), _subscription()) is None
