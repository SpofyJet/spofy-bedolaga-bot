from decimal import Decimal

import pytest

from app.config import settings


@pytest.mark.parametrize(
    ('rubles', 'kopeks'),
    [
        (19.99, 1999),
        (1.15, 115),
        (1150.55, 115055),
        ('0.01', 1),
        (Decimal('149.90'), 14990),
        (500, 50000),
        (-19.99, -1999),
    ],
)
def test_rubles_to_kopeks_has_no_float_error(rubles, kopeks) -> None:
    assert settings.rubles_to_kopeks(rubles) == kopeks


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf')])
def test_rubles_to_kopeks_rejects_non_finite_amounts(value: float) -> None:
    with pytest.raises(ValueError):
        settings.rubles_to_kopeks(value)
