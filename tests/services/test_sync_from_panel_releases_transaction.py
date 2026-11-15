"""Импорт из панели не держит транзакцию базы, пока грузит панель, и после сбоя
отдаёт сессию чистой.

Тот же класс дефекта, что в проходе «в панель» (0715b5c7). Из кабинета и из бота
сессия приходит с уже открытой транзакцией (авторизация, middleware), и всё время
выгрузки панели — страницы по 500, паузы по 429 на минуты — соединение простаивает
в транзакции, пока база его не закроет. Первое чтение после выгрузки падало,
импорт молча отдавал errors=1, а сессия оставалась в невалидной транзакции — и
следующие шаги полной синхронизации («в панель», серверы) падали уже на ней.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import DBAPIError

from app.services.remnawave_service import RemnaWaveService


EMPTY_PANEL_PAGE = {'users': [], 'hasMore': False, 'nextCursor': None}


def _empty_result() -> SimpleNamespace:
    return SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=list),
        scalar_one_or_none=lambda: None,
    )


def _connection_lost() -> DBAPIError:
    return DBAPIError('SELECT 1', {}, Exception('the underlying connection is closed'))


@pytest.fixture
def events() -> list[str]:
    return []


@pytest.fixture
def db(events) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_empty_result())

    async def commit() -> None:
        events.append('commit')

    async def rollback() -> None:
        events.append('rollback')

    session.commit = AsyncMock(side_effect=commit)
    session.rollback = AsyncMock(side_effect=rollback)
    return session


@pytest.fixture
def service(monkeypatch, events) -> RemnaWaveService:
    api = AsyncMock()

    async def load_page(**_kwargs):
        events.append('panel')
        return EMPTY_PANEL_PAGE

    api.get_all_users_page_stream = AsyncMock(side_effect=load_page)

    svc = RemnaWaveService()
    svc._config_error = None

    @asynccontextmanager
    async def fake_client():
        yield api

    monkeypatch.setattr(svc, 'get_api_client', fake_client)
    return svc


@pytest.mark.asyncio
async def test_import_releases_callers_transaction_before_loading_panel(monkeypatch, service, db, events):

    await service.sync_users_from_panel(db, 'all')

    assert events[:2] == ['commit', 'panel'], (
        f'транзакцию, которую сессия принесла от вызывающего, закрываем ДО выгрузки панели: порядок событий {events}'
    )


@pytest.mark.asyncio
async def test_import_rolls_back_after_failure_so_session_stays_usable(monkeypatch, service, db, events):
    db.execute = AsyncMock(side_effect=_connection_lost())

    stats = await service.sync_users_from_panel(db, 'all')

    assert stats['errors'] == 1
    assert 'rollback' in events, f'после сбоя сессию надо откатить, иначе следующий шаг синхронизации упадёт: {events}'
    assert events.index('rollback') > events.index('panel')
