"""Истёкший триал нельзя удалить из кабинета.

`is_trial_already_used` считает триал использованным по наличию подписок. Удаление
истёкшего триала через DELETE /cabinet/subscriptions/{id} снимало этот след, и
`POST /cabinet/subscription/trial` выдавал новый триал — сколько угодно раз.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.cabinet.routes.subscription_modules import multi_tariff
from app.database.models import SubscriptionStatus


@pytest.mark.asyncio
async def test_expired_trial_cannot_be_deleted() -> None:
    trial = SimpleNamespace(id=7, is_trial=True, status=SubscriptionStatus.EXPIRED.value)
    delete_record = AsyncMock()

    with (
        patch.object(multi_tariff, 'get_subscription_by_id_for_user', AsyncMock(return_value=trial)),
        patch('app.services.subscription_deletion_service.delete_subscription_record', delete_record),
        pytest.raises(HTTPException) as exc,
    ):
        await multi_tariff.delete_subscription(7, user=SimpleNamespace(id=1), db=AsyncMock())

    assert exc.value.status_code == 400
    delete_record.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_paid_subscription_still_deletable() -> None:
    paid = SimpleNamespace(id=8, is_trial=False, status=SubscriptionStatus.EXPIRED.value)
    delete_record = AsyncMock()

    with (
        patch.object(multi_tariff, 'get_subscription_by_id_for_user', AsyncMock(return_value=paid)),
        patch('app.services.subscription_deletion_service.delete_subscription_record', delete_record),
    ):
        result = await multi_tariff.delete_subscription(8, user=SimpleNamespace(id=1), db=AsyncMock())

    assert result == {'message': 'Subscription deleted'}
    delete_record.assert_awaited_once()
