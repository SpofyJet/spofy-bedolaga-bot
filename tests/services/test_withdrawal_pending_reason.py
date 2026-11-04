"""«У вас уже есть активная заявка» — с номером, суммой и датой.

Раньше причина была без деталей, а проверка шла после минимальной суммы и
cooldown: сумма активной заявки уже вычтена из доступного, поэтому человек
чаще видел «Минимальная сумма вывода», чем свою заявку.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import settings
from app.database.models import User, WithdrawalRequest, WithdrawalRequestStatus
from app.services.referral_withdrawal_service import ReferralWithdrawalService
from app.utils.timezone import format_local_datetime
from tests.fixtures.sqlite_memory import memory_session


@pytest.mark.asyncio
async def test_pending_request_reason_has_number_amount_and_date(monkeypatch):
    monkeypatch.setattr(type(settings), 'is_referral_withdrawal_enabled', lambda self: True)
    created = datetime.now(UTC) - timedelta(days=2)
    async with memory_session(monkeypatch, [User.__table__, WithdrawalRequest.__table__]) as db:
        db.add(User(id=1, telegram_id=1, language='ru'))
        db.add(
            WithdrawalRequest(
                id=17,
                user_id=1,
                amount_kopeks=150_000,
                status=WithdrawalRequestStatus.PENDING.value,
                created_at=created,
            )
        )
        await db.commit()
        service = ReferralWithdrawalService()
        stats = {'available_total': 0, 'available_referral': 0}

        can_request, reason, _ = await service.can_request_withdrawal(db, 1, stats=stats)

    assert can_request is False
    assert '#17' in reason
    assert settings.format_price(150_000) in reason
    assert format_local_datetime(created, '%d.%m.%Y') in reason


@pytest.mark.asyncio
async def test_without_pending_request_min_amount_reason_stays(monkeypatch):
    monkeypatch.setattr(type(settings), 'is_referral_withdrawal_enabled', lambda self: True)
    async with memory_session(monkeypatch, [User.__table__, WithdrawalRequest.__table__]) as db:
        db.add(User(id=1, telegram_id=1, language='ru'))
        db.add(
            WithdrawalRequest(
                id=3,
                user_id=1,
                amount_kopeks=150_000,
                status=WithdrawalRequestStatus.COMPLETED.value,
                created_at=datetime.now(UTC) - timedelta(days=90),
            )
        )
        await db.commit()

        can_request, reason, _ = await ReferralWithdrawalService().can_request_withdrawal(
            db, 1, stats={'available_total': 0, 'available_referral': 0}
        )

    assert can_request is False
    assert 'Минимальная сумма' in reason
