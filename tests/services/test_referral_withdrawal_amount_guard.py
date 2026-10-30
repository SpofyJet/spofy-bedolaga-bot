"""Сумма заявки на вывод проверяется в сервисе, а не только при ручном вводе.

Кнопка «Вывести всё» передаёт сумму в callback_data, а её клиент может подменить
(MTProto getBotCallbackAnswer). Заявка на −100 000 ₽ проходила проверку
`amount > available`, и при одобрении `balance -= amount` зачислял деньги.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.database.models import WithdrawalRequestStatus
from app.services.referral_withdrawal_service import ReferralWithdrawalService


def _service(available: int) -> ReferralWithdrawalService:
    service = ReferralWithdrawalService()
    stats = {'available_total': available, 'available_referral': available}
    service.can_request_withdrawal = AsyncMock(return_value=(True, '', stats))
    service.analyze_for_money_laundering = AsyncMock(return_value={'risk_score': 0})
    return service


@pytest.mark.asyncio
@pytest.mark.parametrize('amount', [-10_000_000, 0, 1])
async def test_create_rejects_non_positive_and_below_minimum(amount: int) -> None:
    db = AsyncMock()
    db.add = MagicMock()
    service = _service(available=settings.REFERRAL_WITHDRAWAL_MIN_AMOUNT_KOPEKS * 10)

    request, error = await service.create_withdrawal_request(db, user_id=1, amount_kopeks=amount, payment_details='x')

    assert request is None
    assert error
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_approve_refuses_negative_request() -> None:
    request = SimpleNamespace(id=5, user_id=1, status=WithdrawalRequestStatus.PENDING.value, amount_kopeks=-50_000)
    user = SimpleNamespace(id=1, balance_kopeks=0)
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalar_one_or_none=lambda: request),
            SimpleNamespace(scalar_one_or_none=lambda: user),
        ]
    )

    ok, error = await ReferralWithdrawalService().approve_request(db, request_id=5, admin_id=99)

    assert ok is False
    assert error
    assert user.balance_kopeks == 0
    db.add.assert_not_called()
