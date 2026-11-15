"""Резолверы аккаунта панели для экрана устройств (бот и кабинет).

API 3.0.0: панельный пользователь адресуется числовым `remnawave_id`, а не UUID.
Резолверы обязаны отдавать именно id — легаси-колонка `remnawave_uuid` осталась
в БД как исторические данные и читаться не должна (иначе клиент получит мусорный
идентификатор и запрос отвалится валидацией на границе, а не 404).
"""

from __future__ import annotations

from app.cabinet.routes.subscription_modules.devices import _resolve_panel_user_id
from app.handlers.subscription.devices import _get_panel_user_id


USER_PANEL_ID = 101
SUB_B_PANEL_ID = 202


class _Obj:
    """Носитель панельной привязки: числовой id 3.0.0 + легаси-uuid-ловушка."""

    def __init__(self, panel_id: int | None, legacy_uuid: str = 'legacy-uuid-must-not-be-read'):
        self.remnawave_id = panel_id
        self.remnawave_uuid = legacy_uuid


# ---- bot handler: _get_panel_user_id ----


def test_bot_single_tariff_falls_back_to_user():
    assert _get_panel_user_id(_Obj(None), _Obj(USER_PANEL_ID)) == USER_PANEL_ID


def test_bot_no_subscription_uses_user_panel_id():
    assert _get_panel_user_id(None, _Obj(USER_PANEL_ID)) == USER_PANEL_ID


def test_bot_never_returns_legacy_uuid():
    """Пустой remnawave_id не должен подмениться легаси-uuid'ом ни в одном режиме."""
    resolved = _get_panel_user_id(_Obj(None), _Obj(None))
    assert resolved is None, f'резолвер вернул {resolved!r} вместо None'


# ---- cabinet route: _resolve_panel_user_id ----


def test_cabinet_single_tariff_uses_user_panel_id():
    assert _resolve_panel_user_id(_Obj(None), _Obj(USER_PANEL_ID)) == USER_PANEL_ID


def test_cabinet_no_subscription_uses_user_panel_id():
    assert _resolve_panel_user_id(None, _Obj(USER_PANEL_ID)) == USER_PANEL_ID


def test_cabinet_never_returns_legacy_uuid():
    resolved = _resolve_panel_user_id(_Obj(None), _Obj(None))
    assert resolved is None, f'резолвер вернул {resolved!r} вместо None'
