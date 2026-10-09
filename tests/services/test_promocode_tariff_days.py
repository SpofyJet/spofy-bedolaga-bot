"""Промокод на дни с тарифом: выдаёт именно этот тариф, но не понижает человека."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.database.crud import server_squad, subscription as sub_crud, tariff as tariff_crud
from app.database.models import PromoCodeType
from app.services import promocode_service as module


BYPASS = SimpleNamespace(id=3, is_active=True, tier_level=2, traffic_limit_gb=100, device_limit=3, allowed_squads=['b'])
ULTIMA = SimpleNamespace(id=4, is_active=True, tier_level=10, traffic_limit_gb=0, device_limit=5, allowed_squads=['b'])
STANDARD = SimpleNamespace(id=2, is_active=True, tier_level=1, traffic_limit_gb=0, device_limit=3, allowed_squads=['a'])


def _code(tariff_id=3, kind=PromoCodeType.SUBSCRIPTION_DAYS.value):
    return SimpleNamespace(type=kind, tariff_id=tariff_id, subscription_days=730, code='X')


def _sub(tariff_id, *, trial=False, status='active', days_left=10):
    return SimpleNamespace(
        id=1, tariff_id=tariff_id, is_trial=trial, status=status, days_left=days_left,
        end_date=datetime.now(UTC) + timedelta(days=days_left),
    )  # fmt: skip


@pytest.fixture
def env(monkeypatch):
    tariffs = {2: STANDARD, 3: BYPASS, 4: ULTIMA}
    calls = SimpleNamespace(
        create=AsyncMock(return_value=_sub(3)),
        replace=AsyncMock(return_value=_sub(3)),
        extend=AsyncMock(),
        current=None,
    )
    monkeypatch.setattr(settings, 'MULTI_TARIFF_ENABLED', False, raising=False)
    monkeypatch.setattr(tariff_crud, 'get_tariff_by_id', AsyncMock(side_effect=lambda _db, tid: tariffs.get(tid)))
    monkeypatch.setattr(server_squad, 'get_effective_tariff_squad_uuids', AsyncMock(return_value=['b']))
    monkeypatch.setattr(sub_crud, 'create_paid_subscription', calls.create)
    monkeypatch.setattr(sub_crud, 'replace_subscription', calls.replace)
    monkeypatch.setattr(module, 'extend_subscription', calls.extend)
    monkeypatch.setattr(module, 'get_subscription_by_user_id', AsyncMock(side_effect=lambda *_: calls.current))
    service = module.PromoCodeService.__new__(module.PromoCodeService)
    service.subscription_service = MagicMock(sync_remnawave_user=AsyncMock())
    return service, calls


async def test_plain_days_code_has_no_tariff(env):
    service, _ = env
    assert await service._tariff_for_days(None, _code(tariff_id=None)) is None
    assert await service._tariff_for_days(None, _code(kind=PromoCodeType.BALANCE.value)) is None
    assert await service._tariff_for_days(None, _code()) is BYPASS


async def test_user_without_subscription_gets_the_tariff(env):
    service, calls = env
    await service._grant_tariff_days(None, SimpleNamespace(id=7), _code(), BYPASS)
    kwargs = calls.create.await_args.kwargs
    assert (kwargs['tariff_id'], kwargs['duration_days'], kwargs['is_trial']) == (3, 730, False)
    assert kwargs['traffic_limit_gb'] == 100
    service.subscription_service.sync_remnawave_user.assert_awaited_once()


async def test_live_trial_is_converted_and_keeps_remaining_days(env):
    service, calls = env
    calls.current = _sub(2, trial=True, status='trial', days_left=2)
    await service._grant_tariff_days(None, SimpleNamespace(id=7), _code(), BYPASS)
    kwargs = calls.replace.await_args.kwargs
    assert kwargs['duration_days'] == 732 and kwargs['tariff_id'] == 3 and kwargs['is_trial'] is False


async def test_expired_subscription_does_not_carry_days(env):
    service, calls = env
    calls.current = _sub(2, status='expired', days_left=0)
    await service._grant_tariff_days(None, SimpleNamespace(id=7), _code(), BYPASS)
    assert calls.replace.await_args.kwargs['duration_days'] == 730


async def test_same_tariff_is_just_extended(env):
    service, calls = env
    calls.current = _sub(3)
    await service._grant_tariff_days(None, SimpleNamespace(id=7), _code(), BYPASS)
    calls.extend.assert_awaited_once()
    calls.replace.assert_not_awaited()
    calls.create.assert_not_awaited()


async def test_higher_tariff_is_never_downgraded(env):
    service, calls = env
    calls.current = _sub(4)  # ULTIMA
    result = await service._grant_tariff_days(None, SimpleNamespace(id=7), _code(), BYPASS)
    assert result.tariff_id == 4
    calls.extend.assert_awaited_once()
    calls.replace.assert_not_awaited()


async def test_lower_paid_tariff_is_upgraded(env):
    service, calls = env
    calls.current = _sub(2, days_left=30)
    await service._grant_tariff_days(None, SimpleNamespace(id=7), _code(), BYPASS)
    assert calls.replace.await_args.kwargs['duration_days'] == 760
