"""Кнопки оплаты криптовалютой названы по тому, чем платят, а не по имени платёжки."""

from app.config import settings
from app.keyboards.inline import get_payment_methods_keyboard
from app.localization.texts import get_texts
from app.utils.payment_utils import get_payment_methods_text, pay2328_button_label, xrocket_button_label


def test_xrocket_button_lists_configured_coins(monkeypatch) -> None:
    monkeypatch.setattr(type(settings), 'get_xrocket_assets', lambda self: ['USDT', 'TONCOIN', 'BTC', 'ETH'])

    assert xrocket_button_label(get_texts('ru')) == 'Криптовалюта · USDT, TON, BTC, ETH'
    assert xrocket_button_label(get_texts('en')) == 'Crypto · USDT, TON, BTC, ETH'


def test_pay2328_button_does_not_name_the_provider() -> None:
    assert pay2328_button_label(get_texts('ru')) == 'Криптовалюта · перевод на адрес'
    assert '2328' not in pay2328_button_label(get_texts('en'))


def test_keyboard_and_text_above_it(monkeypatch) -> None:
    cls = type(settings)
    monkeypatch.setattr(cls, 'is_xrocket_enabled', lambda self: True)
    monkeypatch.setattr(cls, 'is_pay2328_enabled', lambda self: True)
    monkeypatch.setattr(cls, 'get_xrocket_assets', lambda self: ['USDT', 'TONCOIN'])

    keyboard = get_payment_methods_keyboard(0, 'ru')
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert 'Криптовалюта · USDT, TON' in labels
    assert 'Криптовалюта · перевод на адрес' in labels
    assert not [label for label in labels if 'xRocket' in label or '2328' in label]

    # Текст над кнопками — заголовок и приглашение, без повторения списка способов.
    above = get_payment_methods_text('ru')
    for word in ('xRocket', '2328', 'Криптовалюта', 'Stars', 'СБП'):
        assert word not in above
