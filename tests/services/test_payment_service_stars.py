"""Тесты для Telegram Stars-сценариев внутри PaymentService."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.services.payment_service import PaymentService


@pytest.fixture
def anyio_backend() -> str:
    """Ограничиваем anyio тесты только бэкендом asyncio."""
    return 'asyncio'


class DummyBot:
    """Минимальная заглушка aiogram.Bot для тестов."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.sent_messages: list[dict[str, Any]] = []

    async def create_invoice_link(self, **kwargs: Any) -> str:
        """Эмулируем создание платежной ссылки и сохраняем параметры вызова."""
        self.calls.append(kwargs)
        return 'https://t.me/invoice/stars'

    async def send_message(self, **kwargs: Any) -> None:
        """Фиксируем отправленные сообщения пользователю."""
        self.sent_messages.append(kwargs)


def _make_service(bot: DummyBot | None) -> PaymentService:
    """Создаёт экземпляр PaymentService без выполнения полного конструктора."""
    service = PaymentService.__new__(PaymentService)  # type: ignore[call-arg]
    service.bot = bot
    # Stars-сервис достаточно обозначить любым truthy-значением.
    service.stars_service = object() if bot else None
    return service


class DummySession:
    """Минимальная заглушка AsyncSession для проверки сценариев Stars."""

    def __init__(self, pending_subscription: 'DummySubscription') -> None:
        self.pending_subscription = pending_subscription
        self.commits: int = 0
        self.refreshed: list[Any] = []

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        class _Result:
            def __init__(self, subscription: 'DummySubscription') -> None:
                self._subscription = subscription

            def scalar_one_or_none(self) -> 'DummySubscription':
                return self._subscription

        return _Result(self.pending_subscription)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj: Any) -> None:
        self.refreshed.append(obj)


class DummySubscription:
    """Упрощённая модель подписки для тестов."""

    def __init__(
        self,
        subscription_id: int,
        *,
        traffic_limit_gb: int = 0,
        device_limit: int = 1,
        period_days: int = 30,
    ) -> None:
        self.id = subscription_id
        self.traffic_limit_gb = traffic_limit_gb
        self.device_limit = device_limit
        self.status = 'pending'
        self.start_date = datetime(2024, 1, 1, tzinfo=UTC)
        self.end_date = self.start_date + timedelta(days=period_days)


class DummyUser:
    """Минимальные данные пользователя для тестов Stars-покупки."""

    def __init__(self, user_id: int = 501, telegram_id: int = 777) -> None:
        self.id = user_id
        self.telegram_id = telegram_id
        self.language = 'ru'
        self.balance_kopeks = 0
        self.has_made_first_topup = False
        self.has_had_paid_subscription = False
        self.promo_group = None
        self.subscription = None


class DummyTransaction:
    """Локальная транзакция, созданная в тестах."""

    def __init__(self, external_id: str, description: str = '') -> None:
        self.external_id = external_id
        self.description = description


class DummySubscriptionService:
    """Заглушка SubscriptionService, запоминающая вызовы."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any]] = []

    async def create_remnawave_user(self, db: Any, subscription: Any) -> object:
        self.calls.append((db, subscription))
        return object()


@pytest.mark.anyio('asyncio')
async def test_create_stars_invoice_calculates_stars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Количество звёзд должно рассчитываться по курсу с округлением вниз и нижним порогом 1."""
    bot = DummyBot()
    service = _make_service(bot)

    monkeypatch.setattr(
        type(settings),
        'get_stars_rate',
        lambda self: 70,
        raising=False,
    )
    monkeypatch.setattr(
        type(settings),
        'format_price',
        lambda self, amount: f'{amount / 100:.0f}₽',
        raising=False,
    )

    result = await service.create_stars_invoice(
        amount_kopeks=14000,
        description='Пополнение',
        payload='custom_payload',
    )

    assert result == 'https://t.me/invoice/stars'
    assert len(bot.calls) == 1
    call = bot.calls[0]
    assert call['title'] == 'Пополнение баланса VPN'
    assert call['payload'] == 'custom_payload'
    prices = call['prices']
    assert len(prices) == 1
    assert prices[0].amount == 2  # 14000 коп. → 140 ₽ → 2 звезды при курсе 70
    assert '≈2 ⭐' in call['description']


@pytest.mark.anyio('asyncio')
async def test_create_stars_invoice_enforces_minimum_star(monkeypatch: pytest.MonkeyPatch) -> None:
    """При слишком маленькой сумме минимум должен составлять 1 звезду."""
    bot = DummyBot()
    service = _make_service(bot)

    monkeypatch.setattr(type(settings), 'get_stars_rate', lambda self: 500, raising=False)
    monkeypatch.setattr(type(settings), 'format_price', lambda self, amount: amount, raising=False)

    await service.create_stars_invoice(
        amount_kopeks=50,  # 0.5 ₽ при курсе 500 => <1 звезды
        description='Микроплатёж',
    )

    prices = bot.calls[0]['prices']
    assert prices[0].amount == 1


@pytest.mark.anyio('asyncio')
async def test_create_stars_invoice_uses_explicit_stars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Если передано значение stars_amount, функция должна использовать его напрямую."""
    bot = DummyBot()
    service = _make_service(bot)

    # При явном указании звёзд курс не запрашивается.
    monkeypatch.setattr(type(settings), 'format_price', lambda self, amount: amount, raising=False)

    await service.create_stars_invoice(
        amount_kopeks=1000,
        description='Оплата подписки',
        stars_amount=5,
    )

    prices = bot.calls[0]['prices']
    assert prices[0].amount == 5
    assert '≈5 ⭐' in bot.calls[0]['description']


@pytest.mark.anyio('asyncio')
async def test_create_stars_invoice_rejects_invalid_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отрицательный или нулевой курс должен приводить к исключению."""
    bot = DummyBot()
    service = _make_service(bot)

    monkeypatch.setattr(type(settings), 'get_stars_rate', lambda self: 0, raising=False)

    with pytest.raises(ValueError, match='Stars rate must be positive'):
        await service.create_stars_invoice(
            amount_kopeks=1000,
            description='Пополнение',
        )


@pytest.mark.anyio('asyncio')
async def test_create_stars_invoice_requires_bot() -> None:
    """Без экземпляра бота и stars_service функция должна отказывать."""
    service = _make_service(bot=None)

    with pytest.raises(ValueError, match='Bot instance required'):
        await service.create_stars_invoice(
            amount_kopeks=1000,
            description='Пополнение',
        )
