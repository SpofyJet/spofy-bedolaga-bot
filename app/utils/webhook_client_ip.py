"""Определение адреса отправителя платёжного вебхука за прокси."""

from __future__ import annotations

from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_address,
    ip_network,
)
from typing import Union

import structlog

from app.config import settings


logger = structlog.get_logger(__name__)


IPAddress = Union[IPv4Address, IPv6Address]
IPNetwork = Union[IPv4Network, IPv6Network]

CLOUDFLARE_TRUSTED_NETWORKS: tuple[IPNetwork, ...] = (
    ip_network('173.245.48.0/20'),
    ip_network('103.21.244.0/22'),
    ip_network('103.22.200.0/22'),
    ip_network('103.31.4.0/22'),
    ip_network('141.101.64.0/18'),
    ip_network('108.162.192.0/18'),
    ip_network('190.93.240.0/20'),
    ip_network('188.114.96.0/20'),
    ip_network('197.234.240.0/22'),
    ip_network('198.41.128.0/17'),
    ip_network('162.158.0.0/15'),
    ip_network('104.16.0.0/13'),
    ip_network('104.24.0.0/14'),
    ip_network('172.64.0.0/13'),
    ip_network('131.0.72.0/22'),
    ip_network('2400:cb00::/32'),
    ip_network('2606:4700::/32'),
    ip_network('2803:f800::/32'),
    ip_network('2405:b500::/32'),
    ip_network('2405:8100::/32'),
    ip_network('2a06:98c0::/29'),
    ip_network('2c0f:f248::/32'),
)


def _split_ip_candidates(*values: str | None) -> list[str]:
    candidates: list[str] = []
    for value in values:
        if not value:
            continue
        for part in value.split(','):
            normalized = part.strip()
            if normalized:
                candidates.append(normalized)
    return candidates


def _parse_candidate_ip(candidate: str) -> IPAddress | None:
    value = candidate.strip()
    if not value:
        return None

    if value.startswith('[') and ']' in value:
        value = value[1 : value.index(']')]

    if '%' in value:
        value = value.split('%', 1)[0]

    if value.count(':') == 1 and '.' in value:
        host, _, port = value.rpartition(':')
        if port.isdigit():
            value = host

    try:
        return ip_address(value)
    except ValueError:
        return None


_TRUSTED_PROXY_NETWORKS_CACHE: tuple[str, tuple[IPNetwork, ...]] = ('', ())


def _get_trusted_proxy_networks() -> tuple[IPNetwork, ...]:
    global _TRUSTED_PROXY_NETWORKS_CACHE

    raw_value = settings.WEBHOOK_TRUSTED_PROXY_NETWORKS or ''
    cached_raw, cached_networks = _TRUSTED_PROXY_NETWORKS_CACHE

    if raw_value == cached_raw:
        return cached_networks

    networks: list[IPNetwork] = []
    for part in raw_value.split(','):
        candidate = part.strip()
        if not candidate:
            continue

        try:
            networks.append(ip_network(candidate, strict=False))
        except ValueError:
            logger.warning('Неверная сеть доверенного прокси вебхуков', candidate=candidate)

    cached_networks = tuple(networks)
    _TRUSTED_PROXY_NETWORKS_CACHE = (raw_value, cached_networks)
    return cached_networks


def _is_trusted_proxy_ip(ip_object: IPAddress) -> bool:
    if any(
        getattr(ip_object, attribute) for attribute in ('is_private', 'is_loopback', 'is_link_local', 'is_reserved')
    ):
        return True

    if any(ip_object in network for network in CLOUDFLARE_TRUSTED_NETWORKS):
        return True

    return any(ip_object in network for network in _get_trusted_proxy_networks())


def _is_cloudflare_ip(ip_object: IPAddress) -> bool:
    return any(ip_object in network for network in CLOUDFLARE_TRUSTED_NETWORKS)


def resolve_webhook_client_ip(
    remote: str | None,
    *,
    forwarded_for: str | None = None,
    real_ip: str | None = None,
    cf_connecting_ip: str | None = None,
) -> IPAddress | None:
    """Адрес отправителя вебхука без доверия к заголовкам, которые мог выставить сам клиент.

    Локальный прокси (Caddy, nginx) пропускает клиентские заголовки как есть и от себя
    дописывает только ``X-Forwarded-For``, поэтому читать можно лишь то, что выставил
    сам прокси. Правила:

    - peer публичный и не из доверенных прокси → отправитель он сам, заголовки не читаются;
    - peer из сетей Cloudflare → ``Cf-Connecting-Ip`` выставил Cloudflare, ему верим;
    - peer локальный/доверенный прокси → ``X-Forwarded-For`` справа налево, пропуская
      доверенные хопы; первый недоверенный — отправитель. ``Cf-Connecting-Ip`` здесь
      игнорируется. ``X-Real-IP`` — только когда ``X-Forwarded-For`` нет вовсе;
    - peer неизвестен или все хопы доверенные → ``None``, вебхук отклоняется.

    Прокси, который не дописывает свой peer в ``X-Forwarded-For``, отличить нельзя,
    поэтому IP-гейт — лишь первый барьер перед проверкой подписи провайдера.
    """
    remote_ip = _parse_candidate_ip(remote) if remote else None
    if remote_ip is None:
        return None

    if not _is_trusted_proxy_ip(remote_ip):
        return remote_ip

    if _is_cloudflare_ip(remote_ip) and cf_connecting_ip:
        cloudflare_client = _parse_candidate_ip(cf_connecting_ip)
        if cloudflare_client is not None:
            return cloudflare_client

    hops = [
        ip_object
        for ip_object in (_parse_candidate_ip(part) for part in _split_ip_candidates(forwarded_for))
        if ip_object is not None
    ]
    for hop in reversed(hops):
        if not _is_trusted_proxy_ip(hop):
            return hop

    if not hops and real_ip:
        real_client = _parse_candidate_ip(real_ip)
        if real_client is not None and not _is_trusted_proxy_ip(real_client):
            return real_client

    return None
