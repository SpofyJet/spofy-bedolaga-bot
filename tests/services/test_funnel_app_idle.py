"""Подписка уже в приложении, а трафика нет — напоминание с шагами «включить VPN»."""

from types import SimpleNamespace

from app.localization.texts import get_texts
from app.services import activation_funnel_service as funnel


class _Api:
    def __init__(self, devices, fail=False):
        self.devices, self.fail = devices, fail

    async def __aenter__(self):
        if self.fail:
            raise RuntimeError('panel down')
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_user_devices_all(self, user_id):
        return {'devices': self.devices, 'total': len(self.devices)}


def _patch(monkeypatch, devices, fail=False):
    from app.services import remnawave_service

    monkeypatch.setattr(
        remnawave_service, 'RemnaWaveService', lambda: SimpleNamespace(get_api_client=lambda: _Api(devices, fail))
    )


_SUB = SimpleNamespace(remnawave_id=101)
_USER = SimpleNamespace(id=7, remnawave_id=None)


async def test_known_app_name(monkeypatch):
    _patch(monkeypatch, [{'userAgent': 'Happ/3.2.1/ios CFNetwork'}])
    assert await funnel._added_app_name(_SUB, _USER) == 'Happ'


async def test_unknown_app_is_empty_string(monkeypatch):
    _patch(monkeypatch, [{'userAgent': 'Shax&Mat/1.0'}])
    assert await funnel._added_app_name(_SUB, _USER) == ''


async def test_no_devices_or_panel_error_is_none(monkeypatch):
    _patch(monkeypatch, [])
    assert await funnel._added_app_name(_SUB, _USER) is None
    _patch(monkeypatch, [], fail=True)
    assert await funnel._added_app_name(_SUB, _USER) is None
    assert await funnel._added_app_name(SimpleNamespace(remnawave_id=None), _USER) is None


def test_texts(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, 'BYPASS_INCLUDE_TRIAL', True)
    monkeypatch.setattr(settings, 'TRIAL_TRAFFIC_LIMIT_GB', 5)
    texts = get_texts('ru')
    text = funnel._app_idle_text(texts, 'FUNNEL_TRIAL_APP_IDLE', 'INCY')
    assert 'Подписка уже в INCY' in text and 'Откройте INCY' in text and '«Обход»' in text
    generic = funnel._app_idle_text(texts, 'FUNNEL_TRIAL_APP_IDLE', '')
    assert 'в приложении' in generic and 'Откройте приложение' in generic
    assert 'в Happ' in funnel._app_idle_text(texts, 'TRIAL_INACTIVE_24H_APP_ADDED', 'Happ')


def test_no_bypass_step_when_trial_has_no_bypass(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, 'BYPASS_INCLUDE_TRIAL', False)
    text = funnel._app_idle_text(get_texts('ru'), 'FUNNEL_TRIAL_APP_IDLE', 'Happ')
    assert 'Обход' not in text and 'Нажмите большую кнопку включения\n\nНе получается' in text
