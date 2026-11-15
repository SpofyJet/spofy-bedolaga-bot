import pytest

from app.config import settings
from app.database.models import Base, PaymentMethodConfig
from app.keyboards.inline import get_payment_methods_keyboard
from app.services import payment_method_config_service as service
from tests.fixtures.postgres_db import postgres_session


pytestmark = [pytest.mark.postgres, pytest.mark.asyncio]


async def test_saved_names_order_and_reset_reach_telegram_without_restart(postgres_database, monkeypatch):
    monkeypatch.setattr(service, '_display_name_overrides', {})
    monkeypatch.setattr(service, '_display_sort_orders', {})
    monkeypatch.setattr(settings, 'TELEGRAM_STARS_ENABLED', True)
    monkeypatch.setattr(settings, 'PLATEGA_ACTIVE_METHODS', '2,11')
    monkeypatch.setattr(settings, 'PLATEGA_INLINE_METHODS', True)
    monkeypatch.setattr(type(settings), 'is_platega_enabled', lambda self: True)
    monkeypatch.setattr(type(settings), 'is_xrocket_enabled', lambda self: True)

    def buttons():
        return {
            button.callback_data: button.text
            for row in get_payment_methods_keyboard(12345, 'ru').inline_keyboard
            for button in row
            if (button.callback_data or '').startswith('topup_amount|')
        }

    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        db.add_all(
            [
                PaymentMethodConfig(method_id='platega', sort_order=0),
                PaymentMethodConfig(method_id='telegram_stars', sort_order=1),
                PaymentMethodConfig(method_id='xrocket', sort_order=2),
            ]
        )
        await db.commit()
        await service.refresh_display_name_overrides(db)
        default = buttons()
        assert list(default) == [
            'topup_amount|platega_m2|12345',
            'topup_amount|platega_m11|12345',
            'topup_amount|stars|12345',
            'topup_amount|xrocket|12345',
        ]

        await service.update_config(db, 'xrocket', {'display_name': 'Gateway'})
        await service.update_config(db, 'telegram_stars', {'display_name': 'Custom Stars'})
        await service.update_config(db, 'platega', {'display_name': 'Platega Custom'})
        await service.update_sort_order(db, ['xrocket', 'telegram_stars', 'platega'])
        current = buttons()
        # Встроенные методы Platega наследуют порядок родителя и идут подряд.
        assert list(current) == [
            'topup_amount|xrocket|12345',
            'topup_amount|stars|12345',
            'topup_amount|platega_m2|12345',
            'topup_amount|platega_m11|12345',
        ]
        assert current['topup_amount|xrocket|12345'] == 'Gateway'
        assert current['topup_amount|stars|12345'] == 'Custom Stars'
        # Имя родителя на встроенные методы не переносится: у каждого своё название.
        assert current['topup_amount|platega_m2|12345'] == default['topup_amount|platega_m2|12345']
        assert current['topup_amount|platega_m11|12345'] == default['topup_amount|platega_m11|12345']

        await service.update_config(db, 'xrocket', {'display_name': None})
        reset = buttons()
        assert list(reset) == list(current)
        assert 'Gateway' not in str(reset)
        assert reset['topup_amount|xrocket|12345'] == default['topup_amount|xrocket|12345']
        assert reset['topup_amount|stars|12345'] == 'Custom Stars'
