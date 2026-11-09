from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import TransactionType, User
from app.services.subscription_auto_purchase_service import (
    auto_purchase_saved_cart_after_topup,
)
from app.services.subscription_purchase_service import (
    PurchaseDevicesConfig,
    PurchaseOptionsContext,
    PurchasePeriodConfig,
    PurchasePricingResult,
    PurchaseSelection,
    PurchaseServersConfig,
    PurchaseTrafficConfig,
)


@pytest.fixture(autouse=True)
def _grant_cart_topup_intent(monkeypatch):
    """Эти тесты моделируют «пользователь пополнил баланс ради сохранённой корзины»,
    поэтому метку свежего намерения (cart_topup_intent) считаем выставленной.

    Тихая авто-покупка после пополнения теперь срабатывает только при наличии этой
    метки; тест, проверяющий ПРОПУСК без намерения, переопределяет фикстуру явно.
    """
    monkeypatch.setattr('app.database.crud.transaction.emit_transaction_side_effects', AsyncMock())
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.has_topup_intent',
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.clear_topup_intent',
        AsyncMock(),
    )
    # Race guard (cart_sub_id path) also probes recent transactions when
    # updated_at is fresh; empty list means no SUBSCRIPTION_PAYMENT confirmation,
    # so traffic-only updated_at bumps do not block the tests.
    monkeypatch.setattr(
        'app.database.crud.transaction.get_user_transactions',
        AsyncMock(return_value=[]),
    )


class DummyTexts:
    def t(self, key: str, default: str):
        return default

    def format_price(self, value: int) -> str:
        return f'{value / 100:.0f} ₽'


async def test_auto_purchase_saved_cart_after_topup_success(monkeypatch):
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', True)

    user = MagicMock(spec=User)
    user.restriction_subscription = False
    user.id = 42
    user.telegram_id = 4242
    user.balance_kopeks = 200_000
    user.language = 'ru'
    user.subscription = None
    user.get_primary_promo_group = MagicMock(return_value=None)

    cart_data = {
        'period_days': 30,
        'countries': ['ru'],
        'traffic_gb': 0,
        'devices': 1,
    }

    traffic_config = PurchaseTrafficConfig(
        selectable=False,
        mode='fixed',
        options=[],
        default_value=0,
        current_value=0,
    )
    servers_config = PurchaseServersConfig(
        options=[],
        min_selectable=0,
        max_selectable=0,
        default_selection=['ru'],
    )
    devices_config = PurchaseDevicesConfig(
        minimum=1,
        maximum=5,
        default=1,
        current=1,
        price_per_device=0,
        discounted_price_per_device=0,
        price_label='0 ₽',
    )

    period_config = PurchasePeriodConfig(
        id='days:30',
        days=30,
        months=1,
        label='30 дней',
        base_price=100_000,
        base_price_label='1000 ₽',
        base_price_original=100_000,
        base_price_original_label=None,
        discount_percent=0,
        per_month_price=100_000,
        per_month_price_label='1000 ₽',
        traffic=traffic_config,
        servers=servers_config,
        devices=devices_config,
    )

    context = PurchaseOptionsContext(
        user=user,
        subscription=None,
        currency='RUB',
        balance_kopeks=user.balance_kopeks,
        periods=[period_config],
        default_period=period_config,
        period_map={'days:30': period_config},
        server_uuid_to_id={'ru': 1},
        payload={},
    )

    base_pricing = PurchasePricingResult(
        selection=PurchaseSelection(
            period=period_config,
            traffic_value=0,
            servers=['ru'],
            devices=1,
        ),
        server_ids=[1],
        server_prices_for_period=[100_000],
        base_original_total=100_000,
        discounted_total=100_000,
        promo_discount_value=0,
        promo_discount_percent=0,
        final_total=100_000,
        months=1,
        details={'servers_individual_prices': [100_000]},
    )

    class DummyMiniAppService:
        async def build_options(self, db, user):
            return context

        async def calculate_pricing(self, db, ctx, selection):
            return PurchasePricingResult(
                selection=selection,
                server_ids=base_pricing.server_ids,
                server_prices_for_period=base_pricing.server_prices_for_period,
                base_original_total=base_pricing.base_original_total,
                discounted_total=base_pricing.discounted_total,
                promo_discount_value=base_pricing.promo_discount_value,
                promo_discount_percent=base_pricing.promo_discount_percent,
                final_total=base_pricing.final_total,
                months=base_pricing.months,
                details=base_pricing.details,
            )

        async def submit_purchase(self, db, prepared_context, pricing):
            return {
                'subscription': MagicMock(),
                'transaction': MagicMock(),
                'was_trial_conversion': False,
                'message': '🎉 Subscription purchased',
            }

    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.MiniAppSubscriptionPurchaseService',
        DummyMiniAppService,
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.get_user_cart',
        AsyncMock(return_value=cart_data),
    )
    delete_cart_mock = AsyncMock()
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.delete_processed_cart',
        delete_cart_mock,
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.get_texts',
        lambda lang: DummyTexts(),
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.format_period_description',
        lambda days, lang: f'{days} дней',
    )

    admin_service_mock = MagicMock()
    admin_service_mock.send_subscription_purchase_notification = AsyncMock()
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.AdminNotificationService',
        lambda bot: admin_service_mock,
    )
    # Лочим пользователя для расчёта цены (новый сид вместо устаревшего get_user_by_id)
    monkeypatch.setattr(
        'app.database.crud.user.lock_user_for_pricing',
        AsyncMock(return_value=user),
    )
    # Избегаем обращения к фейковому Redis при сканировании per-subscription корзин
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.get_all_subscription_carts',
        AsyncMock(return_value=[]),
    )

    bot = AsyncMock()
    db_session = AsyncMock(spec=AsyncSession)

    result = await auto_purchase_saved_cart_after_topup(db_session, user, bot=bot)

    assert result is True
    delete_cart_mock.assert_awaited_once_with(user.id, cart_data)
    bot.send_message.assert_awaited()
    admin_service_mock.send_subscription_purchase_notification.assert_awaited()


def _prepare_extend_race_guard_scenario(monkeypatch, *, recent_transactions: list):
    """Общий сетап продления с свежим updated_at для тестов race-guard."""
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', True)

    subscription = MagicMock()
    subscription.id = 82
    subscription.is_trial = False
    subscription.status = 'active'
    subscription.end_date = datetime.now(UTC) + timedelta(days=5)
    subscription.updated_at = datetime.now(UTC) - timedelta(seconds=10)  # свежий updated_at
    subscription.tariff_id = 5
    subscription.device_limit = 1
    subscription.traffic_limit_gb = 100
    subscription.connected_squads = ['squad-a']

    user = MagicMock(spec=User)
    user.restriction_subscription = False
    user.id = 820
    user.telegram_id = 820820
    user.balance_kopeks = 200_000
    user.language = 'ru'
    user.subscription = subscription
    user.get_primary_promo_group = MagicMock(return_value=None)
    user.promo_offer_discount_percent = 0
    user.promo_offer_discount_source = None
    user.promo_offer_discount_expires_at = None

    cart_data = {
        'cart_mode': 'extend',
        'subscription_id': subscription.id,
        'period_days': 90,
        'total_price': 50_000,
        'description': 'Продление подписки на 90 дней',
    }

    # Переопределяем autouse-фикстуру: нужны конкретные транзакции, не []
    monkeypatch.setattr(
        'app.database.crud.transaction.get_user_transactions',
        AsyncMock(return_value=recent_transactions),
    )

    subtract_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.subtract_user_balance',
        subtract_mock,
    )

    async def extend_stub(db, current_subscription, days, **kwargs):
        current_subscription.end_date = current_subscription.end_date + timedelta(days=days)
        return current_subscription

    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.extend_subscription',
        extend_stub,
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.create_transaction',
        AsyncMock(return_value=MagicMock()),
    )

    service_mock = MagicMock()
    service_mock.update_remnawave_user = AsyncMock()
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.SubscriptionService',
        lambda: service_mock,
    )

    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.get_user_cart',
        AsyncMock(return_value=cart_data),
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.delete_subscription_cart',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.delete_global_cart_only',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.delete_user_cart',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.get_texts',
        lambda lang: DummyTexts(),
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.format_period_description',
        lambda days, lang: f'{days} дней',
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.format_local_datetime',
        lambda dt, fmt: dt.strftime(fmt) if dt else '',
    )

    admin_service_mock = MagicMock()
    admin_service_mock.send_subscription_extension_notification = AsyncMock()
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.AdminNotificationService',
        lambda bot: admin_service_mock,
    )

    async def fake_with_admin(handler):
        await handler(admin_service_mock)

    monkeypatch.setattr(
        'app.services.subscription_renewal_service.with_admin_notification_service',
        fake_with_admin,
    )
    monkeypatch.setattr(
        'app.database.crud.subscription.get_subscription_by_user_id',
        AsyncMock(return_value=subscription),
    )
    monkeypatch.setattr(
        'app.database.crud.subscription.get_subscription_by_id_for_user',
        AsyncMock(return_value=subscription),
    )
    monkeypatch.setattr(
        'app.database.crud.user.lock_user_for_pricing',
        AsyncMock(return_value=user),
    )

    fresh_pricing = MagicMock()
    fresh_pricing.final_total = 50_000
    fresh_pricing.original_total = 50_000
    monkeypatch.setattr(
        'app.services.pricing_engine.pricing_engine.calculate_renewal_price',
        AsyncMock(return_value=fresh_pricing),
    )
    monkeypatch.setattr(
        'app.utils.promo_offer.get_user_active_promo_discount_percent',
        lambda _user, _tariff_id=None: 0,
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.get_all_subscription_carts',
        AsyncMock(return_value=[]),
    )

    return user, subscription, subtract_mock


async def test_race_guard_fresh_updated_at_without_subscription_payment_allows_purchase(monkeypatch):
    """Свежий updated_at без SUBSCRIPTION_PAYMENT (только deposit) не блокирует автопокупку."""
    deposit = MagicMock()
    deposit.type = TransactionType.DEPOSIT.value
    deposit.created_at = datetime.now(UTC) - timedelta(seconds=5)

    user, _subscription, subtract_mock = _prepare_extend_race_guard_scenario(
        monkeypatch,
        recent_transactions=[deposit],
    )

    result = await auto_purchase_saved_cart_after_topup(
        AsyncMock(spec=AsyncSession, scalar=AsyncMock(return_value=_subscription)),
        user,
        bot=AsyncMock(),
    )

    assert result is True
    subtract_mock.assert_awaited()


async def test_race_guard_fresh_updated_at_with_subscription_payment_skips_purchase(monkeypatch):
    """Свежий updated_at + свежий SUBSCRIPTION_PAYMENT → пропуск автопокупки (защита от двойного списания)."""
    deposit = MagicMock()
    deposit.type = TransactionType.DEPOSIT.value
    deposit.created_at = datetime.now(UTC) - timedelta(seconds=2)

    payment = MagicMock()
    payment.type = TransactionType.SUBSCRIPTION_PAYMENT.value
    payment.created_at = datetime.now(UTC) - timedelta(seconds=15)

    user, _subscription, subtract_mock = _prepare_extend_race_guard_scenario(
        monkeypatch,
        recent_transactions=[deposit, payment],
    )

    result = await auto_purchase_saved_cart_after_topup(
        AsyncMock(spec=AsyncSession, scalar=AsyncMock(return_value=_subscription)),
        user,
        bot=AsyncMock(),
    )

    assert result is False
    subtract_mock.assert_not_awaited()


async def test_auto_purchase_skipped_without_topup_intent(monkeypatch):
    """Без свежего намерения корзина НЕ покупается, даже если она сохранена и
    авто-покупка включена.

    Это и есть фикс «захвата средств подарка»: пополнил ради другого → метки
    нет → старая/сохранённая корзина не трогается.
    """
    monkeypatch.setattr(settings, 'AUTO_PURCHASE_AFTER_TOPUP_ENABLED', True)

    # Переопределяем autouse-фикстуру: свежего намерения НЕТ
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.has_topup_intent',
        AsyncMock(return_value=False),
    )

    cart_data = {
        'period_days': 30,
        'countries': ['ru'],
        'traffic_gb': 0,
        'devices': 1,
        'total_price': 100_000,
    }
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.get_user_cart',
        AsyncMock(return_value=cart_data),
    )
    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.user_cart_service.get_all_subscription_carts',
        AsyncMock(return_value=[]),
    )

    # Если бы дошло до покупки — эта замена поймала бы попытку (и упала бы тест)
    def _boom(*_args, **_kwargs):
        raise AssertionError('submit_purchase must NOT be called without fresh intent')

    monkeypatch.setattr(
        'app.services.subscription_auto_purchase_service.MiniAppSubscriptionPurchaseService',
        _boom,
    )

    user = MagicMock(spec=User)
    user.restriction_subscription = False
    user.id = 555
    user.balance_kopeks = 500_000

    db_session = AsyncMock(spec=AsyncSession)
    result = await auto_purchase_saved_cart_after_topup(db_session, user, bot=AsyncMock())

    assert result is False
