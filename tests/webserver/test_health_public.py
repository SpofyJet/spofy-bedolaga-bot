"""The web_api /health liveness probe must be reachable WITHOUT an API token.

It previously required Security(require_api_token), so Docker/LB/monitoring/
cabinet healthchecks got 401. Liveness must be public; the detailed
database/pool endpoints stay token-gated.
"""

from __future__ import annotations


def test_health_is_public() -> None:
    assert _uses_token('/health') is False, '/health must require no API token'


def test_detailed_health_stays_gated() -> None:
    assert _uses_token('/health/database') is True
    assert _uses_token('/metrics/pool') is True
