import pytest

from app.config import settings
from app.database.models import Base
from app.keyboards.inline import get_payment_methods_keyboard
from app.services import payment_method_config_service as service
from tests.fixtures.postgres_db import postgres_session


pytestmark = [pytest.mark.postgres, pytest.mark.asyncio]


async def test_saved_names_order_and_reset_reach_telegram_without_restart(postgres_database, monkeypatch):
    monkeypatch.setattr(service, '_display_name_overrides', {})
    monkeypatch.setattr(service, '_display_sort_orders', {})
    monkeypatch.setattr(settings, 'TELEGRAM_STARS_ENABLED', True)
    monkeypatch.setattr(settings, 'PLATEGA_SBP_ENABLED', True)
    monkeypatch.setattr(type(settings), 'is_platega_enabled', lambda self: True)

    def buttons():
        return {
            button.callback_data: button.text
            for row in get_payment_methods_keyboard(12345, 'ru').inline_keyboard
            for button in row
            if button.callback_data
            in {
                'topup_amount|stars|12345',
                'topup_amount|platega|12345',
            }
        }

    async with postgres_session(postgres_database, list(Base.metadata.sorted_tables)) as db:
        await db.commit()
        await service.refresh_display_name_overrides(db)
        assert next(iter(buttons())) == 'topup_amount|stars|12345'
        await service.update_config(db, 'platega', {'display_name': 'Gateway'})
        await service.update_config(db, 'telegram_stars', {'display_name': 'Custom Stars'})
        current = buttons()
        assert list(current) == [
            'topup_amount|platega|12345',
            'topup_amount|platega|12345',
            'topup_amount|stars|12345',
        ]
        assert current['topup_amount|platega|12345'] == '🏦 Оплата по СБП (Gateway)'
        assert current['topup_amount|platega|12345'] == '💳 Банковская карта (Gateway)'
        assert current['topup_amount|stars|12345'] == 'Custom Stars'
        await service.update_config(db, 'platega', {'display_name': None})
        reset = buttons()
        assert list(reset) == list(current)
        assert 'Gateway' not in str(reset)
        assert reset['topup_amount|platega|12345'] == '💳 Банковская карта (Platega)'
