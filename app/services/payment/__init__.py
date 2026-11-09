"""Пакет с mixin-классами, делающими платёжный сервис модульным.

Здесь собираем все вспомогательные части, чтобы основной `PaymentService`
оставался компактным и импортировал только нужные компоненты.
"""

from .common import PaymentCommonMixin
from .cryptobot import CryptoBotPaymentMixin
from .heleket import HeleketPaymentMixin
from .platega import PlategaPaymentMixin
from .stars import TelegramStarsMixin
from .wata import WataPaymentMixin
from .xrocket import XRocketPaymentMixin


__all__ = [
    'CryptoBotPaymentMixin',
    'HeleketPaymentMixin',
    'PaymentCommonMixin',
    'PlategaPaymentMixin',
    'TelegramStarsMixin',
    'WataPaymentMixin',
    'XRocketPaymentMixin',
]
