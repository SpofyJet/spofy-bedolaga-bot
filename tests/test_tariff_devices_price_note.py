"""Цена периода для человека с доп. устройствами: список, подтверждение и пояснение совпадают."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.handlers.subscription import tariff_purchase as tp
from app.localization.texts import get_texts


def _tariff(**kw):
    base = dict(id=3, name='T', device_limit=3, device_price_kopeks=5000, device_price_flat=False,
                period_prices={'30': 27000, '365': 180000})  # fmt: skip
    base.update(kw)
    return SimpleNamespace(**base)


async def _prices(existing, tariff):
    engine = MagicMock()
    engine.calculate_tariff_purchase_price = AsyncMock(
        side_effect=lambda t, p, device_limit, user: SimpleNamespace(
            final_total=int(t.period_prices[str(p)]) + (device_limit - 3) * 5000 * (12 if p == 365 else 1)
        )
    )
    with (
        patch.object(tp, 'get_subscription_by_user_id', AsyncMock(return_value=existing)),
        patch('app.services.pricing_engine.pricing_engine', engine),
    ):
        return await tp._personal_period_prices(None, SimpleNamespace(id=1), tariff)


async def test_year_price_includes_extra_devices():
    sub = SimpleNamespace(tariff_id=3, device_limit=5)
    prices, extra = await _prices(sub, _tariff())
    assert extra == 2
    assert prices[365] == 180000 + 2 * 5000 * 12  # 3000 ₽


async def test_no_extra_devices_keeps_base_prices():
    sub = SimpleNamespace(tariff_id=3, device_limit=3)
    assert await _prices(sub, _tariff()) == (None, 0)
    assert await _prices(None, _tariff()) == (None, 0)


def test_breakdown_note_mentions_extra_devices_only_when_paid():
    texts = get_texts('ru')
    note = tp._price_breakdown_note(texts, _tariff(), 5, SimpleNamespace(devices_price=120000))
    assert '1200' in note.replace(' ', '').replace('\u00a0', '')
    assert tp._price_breakdown_note(texts, _tariff(), 3, SimpleNamespace(devices_price=0)) == ''


def test_period_note_skipped_for_flat_device_price():
    texts = get_texts('ru')
    assert tp._extra_devices_note(texts, _tariff(device_price_flat=True), 2) == ''
    assert 'доп' in tp._extra_devices_note(texts, _tariff(), 2)
