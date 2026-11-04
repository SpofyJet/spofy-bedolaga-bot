"""Stars payment for a gift that can't be applied must not be reported as «успешно оплачена»."""

from types import SimpleNamespace

from app.database.models import GuestPurchaseStatus
from app.handlers.stars_payments import _gift_purchase_problem


def _purchase(status: str, payment_id: str | None = None):
    return SimpleNamespace(id=5, status=status, payment_id=payment_id)


def test_missing_purchase_is_a_problem() -> None:
    assert 'не найдена' in _gift_purchase_problem(None, 'ch1')


def test_pending_purchase_is_applied() -> None:
    assert _gift_purchase_problem(_purchase(GuestPurchaseStatus.PENDING.value), 'ch1') is None
    assert _gift_purchase_problem(_purchase(GuestPurchaseStatus.EXPIRED.value), 'ch1') is None


def test_purchase_paid_by_another_payment_is_a_problem() -> None:
    for status in ('paid', 'delivered', 'pending_activation', 'failed'):
        assert _gift_purchase_problem(_purchase(status, payment_id='other'), 'ch1'), status
    assert _gift_purchase_problem(_purchase('failed', payment_id=None), 'ch1')


def test_redelivery_of_the_same_charge_is_fine() -> None:
    assert _gift_purchase_problem(_purchase('paid', payment_id='ch1'), 'ch1') is None
