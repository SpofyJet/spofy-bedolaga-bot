"""Флаги брендинга (анимация, полный экран, лайт, футер, виджет Telegram) и ответ счётчиков аналитики."""

from types import SimpleNamespace

import pytest

from app.cabinet.routes import branding


@pytest.fixture
def store(monkeypatch):
    values: dict[str, str] = {}

    async def get(db, key):
        return values.get(key)

    async def put(db, key, value):
        values[key] = value

    monkeypatch.setattr(branding, 'get_setting_value', get)
    monkeypatch.setattr(branding, 'set_setting_value', put)
    return values


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('stored', 'default', 'expected'),
    [(None, True, True), (None, False, False), ('TRUE', False, True), ('True', False, True), ('false', True, False)],
)
async def test_flag_setting(store, stored, default, expected):
    if stored is not None:
        store['K'] = stored
    assert await branding._get_flag_setting('db', 'K', default) is expected


@pytest.mark.asyncio
async def test_public_flags_keep_their_defaults(store):
    assert (await branding.get_animation_enabled(db='db')).enabled is True
    assert (await branding.get_footer_enabled(db='db')).enabled is True
    assert (await branding.get_fullscreen_enabled(db='db')).enabled is False
    assert (await branding.get_lite_mode_enabled(db='db')).enabled is False


@pytest.mark.asyncio
async def test_oidc_needs_client_id(store, monkeypatch):
    monkeypatch.setattr(branding.settings, 'TELEGRAM_OIDC_CLIENT_ID', '')
    store[branding.TELEGRAM_OIDC_ENABLED_KEY] = 'true'
    store[branding.TELEGRAM_WIDGET_USERPIC_KEY] = 'False'
    config = await branding.get_telegram_widget_config(db='db')
    assert (config.oidc_enabled, config.oidc_client_id, config.userpic) == (False, '', False)

    store[branding.TELEGRAM_OIDC_CLIENT_ID_KEY] = 'client'
    config = await branding.get_telegram_widget_config(db='db')
    assert (config.oidc_enabled, config.oidc_client_id) == (True, 'client')


@pytest.mark.asyncio
async def test_analytics_update_returns_same_shape_as_get(store, monkeypatch):
    monkeypatch.setattr(branding.settings, 'YANDEX_OFFLINE_CONV_ENABLED', True)
    monkeypatch.setattr(branding.settings, 'YANDEX_OFFLINE_CONV_MEASUREMENT_SECRET', 'secret-1234')

    updated = await branding.update_analytics_counters(
        payload=branding.AnalyticsCountersUpdate(yandex_metrika_id=' 42 ', google_ads_label=' L '),
        admin=SimpleNamespace(telegram_id=1),
        db='db',
    )
    current = await branding.get_analytics_counters(db='db')

    assert updated == current
    assert (current.yandex_metrika_id, current.google_ads_label) == ('42', 'L')
    assert current.offline_conv_measurement_secret_masked == '********1234'
    assert [goal.event_id for goal in current.offline_conv_goals] == ['registration', 'trial-add', 'purchase']
