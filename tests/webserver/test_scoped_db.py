from unittest.mock import AsyncMock

import pytest

from app.webserver import payments


def _fake_get_db(session: AsyncMock):
    async def get_db():
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return get_db


async def test_scoped_db_commits_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    monkeypatch.setattr(payments, 'get_db', _fake_get_db(session))

    async with payments._scoped_db() as db:
        assert db is session

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


async def test_scoped_db_rolls_back_and_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    monkeypatch.setattr(payments, 'get_db', _fake_get_db(session))

    with pytest.raises(RuntimeError, match='boom'):
        async with payments._scoped_db():
            raise RuntimeError('boom')

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
