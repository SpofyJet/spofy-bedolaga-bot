"""Пакет с mixin-классами, делающими платёжный сервис модульным.

Здесь собираем все вспомогательные части, чтобы основной `PaymentService`
оставался компактным и импортировал только нужные компоненты.
"""

from .common import PaymentCommonMixin
from .cryptobot import CryptoBotPaymentMixin
from .pay2328 import Pay2328PaymentMixin
from .platega import PlategaPaymentMixin
from .stars import TelegramStarsMixin
from .wata import WataPaymentMixin
from .xrocket import XRocketPaymentMixin


__all__ = [
    'CryptoBotPaymentMixin',
    'Pay2328PaymentMixin',
    'PaymentCommonMixin',
    'PlategaPaymentMixin',
    'TelegramStarsMixin',
    'WataPaymentMixin',
    'XRocketPaymentMixin',
]
