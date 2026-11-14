"""Права удалённых разделов в сохранённой роли не ломают её сохранение.

Bootstrap только добавляет права в роли, поэтому у роли Admin в базе остались
``reachability:*`` и ``dpichecker:*``. Редактор ролей присылает список целиком:
без отбрасывания удалённых разделов сохранение отвечало бы 400.
"""

import pytest

from app.cabinet.routes import admin_roles as m
from app.services.permission_service import PERMISSION_REGISTRY


def test_retired_sections_are_not_in_registry() -> None:
    assert not (m._RETIRED_PERMISSION_SECTIONS & PERMISSION_REGISTRY.keys())


@pytest.mark.parametrize('section', sorted(m._RETIRED_PERMISSION_SECTIONS))
def test_saved_role_with_retired_permission_still_validates(section: str) -> None:
    saved = ['users:*', f'{section}:*', f'{section}:read', 'tickets:read']

    kept = m._drop_retired_permissions(saved)

    assert kept == ['users:*', 'tickets:read']
    m._validate_permissions(kept)


def test_unknown_permission_is_still_rejected() -> None:
    with pytest.raises(m.HTTPException) as error:
        m._validate_permissions(m._drop_retired_permissions(['nosuch:read']))
    assert error.value.status_code == 400
