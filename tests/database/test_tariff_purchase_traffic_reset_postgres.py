import pytest


pytestmark = pytest.mark.postgres


class PanelBoundary(BaseException):
    """Inspect persisted state before external panel I/O."""


@pytest.mark.parametrize('flow', ['telegram', 'custom', 'miniapp', 'auto'])
async def test_expired_tariff_renewal_preserves_and_prices_extra_devices(postgres_database, monkeypatch, flow):
    await test_tariff_purchase_uses_same_reset_decision_in_db_and_panel(
        postgres_database, monkeypatch, flow, False, True, False, True, devices=5, expected_price=600
    )
