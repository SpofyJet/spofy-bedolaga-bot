"""Ответ в конкурсах кабинета проверяет сервер, лимит победителей соблюдается.

Раньше для «найди сервер»/«замки» сервер отдавал `secret` клиенту, а победой
считал `idx == secret` из ответа самого клиента: `{"answer": "0_0"}` выигрывал
всегда. `max_winners` не проверялся, приз баланса умножался на 100.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cabinet.routes import contests
from app.services.contest_rotation_service import GAME_QUEST


def _round(secret_idx: int) -> SimpleNamespace:
    template = SimpleNamespace(slug=GAME_QUEST, is_enabled=True, prize_type='balance', prize_value='5000')
    return SimpleNamespace(id=3, template=template, payload={'rows': 3, 'cols': 3, 'secret_idx': secret_idx})


async def _answer(answer: str, *, round_obj, winner_slot: bool = True):
    service = MagicMock()
    service._atomic_winner_check = AsyncMock(side_effect=lambda db, rid, is_winner: is_winner and winner_slot)
    service._award_prize = AsyncMock(return_value='Бонус зачислен!')
    create_attempt = AsyncMock()
    with (
        patch.object(contests, '_resolve_subscription_for_prize', AsyncMock(return_value=object())),
        patch.object(contests, '_user_allowed', return_value=True),
        patch.object(contests, 'get_active_rounds', AsyncMock(return_value=[round_obj])),
        patch.object(contests, 'get_attempt', AsyncMock(return_value=None)),
        patch.object(contests, 'create_attempt', create_attempt),
        patch.object(contests, 'ContestAttemptService', return_value=service),
    ):
        result = await contests.submit_contest_answer(
            round_obj.id,
            contests.ContestAnswerRequest(round_id=round_obj.id, answer=answer),
            user=SimpleNamespace(id=1, language='ru'),
            db=AsyncMock(),
        )
    return result, service, create_attempt


@pytest.mark.asyncio
async def test_self_consistent_answer_no_longer_wins() -> None:
    result, service, _ = await _answer('0_0', round_obj=_round(secret_idx=5))

    assert result.is_winner is False
    service._award_prize.assert_not_awaited()


@pytest.mark.asyncio
async def test_correct_index_wins_regardless_of_client_suffix() -> None:
    result, service, _ = await _answer('5_undefined', round_obj=_round(secret_idx=5))

    assert result.is_winner is True
    service._award_prize.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_prize_when_winner_limit_reached() -> None:
    result, service, create_attempt = await _answer('5_0', round_obj=_round(secret_idx=5), winner_slot=False)

    assert result.is_winner is False
    service._award_prize.assert_not_awaited()
    assert create_attempt.await_args.kwargs['is_winner'] is False


@pytest.mark.asyncio
async def test_game_data_does_not_reveal_secret() -> None:
    round_obj = _round(secret_idx=5)
    with (
        patch.object(contests, '_resolve_subscription_for_prize', AsyncMock(return_value=object())),
        patch.object(contests, '_user_allowed', return_value=True),
        patch.object(contests, 'get_active_rounds', AsyncMock(return_value=[round_obj])),
        patch.object(contests, 'get_attempt', AsyncMock(return_value=None)),
    ):
        game = await contests.get_contest_game(round_obj.id, user=SimpleNamespace(id=1), db=AsyncMock())

    assert 'secret' not in game.game_data
    assert 5 not in game.game_data.values()
