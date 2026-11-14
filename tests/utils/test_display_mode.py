import pytest

from app.services.system_settings_service import BotConfigurationService
from app.utils.display_mode import (
    is_visible_in_bot,
    is_visible_in_web,
    normalize_display_mode,
)


DISPLAY_MODE_KEYS = (
    'PRIVACY_POLICY_DISPLAY_MODE',
    'PUBLIC_OFFER_DISPLAY_MODE',
    'SERVICE_RULES_DISPLAY_MODE',
    'FAQ_DISPLAY_MODE',
)


def test_normalize_display_mode_known_values():
    assert normalize_display_mode('bot') == 'bot'
    assert normalize_display_mode('WEB') == 'web'
    assert normalize_display_mode(' both ') == 'both'


def test_normalize_display_mode_fallback_to_both():
    assert normalize_display_mode(None) == 'both'
    assert normalize_display_mode('') == 'both'
    assert normalize_display_mode('garbage') == 'both'


def test_visibility_matrix():
    assert is_visible_in_bot('bot')
    assert is_visible_in_bot('both')
    assert not is_visible_in_bot('web')
    assert is_visible_in_web('web')
    assert is_visible_in_web('both')
    assert not is_visible_in_web('bot')


@pytest.mark.parametrize('key', DISPLAY_MODE_KEYS)
def test_config_defaults_are_both(key):
    from app.config import Settings

    assert Settings.model_fields[key].default == 'both'


@pytest.mark.parametrize('key', DISPLAY_MODE_KEYS)
def test_settings_registered_in_info_pages_category(key):
    BotConfigurationService.initialize_definitions()
    definition = BotConfigurationService.get_definition(key)
    assert definition.category_key == 'INFO_PAGES'
    choices = {option.value for option in BotConfigurationService.CHOICES[key]}
    assert choices == {'bot', 'web', 'both'}
