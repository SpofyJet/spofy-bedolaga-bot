from types import SimpleNamespace

from app.config import settings
from app.handlers.subscription.tariff_purchase import get_tariff_extend_keyboard, get_tariff_periods_keyboard
from app.keyboards.inline import get_add_traffic_keyboard_from_tariff, get_change_devices_keyboard


def _rows(keyboard):
    return [(row[0].text, row[0].callback_data, row[0].style) for row in keyboard.inline_keyboard[:-1]]


def _devices(monkeypatch, current, max_devices=None):
    monkeypatch.setattr(settings, 'MAX_DEVICES_LIMIT', 0)
    tariff = SimpleNamespace(device_limit=3, max_device_limit=max_devices, device_price_kopeks=5900)
    return _rows(get_change_devices_keyboard(current_devices=current, language='ru', tariff=tariff))


def test_devices_upsell_is_green_and_one_more_is_last_without_price(monkeypatch):
    rows = _devices(monkeypatch, 3)
    assert [cb for _, cb, _ in rows] == [
        'change_devices_5',
        'change_devices_7',
        'change_devices_10',
        'change_devices_4',
    ]
    assert [style for _, _, style in rows] == ['success', 'success', 'success', None]
    assert rows[0][0] == '5 устройств — 118 ₽'
    assert rows[-1][0] == '4 устройства'


def test_devices_above_ten_keep_three_green_steps(monkeypatch):
    rows = _devices(monkeypatch, 10)
    assert [cb for _, cb, _ in rows] == [
        'change_devices_12',
        'change_devices_13',
        'change_devices_15',
        'change_devices_11',
    ]


def test_devices_respect_tariff_maximum(monkeypatch):
    rows = _devices(monkeypatch, 3, max_devices=6)
    assert [cb for _, cb, _ in rows] == ['change_devices_5', 'change_devices_4']
    assert _devices(monkeypatch, 6, max_devices=6) == []


def test_traffic_smallest_pack_goes_last_without_price():
    keyboard = get_add_traffic_keyboard_from_tariff('ru', {25: 9900, 50: 18900, 100: 34900})
    assert _rows(keyboard) == [
        ('📊 +50 ГБ трафика — 189 ₽ /мес', 'add_traffic_50', 'success'),
        ('📊 +100 ГБ трафика — 349 ₽ /мес', 'add_traffic_100', 'success'),
        ('📊 +25 ГБ трафика', 'add_traffic_25', None),
    ]


def _tariff(prices):
    return SimpleNamespace(
        id=2, period_prices=prices, device_limit=3, device_price_kopeks=5900, highlight_period_days=None
    )


def test_shortest_period_goes_last_without_price():
    rows = _rows(get_tariff_periods_keyboard(_tariff({'14': 15900, '30': 17900, '60': 31900}), 'ru'))
    assert [(cb, style) for _, cb, style in rows] == [
        ('tariff_period:2:30', 'success'),
        ('tariff_period:2:60', 'success'),
        ('tariff_period:2:14', None),
    ]
    assert '₽' in rows[0][0] and '₽' not in rows[-1][0]


def test_single_period_stays_plain():
    rows = _rows(get_tariff_periods_keyboard(_tariff({'30': 17900}), 'ru'))
    assert [(cb, style) for _, cb, style in rows] == [('tariff_period:2:30', None)]
    assert '₽' in rows[0][0]


def test_renewal_shortest_period_goes_last():
    rows = _rows(get_tariff_extend_keyboard(_tariff({'30': 31000, '90': 83000}), 'ru', subscription_id=7))
    assert [(cb, style) for _, cb, style in rows] == [
        ('tariff_extend:7:2:90', 'success'),
        ('tariff_extend:7:2:30', None),
    ]
