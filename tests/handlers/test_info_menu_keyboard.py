from app.keyboards.inline import get_info_menu_keyboard


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_legal_entry_shown_by_default():
    # Spofy: правила, оферта и политика собраны в один вход «Правила и документы»
    markup = get_info_menu_keyboard()
    assert 'menu_legal' in _callbacks(markup)


def test_legal_entry_hidden_when_all_documents_disabled():
    markup = get_info_menu_keyboard(show_rules=False, show_privacy_policy=False, show_public_offer=False)
    assert 'menu_legal' not in _callbacks(markup)
