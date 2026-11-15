"""Настройки поддержки — обычные настройки бота в базе, а не файл ``data/support_settings.json``.

Тот же класс дефекта, что у переключателей уведомлений истёкшим: файл на диске с вечным кэшем в
памяти процесса. Владелец: «таких отголосков прошлого не должно быть совсем». Режим поддержки,
меню, флаги уведомлений о тикетах, SLA, модераторы и тексты «о поддержке» по языкам теперь ключи
``SUPPORT_*`` в ``Settings``: база через слой системных настроек, кабинет, живое чтение. Старый
файл импортируется один раз при старте; уже заданное в базе главнее файла.
"""

from __future__ import annotations

import json

import pytest

from app.config import settings
from app.database.crud.system_setting import get_setting_value
from app.database.models import SystemSetting
from app.services.support_settings_service import SupportSettingsService
from app.services.system_settings_service import bot_configuration_service
from tests.fixtures.sqlite_memory import memory_session


TABLES = [SystemSetting.__table__]
KEYS = (
    'SUPPORT_SYSTEM_MODE',
    'SUPPORT_MENU_ENABLED',
    'SUPPORT_TICKET_SLA_ENABLED',
    'SUPPORT_TICKET_SLA_MINUTES',
    'SUPPORT_ADMIN_TICKET_NOTIFICATIONS_ENABLED',
    'SUPPORT_USER_TICKET_NOTIFICATIONS_ENABLED',
    'SUPPORT_CABINET_USER_NOTIFICATIONS_ENABLED',
    'SUPPORT_CABINET_ADMIN_NOTIFICATIONS_ENABLED',
    'SUPPORT_MODERATOR_IDS',
    'SUPPORT_INFO_TEXT_RU',
    'SUPPORT_INFO_TEXT_EN',
)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    bot_configuration_service.initialize_definitions()
    for key in KEYS:
        monkeypatch.setattr(settings, key, getattr(settings, key))
    monkeypatch.setattr(settings, 'ENABLE_NOTIFICATIONS', True)
    monkeypatch.setattr(SupportSettingsService, '_legacy_path', tmp_path / 'support_settings.json')
    yield
    for key in KEYS:
        bot_configuration_service._overrides_raw.pop(key, None)


def test_keys_are_bot_settings_in_the_support_category() -> None:
    for key in KEYS:
        assert bot_configuration_service.get_definition(key).category_key == 'SUPPORT', key
    for key in KEYS[4:9]:
        assert bot_configuration_service.SETTING_HINTS[key]['description'], f'{key}: подсказка словами для кабинета'
    assert not hasattr(SupportSettingsService, '_data') and not hasattr(SupportSettingsService, '_loaded'), (
        'кэша файла больше нет — источник один'
    )


def test_getters_read_live_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'SUPPORT_SYSTEM_MODE', 'contact')
    monkeypatch.setattr(settings, 'SUPPORT_MENU_ENABLED', False)
    monkeypatch.setattr(settings, 'SUPPORT_TICKET_SLA_ENABLED', True)
    monkeypatch.setattr(settings, 'SUPPORT_TICKET_SLA_MINUTES', 0)
    monkeypatch.setattr(settings, 'SUPPORT_MODERATOR_IDS', ' 10, 20,мусор,30 ')
    assert SupportSettingsService.get_system_mode() == 'contact'
    assert SupportSettingsService.is_tickets_enabled() is False and SupportSettingsService.is_contact_enabled()
    assert settings.is_support_tickets_enabled() is False, 'кабинет и бот читают одно и то же'
    assert SupportSettingsService.is_support_menu_enabled() is False
    assert SupportSettingsService.get_sla_enabled() is True
    assert SupportSettingsService.get_sla_minutes() == 60, 'ноль минут — значение по умолчанию'
    assert SupportSettingsService.get_moderators() == [10, 20, 30]
    assert SupportSettingsService.is_moderator('20') and not SupportSettingsService.is_moderator(99)
    monkeypatch.setattr(settings, 'SUPPORT_SYSTEM_MODE', 'nonsense')
    assert SupportSettingsService.get_system_mode() == 'both', 'мусорный режим нормализуется'


def test_ticket_notification_flags_respect_global_switches(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'SUPPORT_USER_TICKET_NOTIFICATIONS_ENABLED', True)
    monkeypatch.setattr(settings, 'ENABLE_NOTIFICATIONS', False)
    assert SupportSettingsService.get_user_ticket_notifications_enabled() is False
    monkeypatch.setattr(settings, 'ENABLE_NOTIFICATIONS', True)
    assert SupportSettingsService.get_user_ticket_notifications_enabled() is True
    monkeypatch.setattr(settings, 'SUPPORT_ADMIN_TICKET_NOTIFICATIONS_ENABLED', False)
    assert SupportSettingsService.get_admin_ticket_notifications_enabled() is False
    monkeypatch.setattr(settings, 'SUPPORT_CABINET_ADMIN_NOTIFICATIONS_ENABLED', False)
    assert SupportSettingsService.get_cabinet_admin_notifications_enabled() is False
    assert SupportSettingsService.get_cabinet_user_notifications_enabled() is True


def test_support_info_text_per_language_with_locale_fallback(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'SUPPORT_INFO_TEXT_RU', '<b>Наша поддержка</b>')
    monkeypatch.setattr(settings, 'SUPPORT_INFO_TEXT_EN', '   ')
    assert SupportSettingsService.get_support_info_text('ru-RU') == '<b>Наша поддержка</b>'
    from app.localization.texts import get_texts

    assert SupportSettingsService.get_support_info_text('en') == get_texts('en').SUPPORT_INFO, 'пусто — текст локали'
    assert SupportSettingsService.get_support_info_text('xx') == get_texts('xx').SUPPORT_INFO, (
        'неизвестный язык — локаль'
    )


@pytest.mark.asyncio
async def test_legacy_file_is_imported_once_and_never_overrides_the_db(monkeypatch, tmp_path) -> None:
    legacy = tmp_path / 'support_settings.json'
    legacy.write_text(
        json.dumps(
            {
                'system_mode': 'contact',
                'menu_enabled': False,
                'support_info_texts': {'ru': '<b>Пишите</b>', 'en': '', 'xx': 'нет такого языка'},
                'admin_ticket_notifications_enabled': False,
                'user_ticket_notifications_enabled': True,
                'ticket_sla_enabled': True,
                'ticket_sla_minutes': 'мусор',
                'moderators': [30, '10', 'мусор', 20],
                'cabinet_user_notifications_enabled': False,
            }
        ),
        encoding='utf-8',
    )
    monkeypatch.setattr(SupportSettingsService, '_legacy_path', legacy)
    async with memory_session(monkeypatch, TABLES) as db:
        # В базе уже есть своё значение — оно главнее файла.
        await bot_configuration_service.set_value(db, 'SUPPORT_MENU_ENABLED', True)
        imported = await SupportSettingsService.import_legacy_file(db)
        await db.rollback()
        assert imported == {
            'SUPPORT_SYSTEM_MODE': 'contact',
            'SUPPORT_INFO_TEXT_RU': '<b>Пишите</b>',
            'SUPPORT_ADMIN_TICKET_NOTIFICATIONS_ENABLED': False,
            'SUPPORT_USER_TICKET_NOTIFICATIONS_ENABLED': True,
            'SUPPORT_TICKET_SLA_ENABLED': True,
            'SUPPORT_MODERATOR_IDS': '10,20,30',
            'SUPPORT_CABINET_USER_NOTIFICATIONS_ENABLED': False,
        }, 'мусор, пустой текст и неизвестный язык пропущены; меню из базы не тронуто'
        assert await get_setting_value(db, 'SUPPORT_SYSTEM_MODE') == 'contact'
        assert await get_setting_value(db, 'SUPPORT_MENU_ENABLED') == 'true'
    assert settings.SUPPORT_SYSTEM_MODE == 'contact' and settings.SUPPORT_MENU_ENABLED is True
    assert SupportSettingsService.get_moderators() == [10, 20, 30]
    assert not legacy.exists() and legacy.with_name('support_settings.json.imported').exists()
    async with memory_session(monkeypatch, TABLES) as db:
        assert await SupportSettingsService.import_legacy_file(db) == {}, 'второй старт — импортировать нечего'


@pytest.mark.asyncio
async def test_broken_legacy_file_is_left_to_a_human(monkeypatch, tmp_path) -> None:
    broken = tmp_path / 'support_settings.json'
    broken.write_text('{не json', encoding='utf-8')
    monkeypatch.setattr(SupportSettingsService, '_legacy_path', broken)
    async with memory_session(monkeypatch, TABLES) as db:
        assert await SupportSettingsService.import_legacy_file(db) == {}
    assert broken.exists()
