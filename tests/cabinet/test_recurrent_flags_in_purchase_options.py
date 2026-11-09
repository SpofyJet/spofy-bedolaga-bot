"""Признак «автооплата включена» кабинет получает в обоих режимах продаж.

Кабинет спрашивал состояние автооплаты СБП и Lava у каждой подписки и по ответу
403 «disabled» понимал, что фича выключена. В консоли браузера каждый такой
ответ — красная строка с полным стеком, а на странице сохранённых карт их
столько, сколько у человека подписок.

Признак есть в опциях покупки, но только в тарифном режиме — в классическом
кабинету нечем гейтить запрос. Флаг относится к системе, а не к режиму продаж,
поэтому обязан приезжать в обоих.
"""

from __future__ import annotations

import pytest

from app.cabinet.routes.subscription_modules import purchase as purchase_routes


RECURRENT_FLAGS = ('platega_recurrent_enabled',)


class _StubUser:
    id = 1
    balance_kopeks = 0
    language = 'ru'


@pytest.fixture
def stub_purchase_service(monkeypatch):
    """Классическая ветка строит ответ сервисом — подменяем его целиком."""

    class _Context:
        payload: dict = {'periods': [], 'balance_kopeks': 0}

    async def _build_options(db, user, subscription_id=None):
        return _Context()

    monkeypatch.setattr(purchase_routes.purchase_service, 'build_options', _build_options)
