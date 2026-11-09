"""Проверяем, что PaymentService собирается из mixin-классов."""

import sys
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.payment import (
    CryptoBotPaymentMixin,
    Pay2328PaymentMixin,
    PaymentCommonMixin,
    TelegramStarsMixin,
    WataPaymentMixin,
)
from app.services.payment.platega import PlategaPaymentMixin
from app.services.payment_service import PaymentService


@pytest.mark.parametrize(
    'attribute',
    [
        'build_topup_success_keyboard',
        'create_stars_invoice',
        'create_cryptobot_payment',
        'create_pay2328_payment',
        'create_wata_payment',
    ],
)
def test_payment_service_exposes_provider_methods(attribute: str) -> None:
    """Каждый mixin обязан добавить публичный метод в PaymentService."""
    assert hasattr(PaymentService, attribute), f'Отсутствует метод {attribute}'


def test_payment_service_mro_contains_all_mixins() -> None:
    """Убеждаемся, что сервис действительно включает все mixin-классы."""
    mixins = {
        PaymentCommonMixin,
        TelegramStarsMixin,
        PlategaPaymentMixin,
        CryptoBotPaymentMixin,
        Pay2328PaymentMixin,
        WataPaymentMixin,
    }
    service_mro = set(PaymentService.__mro__)
    assert mixins.issubset(service_mro), 'PaymentService должен содержать все mixin-классы'
