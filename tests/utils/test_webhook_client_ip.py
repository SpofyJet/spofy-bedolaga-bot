import pytest

from app.config import settings
from app.utils.webhook_client_ip import resolve_webhook_client_ip


ALLOWED_IP = '185.71.76.10'


@pytest.mark.parametrize(
    ('remote', 'expected'),
    (
        ('185.71.76.10', '185.71.76.10'),  # публичный peer — отправитель он сам
        ('8.8.8.8', '8.8.8.8'),  # заголовки от публичного peer не читаются
        ('10.0.0.5', '185.71.76.10'),  # локальный прокси дописал peer в X-Forwarded-For
        (None, None),  # peer неизвестен — отказ, а не доверие заголовкам
    ),
)
def test_resolve_webhook_client_ip_trust_rules(remote: str | None, expected: str | None) -> None:
    ip_object = resolve_webhook_client_ip(remote, forwarded_for=ALLOWED_IP, cf_connecting_ip=ALLOWED_IP)

    assert (str(ip_object) if ip_object is not None else None) == expected


def test_resolve_webhook_client_ip_prefers_last_forwarded_candidate() -> None:
    ip_object = resolve_webhook_client_ip('10.0.0.5', forwarded_for='185.71.76.10, 8.8.8.8')

    assert ip_object is not None
    assert str(ip_object) == '8.8.8.8'


def test_resolve_webhook_client_ip_accepts_allowed_last_forwarded_candidate() -> None:
    ip_object = resolve_webhook_client_ip('10.0.0.5', forwarded_for=f'8.8.8.8, {ALLOWED_IP}')

    assert ip_object is not None
    assert str(ip_object) == ALLOWED_IP


def test_resolve_webhook_client_ip_skips_trusted_proxy_hops(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'WEBHOOK_TRUSTED_PROXY_NETWORKS', '203.0.113.0/24', raising=False)

    ip_object = resolve_webhook_client_ip('10.0.0.5', forwarded_for=f'{ALLOWED_IP}, 203.0.113.10')

    assert ip_object is not None
    assert str(ip_object) == ALLOWED_IP


def test_resolve_webhook_client_ip_trusted_public_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'WEBHOOK_TRUSTED_PROXY_NETWORKS', '198.51.100.0/24', raising=False)

    ip_object = resolve_webhook_client_ip('198.51.100.20', forwarded_for=f'{ALLOWED_IP}, 198.51.100.10')

    assert ip_object is not None
    assert str(ip_object) == ALLOWED_IP


def test_resolve_webhook_client_ip_ignores_cf_connecting_ip_behind_local_proxy() -> None:
    """Cf-Connecting-Ip за локальным прокси приходит от клиента как есть и не читается."""
    ip_object = resolve_webhook_client_ip('172.18.0.5', forwarded_for='8.8.8.8', cf_connecting_ip=ALLOWED_IP)

    assert ip_object is not None
    assert str(ip_object) == '8.8.8.8'


def test_resolve_webhook_client_ip_trusts_cf_connecting_ip_only_from_cloudflare_peer() -> None:
    ip_object = resolve_webhook_client_ip('104.16.1.1', forwarded_for='8.8.8.8', cf_connecting_ip=ALLOWED_IP)

    assert ip_object is not None
    assert str(ip_object) == ALLOWED_IP


def test_resolve_webhook_client_ip_walks_cloudflare_then_local_proxy_chain() -> None:
    """Cloudflare → Caddy → бот: Caddy дописывает адрес узла Cloudflare, тот доверенный хоп."""
    ip_object = resolve_webhook_client_ip(
        '172.18.0.5', forwarded_for=f'{ALLOWED_IP}, 104.16.1.1', cf_connecting_ip='9.9.9.9'
    )

    assert ip_object is not None
    assert str(ip_object) == ALLOWED_IP


def test_resolve_webhook_client_ip_uses_x_real_ip_only_without_forwarded_for() -> None:
    assert str(resolve_webhook_client_ip('10.0.0.5', real_ip=ALLOWED_IP)) == ALLOWED_IP
    assert str(resolve_webhook_client_ip('10.0.0.5', forwarded_for='8.8.8.8', real_ip=ALLOWED_IP)) == '8.8.8.8'


def test_resolve_webhook_client_ip_returns_none_when_no_candidates() -> None:
    assert resolve_webhook_client_ip(None) is None
    assert resolve_webhook_client_ip('10.0.0.5') is None
    assert resolve_webhook_client_ip('10.0.0.5', forwarded_for='10.0.0.1, 192.168.1.1') is None
