"""Права журнала системных ошибок должны быть в PERMISSION_REGISTRY.

``require_permission('system_errors:read')`` работает и без регистрации — проверка
идёт по строке. Реестр — единый список прав кабинета, по нему сверяются роли
из bootstrap.

Ратчет на каждое право, которое проверяют роуты кабинета: тот же класс промаха,
что был у ``users:send_message`` и ``coupons:*``.
"""

import re
from pathlib import Path

import pytest

from app.services.permission_service import PERMISSION_REGISTRY, get_all_permissions
from app.services.rbac_bootstrap_service import _PRESET_ROLES


SYSTEM_ERROR_PERMISSIONS = ('system_errors:read', 'system_errors:manage')


def test_section_is_registered():
    assert 'system_errors' in PERMISSION_REGISTRY


@pytest.mark.parametrize('permission', SYSTEM_ERROR_PERMISSIONS)
def test_permission_is_registered(permission):
    assert permission in get_all_permissions()


def test_every_permission_required_by_cabinet_routes_is_registered():
    """Ратчет: право, проверяемое роутом, но не заведённое в реестре, не выдать никому."""
    used: set[str] = set()
    for path in Path('app/cabinet/routes').rglob('*.py'):
        used |= set(re.findall(r"require_permission\(\s*'([a-z_]+:[a-z_*]+)'", path.read_text()))

    known = set(get_all_permissions()) | {f'{section}:*' for section in PERMISSION_REGISTRY} | {'*:*'}
    assert not (used - known), f'права проверяются, но не заведены в PERMISSION_REGISTRY: {sorted(used - known)}'


def test_bootstrap_roles_only_grant_registered_permissions():
    """То же с другой стороны: роль из bootstrap раздаёт только права из реестра."""
    known = set(get_all_permissions()) | {f'{section}:*' for section in PERMISSION_REGISTRY} | {'*:*'}

    for role in _PRESET_ROLES:
        unknown = set(role.get('permissions', [])) - known
        assert not unknown, f'роль {role.get("name")} раздаёт незарегистрированные права: {sorted(unknown)}'
