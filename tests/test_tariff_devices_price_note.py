"""Цена периода для человека с доп. устройствами: список, подтверждение и пояснение совпадают."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.handlers.subscription import tariff_purchase as tp
from app.localization.texts import get_texts


def _tariff(**kw):
    base = dict(id=3, name='T', device_limit=3, device_price_kopeks=5000, device_price_flat=False,
                period_prices={'30': 27000, '365': 180000}, highlight_period_days=None)  # fmt: skip
    base.update(kw)
    return SimpleNamespace(**base)


async def _extra(existing, tariff):
    with patch.object(tp, 'get_subscription_by_user_id', AsyncMock(return_value=existing)):
        return await tp._extra_device_count(None, SimpleNamespace(id=1), tariff)


async def test_extra_devices_are_counted_beyond_the_tariff():
    assert await _extra(SimpleNamespace(tariff_id=3, device_limit=5), _tariff()) == 2


async def test_no_extra_devices_means_no_note():
    assert await _extra(SimpleNamespace(tariff_id=3, device_limit=3), _tariff()) == 0
    assert await _extra(None, _tariff()) == 0


def test_period_keyboard_keeps_the_base_prices():
    kb = tp.get_tariff_periods_keyboard(
        _tariff(id=3, name='T', period_prices={'365': 180000}, highlight_period_days=None), 'ru'
    )
    assert '1800' in kb.inline_keyboard[0][0].text.replace(' ', '').replace('\u00a0', '')


def test_breakdown_note_mentions_extra_devices_only_when_paid():
    texts = get_texts('ru')
    note = tp._price_breakdown_note(texts, _tariff(), 5, SimpleNamespace(devices_price=120000))
    assert '1200' in note.replace(' ', '').replace('\u00a0', '')
    assert tp._price_breakdown_note(texts, _tariff(), 3, SimpleNamespace(devices_price=0)) == ''


def test_period_note_shows_device_count_only_when_above_included():
    texts = get_texts('ru')
    assert tp._devices_included_note(texts, _tariff(), None) == ''
    assert tp._devices_included_note(texts, _tariff(), 3) == ''
    note = tp._devices_included_note(texts, _tariff(), 5)
    assert '5' in note


def _period_button(kb, period_days: int) -> str:
    for row in kb.inline_keyboard:
        for button in row:
            if f'{period_days} дней' in button.text or f'{period_days} дня' in button.text:
                return button.text
    raise AssertionError(f'кнопка периода {period_days} не найдена')


def test_period_keyboard_shows_the_honest_price_with_extra_devices():
    kb = tp.get_tariff_periods_keyboard(_tariff(), 'ru', device_limit=5)
    text = _period_button(kb, 365).replace(' ', '').replace('\u00a0', '')
    # 180000 база + 2 доп. устройства × 5000 × 365//30 (пропорция дням, upstream)
    # = 180000 + 121666 = 301666 → 3016.66 ₽
    assert '3016' in text


def test_period_keyboard_keeps_base_prices_without_extra_devices():
    kb = tp.get_tariff_periods_keyboard(_tariff(), 'ru', device_limit=3)
    text = _period_button(kb, 365).replace(' ', '').replace('\u00a0', '')
    assert '1800' in text


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


async def test_trim_only_sets_the_flag_and_reopens_the_period_screen():
    """«Только N устр.» до оплаты НИЧЕГО не урезает: лишние устройства отключает
    confirm_tariff_purchase только после успешной оплаты."""
    sub = SimpleNamespace(tariff_id=3, device_limit=5, remnawave_id=None)
    user = SimpleNamespace(id=1, language='ru', remnawave_id=None)
    db = MagicMock(commit=AsyncMock())
    state = MagicMock()
    state.update_data = AsyncMock()
    callback = MagicMock(data='tariff_trim:3:365')
    callback.model_copy = MagicMock(return_value='reopened')
    reopen = AsyncMock()
    with (
        patch.object(
            tp, 'get_tariff_by_id', AsyncMock(return_value=SimpleNamespace(id=3, is_active=True, device_limit=3))
        ),
        patch.object(tp, 'select_tariff_period', reopen),
    ):
        await tp.trim_tariff_devices(callback, user, db, state)
    assert sub.device_limit == 5
    db.commit.assert_not_awaited()
    state.update_data.assert_awaited_once()
    assert state.update_data.await_args.kwargs['trim_devices_to_included'] is True
    reopen.assert_awaited_once()
