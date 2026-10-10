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


def test_confirm_and_insufficient_keyboards_offer_the_trim_button():
    row = tp._trim_devices_row(get_texts('ru'), _tariff(), 365, 180000)
    for kb in (
        tp.get_tariff_confirm_keyboard(3, 365, 'ru', show_sbp=False, trim_row=row),
        tp.get_tariff_insufficient_balance_keyboard(3, 365, 'ru', missing_kopeks=0, show_sbp=False, trim_row=row),
    ):
        buttons = [b for r in kb.inline_keyboard for b in r]
        assert any(b.callback_data == 'tariff_trim:3:365' and '1' in b.text and '800' in b.text for b in buttons)
    plain = tp.get_tariff_confirm_keyboard(3, 365, 'ru', show_sbp=False)
    assert not any((b.callback_data or '').startswith('tariff_trim') for r in plain.inline_keyboard for b in r)


async def test_trim_lowers_the_limit_and_reopens_the_period_screen():
    sub = SimpleNamespace(tariff_id=3, device_limit=5, remnawave_id=None)
    user = SimpleNamespace(id=1, language='ru', remnawave_id=None)
    db = MagicMock(commit=AsyncMock())
    callback = MagicMock(data='tariff_trim:3:365')
    callback.model_copy = MagicMock(return_value='reopened')
    reopen = AsyncMock()
    with (
        patch.object(
            tp, 'get_tariff_by_id', AsyncMock(return_value=SimpleNamespace(id=3, is_active=True, device_limit=3))
        ),
        patch.object(tp, 'get_subscription_by_user_id', AsyncMock(return_value=sub)),
        patch.object(tp.settings, 'MULTI_TARIFF_ENABLED', False, create=True),
        patch('app.services.subscription_service.SubscriptionService.update_remnawave_user', AsyncMock()),
        patch.object(tp, 'select_tariff_period', reopen),
    ):
        await tp.trim_tariff_devices(callback, user, db, MagicMock())
    assert sub.device_limit == 3
    reopen.assert_awaited_once()
