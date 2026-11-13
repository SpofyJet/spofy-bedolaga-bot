"""After paying an invoice created on the subscription page, the provider must send the
customer back to the page — not to the cabinet's ``/balance/top-up/result``, where a person
who never logged in lands on the login screen (11 of 33 payers, 07–13.11).

* the page passes a neutral ``return_url`` (no subscription token) with the checkout;
* only THIS invoice gets it — cabinet and bot top-ups keep the cabinet URL;
* a URL that contains the short UUID, is not plain https or carries a query is ignored.

The real ``create_topup`` runs here; only the provider call is mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.cabinet.routes import balance, spofy_subpage as bridge
from app.cabinet.schemas.balance import PaymentMethodResponse, TopUpRequest
from app.config import Settings, settings
from app.services import spofy_subpage_context as context, spofy_subpage_service as completion


pytestmark = pytest.mark.anyio

SHORT_UUID = 'Qf_Wtzcw6JXrffn0'
PAGE_RETURN = 'https://sub.example/spofy-api/payment/return'
CABINET = 'https://web.example'
CABINET_RETURN = f'{CABINET}/balance/top-up/result'


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
def provider(monkeypatch):
    """Everything around the provider call, which is the mock returned here."""
    user = SimpleNamespace(
        id=5,
        telegram_id=None,
        language='ru',
        status='active',
        balance_kopeks=0,
        restriction_subscription=False,
        restriction_topup=False,
    )
    subscription = SimpleNamespace(
        id=42,
        status='active',
        actual_status='active',
        is_trial=False,
        tariff_id=7,
        tariff=SimpleNamespace(name='Base'),
        end_date=None,
        device_limit=3,
        traffic_limit_gb=0,
    )
    method = PaymentMethodResponse(
        id='platega', name='Card', min_amount_kopeks=10000, max_amount_kopeks=10**8, is_available=True
    )
    service = SimpleNamespace(
        create_platega_payment=AsyncMock(return_value={'redirect_url': 'https://pay.example/x', 'transaction_id': '17'})
    )
    monkeypatch.setattr(settings, 'CABINET_URL', CABINET, raising=False)
    monkeypatch.setattr(Settings, 'is_platega_enabled', lambda self: True)
    monkeypatch.setattr(Settings, 'get_platega_active_methods', lambda self: [2])
    monkeypatch.setattr(Settings, 'get_balance_payment_description', lambda self, *a, **kw: 'top-up')
    monkeypatch.setattr(balance, 'get_payment_methods', AsyncMock(return_value=[method]))
    monkeypatch.setattr(balance, 'PaymentService', lambda: service)
    monkeypatch.setattr(bridge, 'get_payment_methods', AsyncMock(return_value=[method]))
    monkeypatch.setattr(bridge, 'resolve_owner', AsyncMock(return_value=(user, subscription)))
    monkeypatch.setattr(bridge, 'save_renewal_cart', AsyncMock(return_value=19900))
    monkeypatch.setattr(bridge, 'bind_cart_to_payment', AsyncMock(return_value=True))
    monkeypatch.setattr(bridge, 'next_traffic_reset_at', lambda *a, **kw: None)
    monkeypatch.setattr(bridge, 'checkout_serializer', completion.CheckoutSerializer())
    return SimpleNamespace(user=user, create=service.create_platega_payment, db=SimpleNamespace(commit=AsyncMock()))


def _urls(create: AsyncMock) -> tuple[str, str]:
    kwargs = create.await_args.kwargs
    return kwargs['return_url'], kwargs['failed_url']


async def _page_checkout(provider, return_url: str | None) -> None:
    body = bridge.CheckoutRequest(kind='renew', period_days=30, payment_method='platega', return_url=return_url)
    result = await bridge.checkout(SHORT_UUID, body, db=provider.db)
    assert result['payment_url'] == 'https://pay.example/x'


async def test_page_invoice_returns_to_the_page_not_to_the_cabinet(provider):
    await _page_checkout(provider, PAGE_RETURN)

    assert _urls(provider.create) == (
        f'{PAGE_RETURN}?method=platega&status=success',
        f'{PAGE_RETURN}?method=platega&status=failed',
    )
    # nothing of the bridge's invoice leaks into the next request
    assert context.subpage_return_url() is None


async def test_cabinet_topup_keeps_the_cabinet_return_url(provider):
    await balance.create_topup(
        request=TopUpRequest(amount_kopeks=19900, payment_method='platega'), user=provider.user, db=provider.db
    )

    assert _urls(provider.create) == (
        f'{CABINET_RETURN}?method=platega&status=success',
        f'{CABINET_RETURN}?method=platega&status=failed',
    )


async def test_cabinet_topup_right_after_a_page_invoice_is_unaffected(provider):
    await _page_checkout(provider, PAGE_RETURN)
    await balance.create_topup(
        request=TopUpRequest(amount_kopeks=19900, payment_method='platega'), user=provider.user, db=provider.db
    )

    assert _urls(provider.create)[0] == f'{CABINET_RETURN}?method=platega&status=success'


async def test_page_without_a_return_url_behaves_as_before(provider):
    await _page_checkout(provider, None)

    assert _urls(provider.create)[0] == f'{CABINET_RETURN}?method=platega&status=success'


@pytest.mark.parametrize(
    'unsafe',
    [
        f'https://sub.example/{SHORT_UUID}',  # the subscription link itself — a credential
        f'https://sub.example/{SHORT_UUID.lower()}/paid',
        f'https://sub.example/spofy-api/payment/return?next=/{SHORT_UUID}',
        'https://sub.example/spofy-api/payment/return?x=1',
        'https://sub.example/spofy-api/payment/return#x',
        'http://sub.example/spofy-api/payment/return',
        'https://user:pw@sub.example/spofy-api/payment/return',
        'https://sub.example/spofy-api/payment/%51f_return',
        'javascript:alert(1)',
        '//sub.example/spofy-api/payment/return',
    ],
)
async def test_unsafe_return_url_is_never_handed_to_the_provider(provider, unsafe):
    assert bridge.safe_return_url(unsafe, SHORT_UUID) is None

    await _page_checkout(provider, unsafe)

    assert _urls(provider.create)[0] == f'{CABINET_RETURN}?method=platega&status=success'


def test_plain_https_return_url_is_accepted():
    assert bridge.safe_return_url(PAGE_RETURN, SHORT_UUID) == PAGE_RETURN
    assert bridge.safe_return_url('https://sub.example/sub/spofy-api/payment/return', SHORT_UUID) is not None
    assert bridge.safe_return_url(None, SHORT_UUID) is None
    assert bridge.safe_return_url('', SHORT_UUID) is None
