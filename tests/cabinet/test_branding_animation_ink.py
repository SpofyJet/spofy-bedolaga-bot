"""Анимированный фон кабинета с 15.11.2026 один — «чернила».

Кабинет больше не умеет 20 прежних эффектов: админка сохраняет только 'ink' или
'none'. GET отдаёт сохранённое как есть — старое значение (boxes) кабинет читает как
'ink', а вкладкам со старым кабинетом неизвестный тип включил бы их запасной aurora.
"""

import pytest
from pydantic import ValidationError

from app.cabinet.routes.branding import DEFAULT_ANIMATION_CONFIG, AnimationConfigResponse, AnimationConfigUpdate


def test_update_accepts_only_ink_or_none() -> None:
    assert AnimationConfigUpdate(type='ink', enabled=True, opacity=0.8).type == 'ink'
    assert AnimationConfigUpdate(type='none').type == 'none'
    assert AnimationConfigUpdate(enabled=False).type is None  # частичное обновление
    with pytest.raises(ValidationError):
        AnimationConfigUpdate(type='aurora')


def test_stored_legacy_config_is_returned_as_is() -> None:
    stored = {'enabled': False, 'type': 'boxes', 'settings': {'rows': 20}, 'opacity': 0.1, 'blur': 0.0}
    assert AnimationConfigResponse(**stored).type == 'boxes'


def test_default_is_ink_and_off() -> None:
    assert DEFAULT_ANIMATION_CONFIG['type'] == 'ink'
    assert DEFAULT_ANIMATION_CONFIG['enabled'] is False
