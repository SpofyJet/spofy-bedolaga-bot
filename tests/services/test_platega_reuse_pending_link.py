"""Повторное нажатие «Карта / СБП» с той же суммой: прежняя живая ссылка вместо нового платежа.

Раньше каждое нажатие создавало новый платёж у Platega; за 30 дней — около 180 повторов,
семь человек оплатили обе ссылки. Теперь недавний (до 10 минут) неоплаченный платёж того же
человека, той же суммы и способа отдаётся снова — если провайдер подтверждает, что он ещё ждёт
оплаты. Код настоящий, база — SQLite, провайдер — заглушка.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.config import settings
from app.database.models import PlategaPayment, User
from app.services.payment_service import PaymentService
from tests.fixtures.sqlite_memory import memory_session


USER_ID = 5
AMOUNT = 35_900
SBP = 2


class _Provider:
    """Platega: создание платежа и запрос его статуса (как у кнопки «Проверить статус»)."""

    def __init__(self, remote_status: str | None = 'PENDING') -> None:
        self.is_configured = True
        self.remote_status = remote_status
        self.created: list[dict[str, Any]] = []
        self.lookups: list[str] = []

    async def create_payment(self, **kwargs: Any) -> dict[str, Any]:
        self.created.append(kwargs)
        number = len(self.created)
        return {
            'transactionId': f'trx-{number}',
            'redirect': f'https://pay.example/{number}',
            'status': 'PENDING',
            'expiresIn': '00:30:00',
        }

    async def get_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        self.lookups.append(transaction_id)
        if self.remote_status is None:
            return None
        return {'id': transaction_id, 'status': self.remote_status}


def _service(provider: _Provider) -> PaymentService:
    service = PaymentService.__new__(PaymentService)
    service.bot = None
    service.platega_service = provider
    return service


@pytest.fixture(autouse=True)
def _platega_settings(monkeypatch):
    monkeypatch.setattr(settings, 'PLATEGA_MIN_AMOUNT_KOPEKS', 10_000, raising=False)
    monkeypatch.setattr(settings, 'PLATEGA_MAX_AMOUNT_KOPEKS', 5_000_000, raising=False)
    monkeypatch.setattr(settings, 'PLATEGA_CURRENCY', 'RUB', raising=False)
    monkeypatch.setattr(settings, 'PLATEGA_RETURN_URL', 'https://bot.example/ok', raising=False)
    monkeypatch.setattr(settings, 'PLATEGA_FAILED_URL', 'https://bot.example/fail', raising=False)


async def _session(monkeypatch):
    return memory_session(monkeypatch, [User.__table__, PlategaPayment.__table__])


async def _seed_user(db) -> None:
    db.add(User(id=USER_ID, telegram_id=500500, first_name='U', status='active', language='ru'))
    await db.commit()


async def _press(service: PaymentService, db, *, amount: int = AMOUNT, method: int = SBP) -> dict[str, Any]:
    """Как в обработчике: сначала прежняя живая ссылка, иначе новый платёж."""
    found = await service.find_reusable_platega_payment(
        db, user_id=USER_ID, amount_kopeks=amount, payment_method_code=method
    )
    return found or await service.create_platega_payment(
        db=db,
        user_id=USER_ID,
        amount_kopeks=amount,
        description='Пополнение баланса',
        language='ru',
        payment_method_code=method,
    )


@pytest.mark.asyncio
async def test_second_press_gets_the_same_live_link(monkeypatch):
    provider = _Provider('PENDING')
    service = _service(provider)
    async with await _session(monkeypatch) as db:
        await _seed_user(db)
        first = await _press(service, db)
        second = await _press(service, db)
        rows = list((await db.execute(select(PlategaPayment))).scalars().all())

    assert len(provider.created) == 1, 'у провайдера один платёж, а не два'
    assert second['redirect_url'] == first['redirect_url']
    assert second['local_payment_id'] == first['local_payment_id']
    assert second['transaction_id'] == 'trx-1', 'вебхук найдёт ту же строку по transaction_id — зачисление прежнее'
    assert provider.lookups == ['trx-1'], 'живость ссылки проверена у провайдера'
    assert len(rows) == 1


@pytest.mark.parametrize('remote_status', ['CANCELED', 'EXPIRED', 'FAILED', None], ids=str)
@pytest.mark.asyncio
async def test_dead_or_unknown_link_is_replaced_by_a_new_payment(monkeypatch, remote_status):
    """Провайдер отменил платёж (или не ответил) — новый платёж, как раньше."""
    provider = _Provider(remote_status)
    service = _service(provider)
    async with await _session(monkeypatch) as db:
        await _seed_user(db)
        first = await _press(service, db)
        second = await _press(service, db)

    assert len(provider.created) == 2
    assert second['redirect_url'] != first['redirect_url']


@pytest.mark.asyncio
async def test_paid_link_is_not_handed_out_again(monkeypatch):
    provider = _Provider('PENDING')
    service = _service(provider)
    async with await _session(monkeypatch) as db:
        await _seed_user(db)
        first = await _press(service, db)
        payment = await db.get(PlategaPayment, first['local_payment_id'])
        payment.is_paid = True
        payment.status = 'CONFIRMED'
        await db.commit()

        await _press(service, db)

    assert len(provider.created) == 2
    assert provider.lookups == [], 'оплаченный платёж даже не проверяем'


@pytest.mark.parametrize(
    'change',
    [
        pytest.param({'amount': AMOUNT + 10_000}, id='другая-сумма'),
        pytest.param({'method': 11}, id='другой-способ'),
    ],
)
@pytest.mark.asyncio
async def test_other_amount_or_method_gets_its_own_payment(monkeypatch, change):
    provider = _Provider('PENDING')
    service = _service(provider)
    async with await _session(monkeypatch) as db:
        await _seed_user(db)
        await _press(service, db)
        await _press(service, db, **change)

    assert len(provider.created) == 2
    assert provider.lookups == []


@pytest.mark.parametrize(
    'aged',
    [
        pytest.param({'created_at': datetime.now(UTC) - timedelta(minutes=11)}, id='старше-10-минут'),
        pytest.param({'expires_at': datetime.now(UTC) + timedelta(minutes=5)}, id='скоро-истекает'),
        pytest.param({'return_url': 'https://cabinet.example/ok'}, id='платёж-кабинета'),
        pytest.param({'metadata_json': {'purchase_token': 'gift'}}, id='покупка-гостя'),
    ],
)
@pytest.mark.asyncio
async def test_old_expiring_or_foreign_payment_is_not_reused(monkeypatch, aged):
    """Кто вернулся по напоминанию на 10-й минуте, получает новую ссылку — как раньше."""
    provider = _Provider('PENDING')
    service = _service(provider)
    async with await _session(monkeypatch) as db:
        await _seed_user(db)
        first = await _press(service, db)
        payment = await db.get(PlategaPayment, first['local_payment_id'])
        for field, value in aged.items():
            setattr(payment, field, value)
        await db.commit()

        await _press(service, db)

    assert len(provider.created) == 2
    assert provider.lookups == []


@pytest.mark.asyncio
async def test_handler_shows_the_reused_link_without_creating(monkeypatch):
    import app.handlers.balance.platega as module

    reused = {
        'local_payment_id': 9,
        'transaction_id': 'trx-1',
        'redirect_url': 'https://pay.example/1',
        'reused': True,
    }
    service = SimpleNamespace(
        find_reusable_platega_payment=AsyncMock(return_value=reused),
        create_platega_payment=AsyncMock(),
    )
    monkeypatch.setattr(type(settings), 'is_platega_enabled', lambda self: True)
    monkeypatch.setattr(module, '_get_active_methods', lambda: [SBP])
    monkeypatch.setattr(module, 'PaymentService', lambda bot: service)
    monkeypatch.setattr('app.services.payment_service.get_platega_payment_by_id', AsyncMock(return_value=None))
    user = SimpleNamespace(id=USER_ID, language='ru', telegram_id=500500, restriction_topup=False)
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={'platega_method': SBP}),
        clear=AsyncMock(),
        set_state=AsyncMock(),
        update_data=AsyncMock(),
    )
    message = MagicMock()
    message.answer = AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(id=1), message_id=2))
    message.delete = AsyncMock()
    message.chat = SimpleNamespace(id=1)

    await module.process_platega_payment_amount(message, user, MagicMock(), AMOUNT, state)

    service.create_platega_payment.assert_not_awaited()
    keyboard = message.answer.await_args.kwargs['reply_markup']
    assert keyboard.inline_keyboard[0][0].url == 'https://pay.example/1'
    assert keyboard.inline_keyboard[1][0].callback_data == 'check_platega_9'
