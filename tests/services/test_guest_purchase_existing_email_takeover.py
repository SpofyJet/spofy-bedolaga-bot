"""Регрессия: покупка на лендинге с чужим email не даёт доступ к чужому аккаунту.

Раньше `_find_or_create_user` находил существующего пользователя по email и,
если у него не было пароля (вход через Google/VK/Discord), генерировал пароль,
клал его открытым текстом в покупку и помечал `is_new_account=True`. Страница
статуса покупки отдавала покупателю этот пароль и `auto_login_token` — любой,
кто знал email жертвы, получал её аккаунт за цену самого дешёвого тарифа.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.guest_purchase_service import _find_or_create_user


def _single_result(user: object) -> SimpleNamespace:
    return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: user))


def _oauth_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=42,
        auth_type='google',
        password_hash=None,
        email_verified=False,
        email_verified_at=None,
        promo_group_id=1,
        referral_code='KEEP',
    )


@pytest.mark.asyncio
async def test_existing_passwordless_user_gets_no_credentials() -> None:
    victim = _oauth_user()
    purchase = SimpleNamespace(cabinet_password=None)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_single_result(victim))

    user, is_new = await _find_or_create_user(db, 'email', 'victim@example.com', purchase=purchase)

    assert user is victim
    assert is_new is False, 'is_new_account=True выдаёт auto_login_token покупателю'
    assert victim.password_hash is None
    assert purchase.cabinet_password is None
    assert victim.email_verified is False, 'покупатель не доказал владение ящиком'


@pytest.mark.asyncio
async def test_concurrent_create_race_gives_no_credentials() -> None:
    """Ветка IntegrityError (пользователь создан параллельно) — то же правило."""
    victim = _oauth_user()
    purchase = SimpleNamespace(cabinet_password=None)

    nested = MagicMock()
    nested.__aenter__ = AsyncMock(return_value=None)
    nested.__aexit__ = AsyncMock(side_effect=IntegrityError('insert', {}, Exception('dup')))

    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=nested)
    db.add = MagicMock()
    db.execute = AsyncMock(side_effect=[_single_result(None), _single_result(victim)])

    with (
        patch('app.services.guest_purchase_service.create_unique_referral_code', AsyncMock(return_value='NEW')),
        patch(
            'app.services.guest_purchase_service._get_or_create_default_promo_group',
            AsyncMock(return_value=SimpleNamespace(id=1)),
        ),
    ):
        user, is_new = await _find_or_create_user(db, 'email', 'victim@example.com', purchase=purchase)

    assert user is victim
    assert is_new is False
    assert victim.password_hash is None
    assert purchase.cabinet_password is None
