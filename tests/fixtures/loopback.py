"""Проверка петли 127.0.0.1 для тестов с локальным HTTP-сервером.

Такие тесты не выходят в сеть, но им нужен интерфейс lo. В `unshare -n` без
`ip link set lo up` его нет, и запрос к своему же серверу падает с «Network is
unreachable» — это не сбой кода, поэтому тест пропускается с понятной причиной.
"""

import socket

import pytest


def loopback_reachable() -> bool:
    try:
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0))
            server.listen(1)
            with socket.create_connection(server.getsockname(), timeout=1):
                return True
    except OSError:
        return False


requires_loopback = pytest.mark.skipif(
    not loopback_reachable(),
    reason='нет петли 127.0.0.1 (сеть отключена вместе с lo) — тест поднимает локальный HTTP-сервер',
)
