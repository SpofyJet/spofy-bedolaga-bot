"""История операций: дубли склеиваются по всему списку, страницы не перекрываются и не теряют операции."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.crud.transaction import get_user_history_page
from app.database.models import Base, Transaction, TransactionType, User
from tests.fixtures.sqlite_memory import memory_session


TABLES = list(Base.metadata.sorted_tables)
BASE_TIME = datetime(2026, 11, 1, 12, 0, 30, tzinfo=UTC)


def _transaction(tx_id: int, minutes_ago: int, *, amount: int = 10000, description: str | None = None) -> Transaction:
    return Transaction(
        id=tx_id,
        user_id=1,
        type=TransactionType.DEPOSIT.value,
        amount_kopeks=amount,
        description=description or f'Пополнение {tx_id}',
        created_at=BASE_TIME - timedelta(minutes=minutes_ago),
    )


def _rows() -> list:
    rows: list = [User(id=1, telegram_id=1001, first_name='U', language='ru', status='active')]
    # 23 разные операции, у каждой третьей — дубль в ту же минуту (повторная запись вебхука).
    tx_id = 1
    for index in range(23):
        rows.append(_transaction(tx_id, index, description=f'Операция {index}'))
        tx_id += 1
        if index % 3 == 0:
            rows.append(_transaction(tx_id, index, description=f'Операция {index}'))
            tx_id += 1
    return rows


@pytest.mark.asyncio
async def test_pages_cover_every_operation_once(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        db.add_all(_rows())
        await db.commit()

        seen: list[str] = []
        totals = set()
        for page in (1, 2, 3):
            transactions, total = await get_user_history_page(db, 1, page=page, per_page=10)
            totals.add(total)
            seen.extend(transaction.description for transaction in transactions)
        beyond, _ = await get_user_history_page(db, 1, page=4, per_page=10)

    assert totals == {23}
    assert seen == [f'Операция {index}' for index in range(23)]  # по убыванию даты, без дублей и пропусков
    assert beyond == []


@pytest.mark.asyncio
async def test_same_amount_in_different_minutes_is_not_merged(monkeypatch):
    async with memory_session(monkeypatch, TABLES) as db:
        db.add_all(
            [
                User(id=1, telegram_id=1001, first_name='U', language='ru', status='active'),
                _transaction(1, 0, description='Пополнение'),
                _transaction(2, 5, description='Пополнение'),
            ]
        )
        await db.commit()
        transactions, total = await get_user_history_page(db, 1, page=1, per_page=10)

    assert total == 2
    assert [transaction.id for transaction in transactions] == [1, 2]


def _callback():
    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_handler_shows_pages_and_empty_state_with_buttons(monkeypatch):
    from app.handlers.balance import main as balance_main

    user = SimpleNamespace(id=1, language='ru')
    async with memory_session(monkeypatch, TABLES) as db:
        db.add_all(_rows())
        await db.commit()

        callback = _callback()
        await balance_main.show_balance_history(callback, user, db, page=3)
        text = callback.message.edit_text.await_args.args[0]
        markup = callback.message.edit_text.await_args.kwargs['reply_markup']
        assert 'Операция 22' in text and 'Операция 19' not in text
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        assert 'balance_history_page_2' in callbacks and callbacks[-1] == 'menu_balance'

        empty = _callback()
        await balance_main.show_balance_history(empty, SimpleNamespace(id=2, language='en'), db)
        assert empty.message.edit_text.await_args.args[0] == '📊 No transactions yet'
        markup = empty.message.edit_text.await_args.kwargs['reply_markup']
        assert [button.callback_data for row in markup.inline_keyboard for button in row] == ['menu_balance']


@pytest.mark.parametrize('lang', ['ru', 'en', 'ua', 'zh', 'fa'])
def test_locales_have_history_and_unknown_method_texts(lang):
    import json
    from pathlib import Path

    data = json.loads(Path(f'app/localization/locales/{lang}.json').read_text(encoding='utf-8'))
    for key in ('BALANCE_HISTORY_EMPTY', 'BALANCE_HISTORY_TITLE', 'PAYMENT_METHOD_UNKNOWN'):
        assert data[key]
