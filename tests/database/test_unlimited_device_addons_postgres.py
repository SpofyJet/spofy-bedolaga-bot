"""Adding slots must never replace an already paid unlimited device allowance."""

import pytest


pytestmark = pytest.mark.postgres


@pytest.mark.parametrize('mode', ['classic', 'tariff', 'multi'])
@pytest.mark.parametrize('entry', ['purchase', 'legacy', 'auto', 'telegram_change'])
async def test_unlimited_granted_after_debit_refunds_and_preserves_limit(postgres_database, monkeypatch, mode, entry):
    await test_unlimited_devices_cannot_be_sold_additional_slots(postgres_database, monkeypatch, mode, entry, race=True)


@pytest.mark.parametrize('mode', ['classic', 'tariff', 'multi'])
@pytest.mark.parametrize('entry', ['purchase', 'legacy', 'auto', 'telegram_change'])
async def test_concurrent_device_increase_refunds_with_balanced_ledger(postgres_database, monkeypatch, mode, entry):
    await test_unlimited_devices_cannot_be_sold_additional_slots(
        postgres_database, monkeypatch, mode, entry, race=True, concurrent_limit=10
    )
