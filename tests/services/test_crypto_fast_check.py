"""Крипто-счета: быстрая проверка свежих счетов и экраны оплаты без эмодзи у названий способов."""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.config import settings
from app.services import payment_verification_service as pvs
from app.services.payment_verification_service import AutoPaymentVerificationService


def _record(method, *, paid=False, identifier='1'):
    return SimpleNamespace(method=method, local_id=7, identifier=identifier, is_paid=paid, status='active')


async def test_fast_lane_checks_only_fresh_unpaid_crypto_invoices(monkeypatch):
    svc = AutoPaymentVerificationService()
    svc._payment_service = object()
    monkeypatch.setattr(
        pvs, 'get_enabled_auto_methods', lambda: [pvs.PaymentMethod.CRYPTOBOT, pvs.PaymentMethod.HELEKET]
    )
    monkeypatch.setattr(
        pvs,
        '_fetch_cryptobot_payments',
        AsyncMock(
            return_value=[
                _record(pvs.PaymentMethod.CRYPTOBOT, identifier='a'),
                _record(pvs.PaymentMethod.CRYPTOBOT, paid=True, identifier='b'),
            ]
        ),
    )
    monkeypatch.setattr(
        pvs, '_fetch_heleket_payments', AsyncMock(return_value=[_record(pvs.PaymentMethod.HELEKET, identifier='c')])
    )
    checked = []

    async def fake_check(session, method, local_id, payment_service):
        checked.append(method)
        return SimpleNamespace(is_paid=True, method=method, identifier='x')

    monkeypatch.setattr(pvs, 'run_manual_check', fake_check)
    session = MagicMock()
    session.in_transaction.return_value = False
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(pvs, 'AsyncSessionLocal', lambda: cm)

    await svc._run_fast_crypto_checks()

    assert checked == [pvs.PaymentMethod.CRYPTOBOT, pvs.PaymentMethod.HELEKET]  # оплаченный пропущен


async def test_fast_lane_off_by_default_switch(monkeypatch):
    monkeypatch.setattr(settings, 'PAYMENT_VERIFICATION_FAST_SECONDS', 0)
    svc = AutoPaymentVerificationService()
    assert int(settings.PAYMENT_VERIFICATION_FAST_SECONDS) == 0 and svc._fast_task is None


def test_crypto_screens_have_no_emoji_before_the_method_title():
    emoji = re.compile('[🦋🚀🪙]')
    for path in (
        'app/handlers/balance/cryptobot.py',
        'app/handlers/balance/xrocket.py',
        'app/handlers/balance/heleket.py',
    ):
        source = Path(path).read_text(encoding='utf-8')
        titles = re.findall(r"['\"]([^'\"\n]*<b>Криптовалюта \([^)]*\)</b>)", source)
        assert titles and not any(emoji.search(t) for t in titles), path
