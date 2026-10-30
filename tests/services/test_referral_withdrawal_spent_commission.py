"""К выводу доступны только непотраченные реферальные деньги.

Формула `min(кошелёк, заработано - выведено - в ожидании)` не учитывала покупки:
заработал 1000 ₽ → потратил их на подписку → кошелёк пополнился бонусом кампании или
промокодом → эти 1000 ₽ бонусных денег выводились как реферальные. Реплей кошелька
списывает покупки сначала с прочих денег, и поздний бонус потраченное не возвращает.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.database.models import TransactionType
from app.services.referral_withdrawal_service import WITHDRAWAL_TX_DESCRIPTION_PREFIX, ReferralWithdrawalService


REF = TransactionType.REFERRAL_REWARD.value
DEPOSIT = TransactionType.DEPOSIT.value
BUY = TransactionType.SUBSCRIPTION_PAYMENT.value
WITHDRAWAL = TransactionType.WITHDRAWAL.value


def _db(history: list[tuple[str, int, str]]) -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: history))
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('history', 'expected'),
    [
        # Потратил реферальные, потом пришёл бонус — бонус реферальным не становится
        ([(REF, 100_000, ''), (BUY, -100_000, ''), (DEPOSIT, 100_000, 'Бонус по промокоду')], 0),
        # Покупка оплачена своими деньгами — реферальные целы
        ([(DEPOSIT, 50_000, ''), (REF, 10_000, ''), (BUY, -50_000, '')], 10_000),
        # Покупка больше прочих денег — остаток съедает реферальные
        ([(REF, 10_000, ''), (DEPOSIT, 5_000, ''), (BUY, -12_000, '')], 3_000),
        # Старые записи с положительной суммой покупки — тоже списание
        ([(REF, 10_000, ''), (BUY, 4_000, '')], 6_000),
        # Одобренный вывод — из реферальных; админское списание — из прочих
        (
            [
                (REF, 10_000, ''),
                (DEPOSIT, 3_000, ''),
                (WITHDRAWAL, -4_000, f'{WITHDRAWAL_TX_DESCRIPTION_PREFIX} (заявка #1)'),
                (WITHDRAWAL, -3_000, 'Списание администратором'),
            ],
            6_000,
        ),
    ],
)
async def test_unspent_referral_replay(history, expected) -> None:
    assert await ReferralWithdrawalService().get_unspent_referral_amount(_db(history), user_id=1) == expected


def _stats_service(*, earned: int, withdrawn: int, pending: int, unspent: int) -> ReferralWithdrawalService:
    service = ReferralWithdrawalService()
    service.get_total_referral_earnings = AsyncMock(return_value=earned)
    service.get_user_own_deposits = AsyncMock(return_value=0)
    service.get_user_spending = AsyncMock(return_value=0)
    service.get_withdrawn_amount = AsyncMock(return_value=withdrawn)
    service.get_pending_withdrawal_amount = AsyncMock(return_value=pending)
    service.get_unspent_referral_amount = AsyncMock(return_value=unspent)
    return service


@pytest.mark.asyncio
async def test_spent_commission_is_not_withdrawable(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'REFERRAL_WITHDRAWAL_ONLY_REFERRAL_BALANCE', True)
    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(balance_kopeks=100_000))
    service = _stats_service(earned=100_000, withdrawn=0, pending=0, unspent=0)

    stats = await service.get_referral_balance_stats(db, user_id=1)

    assert stats['available_referral'] == 0
    assert stats['available_total'] == 0
    assert stats['referral_spent'] == 100_000


@pytest.mark.asyncio
async def test_pending_request_is_reserved_from_wallet(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'REFERRAL_WITHDRAWAL_ONLY_REFERRAL_BALANCE', True)
    db = AsyncMock()
    # Заявка 2 500 ₽ ещё не списана с кошелька 4 000 ₽
    db.get = AsyncMock(return_value=SimpleNamespace(balance_kopeks=400_000))
    service = _stats_service(earned=1_000_000, withdrawn=500_000, pending=250_000, unspent=400_000)

    stats = await service.get_referral_balance_stats(db, user_id=1)

    assert stats['available_referral'] == 150_000


@pytest.mark.asyncio
async def test_unspent_is_capped_by_recorded_earnings(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'REFERRAL_WITHDRAWAL_ONLY_REFERRAL_BALANCE', True)
    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(balance_kopeks=500_000))
    # Реплей видит больше реферальных денег, чем записано начислений — берём меньшее
    service = _stats_service(earned=300_000, withdrawn=100_000, pending=0, unspent=450_000)

    stats = await service.get_referral_balance_stats(db, user_id=1)

    assert stats['available_referral'] == 200_000
    assert stats['referral_spent'] == 0
