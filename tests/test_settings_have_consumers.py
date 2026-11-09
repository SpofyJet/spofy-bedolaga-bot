"""Поля настроек, которые никто не читает, не возвращаются в конфиг и в .env.example."""

from pathlib import Path

from app.config import Settings


REMOVED = (
    'PLATEGA_WEBHOOK_HOST',
    'PLATEGA_WEBHOOK_PORT',
    'WATA_PAYMENT_DESCRIPTION',
    'WATA_WEBHOOK_HOST',
    'WATA_WEBHOOK_PORT',
    'YANDEX_OFFLINE_CONV_START_PREFIX',
    'WEBHOOK_DROP_PENDING_UPDATES',
    'PAY2328_WEBHOOK_HOST',
    'PAY2328_WEBHOOK_PORT',
    'MODEM_ENABLED',
    'MODEM_PRICE_PER_MONTH',
    'MODEM_PERIOD_DISCOUNTS',
)


def test_removed_fields_are_not_in_settings() -> None:
    assert [name for name in REMOVED if name in Settings.model_fields] == []


def test_removed_keys_are_not_in_env_example() -> None:
    example = (Path(__file__).resolve().parents[1] / '.env.example').read_text(encoding='utf-8')
    assert [name for name in REMOVED if f'{name}=' in example] == []


def test_old_env_file_with_removed_keys_still_loads() -> None:
    """На проде эти ключи ещё лежат в .env: лишние переменные не должны ронять запуск."""
    assert Settings.model_config['extra'] == 'ignore'
